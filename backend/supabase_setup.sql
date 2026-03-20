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
    manual_type TEXT,  -- 'teacher' or 'student'
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for better search performance
CREATE INDEX IF NOT EXISTS documents_embedding_idx ON documents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS documents_manual_type_idx ON documents(manual_type);
CREATE INDEX IF NOT EXISTS documents_created_at_idx ON documents(created_at);

-- Create RPC function for vector similarity search
CREATE OR REPLACE FUNCTION search_documents(
    query_embedding vector(1536),
    similarity_threshold float DEFAULT 0.5,
    match_count INT DEFAULT 3,
    manual_type_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    document_title TEXT,
    source_url TEXT,
    manual_type TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        documents.id,
        documents.content,
        documents.document_title,
        documents.source_url,
        documents.manual_type,
        (1 - (documents.embedding <=> query_embedding)) as similarity
    FROM documents
    WHERE
        (1 - (documents.embedding <=> query_embedding)) > similarity_threshold
        AND (manual_type_filter IS NULL OR documents.manual_type = manual_type_filter)
    ORDER BY documents.embedding <=> query_embedding
    LIMIT match_count;
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

-- Optional: Create a table for logging chat interactions
CREATE TABLE IF NOT EXISTS chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_message TEXT NOT NULL,
    bot_response TEXT NOT NULL,
    sources JSONB,
    manual_type_filter TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chat_history_created_at_idx ON chat_history(created_at);

-- Optional: Create a function to log chat interactions
CREATE OR REPLACE FUNCTION log_chat_interaction(
    user_message TEXT,
    bot_response TEXT,
    sources JSONB,
    manual_type_filter TEXT DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    interaction_id UUID;
BEGIN
    INSERT INTO chat_history (user_message, bot_response, sources, manual_type_filter)
    VALUES (user_message, bot_response, sources, manual_type_filter)
    RETURNING id INTO interaction_id;
    RETURN interaction_id;
END;
$$ LANGUAGE plpgsql;
