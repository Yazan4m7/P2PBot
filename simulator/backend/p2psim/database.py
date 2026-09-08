from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from .models import Base


class Database:
    def __init__(self, url: str):
        kwargs = {"future": True, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url:
                kwargs["poolclass"] = StaticPool
        self.engine = create_engine(url, **kwargs)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def drop_schema(self) -> None:
        Base.metadata.drop_all(self.engine)

    def session(self) -> Session:
        return Session(self.engine, expire_on_commit=False)
