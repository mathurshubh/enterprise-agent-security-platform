"""Database engine factory and configuration for SQL persistence (Plane 3)."""

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.pool import NullPool, StaticPool


def create_sql_engine(
    database_url: str,
    *,
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_recycle: int = 3600,
    pool_pre_ping: bool = True,
    **kwargs: Any,
) -> Engine:
    """Create a configured SQLAlchemy Engine.

    Configures SQLite with `PRAGMA foreign_keys=ON;` and thread safety options.
    Configures client-server databases (e.g. PostgreSQL) with connection pooling and
    pre-ping liveness checks.

    Args:
        database_url: Database connection URL.
        echo: Whether to log generated SQL statements.
        pool_size: Number of connections to keep persistently in the pool.
        max_overflow: Maximum overflow connections above pool_size.
        pool_recycle: Seconds after which connections are recycled.
        pool_pre_ping: Whether to emit a liveness ping on checkout.
        **kwargs: Additional engine kwargs passed to `create_engine`.

    Returns:
        Configured SQLAlchemy `Engine` instance.
    """
    is_sqlite = database_url.startswith("sqlite")
    is_memory_sqlite = (
        database_url == "sqlite://"
        or database_url == "sqlite:///:memory:"
        or "mode=memory" in database_url
    )

    engine_kwargs: dict[str, Any] = {
        "echo": echo,
        **kwargs,
    }

    if is_sqlite:
        connect_args = dict(engine_kwargs.get("connect_args", {}))
        connect_args.setdefault("check_same_thread", False)
        engine_kwargs["connect_args"] = connect_args

        if is_memory_sqlite:
            # StaticPool ensures in-memory SQLite persists across multiple connections/sessions
            engine_kwargs.setdefault("poolclass", StaticPool)
    else:
        # PostgreSQL / other client-server RDBMS
        if engine_kwargs.get("poolclass") != NullPool:
            engine_kwargs.setdefault("pool_size", pool_size)
            engine_kwargs.setdefault("max_overflow", max_overflow)
        engine_kwargs.setdefault("pool_recycle", pool_recycle)
        engine_kwargs.setdefault("pool_pre_ping", pool_pre_ping)

    engine = create_engine(database_url, **engine_kwargs)

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    return engine


def dispose_sql_engine(engine: Engine) -> None:
    """Dispose of all connections checked out or pooled by the given engine."""
    engine.dispose()
