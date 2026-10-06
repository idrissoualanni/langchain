import os
from sqlalchemy import create_engine, text
from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL)

migrations = [
    'CREATE EXTENSION IF NOT EXISTS vector;',
    '''CREATE TABLE IF NOT EXISTS user_cognitive_memories (
        id BIGSERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        content TEXT NOT NULL,
        embedding vector(1536), 
        metadata JSONB,
        memory_type TEXT,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );''',
    'CREATE INDEX IF NOT EXISTS idx_cognitive_memories_embedding ON user_cognitive_memories USING hnsw (embedding vector_cosine_ops);',
    '''CREATE TABLE IF NOT EXISTS user_learning_map (
        user_id TEXT NOT NULL,
        concept_slug TEXT NOT NULL,
        mastery_level FLOAT NOT NULL DEFAULT 0.0,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, concept_slug)
    );''',
    '''CREATE TABLE IF NOT EXISTS concept_dependencies (
        prerequisite_slug TEXT NOT NULL,
        concept_slug TEXT NOT NULL,
        PRIMARY KEY (prerequisite_slug, concept_slug)
    );'''
]

try:
    with engine.begin() as conn:
        for sql in migrations:
            conn.execute(text(sql))
    print('SUCCESS: All migrations applied to Neon.')
except Exception as e:
    print(f'ERROR: Migration failed: {e}')
