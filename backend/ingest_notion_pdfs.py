#!/usr/bin/env python3
"""Ingest Notion PDF/Markdown exports into Supabase for RAG.

Usage:
    python ingest_notion_pdfs.py              # Full ingestion
    python ingest_notion_pdfs.py --dry-run    # Preview without saving
    python ingest_notion_pdfs.py --help       # Show options

Environment Variables (required):
    OPENROUTER_API_KEY
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY

Optional:
    NOTION_EXPORT_DIR     # Default: ./notion_exports
    ENABLE_OCR            # Default: true
    EMBEDDING_MODEL       # Default: openai/text-embedding-3-small

The script walks through Notion exports, extracts text from PDFs/Markdown,
cleans and chunks the text (500 tokens, 10% overlap), generates embeddings
using OpenRouter, and inserts chunks into Supabase. Duplicate chunks are skipped.

The database schema is expected to include:
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
    content TEXT NOT NULL
    embedding VECTOR(1536)
    document_title TEXT
    source_url TEXT
    manual_type TEXT       # teacher or student
    chunk_index INTEGER    # 0-based position within the document
    page_number INTEGER    # PDF page the chunk originated from
    chunk_total INTEGER    # total chunks in the document
    created_at TIMESTAMP DEFAULT NOW()

The code is written for Python 3.10+ with robust error handling.
"""

import os
import sys
import re
import logging
import hashlib
import time
import argparse
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip install PyMuPDF")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

try:
    import pytesseract
except ImportError:
    print("ERROR: pytesseract not installed. Run: pip install pytesseract")
    sys.exit(1)

try:
    from pdf2image import convert_from_path
except ImportError:
    print("ERROR: pdf2image not installed. Run: pip install pdf2image")
    sys.exit(1)

try:
    import tiktoken
except ImportError:
    print("ERROR: tiktoken not installed. Run: pip install tiktoken")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

try:
    from supabase import create_client, Client
except ImportError:
    print("ERROR: supabase not installed. Run: pip install supabase")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv not installed. Run: pip install python-dotenv")
    sys.exit(1)

# --- configuration constants ------------------------------------------------
PDF_ROOT = os.getenv("NOTION_EXPORT_DIR", "./notion_exports")
CHUNK_SIZE = 500  # Optimized for RAG context window
CHUNK_OVERLAP = 50  # 10% of chunk size
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
EMBEDDING_DIM = 1536
BATCH_SIZE = 50  # Conservative batch size for rate limiting
ENABLE_OCR = os.getenv("ENABLE_OCR", "true").lower() == "true"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/embeddings"

# --- logging setup ----------------------------------------------------------
def setup_logging(verbose: bool = False):
    """Configure logging with appropriate verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)

logger = setup_logging()


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
    if len(all_pages) < 3:
        return set()
        
    freq: Dict[str, int] = {}
    for page in all_pages:
        for line in set(page.splitlines()):
            stripped = line.strip()
            if stripped:
                freq[stripped] = freq.get(stripped, 0) + 1
                
    # Threshold: must appear in at least 2 pages AND more than half the pages
    threshold = max(2, len(all_pages) // 2 + 1)
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
    try:
        encoder = tiktoken.encoding_for_model(EMBEDDING_MODEL.replace("openai/", ""))
    except KeyError:
        encoder = tiktoken.get_encoding("cl100k_base")
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
    api_key: str, inputs: List[str]
) -> List[List[float]]:
    """Return list of embeddings corresponding to inputs using OpenRouter. Handles batching.

    Implements simple retry logic for rate limits and transient errors.
    """
    results: List[List[float]] = []
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    for i in range(0, len(inputs), BATCH_SIZE):
        batch = inputs[i : i + BATCH_SIZE]
        retries = 0
        while retries < 3:
            try:
                payload = {
                    "model": EMBEDDING_MODEL,
                    "input": batch
                }
                resp = requests.post(OPENROUTER_API_URL, json=payload, headers=headers, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                
                if "data" in data:
                    for item in data["data"]:
                        results.append(item["embedding"])
                else:
                    logger.error(f"unexpected response from OpenRouter: {data}")
                    time.sleep(5)
                    retries += 1
                    continue
                break
            except requests.exceptions.HTTPError as err:
                if err.response.status_code == 429:  # rate limit
                    logger.warning(f"rate limit hit, sleeping 5s: {err}")
                    time.sleep(5)
                    retries += 1
                else:
                    logger.error(f"failed to fetch embeddings: {err}")
                    retries = 3
            except Exception as err:
                logger.error(f"unexpected error fetching embeddings: {err}")
                time.sleep(5)
                retries += 1
        
        if retries >= 3:
            logger.error(f"failed to get embeddings after 3 retries for batch {i}")
    
    return results


def insert_into_supabase(
    supabase: Client, rows: List[Dict[str, Any]]
) -> None:
    """Batch-insert rows into the Supabase `documents` table.

    Each row is a dict matching the table columns.
    """
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        try:
            resp = supabase.table("documents").insert(batch).execute()
            logger.debug("inserted %d records", len(batch))
        except Exception as e:
            logger.error("supabase insert error: %s", str(e))
            raise e


# ── Utility Functions ───────────────────────────────────────────────────────


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

def validate_environment() -> Tuple[str, str, str]:
    """Validate and return API credentials. Exits if missing."""
    load_dotenv()
    
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not openrouter_key:
        logger.error("OPENROUTER_API_KEY not set in environment")
        sys.exit(1)
    
    supa_url = os.getenv("SUPABASE_URL", "").strip()
    if not supa_url:
        logger.error("SUPABASE_URL not set in environment")
        sys.exit(1)
    
    supa_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supa_key:
        logger.error("SUPABASE_SERVICE_ROLE_KEY not set in environment")
        sys.exit(1)
    
    logger.info("✓ All environment variables present")
    return openrouter_key, supa_url, supa_key


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Notion PDFs into Supabase for RAG system"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview chunks without inserting into database"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--pdf-root",
        default=PDF_ROOT,
        help=f"Path to Notion export directory (default: {PDF_ROOT})"
    )
    parser.add_argument(
        "--output-file",
        default="output.txt",
        help="Output file for preview (default: output.txt)"
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Maximum number of PDF files to process"
    )
    parser.add_argument(
        "--failed-log",
        default="failed_files.txt",
        help="Log file for files that failed ingestion (default: failed_files.txt)"
    )
    args = parser.parse_args()
    
    # Reconfigure logging if verbose
    global logger
    if args.verbose:
        logger = setup_logging(verbose=True)
    
    logger.info("=" * 80)
    logger.info("Notion PDF Ingestion Pipeline - RAG System")
    logger.info("=" * 80)
    
    # Validate environment
    openrouter_key, supa_url, supa_key = validate_environment()
    
    # Check if export directory exists
    if not os.path.isdir(args.pdf_root):
        logger.error(f"NOTION_EXPORT_DIR not found: {args.pdf_root}")
        logger.info(f"Please ensure your Notion exports are in: {args.pdf_root}")
        sys.exit(1)
    
    logger.info(f"Reading from: {args.pdf_root}")
    logger.info(f"Using embedding model: {EMBEDDING_MODEL}")
    logger.info(f"Dry-run mode: {args.dry_run}")
    
    # Initialize Supabase client
    if not args.dry_run:
        try:
            supabase = create_client(supa_url, supa_key)
            logger.info("✓ Supabase client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            sys.exit(1)
    else:
        supabase = None
    
    # Clear output and failed files log at start
    with open(args.output_file, "w", encoding="utf-8") as f:
        f.write("CHUNK OUTPUT LOG\n")
        f.write(f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Dry-run mode: {args.dry_run}\n")
        f.write("=" * 80 + "\n\n")

    with open(args.failed_log, "w", encoding="utf-8") as f:
        f.write("# FAILED INGESTION LOG\n")
        f.write(f"# Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    # Statistics
    total_files = 0
    total_chunks = 0
    total_ocr_pages = 0
    errors: List[str] = []
    
    # Walk through PDFs
    stop_processing = False
    for root, dirs, files in os.walk(args.pdf_root):
        if stop_processing:
            break
        for fname in files:
            if not fname.lower().endswith(".pdf"):
                continue
            
            if args.max_files is not None and total_files >= args.max_files:
                stop_processing = True
                break
                
            total_files += 1
            path = os.path.join(root, fname)
            
            # 1. Start by checking path and filename for keywords (English and Chinese)
            manual_type = ""
            path_lower = (root + os.sep + fname).lower()
            teacher_keywords = ["teacher", "教師", "老師", "教員"]
            student_keywords = ["student", "學生", "學員"]
            
            if any(k in path_lower for k in teacher_keywords):
                manual_type = "teacher"
            elif any(k in path_lower for k in student_keywords):
                manual_type = "student"
            
            logger.info(f"[{total_files}] Processing: {fname}")
            
            try:
                # Extract text from PDF
                pages, ocr_count = extract_text_from_pdf(path)
                total_ocr_pages += ocr_count

                if not pages:
                    logger.warning(f"  ⚠ No text extracted from {fname}")
                    with open(args.failed_log, "a", encoding="utf-8") as f:
                        f.write(f"{path}\n")
                    errors.append(f"{fname}: No text extracted")
                    continue

                # 2. If still unknown, check first two pages of content for common markers
                if not manual_type:
                    content_sample = "\n".join(pages[:2]).lower()
                    if any(k in content_sample for k in teacher_keywords):
                        manual_type = "teacher"
                    elif any(k in content_sample for k in student_keywords):
                        manual_type = "student"
                
                logger.debug(f"  Manual type identified: {manual_type or 'unknown'}")
                logger.debug(f"  Extracted {len(pages)} pages, OCR used on {ocr_count} pages")

                # Identify common headers/footers
                headers = identify_common_headers(pages)

                # Extract Notion source URL
                url_pattern = re.compile(r"https://[^\s]+\.notion\.[^\s]+")
                source_url = ""
                for page_text in pages:
                    match = url_pattern.search(page_text)
                    if match:
                        source_url = match.group(0)
                        break

                # ── Collect ALL chunks across all pages first ─────────────────
                # We need the total so we can assign chunk_total to every row.
                all_chunks: List[Tuple[str, Optional[str], int]] = []  # (text, section, page_num)

                for page_num, raw_page in enumerate(pages, start=1):
                    cleaned = clean_text(raw_page, headers)
                    if not cleaned:
                        continue
                    for chunk_str, section in chunk_text(cleaned):
                        all_chunks.append((chunk_str, section, page_num))

                if not all_chunks:
                    logger.warning(f"  ⚠ No chunks produced from {fname}")
                    with open(args.failed_log, "a", encoding="utf-8") as f:
                        f.write(f"{path}\n")
                    errors.append(f"{fname}: No chunks produced")
                    continue

                chunk_total = len(all_chunks)
                logger.debug(f"  Total chunks across all pages: {chunk_total}")

                # ── Generate embeddings in one batched call ───────────────────
                contents = [c for c, _, _ in all_chunks]
                try:
                    embeddings = generate_embeddings(openrouter_key, contents)
                except Exception as emb_err:
                    logger.error(f"  Failed to generate embeddings: {emb_err}")
                    errors.append(f"{fname}: Embedding failed")
                    continue

                # ── Build rows with chunk_index / page_number / chunk_total ───
                rows_to_insert: List[Dict[str, Any]] = []

                for chunk_index, ((chunked_str, _section, pg_num), emb) in enumerate(
                    zip(all_chunks, embeddings)
                ):
                    row = {
                        "content": chunked_str,
                        "embedding": emb,
                        "document_title": fname,
                        "source_url": source_url,
                        "manual_type": manual_type,
                        "chunk_index": chunk_index,
                        "page_number": pg_num,
                        "chunk_total": chunk_total,
                    }
                    rows_to_insert.append(row)
                
                if rows_to_insert:
                    logger.info(f"  ✓ Generated {len(rows_to_insert)} unique chunks")
                    output_chunks_to_file(rows_to_insert, args.output_file)
                    
                    if not args.dry_run and supabase:
                        try:
                            insert_into_supabase(supabase, rows_to_insert)
                            logger.info(f"  ✓ Inserted {len(rows_to_insert)} chunks into Supabase")
                        except Exception as db_err:
                            logger.error(f"  ✗ Failed to insert into Supabase: {db_err}")
                            errors.append(f"{fname}: DB insert failed - {db_err}")
                            continue
                    
                    total_chunks += len(rows_to_insert)
            
            except Exception as e:
                logger.error(f"  ✗ Failed to process {fname}: {e}")
                with open(args.failed_log, "a", encoding="utf-8") as f:
                    f.write(f"{path}\n")
                errors.append(f"{fname}: {str(e)}")
                continue
    
    # Summary
    logger.info("=" * 80)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 80)
    print(f"\n📊 Summary:")
    print(f"  Files processed:    {total_files}")
    print(f"  Chunks created:     {total_chunks}")
    print(f"  OCR pages used:     {total_ocr_pages}")
    print(f"  Dry-run mode:       {args.dry_run}")
    
    if errors:
        print(f"\n⚠️  Errors/Failures encountered ({len(errors)}):")
        for error in errors[:10]: # show first 10
            print(f"   - {error}")
        if len(errors) > 10:
            print(f"   ... and {len(errors)-10} more")
        print(f"\n📝 See failed file paths here: {args.failed_log}")
    
    if args.dry_run:
        print(f"\n✓ Preview saved to: {args.output_file}")
        print("  Run without --dry-run to insert into database")
    else:
        print(f"\n✓ Process complete. Data ingested into Supabase.")


if __name__ == "__main__":
    main()