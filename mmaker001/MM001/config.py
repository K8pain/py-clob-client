"""Hardcoded configuration for MM001 MVP market-maker paper trading."""

from __future__ import annotations

import os
from pathlib import Path

# Runtime
BOT_NAME = "MM001"
STRATEGY_VERSION = "MM001-1.0"
DEFAULT_DB_PATH = Path("var/mm001/mm001.sqlite")
DEFAULT_OUTPUT_DIR = Path("var/mm001/reports")

# MVP simulation controls
SIMULATION_CYCLES = 120
SIMULATION_BASE_PRICE = 0.50
SIMULATION_VOLATILITY = 0.015
SIMULATION_SIZE = 100.0
SIMULATION_RANDOM_SEED = 7

# Market data source controls
ORDERBOOK_SOURCE = os.getenv("MM001_ORDERBOOK_SOURCE", "api")
CLOB_HOST = os.getenv("MM001_CLOB_HOST", "https://clob.polymarket.com")
MARKET_WS_URL = os.getenv("MM001_MARKET_WS_URL", "wss://ws-subscriptions-clob.polymarket.com/ws/market")
YES_TOKEN_ID = os.getenv("MM001_YES_TOKEN_ID", "")
NO_TOKEN_ID = os.getenv("MM001_NO_TOKEN_ID", "")
MAX_SIMULTANEOUS_OB = max(1, int(os.getenv("MM001_MAX_SIMULTANEOUS_OB", "1")))
MARKET_INCLUDE_ONLY = tuple(
    token.strip().lower()
    for token in os.getenv("MM001_MARKET_INCLUDE_ONLY", "crypto").split(",")
    if token.strip()
)
MARKET_EXCLUDED_PREFIXES = tuple(
    prefix.strip()
    for prefix in os.getenv(
        "MM001_MARKET_EXCLUDED_PREFIXES",
        "Will Bitcoin reach,Will Ethereum reach,Will Solana reach,Counter-Strike,Valorant:",
    ).split(",")
    if prefix.strip()
)
CURRENT_MARKET_SLUG = os.getenv("MM001_CURRENT_MARKET_SLUG", "")
CURRENT_MARKET_CATEGORY = os.getenv("MM001_CURRENT_MARKET_CATEGORY", "crypto")

# Market making economics
FEE_RATE_BPS = 35.0
TAKER_FRACTION = 0.10
ADVERSE_SELECTION_BUFFER = 0.0035
LATENCY_BUFFER = 0.0015
REBATE_EXPECTED = 0.0010
REWARD_EXPECTED = 0.0008
MIN_SPREAD_FLOOR = 0.006
INVENTORY_TARGET = 0.0
INVENTORY_SKEW_FACTOR = 0.002
MAX_ABS_INVENTORY = 800.0

# Pair/full-set logic
ENABLE_PAIR_MERGE = True
MERGE_EDGE_MIN = 0.0025
ENABLE_SPLIT_SELL = True
SPLIT_SELL_EDGE_MIN = 0.0030

# State machine
STATE_IDLE = "idle"
STATE_QUOTE = "quote"
STATE_PARTIAL_FILL = "partial_fill"
STATE_PAIRED_FILL = "paired_fill"
STATE_MERGE_OR_REQUOTE = "merge_or_requote"
STATE_INVENTORY_REBALANCE = "inventory_rebalance"
STATE_EMERGENCY_EXIT = "emergency_exit"
