import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

POSTGRES_URL = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")

if not POSTGRES_URL:
    raise RuntimeError("POSTGRES_URL environment variable is required.")

engine = create_engine(
    POSTGRES_URL,
    pool_pre_ping=True,
    pool_size=int(os.getenv("POSTGRES_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("POSTGRES_MAX_OVERFLOW", "10")),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_metadata_schema() -> None:
    """
    Keep old local development tables compatible with the current metadata-only
    models. SQLAlchemy create_all does not alter existing PostgreSQL tables.
    """
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as connection:
        if "username" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(255)"))
        if "hashed_password" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN hashed_password VARCHAR"))

        if "name" in columns:
            connection.execute(
                text(
                    """
                    UPDATE users
                    SET username = COALESCE(username, name, split_part(email, '@', 1))
                    WHERE username IS NULL
                    """
                )
            )
            connection.execute(text("ALTER TABLE users ALTER COLUMN name DROP NOT NULL"))
        else:
            connection.execute(
                text(
                    """
                    UPDATE users
                    SET username = COALESCE(username, split_part(email, '@', 1))
                    WHERE username IS NULL
                    """
                )
            )

        if "password" in columns:
            connection.execute(
                text(
                    """
                    UPDATE users
                    SET hashed_password = COALESCE(hashed_password, password)
                    WHERE hashed_password IS NULL
                    """
                )
            )
            connection.execute(text("ALTER TABLE users ALTER COLUMN password DROP NOT NULL"))

        connection.execute(text("ALTER TABLE users ALTER COLUMN username SET NOT NULL"))
        connection.execute(text("ALTER TABLE users ALTER COLUMN hashed_password SET NOT NULL"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
