from sqlalchemy import text
from database.models import Base
from database.connection import engine   # use the engine directly

def init():
    with engine.connect() as conn:
        # 1. Drop the index explicitly
        conn.execute(text("DROP INDEX IF EXISTS ix_contacts_phone;"))

        # 2. Drop and recreate schema
        conn.execute(text("DROP SCHEMA public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        conn.commit()

    print("Dropped schema and index, recreated schema.")

    # 3. Recreate all tables
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")

if __name__ == "__main__":
    init()
