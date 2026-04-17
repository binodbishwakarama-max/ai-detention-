"""
Alembic environment configuration.

Configures Alembic to use async SQLAlchemy and the application's
Base.metadata for auto-generating migrations.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.config import get_settings
from src.models import Base  # noqa: F401 — registers all models

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for auto-generating migrations
target_metadata = Base.metadata

# Override sqlalchemy.url from environment
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Generates SQL statements without connecting to the database.
    Used for generating migration scripts in CI/CD.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure context and run migrations synchronously."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in 'online' mode with async engine.

    Creates an async engine, connects, and runs migrations
    through the synchronous migration runner.
    """
    configuration = config.get_section(config.config_ini_section, {})
    
    # Ensure the engine uses asyncpg
    url = configuration.get("sqlalchemy.url", "")
    if "asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    run_async_migrations_sync()


def run_async_migrations_sync() -> None:
    """Sync wrapper for async migrations."""
    try:
        asyncio.run(run_async_migrations())
    except RuntimeError:
        # Already in an event loop
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
