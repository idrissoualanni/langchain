import os
from sqlalchemy import create_engine, text
from app.config import DATABASE_URL

def verify():
    print(f"Connecting to: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'Hidden'}")
    engine = create_engine(DATABASE_URL)
    
    tables = ["user_cognitive_memories", "user_learning_map", "concept_dependencies"]
    
    try:
        with engine.connect() as conn:
            print("\n--- Table Existence ---")
            for table in tables:
                res = conn.execute(text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table}')")).scalar()
                print(f"{table}: {'EXISTS' if res else 'MISSING'}")
            
            print("\n--- HNSW Index Check ---")
            query = text("SELECT indexname FROM pg_indexes WHERE tablename = 'user_cognitive_memories' AND indexdef LIKE '%USING hnsw%'")
            index = conn.execute(query).scalar()
            print(f"HNSW Index: {'FOUND' if index else 'MISSING'}")
            
            print("\n--- Data Sample ---")
            # Just try to count rows to see if it's empty or populated
            for table in tables:
                count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
                print(f"{table} count: {count}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify()
