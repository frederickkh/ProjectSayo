#!/usr/bin/env python3
"""
Generate embeddings for document chunks and store in document_embeddings table.

Usage:
    python generate_embeddings.py                    # Use default model
    python generate_embeddings.py --model qwen/qwen3-embedding-8b  # Use specific model
    python generate_embeddings.py --dry-run          # Preview without saving
    python generate_embeddings.py --limit 10         # Process only first 10 docs
    python generate_embeddings.py --skip-existing    # Skip already embedded docs

Environment Variables:
    OPENROUTER_API_KEY (required)
    SUPABASE_URL (required)
    SUPABASE_SERVICE_ROLE_KEY (required)
"""

import os
import sys
import argparse
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import load_dotenv

# Supabase client
try:
    from supabase import create_client, Client
except ImportError:
    print("ERROR: supabase not installed. Run: pip install supabase")
    sys.exit(1)

load_dotenv()

# ============================================================================
# Configuration
# ============================================================================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not all([OPENROUTER_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY]):
    print("ERROR: Missing required environment variables:")
    print("  - OPENROUTER_API_KEY")
    print("  - SUPABASE_URL")
    print("  - SUPABASE_SERVICE_ROLE_KEY")
    sys.exit(1)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Model configuration
# Note: These are models actually supported by OpenRouter for embeddings
# Check https://openrouter.ai/docs#models for current availability
MODEL_CONFIGS = {
    "openrouter/auto": {"dimensions": 1536, "batch_size": 50},  # OpenRouter default/best
    "openai/text-embedding-3-small": {"dimensions": 1536, "batch_size": 50},
    "openai/text-embedding-3-large": {"dimensions": 3072, "batch_size": 10},
    "perplexity/pplx-embed-v1-4b": {"dimensions": 2560, "batch_size": 50},
}

DEFAULT_MODEL = "openrouter/auto"
DEFAULT_BATCH_SIZE = 50
RATE_LIMIT_DELAY = 0.5  # seconds between requests

# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Document:
    id: str
    content: str
    document_title: str
    source_url: Optional[str] = None
    manual_type: Optional[str] = None
    chunk_index: Optional[int] = None
    page_number: Optional[int] = None
    chunk_total: Optional[int] = None


@dataclass
class EmbeddingResult:
    document_id: str
    model_name: str
    embedding: List[float]
    status: str
    error: Optional[str] = None


# ============================================================================
# Supabase Client
# ============================================================================

def create_supabase_client() -> Client:
    """Create Supabase client."""
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ============================================================================
# Database Operations
# ============================================================================

def fetch_documents_needing_embedding(
    client: Client,
    model_name: str,
    limit: Optional[int] = None,
    skip_existing: bool = False,
) -> List[Document]:
    """Fetch documents that need embedding for a specific model.
    
    Args:
        client: Supabase client
        model_name: Name of the embedding model
        limit: Maximum number of documents to fetch
        skip_existing: If True, skip documents already embedded for this model
    
    Returns:
        List of Document objects
    """
    try:
        query = client.table("documents").select("*")
        
        if limit:
            query = query.limit(limit)
        
        response = query.execute()
        docs = response.data
        
        if not docs:
            logger.warning("No documents found in database")
            return []
        
        logger.info(f"Fetched {len(docs)} documents from database")
        
        if skip_existing:
            # Check which docs already have embeddings for this model
            existing = client.table("document_embeddings").select("document_id").eq(
                "model_name", model_name
            ).execute()
            existing_ids = {row["document_id"] for row in existing.data}
            
            docs = [d for d in docs if d["id"] not in existing_ids]
            logger.info(f"After filtering: {len(docs)} documents need embedding")
        
        # Convert to Document objects
        documents = []
        for doc in docs:
            documents.append(
                Document(
                    id=doc["id"],
                    content=doc["content"],
                    document_title=doc.get("document_title", ""),
                    source_url=doc.get("source_url"),
                    manual_type=doc.get("manual_type"),
                    chunk_index=doc.get("chunk_index"),
                    page_number=doc.get("page_number"),
                    chunk_total=doc.get("chunk_total"),
                )
            )
        
        return documents
    
    except Exception as e:
        logger.error(f"Failed to fetch documents: {e}")
        raise


def insert_embeddings(
    client: Client,
    results: List[EmbeddingResult],
    dry_run: bool = False,
) -> Tuple[int, int]:
    """Insert embeddings into document_embeddings table.
    
    Args:
        client: Supabase client
        results: List of EmbeddingResult objects
        dry_run: If True, don't actually insert
    
    Returns:
        (successful_count, failed_count)
    """
    successful = 0
    failed = 0
    
    for result in results:
        if result.status == "success":
            try:
                if not dry_run:
                    # Upsert to handle duplicates gracefully
                    client.table("document_embeddings").upsert({
                        "document_id": result.document_id,
                        "model_name": result.model_name,
                        "embedding": result.embedding,
                    }).execute()
                
                successful += 1
                logger.debug(f"✓ Inserted embedding for doc {result.document_id[:8]}...")
            
            except Exception as e:
                logger.error(f"Failed to insert embedding for {result.document_id}: {e}")
                failed += 1
        else:
            failed += 1
            logger.warning(
                f"Skipped doc {result.document_id[:8]}... (error: {result.error})"
            )
    
    return successful, failed


# ============================================================================
# Embedding Generation
# ============================================================================

def generate_embedding(model: str, text: str) -> Tuple[Optional[List[float]], float]:
    """Generate embedding using OpenRouter API.
    
    Args:
        model: Model name (e.g., "openai/text-embedding-3-large")
        text: Text to embed
    
    Returns:
        (embedding_vector, latency_ms)
    
    Raises:
        Exception: If API call fails
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/DDA4080",
        "X-Title": "Document Embeddings Generator",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "input": text,
    }
    
    start_time = time.time()
    
    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/embeddings",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        
        latency = (time.time() - start_time) * 1000  # ms
        data = response.json()
        embedding = data["data"][0]["embedding"]
        
        return embedding, latency
    
    except requests.exceptions.RequestException as e:
        logger.error(f"API error: {e}")
        if hasattr(e, "response") and e.response is not None:
            status = e.response.status_code
            try:
                error_data = e.response.json()
                logger.error(f"API response ({status}): {error_data}")
            except:
                pass
            
            if status == 403:
                logger.error("\n" + "="*70)
                logger.error("❌ 403 FORBIDDEN ERROR")
                logger.error("="*70)
                logger.error("\nLikely causes:")
                logger.error("  1. Invalid or expired OPENROUTER_API_KEY")
                logger.error("  2. Model not available on your OpenRouter plan")
                logger.error("  3. Model not supported by OpenRouter for embeddings")
                logger.error("\nSolution:")
                logger.error("  - Check API key: echo $env:OPENROUTER_API_KEY (Windows) or echo $OPENROUTER_API_KEY (Unix)")
                logger.error("  - View available models: https://openrouter.ai/docs#models")
                logger.error("  - Try supported model: openrouter/auto or openai/text-embedding-3-small")
                logger.error(f"\nCurrent model: {model}")
                logger.error("="*70 + "\n")
        raise


def generate_embeddings_batch(
    model: str,
    documents: List[Document],
    batch_size: Optional[int] = None,
    dry_run: bool = False,
) -> List[EmbeddingResult]:
    """Generate embeddings for a batch of documents.
    
    Args:
        model: Model name
        documents: List of Document objects
        batch_size: Number of documents per batch (for rate limiting)
        dry_run: If True, don't actually call API
    
    Returns:
        List of EmbeddingResult objects
    """
    if batch_size is None:
        batch_size = MODEL_CONFIGS.get(model, {}).get("batch_size", DEFAULT_BATCH_SIZE)
    
    results = []
    
    logger.info(f"Generating embeddings for {len(documents)} documents")
    logger.info(f"Model: {model}")
    logger.info(f"Batch size: {batch_size}")
    
    for i, doc in enumerate(documents, 1):
        try:
            if dry_run:
                logger.info(f"[{i}/{len(documents)}] DRY RUN: Would embed '{doc.document_title[:40]}...'")
                # Create a fake embedding for dry run
                embedding = [0.0] * MODEL_CONFIGS.get(model, {}).get("dimensions", 1536)
                latency = 0.0
            else:
                logger.info(f"[{i}/{len(documents)}] Embedding '{doc.document_title[:40]}...'")
                embedding, latency = generate_embedding(model, doc.content)
            
            results.append(
                EmbeddingResult(
                    document_id=doc.id,
                    model_name=model,
                    embedding=embedding,
                    status="success",
                )
            )
            
            logger.debug(f"  Latency: {latency:.0f}ms, dims: {len(embedding)}")
            
            # Rate limiting
            if i < len(documents):
                time.sleep(RATE_LIMIT_DELAY)
        
        except Exception as e:
            logger.error(f"Failed to embed document {doc.id}: {e}")
            results.append(
                EmbeddingResult(
                    document_id=doc.id,
                    model_name=model,
                    embedding=[],
                    status="error",
                    error=str(e),
                )
            )
    
    return results


# ============================================================================
# Main Workflow
# ============================================================================

def main():
    """Main workflow."""
    parser = argparse.ArgumentParser(
        description="Generate embeddings for document chunks"
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Embedding model (default: {DEFAULT_MODEL})",
        choices=list(MODEL_CONFIGS.keys()),
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of documents to process",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip documents already embedded for this model",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without actually storing embeddings",
    )
    
    args = parser.parse_args()
    
    # Print configuration
    print("\n" + "=" * 80)
    print("DOCUMENT EMBEDDING GENERATOR")
    print("=" * 80)
    print(f"Model: {args.model}")
    print(f"Dimensions: {MODEL_CONFIGS[args.model]['dimensions']}")
    print(f"Skip existing: {args.skip_existing}")
    print(f"Dry run: {args.dry_run}")
    if args.limit:
        print(f"Limit: {args.limit} documents")
    print("=" * 80 + "\n")
    
    # Connect to Supabase
    logger.info("Connecting to Supabase...")
    client = create_supabase_client()
    
    # Fetch documents
    logger.info("Fetching documents...")
    documents = fetch_documents_needing_embedding(
        client,
        args.model,
        limit=args.limit,
        skip_existing=args.skip_existing,
    )
    
    if not documents:
        logger.warning("No documents to process")
        return
    
    logger.info(f"Processing {len(documents)} documents")
    
    # Generate embeddings
    results = generate_embeddings_batch(
        args.model,
        documents,
        dry_run=args.dry_run,
    )
    
    # Calculate statistics
    successful = [r for r in results if r.status == "success"]
    failed = [r for r in results if r.status != "success"]
    
    print(f"\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Total processed: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    
    if successful:
        avg_dim = len(successful[0].embedding)
        print(f"Embedding dimension: {avg_dim}")
    
    print("=" * 80 + "\n")
    
    # Insert into database
    if not args.dry_run and successful:
        logger.info(f"Inserting {len(successful)} embeddings into database...")
        inserted, failed_insert = insert_embeddings(client, results, dry_run=args.dry_run)
        logger.info(f"Inserted: {inserted}, Failed: {failed_insert}")
    
    # Summary
    if args.dry_run:
        print("✓ Dry run complete - no data was inserted")
    else:
        print(f"✓ Successfully embedded and stored {len(successful)} documents")
    
    if failed:
        print(f"⚠ Failed to embed {len(failed)} documents")
        for result in failed[:5]:  # Show first 5 errors
            print(f"  - {result.document_id[:8]}...: {result.error}")
        if len(failed) > 5:
            print(f"  ... and {len(failed) - 5} more")


if __name__ == "__main__":
    main()
