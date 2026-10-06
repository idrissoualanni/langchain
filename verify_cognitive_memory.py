import os
import json
import logging
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from app.config import DATABASE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VerifyCognitiveMemory")

def verify():
    if not DATABASE_URL:
        print("DATABASE_URL not found in environment")
        return

    engine = create_engine(DATABASE_URL)
    
    # 1. Verify Tables Existence
    tables_to_check = ["user_cognitive_memories", "user_learning_map", "concept_dependencies"]
    print("\n--- Table Existence Check ---")
    with engine.connect() as conn:
        for table in tables_to_check:
            res = conn.execute(text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table}')")).scalar()
            print(f"Table {table}: {'EXISTS' if res else 'MISSING'}")

    # 2. Verify HNSW Index on user_cognitive_memories
    print("\n--- Index Check ---")
    with engine.connect() as conn:
        # Check for hnsw index on embedding column
        query = text("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'user_cognitive_memories' AND indexdef LIKE '%USING hnsw%'
        """)
        index = conn.execute(query).scalar()
        print(f"HNSW Index on user_cognitive_memories: {'FOUND' if index else 'MISSING'}")

    # 3. Write-Read-Verify Cycle
    test_user_id = "test_user_cognitive_123"
    test_content = "The user loves learning quantum physics using 3D visualizations."
    test_concept = "quantum_entanglement"
    test_level = 0.75
    
    print("\n--- Write-Read-Verify Cycle ---")
    try:
        with engine.begin() as conn:
            # Insert Memory
            # Note: We use a dummy embedding for direct SQL verification since we don't have the embedding provider here
            # In a real scenario, we'd use the provider, but for DB persistence proof, any vector works.
            dummy_embedding = "[0.1] * 1536" # This is conceptual, need actual vector format
            # Let's use a small valid vector for pgvector if dim is small, or just a list of floats.
            # Actually, since we are testing persistence, we can just insert a valid vector.
            # Let's assume 1536 dim for OpenAI/CF.
            vector = [0.1] * 1536
            vector_str = f"[{','.join(map(str, vector))}]"
            
            conn.execute(text("""
                INSERT INTO user_cognitive_memories (user_id, content, embedding, memory_type, updated_at)
                VALUES (:u, :c, :e, 'fact', :n)
            """), {"u": test_user_id, "c": test_content, "e": vector_str, "n": datetime.now(timezone.utc)})
            print("Inserted test memory.")

            # Insert Learning Map
            conn.execute(text("""
                INSERT INTO user_learning_map (user_id, concept_slug, mastery_level, updated_at)
                VALUES (:u, :s, :l, :n)
                ON CONFLICT (user_id, concept_slug) DO UPDATE SET mastery_level = EXCLUDED.mastery_level
            """), {"u": test_user_id, "s": test_concept, "l": test_level, "n": datetime.now(timezone.utc)})
            print("Inserted learning map concept.")

        # Verify Read
        with engine.connect() as conn:
            mem_res = conn.execute(text("SELECT content FROM user_cognitive_memories WHERE user_id = :u AND content = :c"), 
                                    {"u": test_user_id, "c": test_content}).scalar()
            print(f"Read Memory: {'SUCCESS' if mem_res == test_content else 'FAILED'}")

            map_res = conn.execute(text("SELECT mastery_level FROM user_learning_map WHERE user_id = :u AND concept_slug = :s"), 
                                    {"u": test_user_id, "s": test_concept}).scalar()
            print(f"Read Learning Map: {'SUCCESS' if map_res == test_level else 'FAILED'}")

    except Exception as e:
        print(f"Error during Write-Read-Verify: {e}")
    finally:
        # Cleanup
        try:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM user_cognitive_memories WHERE user_id = :u"), {"u": test_user_id})
                conn.execute(text("DELETE FROM user_learning_map WHERE user_id = :u"), {"u": test_user_id})
                print("Cleaned up test data.")
        except Exception as e:
            print(f"Cleanup error: {e}")

if __name__ == "__main__":
    verify()
