"""Session factory and transactional context management for SQL persistence (Plane 3)."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_session_factory(
    engine: Engine,
    *,
    expire_on_commit: bool = False,
    autoflush: bool = True,
    **kwargs: Any,
) -> sessionmaker[Session]:
    """Create a configured sessionmaker bound to the provided engine.

    Args:
        engine: The SQLAlchemy Engine to bind sessions to.
        expire_on_commit: Whether committed objects expire immediately. Defaults to False
            so model attributes remain safely accessible outside session boundaries.
        autoflush: Whether pending changes are flushed before queries. Defaults to True.
        **kwargs: Additional sessionmaker options.

    Returns:
        Configured `sessionmaker[Session]`.
    """
    return sessionmaker(
        bind=engine,
        expire_on_commit=expire_on_commit,
        autoflush=autoflush,
        **kwargs,
    )


@contextmanager
def transactional_session(
    session_or_factory: sessionmaker[Session] | Session,
) -> Generator[Session, None, None]:
    """Provide a transactional boundary for database operations.

    If given a `sessionmaker`, instantiates a new session, begins a transaction,
    yields the session, commits upon successful exit, rolls back on any exception,
    and unconditionally closes the session.

    If given an active `Session`, participates in a transaction on that session,
    commits upon successful exit, rolls back on exception, but does not close an
    externally managed session.

    Args:
        session_or_factory: A `sessionmaker[Session]` or existing `Session` instance.

    Yields:
        An active `Session` inside a transactional boundary.
    """
    if isinstance(session_or_factory, Session):
        session = session_or_factory
        owns_session = False
    else:
        session = session_or_factory()
        owns_session = True

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()
