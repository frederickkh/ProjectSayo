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
RAG_CONTEXT_LIMIT = int(os.getenv("RAG_CONTEXT_LIMIT", "3"))

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


def retrieve_relevant_documents(
    query: str,
    manual_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search Supabase for documents relevant to the query using vector similarity.
    
    Returns a list of documents ordered by similarity.
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
        # Use Supabase vector search (requires pgvector extension)
        # RPC call to search embeddings
        response = supabase.rpc(
            "search_documents",
            {
                "query_embedding": embedding,
                "similarity_threshold": 0.5,
                "match_count": RAG_CONTEXT_LIMIT,
                "manual_type_filter": manual_type
            }
        ).execute()
        
        if response.get("error"):
            logger.error(f"Vector search error: {response['error']}")
            return []
        
        return response.get("data", [])
    except Exception as e:
        logger.warning(f"Vector search failed, returning empty: {e}")
        # Fallback: return nothing if search fails
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
    
    # Build context from retrieved documents
    context_text = ""
    if context_documents:
        context_text = "\n\n---\n\n".join([
            f"Source: {doc.get('document_title', 'Unknown')}\n{doc.get('content', '')}"
            for doc in context_documents
        ])
    
    # Build system prompt
    system_prompt = """You are a helpful AI assistant for teachers using educational platforms. 
You have access to educational documents and materials. 

When answering questions:
1. Use the provided context documents to give accurate answers
2. If the answer is in the context, cite the source document
3. If the answer is not in the context, say so honestly
4. Be concise and helpful"""
    
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
    sources = [
        {
            "title": doc.get("document_title", "Unknown"),
            "type": doc.get("manual_type", "Unknown"),
            "similarity": doc.get("similarity", 0)
        }
        for doc in documents
    ]
    
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
