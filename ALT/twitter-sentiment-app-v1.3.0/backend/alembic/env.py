# C:\Users\mai-s\Desktop\TradersEcho\twitter-sentiment-app-v1.3.0\backend\alembic\env.py

from __future__ import with_statement
from alembic import context
from sqlalchemy import engine_from_config, pool
from logging.config import fileConfig
import os, sys
from dotenv import load_dotenv

# --- Load .env first so Alembic sees DB_URL ---
load_dotenv()

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name:
    fileConfig(config.config_file_name)

# Set sqlalchemy.url from environment (fallback to a sane default).
db_url = os.getenv("DB_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/sentiment")
config.set_main_option("sqlalchemy.url", db_url)

# Add backend folder to path and import Base
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from db import Base  # noqa: E402

target_metadata = Base.metadata

def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
