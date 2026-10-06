-- Migration: Setup Vector Infrastructure for Cognitive Memory
-- Description: Activates pgvector, creates the cognitive memories table, and adds an HNSW index.

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create user_cognitive_memories table
-- We use a vector(1536) as it is the default for OpenAI and many common embedding models.
-- Metadata is stored as JSONB for flexibility.
CREATE TABLE IF NOT EXISTS user_cognitive_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB DEFAULT '{}'::jsonb,
    memory_type TEXT, -- e.g., 'fact', 'preference', 'experience'
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. Add constraints and indices
CREATE INDEX IF NOT EXISTS idx_cognitive_memories_user_id ON user_cognitive_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_cognitive_memories_type ON user_cognitive_memories(memory_type);

-- 4. Create HNSW index for fast cosine similarity search
-- Using cosine distance (<=> operator) for embeddings.
CREATE INDEX IF NOT EXISTS idx_cognitive_memories_embedding_hnsw
ON user_cognitive_memories
USING hnsw (embedding vector_cosine_ops);

-- Comment on the table
COMMENT ON TABLE user_cognitive_memories IS 'Stores vector embeddings of user cognitive memories for semantic retrieval.';
