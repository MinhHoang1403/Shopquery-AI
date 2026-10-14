"""Engine factories for privileged setup and read-only runtime access."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.core.config import get_settings


@lru_cache
def get_setup_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_setup_url, pool_pre_ping=True)


@lru_cache
def get_readonly_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_readonly_url, pool_pre_ping=True)
