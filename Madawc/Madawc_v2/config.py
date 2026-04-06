"""Constantes y configuración por entorno para ejecutar MADAWC v2."""

from __future__ import annotations

import os

DEFAULT_GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
DEFAULT_CLOB_HOST = "https://clob.polymarket.com"
DEFAULT_GAMMA_MIN_INTERVAL_SECONDS = 0.25
DEFAULT_CLOB_MIN_INTERVAL_SECONDS = 0.05
DEFAULT_GAMMA_PAGE_LIMIT = 100
DEFAULT_GAMMA_MAX_PAGES = 0
DEFAULT_GAMMA_SEED_EVENT_SLUG = "btc-updown-5m-1774854300"
DEFAULT_GAMMA_FAMILY_PREFIX = "btc-updown-5m-"
DEFAULT_MARKET_NEAR_EXPIRY_SECONDS = 900
DEFAULT_LOOP_INTERVAL_SECONDS = 240.0

DEFAULT_SIGNAL_ENTRY_PRICE = 0.05
DEFAULT_SIGNAL_ENTRY_SECONDS = 600
DEFAULT_SIGNAL_MIN_DEPTH = 0.0
DEFAULT_SIGNAL_MIN_SIZE = 1.0
DEFAULT_SIGNAL_MAX_STAKE = 1.0
DEFAULT_MAX_TRADES_PER_MARKET = 2
DEFAULT_EXIT_AT_FLAT_ENABLED = False
DEFAULT_EXIT_AT_FLAT = 0.0
DEFAULT_RESET_DB_ON_START = False
DEFAULT_CYCLE_STEP_SLEEP_SECONDS = 0.0
DEFAULT_ONLY_TRADE_THIS_MARKETS = ("Up or Down",)
DEFAULT_SKIPPED_MARKET_PREFIXES = (
    "Bitcoin above",
    "Counter-Strike",
    "Ethereum above",
    "Game 2:",
    "Game Handicap: SN (-1.5) vs CCG Esports (+1.5)",
    "Games Total: O/U 2.5",
    "HYPE Up or Down",
    "Hyperliquid Up or Down",
    "LoL: Supernova vs CCG Esports (BO3) - North American Challengers League Regular Season",
    "LoL: Supernova vs CCG Esports - Game 2 Winner",
    "Map x: Odd/Even",
    "Map Handicap:",
    "Valorant: Akave Esports Black vs MYVRA GC (BO3) - VCT Game Changers Latin America North Playoffs",
    "Valorant: Akave Esports Black vs MYVRA GC - Map 1 Winner",
    "Valorant: Akave Esports Black vs MYVRA GC - Map 2 Winner",
    "Valorant: KRÜ Blaze vs Olimpo Gold (BO3) - VCT Game Changers Latin America South Playoffs",
    "Valorant: KRÜ Blaze vs Olimpo Gold - Map 2 Winner",
    "Will Bitcoin dip",
    "Will Bitcoin reach",
    "Will Ethereum dip",
    "Will Ethereum reach",
    "Will Solana dip",
    "Will Solana reach",
    "Will XRP dip",
    "Will XRP reach",
)

# Configuración final: defaults + override por variables de entorno.
MADAWC_GAMMA_BASE_URL = os.getenv("MADAWC_GAMMA_BASE_URL", DEFAULT_GAMMA_BASE_URL)
MADAWC_CLOB_HOST = os.getenv("MADAWC_CLOB_HOST", DEFAULT_CLOB_HOST)
MADAWC_GAMMA_MIN_INTERVAL_SECONDS = float(
    os.getenv("MADAWC_GAMMA_MIN_INTERVAL_SECONDS", str(DEFAULT_GAMMA_MIN_INTERVAL_SECONDS))
)
MADAWC_CLOB_MIN_INTERVAL_SECONDS = float(
    os.getenv("MADAWC_CLOB_MIN_INTERVAL_SECONDS", str(DEFAULT_CLOB_MIN_INTERVAL_SECONDS))
)
MADAWC_GAMMA_PAGE_LIMIT = int(os.getenv("MADAWC_GAMMA_PAGE_LIMIT", str(DEFAULT_GAMMA_PAGE_LIMIT)))
MADAWC_GAMMA_MAX_PAGES = int(os.getenv("MADAWC_GAMMA_MAX_PAGES", str(DEFAULT_GAMMA_MAX_PAGES)))
MADAWC_GAMMA_SEED_EVENT_SLUG = os.getenv("MADAWC_GAMMA_SEED_EVENT_SLUG", DEFAULT_GAMMA_SEED_EVENT_SLUG)
MADAWC_GAMMA_FAMILY_PREFIX = os.getenv("MADAWC_GAMMA_FAMILY_PREFIX", DEFAULT_GAMMA_FAMILY_PREFIX)
MADAWC_MARKET_NEAR_EXPIRY_SECONDS = int(
    os.getenv("MADAWC_MARKET_NEAR_EXPIRY_SECONDS", str(DEFAULT_MARKET_NEAR_EXPIRY_SECONDS))
)
MADAWC_SIGNAL_ENTRY_PRICE = float(os.getenv("MADAWC_SIGNAL_ENTRY_PRICE", str(DEFAULT_SIGNAL_ENTRY_PRICE)))
MADAWC_SIGNAL_ENTRY_SECONDS = int(os.getenv("MADAWC_SIGNAL_ENTRY_SECONDS", str(DEFAULT_SIGNAL_ENTRY_SECONDS)))
MADAWC_SIGNAL_MIN_DEPTH = float(os.getenv("MADAWC_SIGNAL_MIN_DEPTH", str(DEFAULT_SIGNAL_MIN_DEPTH)))
MADAWC_SIGNAL_MIN_SIZE = float(os.getenv("MADAWC_SIGNAL_MIN_SIZE", str(DEFAULT_SIGNAL_MIN_SIZE)))
MADAWC_SIGNAL_MAX_STAKE = float(os.getenv("MADAWC_SIGNAL_MAX_STAKE", str(DEFAULT_SIGNAL_MAX_STAKE)))
MADAWC_MAX_TRADES_PER_MARKET = int(os.getenv("MADAWC_MAX_TRADES_PER_MARKET", str(DEFAULT_MAX_TRADES_PER_MARKET)))
MADAWC_EXIT_AT_FLAT_ENABLED = os.getenv(
    "MADAWC_EXIT_AT_FLAT_ENABLED",
    str(DEFAULT_EXIT_AT_FLAT_ENABLED),
).strip().lower() in ("1", "true", "yes", "on")
MADAWC_EXIT_AT_FLAT = float(os.getenv("MADAWC_EXIT_AT_FLAT", str(DEFAULT_EXIT_AT_FLAT)))
MADAWC_CYCLE_STEP_SLEEP_SECONDS = float(
    os.getenv("MADAWC_CYCLE_STEP_SLEEP_SECONDS", str(DEFAULT_CYCLE_STEP_SLEEP_SECONDS))
)
MADAWC_LOOP_INTERVAL_SECONDS = float(os.getenv("MADAWC_LOOP_INTERVAL_SECONDS", str(DEFAULT_LOOP_INTERVAL_SECONDS)))
MADAWC_SKIPPED_MARKET_PREFIXES = tuple(
    prefix.strip()
    for prefix in os.getenv("MADAWC_SKIPPED_MARKET_PREFIXES", "\n".join(DEFAULT_SKIPPED_MARKET_PREFIXES)).splitlines()
    if prefix.strip()
)
MADAWC_ONLY_TRADE_THIS_MARKETS = tuple(
    token.strip()
    for token in os.getenv("ONLY_TRADE_THIS_MARKETS", "\n".join(DEFAULT_ONLY_TRADE_THIS_MARKETS)).splitlines()
    if token.strip()
)
MADAWC_RESET_DB_ON_START = os.getenv("MADAWC_RESET_DB_ON_START", str(DEFAULT_RESET_DB_ON_START)).strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
