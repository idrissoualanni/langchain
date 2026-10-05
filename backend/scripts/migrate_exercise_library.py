import os
from sqlalchemy import text
from app.infrastructure.database.connections import get_conn

def migrate():
    print("Starting migration: create_exercise_library...")
    conn = get_conn()
    
    # Table create
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exercise_library (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            subject_id TEXT NOT NULL,
            topic_slug TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            content TEXT NOT NULL,
            success_rate FLOAT DEFAULT 0.0,
            is_validated BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Index for searching
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_exercise_library_subject_topic
        ON exercise_library(subject_id, topic_slug);
    """)
    
    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate()
