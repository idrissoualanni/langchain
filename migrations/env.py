from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Import the application config to get DATABASE_URL
from backend.app.config import DATABASE_URL

# add your model's MetaData object here
# for 'autogenerate' support
# Since the project uses raw SQL in schema.py rather than SQLAlchemy models,
# we leave target_metadata as None. Baselines will be created manually
# or via the current database state.
target_metadata = None

# This is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    # Override the sqlalchemy.url from the ini file with the one from config.py
    url = DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Override the sqlalchemy.url from the ini file with the one from config.py
    # We use the URL from config.py directly to ensure environment consistency.
    from sqlalchemy import create_engine

    # Ensure we use the psycopg driver for PostgreSQL as per the project's pattern
    url = DATABASE_URL
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = url.replace("postgresql://", "postgresql+psycopg://").replace("postgres://", "postgresql+psycopg://")

    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
