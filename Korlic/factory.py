from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .bot import KorlicBot
from .models import OrderBookSnapshot
from .storage import KorlicStorage


@dataclass
class EmptyGammaClient:
    async def get_active_markets(self) -> list:
        return []


@dataclass
class EmptyClobClient:
    async def get_server_time_ms(self) -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    async def get_orderbook(self, token_id: str) -> OrderBookSnapshot:
        return OrderBookSnapshot(token_id=token_id, bids=(), asks=(), ts_ms=await self.get_server_time_ms())


@dataclass
class EmptyWsClient:
    async def subscribe(self, asset_ids: list[str]) -> None:
        return None

    async def is_healthy(self) -> bool:
        return True


def build_bot(db_path: str) -> KorlicBot:
    storage = KorlicStorage(db_path)
    return KorlicBot(gamma=EmptyGammaClient(), clob=EmptyClobClient(), ws=EmptyWsClient(), storage=storage)
