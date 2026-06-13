from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import aiosqlite


@dataclasses.dataclass(slots=True)
class Table(ABC):
    NAME: ClassVar[str]
    db_conn: aiosqlite.Connection
    ignore_history: bool = False

    def __init_subclass__(cls, name: str | None = None) -> None:
        if name:
            cls.NAME = name

    @abstractmethod
    async def create(self) -> None: ...

    async def exists(self) -> bool:
        query = "SELECT 1 FROM sqlite_master WHERE type='table' AND name= ? LIMIT 1;"
        cursor = await self.db_conn.execute(query, (self.NAME,))
        return await cursor.fetchone() is not None
