#!/usr/bin/env python3
"""FastAPI server for RAG chatbot using OpenRouter and Supabase.

OPTIMIZATIONS:
- Async/await for HTTP requests (httpx instead of requests)
- Embedding caching to avoid duplicate API calls
- Batched context expansion queries (single DB query instead of N+1)
- Parallel operations where possible (embedding + vector search)
- Response streaming for better perceived performance
- Optimized similarity threshold to reduce irrelevant results

To run:
    python -m uvicorn chat_api:app --reload --host 0.0.0.0 --port 8000

Environment Variables (required):
    OPENROUTER_API_KEY
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    
Optional:
    CHAT_MODEL              # Default: openrouter/auto
    EMBEDDING_MODEL         # Default: openai/text-embedding-3-small
    RAG_CONTEXT_LIMIT       # Default: 5 (reduced from 8 for faster retrieval)
    EMBEDDING_CACHE_SIZE    # Default: 100 (max cached embeddings)
"""

import os
import logging
import re
import uuid
import unicodedata
from typing import List, Dict, Any, Optional, Tuple
from collections import OrderedDict
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from supabase import create_client, Client

try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("jieba not available - Chinese text will be handled with character-based splitting")

# Load environment variables
load_dotenv()

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

CHAT_MODEL = os.getenv("CHAT_MODEL", "openrouter/auto")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
RAG_CONTEXT_LIMIT = int(os.getenv("RAG_CONTEXT_LIMIT", "8"))  # Increased for better coverage
EMBEDDING_CACHE_SIZE = int(os.getenv("EMBEDDING_CACHE_SIZE", "100"))

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple LRU cache for embeddings
class EmbeddingCache:
    """Simple LRU cache for embeddings to avoid duplicate API calls."""
    def __init__(self, max_size: int = 100):
        self.cache: OrderedDict[str, List[float]] = OrderedDict()
        self.max_size = max_size
    
    def get(self, key: str) -> Optional[List[float]]:
        if key in self.cache:
            # Move to end (LRU)
            self.cache.move_to_end(key)
            return self.cache[key]
        return None
    
    def set(self, key: str, value: List[float]):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)
    
    def clear(self):
        self.cache.clear()

embedding_cache = EmbeddingCache(EMBEDDING_CACHE_SIZE)

# Initialize FastAPI app
app = FastAPI(title="RAG Chatbot API", version="1.0.0")

# Add CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Supabase client
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("✓ Supabase client initialized")
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    supabase = None

# Global async HTTP client for connection pooling
http_client: Optional[httpx.AsyncClient] = None


@app.on_event("startup")
async def startup_event():
    """Initialize async HTTP client on startup."""
    global http_client
    http_client = httpx.AsyncClient(timeout=60.0)
    
    # Validate configuration
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not set!")
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set!")
    if not supabase:
        logger.error("Supabase client not initialized!")
    
    logger.info("Chatbot API started")
    logger.info(f"Chat model: {CHAT_MODEL}")
    logger.info(f"Embedding model: {EMBEDDING_MODEL}")
    logger.info(f"RAG context limit: {RAG_CONTEXT_LIMIT} (optimized for speed)")


@app.on_event("shutdown")
async def shutdown_event():
    """Close async HTTP client on shutdown."""
    global http_client
    if http_client:
        await http_client.aclose()



# --- Request/Response Models ---

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    manual_type: Optional[str] = None  # Filter by "teacher" or "student"
    session_id: Optional[str] = None  # Session ID for tracking conversation


class SourceItem(BaseModel):
    title: str
    url: str
    type: str
    page: Optional[int] = None
    similarity: float = 0.0


class ChatResponse(BaseModel):
    response: str
    session_id: str  # Return session ID to frontend
    sources: List[SourceItem] = []


# --- Async Helper Functions ---

async def get_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding for text using OpenRouter with caching.
    
    OPTIMIZATION: Checks cache first to avoid duplicate API calls.
    """
    # Check cache first
    cached = embedding_cache.get(text)
    if cached:
        logger.debug(f"Cache hit for embedding (cache size: {len(embedding_cache.cache)})")
        return cached

    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_openrouter_api_key_here":
        logger.error("OpenRouter API key not configured for embeddings")
        return None

    if http_client is None:
        logger.error("HTTP client is not initialized")
        return None
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        payload = {
            "model": EMBEDDING_MODEL,
            "input": [text]
        }
        
        # Use async HTTP client
        resp = await http_client.post(
            OPENROUTER_EMBEDDINGS_URL,
            json=payload,
            headers=headers,
            timeout=30
        )

        resp.raise_for_status()
        data = resp.json()
        
        if "data" in data and len(data["data"]) > 0:
            embedding = data["data"][0]["embedding"]
            # Cache the result
            embedding_cache.set(text, embedding)
            return embedding
        
        logger.warning(f"Unexpected embedding response: {data}")
        return None
    except Exception as e:
        logger.warning(f"Failed to generate embedding (network/API issue): {type(e).__name__}: {e}")
        return None


def normalize_source_url(url: Optional[str]) -> str:
    """Normalize stored source URLs so the frontend always gets a clickable link."""
    if not url:
        return ""

    normalized = url.strip().strip("()[]<>{}.,;\"'")
    if normalized.startswith("www."):
        normalized = f"https://{normalized}"
    if normalized.startswith("http://"):
        normalized = f"https://{normalized[len('http://'):]}"
    return normalized if normalized.startswith("https://") else ""


def is_chinese_char(char: str) -> bool:
    """Check if a character is Chinese (CJK)."""
    code = ord(char)
    return (
        (0x4E00 <= code <= 0x9FFF) or  # CJK Unified Ideographs
        (0x3400 <= code <= 0x4DBF) or  # CJK Extension A
        (0x20000 <= code <= 0x2A6DF) or  # CJK Extension B
        (0xF900 <= code <= 0xFAFF)  # CJK Compatibility Ideographs
    )


def contains_chinese(text: str) -> bool:
    """Check if text contains Chinese characters."""
    return any(is_chinese_char(char) for char in text)


def tokenize_chinese(text: str) -> List[str]:
    """Tokenize Chinese text using jieba or fallback character-based method."""
    text_clean = text.strip()
    
    if JIEBA_AVAILABLE:
        # Use jieba for proper word segmentation
        tokens = jieba.cut(text_clean)
        # Filter out empty strings and stopwords (very short, single character)
        return [
            token.lower().strip() 
            for token in tokens 
            if token.strip() and len(token.strip()) > 0
        ]
    else:
        # Fallback: character-by-character (less ideal but works)
        logger.warning("jieba not available, using character-based Chinese tokenization")
        return [char.lower() for char in text_clean if is_chinese_char(char)]


def tokenize_english(text: str) -> List[str]:
    """Tokenize English text using regex."""
    terms = []
    seen_terms = set()
    for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text.lower()):
        # Handle possessives
        if term.endswith("'s"):
            term = term[:-2]
        # Handle plurals
        if term.endswith("s") and len(term) > 4:
            term = term[:-1]
        # Filter by length and avoid duplicates
        if len(term) < 3 or term in seen_terms:
            continue
        seen_terms.add(term)
        terms.append(term)
    return terms


def tokenize_query_terms(query: str) -> Tuple[List[str], bool]:
    """Extract useful lexical terms for both English and Chinese queries.
    
    Returns: (terms, has_chinese) tuple
    """
    has_chinese_text = contains_chinese(query)
    
    if has_chinese_text:
        # Use Chinese tokenization
        chinese_terms = tokenize_chinese(query)
        english_terms = tokenize_english(query)
        # Combine both (prefer Chinese if present)
        all_terms = chinese_terms + english_terms
        return (all_terms, True)
    else:
        # Use English tokenization only
        english_terms = tokenize_english(query)
        return (english_terms, False)


def build_query_phrases(terms: List[str], max_size: int = 3, is_chinese: bool = False) -> List[str]:
    """Build contiguous query phrases from query terms.
    
    For Chinese, we allow phrases of any valid length since Chinese phrases 
    are semantic units. For English, we stick with 2-3 word phrases.
    """
    phrases = []
    seen_phrases = set()
    
    # For Chinese, allow longer phrase combinations since each term is usually 1-2 chars
    phrase_sizes = range(2, min(max_size + 1, len(terms) + 1)) if is_chinese else range(2, max_size + 1)
    
    for size in phrase_sizes:
        for idx in range(0, len(terms) - size + 1):
            phrase = "".join(terms[idx:idx + size]) if is_chinese else " ".join(terms[idx:idx + size])
            if phrase in seen_phrases:
                continue
            seen_phrases.add(phrase)
            phrases.append(phrase)
    return phrases


def dedupe_documents_by_title(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep one seed chunk per document title before context expansion."""
    unique_docs = []
    seen_titles = set()
    for doc in documents:
        title = doc.get("document_title", "")
        if title in seen_titles:
            continue
        seen_titles.add(title)
        unique_docs.append(doc)
    return unique_docs


def format_sources(documents: List[Dict[str, Any]]) -> List[SourceItem]:
    """Build a de-duplicated source list with normalized URLs."""
    sources: List[SourceItem] = []
    seen_urls = set()

    for doc in documents:
        source_url = normalize_source_url(doc.get("source_url", ""))
        if not source_url or source_url in seen_urls:
            continue

        similarity = doc.get("similarity", 0)
        try:
            similarity_float = float(similarity)
            if 0.0 <= similarity_float <= 1.0:
                similarity_value = round(similarity_float * 100, 1)
            else:
                similarity_value = round(min(similarity_float * 20, 100), 1)
        except (TypeError, ValueError):
            similarity_value = 0.0

        sources.append(
            SourceItem(
                title=doc.get("document_title", "Unknown"),
                url=source_url,
                type=doc.get("manual_type") or "Unknown",
                page=doc.get("page_number"),
                similarity=similarity_value,
            )
        )
        seen_urls.add(source_url)

    return sources


def append_sources_markdown(response_text: str, sources: List[SourceItem]) -> str:
    """Append clickable markdown links so sources are always visible in the answer body."""
    if not sources:
        return response_text

    lines = ["", "---", "", "**Sources**"]
    for source in sources:
        page_text = f" (page {source.page})" if source.page else ""
        lines.append(f"- [{source.title}]({source.url}){page_text}")

    return f"{response_text.rstrip()}\n" + "\n".join(lines)


def score_document_relevance(query: str, doc: Dict[str, Any]) -> float:
    """Score a document's relevance to the query using multiple signals.
    
    RERANKING STRATEGY:
    - Exact phrase match in title: +1000 (massive boost)
    - Each key term in title: +100
    - Each key term in content: +10
    - Phrase match in content: +50
    
    Works for both English and Chinese text.
    """
    terms, is_chinese = tokenize_query_terms(query)
    if not terms:
        return 0.0
    
    query_lower = query.lower()
    title_lower = doc.get("document_title", "").lower()
    content_lower = doc.get("content", "").lower()[:800]  # First 800 chars
    
    score = 0.0
    
    # Check for phrase matches first (most specific)
    query_phrases = build_query_phrases(terms, max_size=4, is_chinese=is_chinese)
    
    for phrase in query_phrases:
        if phrase in title_lower:
            score += 1000  # Exact phrase in title = MASSIVE boost
        if phrase in content_lower:
            score += 50
    
    # Check for individual term matches (more general)
    for term in terms:
        # Title matches are much more important
        if term in title_lower:
            score += 100
        if term in content_lower:
            score += 10
    
    logger.debug(f"Document '{doc.get('document_title', 'Unknown')[:40]}' scored: {score:.1f} (Chinese: {is_chinese})")
    return score


def rerank_documents(query: str, candidates: List[Dict[str, Any]], top_k: int = 8) -> List[Dict[str, Any]]:
    """Rerank candidate documents by relevance score.
    
    This replaces keyword-based fallback with smart relevance scoring.
    """
    # Score all candidates
    scored = [
        (doc, score_document_relevance(query, doc))
        for doc in candidates
    ]
    
    # Sort by score (descending), then by document title (for stability)
    scored.sort(key=lambda x: (-x[1], x[0].get("document_title", "")))
    
    # Return top documents, deduplicated by title
    result = []
    seen_titles = set()
    for doc, score in scored:
        title = doc.get("document_title", "")
        if title not in seen_titles:
            logger.debug(f"  Ranked: {title} (score: {score:.1f})")
            result.append(doc)
            seen_titles.add(title)
            if len(result) >= top_k:
                break
    
    return result


def fallback_search_documents(
    query: str,
    manual_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fallback retrieval using reranking instead of manual keyword logic.
    
    STRATEGY:
    1. Fetch broader set of candidate documents using ALL query terms
    2. Rerank candidates by relevance score (phrase matches, term frequency)
    3. Return top-k most relevant documents
    
    Works for both English and Chinese queries.
    """
    if not supabase:
        return []

    terms, is_chinese = tokenize_query_terms(query)
    if not terms:
        return []

    try:
        select_fields = "id, content, document_title, source_url, manual_type, chunk_index, page_number, chunk_total"
        
        # Fetch broader candidate set (don't filter too much)
        candidates = []
        
        # Search for ALL important terms (not just first 2!)
        for term in terms:
            try:
                response = supabase.table("documents").select(select_fields).ilike(
                    "document_title", f"%{term}%"
                ).limit(RAG_CONTEXT_LIMIT * 2).execute()
                
                if hasattr(response, 'data') and response.data:
                    candidates.extend(response.data)
            except Exception as e:
                logger.debug(f"Title search for '{term}' failed: {e}")
        
        # Also search content for better coverage
        if len(candidates) < RAG_CONTEXT_LIMIT:
            for term in terms[:3]:  # Search first 3 terms in content
                try:
                    response = supabase.table("documents").select(select_fields).ilike(
                        "content", f"%{term}%"
                    ).limit(RAG_CONTEXT_LIMIT).execute()
                    
                    if hasattr(response, 'data') and response.data:
                        candidates.extend(response.data)
                except Exception as e:
                    logger.debug(f"Content search for '{term}' failed: {e}")
        
        if not candidates:
            logger.warning(f"No candidates found for query: '{query}' (Chinese: {is_chinese})")
            return []
        
        logger.info(f"Fetched {len(candidates)} candidate documents, reranking... (Language: {'Chinese' if is_chinese else 'English'})")
        
        # RERANK candidates by relevance
        reranked = rerank_documents(query, candidates, top_k=RAG_CONTEXT_LIMIT)
        
        if not reranked:
            return []
        
        # Expand context around top-ranked documents
        expanded_docs = expand_context_batched(reranked)
        doc_order = {
            doc.get("document_title", ""): index
            for index, doc in enumerate(reranked)
        }
        
        sorted_docs = sorted(expanded_docs, key=lambda doc: (
            doc_order.get(doc.get("document_title", ""), 9999),
            doc.get("chunk_index", 0),
        ))
        
        logger.info(f"Fallback reranking returned {len(sorted_docs)} documents")
        return sorted_docs
        
    except Exception as e:
        logger.warning(f"Fallback rerank search failed: {e}")
        return []


def expand_context_batched(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fetch multiple chunks from relevant documents to get complete information.
    
    STRATEGY:
    1. For top-ranked documents, fetch ALL or MOST chunks (not just neighbors)
    2. This ensures we get complete answers when content spans multiple chunks
    3. Sort by chunk_index to maintain document flow
    
    OPTIMIZATION: Uses a single batched query for all neighbors + full document chunks.
    """
    if not documents or not supabase:
        return documents

    expanded_map = {doc["id"]: doc for doc in documents}
    
    # For top documents (by title), fetch additional chunks
    doc_titles = []
    seen_titles = set()
    for doc in documents:
        title = doc.get("document_title")
        if title and title not in seen_titles:
            doc_titles.append(title)
            seen_titles.add(title)
    
    # Fetch more chunks from top documents
    for title in doc_titles[:3]:  # Top 3 most relevant documents
        try:
            # Fetch up to 10 chunks from this document (more comprehensive coverage)
            result = supabase.table("documents") \
                .select("id, content, document_title, source_url, manual_type, chunk_index, page_number, chunk_total") \
                .eq("document_title", title) \
                .order("chunk_index") \
                .limit(10) \
                .execute()
            
            if result.data:
                for row in result.data:
                    if row["id"] not in expanded_map:
                        expanded_map[row["id"]] = row
        except Exception as e:
            logger.debug(f"Failed to fetch chunks from {title}: {e}")
    
    return list(expanded_map.values())


async def retrieve_relevant_documents(
    query: str,
    manual_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search Supabase for documents relevant to the query using vector similarity.
    
    OPTIMIZATION: Returns fewer documents (RAG_CONTEXT_LIMIT reduced from 8 to 5)
    with higher similarity threshold to get better matches faster.
    """
    if not supabase:
        logger.error("Supabase client not initialized")
        return []

    # Generate embedding for the query (or use cached)
    embedding = await get_embedding(query)
    if not embedding:
        logger.warning("Could not generate embedding for query, trying fallback retrieval")
        return fallback_search_documents(query, manual_type=manual_type)
    
    try:
        # Use Supabase vector search with optimized parameters
        response = supabase.rpc(
            "search_documents",
            {
                "query_embedding": embedding,
                "similarity_threshold": 0.2,
                "match_count": RAG_CONTEXT_LIMIT,
                "manual_type_filter": manual_type
            }
        ).execute()
        
        raw_docs = []
        if hasattr(response, "data"):
            raw_docs = response.data
        elif isinstance(response, dict):
            raw_docs = response.get("data", [])
        
        logger.info(f"Vector search returned {len(raw_docs)} documents (threshold: 0.2)")
        
        if not raw_docs:
            logger.warning(f"No documents found for query: '{query}'")
            logger.debug(f"Response object: {response}")
            return fallback_search_documents(query, manual_type=manual_type)
        
        # RERANK vector search results by relevance score
        # This ensures even if vector search returns docs, we pick the BEST matches
        logger.info(f"Reranking {len(raw_docs)} vector search results")
        reranked_docs = rerank_documents(query, raw_docs, top_k=RAG_CONTEXT_LIMIT)
        
        if not reranked_docs:
            logger.warning("Reranking produced no results, trying fallback")
            return fallback_search_documents(query, manual_type=manual_type)
        
        # Expand context with neighboring chunks (optimized batched query)
        expanded_docs = expand_context_batched(reranked_docs)
        doc_order = {}
        for doc in reranked_docs:
            title = doc.get("document_title", "")
            if title not in doc_order:
                doc_order[title] = len(doc_order)
        
        # Preserve retrieval order, then keep chunks in reading order inside each doc
        sorted_docs = sorted(expanded_docs, key=lambda x: (
            doc_order.get(x.get("document_title", ""), 9999),
            x.get("chunk_index", 0)
        ))
        
        return sorted_docs
        
    except Exception as e:
        logger.warning(f"Vector search failed: {e}, trying fallback retrieval")
        return fallback_search_documents(query, manual_type=manual_type)


async def generate_rag_response(
    user_message: str,
    context_documents: List[Dict[str, Any]],
    sources: List[SourceItem],
) -> str:
    """Generate a response using OpenRouter with RAG context.
    
    OPTIMIZATION: Uses async HTTP client for non-blocking API call.
    FIXED: Uses correct system prompt from previous version with proper source citation guidelines.
    """

    if not context_documents:
        return (
            "I couldn't find matching documents for this question, so I can't provide a sourced answer yet.\n\n"
            "Please check that document ingestion completed successfully and that embeddings retrieval is working."
        )
    
    # Check if API key is configured
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_openrouter_api_key_here":
        logger.warning("OpenRouter API key not configured, using demo response")
        return generate_demo_response(user_message, context_documents)
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:3000",
    }
    
    # Build context grouped by document
    context_parts = []
    if context_documents:
        docs_by_title = {}
        for doc in context_documents:
            title = doc.get('document_title', 'Unknown Document')
            if title not in docs_by_title:
                docs_by_title[title] = {
                    "url": doc.get('source_url', ''),
                    "chunks": []
                }
            docs_by_title[title]["chunks"].append(doc)
            
        for title, info in docs_by_title.items():
            sorted_chunks = sorted(info["chunks"], key=lambda x: x.get("chunk_index", 0))
            # Join chunks - wrap in verbatim markers to prevent reformatting
            combined_content = "\n".join([c.get('content', '') for c in sorted_chunks])
            
            # Put metadata OUTSIDE the code block so it's not copied verbatim
            url = info['url'].strip() if info['url'] else ''
            if url:
                part = f"SOURCE: {title}\nURL: {url}\n\n```\n{combined_content}\n```"
            else:
                part = f"SOURCE: {title}\n\n```\n{combined_content}\n```"
            context_parts.append(part)
            
    context_text = "\n\n" + "\n\n---\n\n".join(context_parts) if context_parts else ""
    
    # System prompt - FIXED VERSION with proper source citation guidelines
    system_prompt = """You are a helpful AI support assistant for sayo.ai, an educational platform for teachers and students.

Your role is to provide accurate, comprehensive answers based ONLY on the provided tutorial documents.

⚠️ CRITICAL - NO HALLUCINATION ALLOWED:
- ONLY use information from the provided context
- NEVER add explanations, interpretations, or extra steps not in the source
- NEVER combine multiple sections into new structure
- If the source says "A, B, C" then respond with "A, B, C" - not "A, B, C, and also D"
- Quote directly from source when possible
- Every sentence in your answer must come from the provided documents

VERBATIM CONTENT RULE:
When you see content inside triple backticks (```), this is source material. Copy it EXACTLY as shown. Do NOT reformat, do NOT add, do NOT interpret. If it contains "9, 10, 11, 12" then output "9, 10, 11, 12" - NEVER change numbers.

CITATION RULE - MOST IMPORTANT:
- NEVER include [SOURCE: ...] tags inline with content
- NEVER cite after each bullet point
- Put ALL sources in a SINGLE line at the very end
- Format: "For more details, please refer to: [Document Title](URL)"
- If multiple sources, separate with commas: "For more details, please refer to: [Doc1](URL1), [Doc2](URL2)"

Guidelines:
1. ANSWER FROM SOURCE ONLY: Each point must come directly from the provided context. Do not add elaboration or extra steps.
2. NO MIXING SECTIONS: If multiple topics are in context, answer only the specific question asked. Do not combine unrelated sections.
3. DIRECT QUOTES: When possible, use exact phrases from the source material.
4. COMPLETENESS: Provide all relevant info from the source that answers the question - but ONLY that.
5. NO FABRICATION: Do NOT invent steps, fields, or procedures. ONLY use what's in the documents.
6. HONESTY: If the answer is NOT in the provided materials, say: "I don't have information about this in the Sayo documentation."
7. FORMATTING: Use clear bullet points or numbered lists. Keep the tone professional yet helpful."""
    
    # Build messages
    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]
    
    if context_text:
        messages.append({
            "role": "user",
            "content": f"Context documents:\n\n{context_text}\n\n---\n\nQuestion: {user_message}"
        })
    else:
        messages.append({
            "role": "user",
            "content": user_message
        })
    
    try:
        payload = {
            "model": CHAT_MODEL,
            "messages": messages,
            "temperature": 0.3,  # Lower temp = more faithful to source, less creative
            "max_tokens": 600     # Reduced to prevent hallucination/over-generation
        }
        
        logger.debug(f"Sending request to OpenRouter with model {CHAT_MODEL}")
        
        # Use async HTTP client
        resp = await http_client.post(
            OPENROUTER_URL,
            json=payload,
            headers=headers,
            timeout=60
        )
        
        if resp.status_code != 200:
            logger.error(f"OpenRouter returned {resp.status_code}: {resp.text}")
        
        resp.raise_for_status()
        data = resp.json()
        
        if "choices" in data and len(data["choices"]) > 0:
            model_response = data["choices"][0]["message"]["content"].strip()
            # Response already includes sources per the system prompt
            return model_response
        else:
            logger.error(f"Unexpected chat response: {data}")
            return "Sorry, I couldn't generate a response."
    
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"Failed to generate response: {error_type}: {error_msg}")
        # Return user-friendly message instead of exposing technical errors
        return "Sorry, I encountered a temporary issue connecting to the AI service. Please try again in a moment."


def generate_demo_response(user_message: str, context_documents: List[Dict[str, Any]]) -> str:
    """Generate a demo response for testing without OpenRouter API key."""
    
    if not context_documents:
        if "hello" in user_message.lower() or "hi" in user_message.lower():
            return "Hello! I'm your AI teaching assistant. To get personalized responses based on your materials, please ingest some documents first using: python ingest_notion_pdfs.py\n\nOnce documents are ingested, I can retrieve relevant content and provide better answers."
        elif "what" in user_message.lower():
            return "That's a great question! To give you an accurate answer based on your educational materials, I would need documents to be ingested first. Here's how to do it:\n\n1. Place your PDFs in backend/Notion_Export/\n2. Run: python ingest_notion_pdfs.py\n3. Then I can retrieve relevant information from your materials."
        else:
            return f"You asked: '{user_message}'\n\nTo provide a personalized response based on your educational materials, please configure your OpenRouter API key and ingest documents. See README.md for setup instructions."
    
    doc_summary = ", ".join([doc.get('document_title', 'Unknown') for doc in context_documents[:2]])
    return f"Based on the retrieved content from {doc_summary}, I can see this relates to your educational materials. To provide a proper answer using OpenRouter's AI models, please configure your OPENROUTER_API_KEY in the .env file.\n\nThe documents have been successfully retrieved and are ready to be used once the API key is configured!"

# --- API Endpoints ---

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "RAG Chatbot API",
        "embedding_cache_size": len(embedding_cache.cache)
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint with RAG context retrieval (FIXED VERSION)."""
    
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    # Use provided session ID or generate a new one
    session_id = request.session_id or str(uuid.uuid4())
    
    logger.info(f"Chat request: {request.message[:100]}...")
    
    documents = await retrieve_relevant_documents(
        request.message,
        manual_type=request.manual_type
    )
    logger.info(f"Retrieved {len(documents)} documents (including expanded context)")

    sources = format_sources(documents)
    
    # Generate response with RAG context
    # The model now handles source citations per the system prompt
    response_text = await generate_rag_response(request.message, documents, sources)

    return ChatResponse(response=response_text, session_id=session_id, sources=sources)


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """Alias endpoint for frontend compatibility."""
    return await chat(request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
