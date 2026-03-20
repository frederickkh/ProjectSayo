# 🚀 Quick Start Guide - RAG Chatbot

## What Was Implemented

✅ **Backend RAG System** (`backend/chat_api.py`)
- FastAPI server with Supabase vector search
- OpenRouter integration for embeddings & chat
- RPC functions for efficient vector similarity search

✅ **Document Ingestion** (`backend/ingest_notion_pdfs.py`)
- Converts PDFs to text with OCR support
- Generates embeddings via OpenRouter
- Stores in Supabase with vector index

✅ **Frontend Integration** (`frontend/app/actions/chat.ts`)
- Updated to call backend RAG API
- Displays chat responses with source documents
- Supports filtering by teacher/student documents

✅ **Database Schema** (`backend/supabase_setup.sql`)
- Vector-enabled documents table
- Similarity search RPC function
- Chat history logging (optional)

✅ **Documentation & Setup**
- Comprehensive README.md
- Interactive setup wizard (setup.py)
- .env.example template

---

## Getting Started (5 Steps)

### Step 1: Get API Keys
- **OpenRouter**: https://openrouter.io (for embeddings & chat)
- **Supabase**: https://supabase.com (for vector storage)

### Step 2: Run Setup Wizard
```bash
python setup.py
```
This will:
- Check Python/Node.js versions
- Create `.env` files
- Install dependencies

### Step 3: Set Up Database
1. Go to Supabase dashboard → SQL Editor
2. Copy entire content from `backend/supabase_setup.sql`
3. Paste & run in SQL editor
4. Wait for all queries to complete

### Step 4: Ingest Documents
```bash
cd backend
python ingest_notion_pdfs.py
```

### Step 5: Start Services
**Terminal 1 - Backend:**
```bash
cd backend
python -m uvicorn chat_api:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

Visit: http://localhost:3000

---

## Architecture Overview

```
┌─────────────────────────────────────────┐
│        Frontend (Next.js)                │
│  Chat UI @ http://localhost:3000        │
└────────────────┬────────────────────────┘
                 │ HTTP POST
                 ↓
┌─────────────────────────────────────────┐
│    Backend (FastAPI)                    │
│  @ http://localhost:8000                │
│  - Receives chat messages               │
│  - Performs vector search               │
│  - Generates RAG responses              │
└────┬───────────────────────┬────────────┘
     │                       │
     ↓                       ↓
  OpenRouter            Supabase
  - Embeddings        - Vector DB
  - Chat Response     - Document Storage
```

---

## Key Files

| File | Purpose |
|------|---------|
| `backend/chat_api.py` | FastAPI RAG server |
| `backend/ingest_notion_pdfs.py` | PDF → Embeddings → Supabase |
| `backend/supabase_setup.sql` | Database schema & RPC functions |
| `frontend/app/actions/chat.ts` | Frontend API communication |
| `README.md` | Full documentation |
| `.env.example` | Configuration template |
| `setup.py` | Interactive setup wizard |

---

## Environment Variables

### Backend (`.env`)
```env
OPENROUTER_API_KEY=your_key_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_key_here
```

### Frontend (`.env.local`)
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Common Issues & Solutions

**"Can't connect to backend"**
- Is backend running? Check `http://localhost:8000/health`
- Is `NEXT_PUBLIC_API_URL` correct in `frontend/.env.local`?

**"Vector search not working"**
- Did you run `supabase_setup.sql` in Supabase?
- Check if documents were ingested: `SELECT COUNT(*) FROM documents;`

**"Embeddings failing"**
- Verify OpenRouter API key is correct
- Check API usage at https://openrouter.io

**"Documents not showing up"**
- Run: `python ingest_notion_pdfs.py --verbose`
- Check logs for errors
- Verify Notion export files exist

---

## Next Steps

1. **Customize the system**:
   - Change embedding model in `.env`
   - Adjust RAG context limit (3 docs default)
   - Modify system prompt in `chat_api.py`

2. **Add more documents**:
   - Put PDFs in `backend/Notion_Export/` (or set `NOTION_EXPORT_DIR`)
   - Run `python ingest_notion_pdfs.py` to ingest

3. **Deploy to production**:
   - Build frontend: `npm run build`
   - Deploy to Vercel/Netlify
   - Deploy backend to Heroku/Railway/AWS
   - Update `NEXT_PUBLIC_API_URL` to production backend URL

4. **Monitor & improve**:
   - Check query logs in Supabase
   - Track chat history (stored in `chat_history` table)
   - Optimize embedding model if needed
   - Fine-tune system prompt for better responses

---

## Support & Resources

- 📖 **Full Guide**: See `README.md`
- 🔗 **OpenRouter Docs**: https://openrouter.io/docs
- 🔗 **Supabase Docs**: https://supabase.com/docs
- 🔗 **FastAPI Docs**: https://fastapi.tiangolo.com
- 🔗 **Next.js Docs**: https://nextjs.org/docs

---

## Tips for Best Results

✅ Use `text-embedding-3-small` for cost-effective embeddings
✅ Retrieve 3-5 documents for RAG (good balance)
✅ Keep documents well-organized in Supabase
✅ Monitor OpenRouter spending limits
✅ Use teacher/student filtering for relevant results

---

**You're all set! 🎉 Start chatting at http://localhost:3000**
