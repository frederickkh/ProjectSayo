# RAG Chatbot System - Setup & Usage Guide

## Overview

This project implements a Retrieval-Augmented Generation (RAG) system for an AI chatbot:
- **Backend**: Python FastAPI server with Supabase vector search
- **Frontend**: Next.js 14+ chat UI with Markdown/Code highlighting
- **APIs**: OpenRouter (for embeddings & chat), Supabase (for vector storage)
- **Features**: Semantic search with context expansion (neighboring chunks), source citations with clickable links, and teacher/student document filtering.

## System Architecture

```
Frontend (Next.js)
    ↓
FastAPI Backend (chat_api.py)
    ↓
OpenRouter API (embeddings + chat)
Supabase Vector DB (document storage)
Neighboring Context Expansion (Logic)
```

## Prerequisites

1. **Supabase Account**: Create one at https://supabase.com
2. **OpenRouter Account**: Create one at https://openrouter.io
3. **Python 3.10+**: For backend
4. **Node.js 18+**: For frontend

## Backend Setup

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

Create `backend/.env`:

```env
OPENROUTER_API_KEY=your_key_from_https://openrouter.io
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
EMBEDDING_MODEL=openai/text-embedding-3-small
CHAT_MODEL=openrouter/auto
RAG_CONTEXT_LIMIT=8
NOTION_EXPORT_DIR=./backend/Notion_Export
```

### 3. Set Up Supabase

1. Go to your Supabase project dashboard
2. Open SQL Editor
3. Copy the entire content of `backend/supabase_setup.sql`
4. Paste it in the SQL editor and run it
5. Wait for all queries to complete

**What this sets up:**
- `documents` table with vector embeddings
- Vector search indexes (pgvector)
- `search_documents()` RPC function for similarity search
- `chat_history` table (optional, for logging)

### 4. Ingest Documents

```bash
cd backend
python ingest_notion_pdfs.py
```

**Options:**
```bash
python ingest_notion_pdfs.py --dry-run      # Preview without saving
python ingest_notion_pdfs.py --verbose      # Detailed logging
python ingest_notion_pdfs.py --max-files 5  # Process only the first 5 files
python ingest_notion_pdfs.py --help         # Show all options
```

This script will:
- Extract text from all PDF files in `NOTION_EXPORT_DIR`
- Generate embeddings using OpenRouter
- Store documents in Supabase with vector embeddings

### 5. Start Backend Server

```bash
cd backend
python -m uvicorn chat_api:app --reload --host 0.0.0.0 --port 8000
```

The server will start at `http://localhost:8000`

**Available endpoints:**
- `GET /health` - Health check
- `POST /chat` - Send chat message with RAG context
- `POST /api/chat` - Alias endpoint

## Frontend Setup

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Set Up Environment Variables

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**For production**, change to your deployed backend URL:
```env
NEXT_PUBLIC_API_URL=https://your-backend-domain.com
```

### 3. Start Development Server

```bash
cd frontend
npm run dev
```

Visit `http://localhost:3000` in your browser

## API Documentation

### Chat Endpoint

**Request:**
```bash
POST http://localhost:8000/chat
Content-Type: application/json

{
    "message": "What is active learning?",
    "manual_type": "teacher"  // Optional: "teacher" or "student"
}
```

**Response:**
```json
{
    "response": "Active learning is a pedagogical approach... According to the [Grading Guide](https://notion.so/...), you should...",
    "sources": [
        {
            "title": "AI_Reading_Guide.pdf",
            "type": "teacher",
            "page": 4,
            "similarity": 0.87
        }
    ]
}
```

## Troubleshooting

### "OPENROUTER_API_KEY not set"
- Check that `.env` file exists in the `backend/` directory
- Verify the key is correct at https://openrouter.io/keys
- Restart the backend server after changing `.env`

### "Supabase client not initialized"
- Check `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are correct
- Verify they're from the right Supabase project
- Check that SQL setup script ran successfully

### "Vector search failed"
- Ensure pgvector extension is enabled in Supabase
- Check that documents were ingested (query `select count(*) from documents;`)
- Verify embeddings column has data (query `select count(*) from documents where embedding is not null;`)

### Frontend can't connect to backend
- Ensure backend is running (`http://localhost:8000/health` should return `{"status": "ok"}`)
- Check `NEXT_PUBLIC_API_URL` is correct in `.env.local`
- For Cross-Origin issues: backend already has CORS enabled for all origins

### Slow responses
- Check OpenRouter rate limits at https://openrouter.io
- Verify Supabase vector index is created
- Check logs: `python -m uvicorn chat_api:app --log-level debug`

## Development Tips

### Testing Backend Locally

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}'
```

### Debug Logging

```bash
# Backend with debug logging
python -m uvicorn chat_api:app --log-level debug

# Ingest script with verbose output
python ingest_notion_pdfs.py --verbose
```

### Monitoring Ingestion

Check what was ingested:
```sql
SELECT COUNT(*) FROM documents;
SELECT document_title, COUNT(*) as chunks FROM documents GROUP BY document_title;
SELECT * FROM documents WHERE embedding IS NOT NULL LIMIT 5;
```

### Tuning Search Results

1. **RAG Context Limit**: Adjust `RAG_CONTEXT_LIMIT` in `.env`.
   - Higher values (default 8) provide more context but increase token usage.
2. **Similarity Threshold**: Currently hardcoded to 0.1 in `chat_api.py`.
   - Increase this (e.g., to 0.2-0.3) to require higher relevancy.
3. **Context Expansion**: The system automatically retrieves chunks immediately before and after the most relevant hits. This ensures the LLM sees the complete context of a procedure or explanation that might span across chunks.

## Production Deployment

### Backend (FastAPI)
- Use Gunicorn: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker chat_api:app`
- Deploy to: Heroku, Railway, Render, AWS Lambda, etc.

### Frontend (Next.js)
- Build: `npm run build`
- Deploy to: Vercel, Netlify, AWS Amplify, etc.

### Environment Variables
- Never commit `.env` files
- Use your platform's secrets manager
- Update `NEXT_PUBLIC_API_URL` to production backend URL

## Model Information

### Embedding Models (via OpenRouter)
- `openai/text-embedding-3-small` (recommended, economical)
- `openai/text-embedding-3-large` (more accurate, more expensive)

### Chat Models (via OpenRouter)
- `openrouter/auto` (cheapest available model)
- `openai/gpt-4-turbo` (more powerful)
- `anthropic/claude-3-sonnet` (good balance)

See https://openrouter.io/docs/models for full list.

## Cost Considerations

**OpenRouter Pricing:**
- Embeddings: ~$0.02 per million tokens
- Chat: Varies by model (auto is cheapest)

**Estimate for small deployment:**
- 1000 documents × average 500 tokens = 500K tokens
- Embedding cost: ~$0.01
- Chat requests: ~$0.01 per message with auto model

Storage in Supabase free tier: 500MB shared storage (sufficient for most cases)

## Security Notes

- **Never** commit `.env` files with real keys
- Keep `SUPABASE_SERVICE_ROLE_KEY` secret (backend only)
- Use Row-Level Security (RLS) in Supabase for production
- Consider rate limiting on frontend
- OpenRouter keys should have reasonable spending limits

## Support

For issues:
1. Check the Troubleshooting section above
2. Review logs in both frontend and backend
3. Test each component independently
4. Check OpenRouter status: https://openrouter.io/status
5. Check Supabase status: https://status.supabase.com
