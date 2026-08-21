# migrate.py
from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE message ADD COLUMN msg_type VARCHAR(20) DEFAULT 'text';"))
            print("Added msg_type column.")
        except Exception as e:
            print(f"msg_type column might already exist: {e}")

        try:
            conn.execute(text("ALTER TABLE message ADD COLUMN file_path VARCHAR(255);"))
            print("Added file_path column.")
        except Exception as e:
            print(f"file_path column might already exist: {e}")

        conn.commit()
    print("Migration completed successfully!")
