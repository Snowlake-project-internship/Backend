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
    table_names = inspector.get_table_names()
    if "users" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO organizations (id, name, created_at)
                VALUES (1, 'Default Organization', NOW())
                ON CONFLICT (id) DO NOTHING
                """
            )
        )
        if "username" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(255)"))
        if "hashed_password" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN hashed_password VARCHAR"))
        if "organization_id" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL"))
        if "role" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(50) DEFAULT 'user'"))

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
        connection.execute(text("UPDATE users SET organization_id = COALESCE(organization_id, 1)"))
        connection.execute(text("UPDATE users SET role = COALESCE(role, 'user')"))
        connection.execute(text("ALTER TABLE users ALTER COLUMN role SET NOT NULL"))

        compatibility_columns = {
            "execution_logs": {
                "organization_id": "INTEGER REFERENCES organizations(id) ON DELETE SET NULL",
                "service_name": "VARCHAR(255)",
            },
            "error_logs": {
                "organization_id": "INTEGER REFERENCES organizations(id) ON DELETE SET NULL",
                "service_name": "VARCHAR(255)",
                "exception_type": "VARCHAR(255)",
                "function_name": "VARCHAR(255)",
            },
            "audit_logs": {
                "organization_id": "INTEGER REFERENCES organizations(id) ON DELETE SET NULL",
            },
        }
        for table_name, new_columns in compatibility_columns.items():
            if table_name not in table_names:
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in new_columns.items():
                if column_name not in existing:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))

        if "execution_logs" in table_names:
            connection.execute(
                text(
                    """
                    UPDATE execution_logs AS log
                    SET organization_id = users.organization_id
                    FROM users
                    WHERE log.organization_id IS NULL
                      AND log.user_id = users.id
                    """
                )
            )
        if "error_logs" in table_names:
            connection.execute(
                text(
                    """
                    UPDATE error_logs AS log
                    SET organization_id = users.organization_id
                    FROM users
                    WHERE log.organization_id IS NULL
                      AND log.user_id = users.id
                    """
                )
            )
        if "audit_logs" in table_names:
            connection.execute(
                text(
                    """
                    UPDATE audit_logs AS log
                    SET organization_id = users.organization_id
                    FROM users
                    WHERE log.organization_id IS NULL
                      AND log.user_id = users.id
                    """
                )
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
