#!/usr/bin/env python3
"""FastAPI server for RAG chatbot using OpenRouter and Supabase.

To run:
    python -m uvicorn chat_api:app --reload --host 0.0.0.0 --port 8000

Environment Variables (required):
    OPENROUTER_API_KEY
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    
Optional:
    CHAT_MODEL              # Default: openrouter/auto (use cheapest available)
    EMBEDDING_MODEL         # Default: openai/text-embedding-3-small
    RAG_CONTEXT_LIMIT       # Default: 3 (number of documents to retrieve)
"""

import os
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from supabase import create_client, Client

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

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


# --- Request/Response Models ---

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    manual_type: Optional[str] = None  # Filter by "teacher" or "student"


class ChatResponse(BaseModel):
    response: str
    sources: List[Dict[str, Any]] = []


# --- Helper Functions ---

def get_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding for text using OpenRouter."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        payload = {
            "model": EMBEDDING_MODEL,
            "input": [text]
        }
        resp = requests.post(
            OPENROUTER_EMBEDDINGS_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]["embedding"]
        else:
            logger.error(f"Unexpected embedding response: {data}")
            return None
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return None


def expand_context(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """For each retrieved chunk, also fetch adjacent chunks from the same document.
    
    This ensures the LLM sees the surrounding context even if only one chunk 
    was highly similar to the query.
    """
    if not documents or not supabase:
        return documents

    expanded_map = {doc["id"]: doc for doc in documents}
    
    for doc in documents:
        title = doc.get("document_title")
        idx = doc.get("chunk_index")
        
        # Only expand if we have the necessary metadata
        if title is None or idx is None:
            continue
            
        # Fetch one chunk before and one after
        for neighbor_idx in [idx - 1, idx + 1]:
            if neighbor_idx < 0:
                continue
                
            # Skip if we already have this chunk
            # Note: We don't have the ID yet, so we'll check after fetching
            try:
                result = supabase.table("documents") \
                    .select("id, content, document_title, source_url, manual_type, chunk_index, page_number, chunk_total") \
                    .eq("document_title", title) \
                    .eq("chunk_index", neighbor_idx) \
                    .execute()
                
                if result.data:
                    for row in result.data:
                        if row["id"] not in expanded_map:
                            expanded_map[row["id"]] = row
            except Exception as e:
                logger.warning(f"Failed to fetch neighbor chunk ({title}, {neighbor_idx}): {e}")

    # Convert back to list
    return list(expanded_map.values())


def retrieve_relevant_documents(
    query: str,
    manual_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search Supabase for documents relevant to the query using vector similarity.
    
    Returns a list of documents including expanded context.
    """
    if not supabase:
        logger.error("Supabase client not initialized")
        return []
    
    # Generate embedding for the query
    embedding = get_embedding(query)
    if not embedding:
        logger.warning("Could not generate embedding for query")
        return []
    
    try:
        # Use Supabase vector search
        response = supabase.rpc(
            "search_documents",
            {
                "query_embedding": embedding,
                "similarity_threshold": 0.5,
                "match_count": RAG_CONTEXT_LIMIT,
                "manual_type_filter": manual_type
            }
        ).execute()
        
        raw_docs = []
        if hasattr(response, "data"):
            raw_docs = response.data
        elif isinstance(response, dict):
            raw_docs = response.get("data", [])
            
        if not raw_docs:
            return []
            
        # Expand context to include neighbors
        expanded_docs = expand_context(raw_docs)
        
        # Sort by document title then chunk index for logical flow
        sorted_docs = sorted(expanded_docs, key=lambda x: (
            x.get("document_title", ""), 
            x.get("chunk_index", 0)
        ))
        
        return sorted_docs
        
    except Exception as e:
        logger.warning(f"Vector search failed: {e}")
        return []


def generate_rag_response(
    user_message: str,
    context_documents: List[Dict[str, Any]]
) -> str:
    """Generate a response using OpenRouter with RAG context."""
    
    # Check if API key is configured
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_openrouter_api_key_here":
        logger.warning("OpenRouter API key not configured, using demo response")
        return generate_demo_response(user_message, context_documents)
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:3000",  # Required by OpenRouter
    }
    
    # Build context grouped by document
    context_parts = []
    if context_documents:
        # Group chunks by document
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
            # Sort chunks by index within the document
            sorted_chunks = sorted(info["chunks"], key=lambda x: x.get("chunk_index", 0))
            combined_content = "\n[...]\n".join([c.get('content', '') for c in sorted_chunks])
            
            part = f"DOCUMENT: {title}\nURL: {info['url']}\nCONTENT:\n{combined_content}"
            context_parts.append(part)
            
    context_text = "\n\n" + "\n\n---\n\n".join(context_parts) if context_parts else ""
    
    # Build system prompt
    system_prompt = """You are a helpful AI support assistant for sayo.ai, an educational platform for teachers and students.

Your role is to provide accurate, comprehensive answers based ONLY on the provided tutorial documents .

Guidelines:
1. RESPONSE ACCURACY: Always base your answers on the provided context documents. If the documents contain a step-by-step guide, provide the complete sequence precisely.
2. SOURCE CITATION: Do NOT include document names or links within the body of your response or at the end of each sentence. Instead, provide all relevant sources at the very end of your response in a single, well-formatted sentence.
3. CITATION FORMAT: Use the following format for the citation sentence: "For more details, please refer to: [Document Title 1](URL1), [Document Title 2](URL2)."
4. RELEVANCE: Only cite documents that you actually used to answer the question. If a document is in the context but unrelated to the specific question, ignore it.
5. HONESTY: If the answer is NOT in the provided materials, say: "I don't have information about this in the Sayo documentation. Please contact Sayo support or check the latest tutorials."
6. FOCUS: Do not use outside knowledge. Do not make assumptions. DO NOT MAKE artificial websites or links.
7. FORMATTING: Use clear bullet points or numbered lists for instructions. Keep the tone professional yet helpful."""
    
    # Build messages
    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]
    
    # Add context to user message if available
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
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        logger.debug(f"Sending request to {OPENROUTER_URL} with model {CHAT_MODEL}")
        
        resp = requests.post(
            OPENROUTER_URL,
            json=payload,
            headers=headers,
            timeout=60
        )
        
        # Log response for debugging
        if resp.status_code != 200:
            logger.error(f"OpenRouter returned {resp.status_code}: {resp.text}")
        
        resp.raise_for_status()
        data = resp.json()
        
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"].strip()
        else:
            logger.error(f"Unexpected chat response: {data}")
            return "Sorry, I couldn't generate a response."
    
    except requests.exceptions.Timeout:
        logger.error("Chat request timeout")
        return "Sorry, the response took too long. Please try again."
    except Exception as e:
        logger.error(f"Failed to generate response: {e}")
        return f"Sorry, I encountered an error: {str(e)}"


def generate_demo_response(user_message: str, context_documents: List[Dict[str, Any]]) -> str:
    """Generate a demo response for testing without OpenRouter API key."""
    
    if not context_documents:
        if "hello" in user_message.lower() or "hi" in user_message.lower():
            return "Hello! I'm your AI teaching assistant. To get personalized responses based on your materials, please ingest some document first using: python ingest_notion_pdfs.py\n\nOnce documents are ingested, I can retrieve relevant content and provide better answers."
        elif "what" in user_message.lower():
            return "That's a great question! To give you an accurate answer based on your educational materials, I would need documents to be ingested first. Here's how to do it:\n\n1. Place your PDFs in backend/Notion_Export/\n2. Run: python ingest_notion_pdfs.py\n3. Then I can retrieve relevant information from your materials."
        else:
            return f"You asked: '{user_message}'\n\nTo provide a personalized response based on your educational materials, please configure your OpenRouter API key and ingest documents. See README.md for setup instructions."
    
    # With context documents
    doc_summary = ", ".join([doc.get('document_title', 'Unknown') for doc in context_documents[:2]])
    return f"Based on the retrieved content from {doc_summary}, I can see this relates to your educational materials. To provide a proper answer using OpenRouter's AI models, please configure your OPENROUTER_API_KEY in the .env file.\n\nThe documents have been successfully retrieved and are ready to be used once the API key is configured!"


# --- API Endpoints ---

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "RAG Chatbot API"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Chat endpoint with RAG context retrieval."""
    
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    logger.info(f"Chat request: {request.message[:100]}...")
    
    # Retrieve relevant documents
    logger.info(f"Retrieving documents for query...")
    documents = retrieve_relevant_documents(
        request.message,
        manual_type=request.manual_type
    )
    logger.info(f"Retrieved {len(documents)} documents")
    
    # Generate response with RAG context
    response_text = generate_rag_response(request.message, documents)
    
    # Format sources for response
    sources = []
    seen_sources = set()
    for doc in documents:
        title = doc.get("document_title", "Unknown")
        # Only list unique documents in the simplified sources list if title exists,
        # but the frontend might want specific page info
        source_key = f"{title}_{doc.get('page_number', 0)}"
        if source_key not in seen_sources:
            sources.append({
                "title": title,
                "type": doc.get("manual_type", "Unknown"),
                "page": doc.get("page_number"),
                "similarity": doc.get("similarity", 0)
            })
            seen_sources.add(source_key)
    
    return ChatResponse(response=response_text, sources=sources)


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    """Alias endpoint for frontend compatibility."""
    return chat(request)


# --- Startup/Shutdown ---

@app.on_event("startup")
async def startup_event():
    """Validate configuration on startup."""
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not set!")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set!")
    
    if not supabase:
        logger.error("Supabase client not initialized!")
    
    logger.info("Chatbot API started")
    logger.info(f"Chat model: {CHAT_MODEL}")
    logger.info(f"Embedding model: {EMBEDDING_MODEL}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
