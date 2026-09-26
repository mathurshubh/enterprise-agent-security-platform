"""Declarative base and shared metadata for SQLAlchemy persistence models (Plane 3)."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all relational persistence models."""
    pass
