#!/usr/bin/env python3
"""Ingest Notion PDF exports into Supabase for RAG.

Usage:
    python ingest_notion_pdfs.py

Environment Variables (required):
    OPENAI_API_KEY
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY

The script walks `./notion_exports/` recursively, extracts text from PDFs,
optionally OCRs pages with little text, cleans and chunks the text, generates
embeddings using OpenAI, and inserts the chunks into a Supabase table named
"documents". Duplicate chunks are skipped by hashing.

The database schema is expected to include at least:
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
    content TEXT NOT NULL
    embedding VECTOR(1536)
    document_title TEXT
    source_url TEXT        # extracted from footer, starts with https://cultured-thumb-ad7.notion.site/
    manual_type TEXT       # teacher or student
    created_at TIMESTAMP DEFAULT NOW()

The code is written for Python 3.10+ and has robust error handling and logging.
"""

import os
import sys
import re
import logging
import hashlib
import time
from functools import lru_cache
from typing import List, Tuple, Optional, Dict, Any

import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from pdf2image import convert_from_path
import tiktoken

# OpenAI 1.x client
from openai import OpenAI
from openai import APIError, RateLimitError

from supabase import create_client, Client

# --- configuration constants ------------------------------------------------
PDF_ROOT = "./notion_exports"
CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
EMBEDDING_MODEL = "text-embedding-3-small"  # 1536 dims
EMBEDDING_DIM = 1536
BATCH_SIZE = 100  # for embeddings and db inserts

# --- logging setup ----------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# --- helper functions -------------------------------------------------------

def extract_text_from_pdf(path: str) -> Tuple[List[str], int]:
    """Return a list of strings, one per page. Also count how many pages used OCR.

    Uses PyMuPDF to extract text. If the extracted text is very short (<= 20
    characters after stripping) we fallback to OCR.
    """
    texts: List[str] = []
    ocr_pages = 0
    try:
        doc = fitz.open(path)
    except Exception as exc:  # corrupted pdf etc.
        logger.error("failed to open %s: %s", path, exc)
        return [], 0

    for i, page in enumerate(doc, start=1):
        text = page.get_text("text")
        # only OCR when there is no selectable text at all; short pages may still
        # contain legitimate content and shouldn't be OCR'd.
        if not text.strip():
            logger.debug("page %d empty, running OCR", i)
            try:
                text = ocr_page(page)
                ocr_pages += 1
            except Exception as ocr_exc:
                logger.error("OCR failed for %s page %d: %s", path, i, ocr_exc)
                text = ""
        texts.append(text)
    doc.close()
    return texts, ocr_pages


def ocr_page(page: fitz.Page) -> str:
    """Render a PDF page to an image and run OCR via pytesseract."""
    # render to pixmap at 300 dpi for better OCR quality
    pix = page.get_pixmap(dpi=300)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    text = pytesseract.image_to_string(img)
    return text


def clean_text(raw: str, header_lines: Optional[set] = None) -> str:
    """Clean a chunk of text.

    - remove repeated header/footer lines (if header_lines provided)
    - strip page numbers or lines containing only digits
    - normalize whitespace
    """
    lines = raw.splitlines()
    out_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if header_lines and stripped in header_lines:
            continue
        if re.fullmatch(r"\d+", stripped):
            continue
        if re.match(r"^Page\s+\d+", stripped, flags=re.I):
            continue
        out_lines.append(stripped)
    text = "\n".join(out_lines)
    # normalize whitespace inside lines
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def identify_common_headers(all_pages: List[str]) -> set:
    """Return a set of lines that appear on many pages (e.g. headers/footers)."""
    freq: Dict[str, int] = {}
    for page in all_pages:
        for line in set(page.splitlines()):
            stripped = line.strip()
            if stripped:
                freq[stripped] = freq.get(stripped, 0) + 1
    threshold = max(1, len(all_pages) // 2)
    return {line for line, count in freq.items() if count >= threshold}


def detect_section_heading(text: str) -> Optional[str]:
    """Naively detect a section heading within `text`.

    We look for lines that resemble markdown headings or are all uppercase.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("# ")
        if stripped.isupper() and len(stripped.split()) < 10:
            return stripped
    return None


def chunk_text(text: str) -> List[Tuple[str, Optional[str]]]:
    """Break text into chunks with overlap; return list of (chunk, section).

    We try to avoid splitting in middle of sentences.
    """
    encoder = tiktoken.encoding_for_model(EMBEDDING_MODEL)
    sentences = re.split(r"(?<=[.?!])\s+", text)
    chunks: List[Tuple[str, Optional[str]]] = []
    cur_tokens = 0
    cur_chunk: List[str] = []
    cur_section: Optional[str] = None

    def flush_chunk():
        nonlocal cur_chunk, cur_section, cur_tokens
        if cur_chunk:
            chunked_text = " ".join(cur_chunk).strip()
            if chunked_text:
                chunks.append((chunked_text, cur_section))
        cur_chunk = []
        cur_tokens = 0

    for sentence in sentences:
        if not sentence:
            continue
        sentence_tokens = len(encoder.encode(sentence))
        if cur_tokens + sentence_tokens > CHUNK_SIZE:
            flush_chunk()
            # handle overlap: take last CHUNK_OVERLAP tokens from previous chunk
            if chunks:
                prev = chunks[-1][0]
                prev_tokens = encoder.encode(prev)
                if len(prev_tokens) > CHUNK_OVERLAP:
                    overlap_text = encoder.decode(prev_tokens[-CHUNK_OVERLAP:])
                    cur_chunk = [overlap_text]
                    cur_tokens = len(prev_tokens[-CHUNK_OVERLAP:])
        cur_chunk.append(sentence)
        cur_tokens += sentence_tokens
        # update section if we see a heading
        heading = detect_section_heading(sentence)
        if heading:
            cur_section = heading
    flush_chunk()
    return chunks


def generate_embeddings(
    client: OpenAI, inputs: List[str]
) -> List[List[float]]:
    """Return list of embeddings corresponding to inputs. Handles batching.

    Implements simple retry logic for rate limits and transient errors.
    """
    results: List[List[float]] = []
    for i in range(0, len(inputs), BATCH_SIZE):
        batch = inputs[i : i + BATCH_SIZE]
        while True:
            try:
                resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
                # resp.data is a list of objects with an `embedding` attribute or key
                for item in resp.data:
                    # support either dict or object
                    emb = item.embedding if hasattr(item, "embedding") else item["embedding"]
                    results.append(emb)
                break
            except RateLimitError as err:
                logger.warning("rate limit hit, sleeping 5s: %s", err)
                time.sleep(5)
            except APIError as err:  # generic OpenAI API error
                logger.error("failed to fetch embeddings: %s", err)
                time.sleep(5)
            except Exception as err:  # fallback
                logger.error("unexpected error fetching embeddings: %s", err)
                time.sleep(5)
    return results


def insert_into_supabase(
    supabase: Client, rows: List[Dict[str, Any]]
) -> None:
    """Batch-insert rows into the Supabase `documents` table.

    Each row is a dict matching the table columns.
    """
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        resp = supabase.table("documents").insert(batch).execute()
        if resp.get("error"):
            logger.error("supabase insert error: %s", resp["error"])
        else:
            logger.debug("inserted %d records", len(batch))


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def output_chunks_to_file(rows: List[Dict[str, Any]], output_file: str = "output.txt") -> None:
    """Write chunks to a text file before inserting into database."""
    with open(output_file, "a", encoding="utf-8") as f:
        for i, row in enumerate(rows, 1):
            f.write(f"\n{'='*80}\n")
            f.write(f"Chunk #{i}\n")
            f.write(f"Document: {row.get('document_title', 'N/A')}\n")
            f.write(f"Type: {row.get('manual_type', 'N/A')}\n")
            f.write(f"Source URL: {row.get('source_url', 'N/A')}\n")
            f.write(f"{'='*80}\n")
            f.write(f"{row.get('content', '')}\n")
    logger.info("wrote %d chunks to %s", len(rows), output_file)


# --- main orchestration -----------------------------------------------------

def main():
    from dotenv import load_dotenv
    load_dotenv()
    
    # Clear output.txt at start
    with open("output.txt", "w", encoding="utf-8") as f:
        f.write("CHUNK OUTPUT LOG\n")
        f.write(f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # environment checks
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        logger.error("OPENAI_API_KEY not set")
        sys.exit(1)
    # initialize a single OpenAI client
    client = OpenAI(api_key=key)

    supa_url = os.getenv("SUPABASE_URL")
    supa_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supa_url or not supa_key:
        logger.error("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set")
        sys.exit(1)
    supabase = create_client(supa_url, supa_key)

    total_files = 0
    total_chunks = 0
    total_ocr_pages = 0
    seen_hashes: set = set()

    for root, dirs, files in os.walk(PDF_ROOT):
        for fname in files:
            if not fname.lower().endswith(".pdf"):
                continue
            total_files += 1
            path = os.path.join(root, fname)
            manual_type = "teacher" if "teacher" in root.lower() else "student" if "student" in root.lower() else ""
            logger.info("processing file %s (type=%s)", path, manual_type)
            pages, ocr_count = extract_text_from_pdf(path)
            total_ocr_pages += ocr_count
            if not pages:
                continue
            headers = identify_common_headers(pages)
            # try to pull Notion source URL from any page text
            url_pattern = re.compile(r"https://cultured-thumb-ad7\.notion\.site/\S+")
            source_url = ""
            for page_text in pages:
                match = url_pattern.search(page_text)
                if match:
                    source_url = match.group(0)
                    break
            rows_to_insert: List[Dict[str, Any]] = []
            for page_num, raw_page in enumerate(pages, start=1):
                cleaned = clean_text(raw_page, headers)
                if not cleaned:
                    continue
                chunks = chunk_text(cleaned)
                logger.info("%s page %d produced %d chunks", fname, page_num, len(chunks))
                contents = [c for c, _ in chunks]
                embeddings = generate_embeddings(client, contents)
                for (chunked_text, _section), emb in zip(chunks, embeddings):
                    h = hash_text(chunked_text)
                    if h in seen_hashes:
                        continue
                    seen_hashes.add(h)
                    row = {
                        "content": chunked_text,
                        "embedding": emb,
                        "document_title": fname,
                        "source_url": source_url,
                        "manual_type": manual_type,
                    }
                    rows_to_insert.append(row)
            if rows_to_insert:
                output_chunks_to_file(rows_to_insert)
                insert_into_supabase(supabase, rows_to_insert)
                total_chunks += len(rows_to_insert)
                logger.info("inserted %d chunks from %s", len(rows_to_insert), fname)

    logger.info("done: %d files, %d chunks, %d ocr pages", total_files, total_chunks, total_ocr_pages)
    print(f"Total files processed: {total_files}")
    print(f"Total chunks inserted: {total_chunks}")
    print(f"Total OCR pages used: {total_ocr_pages}")


if __name__ == "__main__":
    main()
