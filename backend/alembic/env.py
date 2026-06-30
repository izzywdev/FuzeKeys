from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import our app
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database import Base
from app.models import user, identity, account, signup_script, api_key

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    """Get a *synchronous* (psycopg2) database URL for Alembic's own engine.

    Alembic uses a synchronous SQLAlchemy engine.  The runtime app uses asyncpg
    (DATABASE_URL_ASYNC).  This function normalises whatever is in DATABASE_URL
    to the plain postgresql:// scheme so Alembic can connect with psycopg2.
    """
    # Prefer DATABASE_URL_SYNC if set explicitly; fall back to DATABASE_URL.
    url = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL")
    if url:
        # Strip the asyncpg driver variant so Alembic uses psycopg2.
        url = url.replace("postgresql+asyncpg://", "postgresql://")
        return url

    # Last resort: fall back to alembic.ini hard-coded value.
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

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