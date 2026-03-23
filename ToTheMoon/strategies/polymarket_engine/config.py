from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class StrategyConfig:
    incoherence_threshold: float = 0.08
    tail_threshold: float = 0.92
    min_time_to_resolution_seconds: int = 3600
    max_spread: float = 0.10


@dataclass(frozen=True)
class RiskConfig:
    max_position_per_market: float = 100.0
    max_global_exposure: float = 1000.0
    max_open_positions: int = 10


@dataclass(frozen=True)
class StorageConfig:
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "data")
    catalog_dir: Path = Path("catalog")
    history_dir: Path = Path("historical")
    execution_dir: Path = Path("execution")
    reports_dir: Path = Path("reports")

    def resolve(self, *parts: str) -> Path:
        return self.base_dir.joinpath(*parts)


@dataclass(frozen=True)
class EngineConfig:
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    clob_base_url: str = "https://clob.polymarket.com"
    history_path: str = "/prices-history"
    ws_stale_after_seconds: int = 30
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
