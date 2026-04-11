-- Supabase setup SQL for RAG system
-- Run these commands in your Supabase SQL editor

-- Enable pgvector extension (for embeddings)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create documents table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding vector(1536),
    document_title TEXT,
    source_url TEXT,
    manual_type TEXT,       -- 'teacher' or 'student'
    chunk_index INTEGER,    -- 0-based position of this chunk within the document
    page_number INTEGER,    -- PDF page number this chunk originated from
    chunk_total INTEGER,    -- Total number of chunks in this document
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for better search performance
CREATE INDEX IF NOT EXISTS documents_embedding_idx ON documents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS documents_manual_type_idx ON documents(manual_type);
CREATE INDEX IF NOT EXISTS documents_created_at_idx ON documents(created_at);
-- Index for fast neighbour-chunk lookups (used by context expansion)
CREATE INDEX IF NOT EXISTS documents_title_chunk_idx ON documents(document_title, chunk_index);

-- Create RPC function for vector similarity search
-- Returns chunk metadata (index, page, total) needed for context expansion
CREATE OR REPLACE FUNCTION search_documents(
    query_embedding vector(1536),
    similarity_threshold float DEFAULT 0.1,
    match_count INT DEFAULT 8,
    manual_type_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    document_title TEXT,
    source_url TEXT,
    manual_type TEXT,
    chunk_index INTEGER,
    page_number INTEGER,
    chunk_total INTEGER,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    WITH matched AS (
        -- Step 1: Find top-K chunks by cosine similarity (same as before)
        SELECT
            d.id,
            d.content,
            d.document_title,
            d.source_url,
            d.manual_type,
            d.chunk_index,
            d.page_number,
            d.chunk_total,
            (1 - (d.embedding <=> query_embedding)) AS similarity
        FROM documents d
        WHERE
            (1 - (d.embedding <=> query_embedding)) > similarity_threshold
            AND (manual_type_filter IS NULL OR d.manual_type = manual_type_filter)
        ORDER BY d.embedding <=> query_embedding
        LIMIT match_count
    ),
    -- Step 2: Collect all needed chunk indices (matched ± 1)
    needed_indices AS (
        SELECT DISTINCT
            m.document_title AS title,
            idx AS target_idx
        FROM matched m,
             LATERAL unnest(ARRAY[m.chunk_index - 1, m.chunk_index, m.chunk_index + 1]) AS idx
        WHERE idx >= 0
    ),
    -- Step 3: Fetch all needed chunks (matched + neighbors) in one pass
    expanded AS (
        SELECT DISTINCT ON (d.id)
            d.id,
            d.content,
            d.document_title,
            d.source_url,
            d.manual_type,
            d.chunk_index,
            d.page_number,
            d.chunk_total,
            COALESCE(m.similarity, 0.0) AS similarity
        FROM needed_indices ni
        JOIN documents d
            ON d.document_title = ni.title
            AND d.chunk_index = ni.target_idx
        LEFT JOIN matched m
            ON m.id = d.id
    )
    SELECT * FROM expanded
    ORDER BY expanded.document_title, expanded.chunk_index;
END;
$$ LANGUAGE plpgsql;

-- Create RPC function for inserting documents (for easier batch insertion)
CREATE OR REPLACE FUNCTION insert_documents(
    documents_data JSONB[]
)
RETURNS TABLE (
    id UUID,
    created_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    INSERT INTO documents (content, embedding, document_title, source_url, manual_type)
    SELECT
        (doc->>'content'),
        (doc->'embedding')::vector,
        (doc->>'document_title'),
        (doc->>'source_url'),
        (doc->>'manual_type')
    FROM (SELECT UNNEST(documents_data) as doc) t
    RETURNING documents.id, documents.created_at;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions (if needed based on your auth setup)
-- GRANT SELECT ON documents TO authenticated;
-- GRANT SELECT ON documents TO anon;

-- Create a view for recent documents (useful for monitoring)
CREATE OR REPLACE VIEW recent_documents AS
SELECT
    id,
    document_title,
    manual_type,
    created_at,
    LENGTH(content) as content_length
FROM documents
ORDER BY created_at DESC
LIMIT 100;

-- Optional: Create a table for logging chat sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Optional: Create a table for logging chat interactions
CREATE TABLE IF NOT EXISTS chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_message TEXT NOT NULL,
    bot_response TEXT NOT NULL,
    sources JSONB,
    manual_type_filter TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chat_history_created_at_idx ON chat_history(created_at);
CREATE INDEX IF NOT EXISTS chat_history_session_id_idx ON chat_history(session_id);

-- Optional: Create a function to log chat interactions
CREATE OR REPLACE FUNCTION log_chat_interaction(
    p_session_id UUID,
    p_user_message TEXT,
    p_bot_response TEXT,
    p_sources JSONB,
    p_manual_type_filter TEXT DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    interaction_id UUID;
BEGIN
    INSERT INTO chat_history (session_id, user_message, bot_response, sources, manual_type_filter)
    VALUES (p_session_id, p_user_message, p_bot_response, p_sources, p_manual_type_filter)
    RETURNING id INTO interaction_id;
    
    -- Update session updated_at timestamp
    UPDATE chat_sessions SET updated_at = NOW() WHERE id = p_session_id;
    
    RETURN interaction_id;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- MIGRATION: Run this block if the database already exists
-- ============================================================
-- Add chunk tracking columns (safe to run multiple times)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunk_index INTEGER;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_number INTEGER;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunk_total INTEGER;

-- Add index for context expansion neighbour lookups
CREATE INDEX IF NOT EXISTS documents_title_chunk_idx ON documents(document_title, chunk_index);

-- Add session support to existing DB
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS chat_history_session_id_idx ON chat_history(session_id);

-- After running the above, also re-run the CREATE OR REPLACE FUNCTION
-- search_documents(...) and log_chat_interaction(...) blocks above to update the RPC return signature.
-- ============================================================
