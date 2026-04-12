"""Hardcoded configuration for Madawc v3 MVP market-maker paper trading."""

from __future__ import annotations

from pathlib import Path

# Runtime
BOT_NAME = "Madawc_v3"
STRATEGY_VERSION = "madawc-v3.0"
DEFAULT_DB_PATH = Path("var/madawc_v3/madawc_v3.sqlite")
DEFAULT_OUTPUT_DIR = Path("var/madawc_v3/reports")

# MVP simulation controls
SIMULATION_CYCLES = 120
SIMULATION_BASE_PRICE = 0.50
SIMULATION_VOLATILITY = 0.015
SIMULATION_SIZE = 100.0
SIMULATION_RANDOM_SEED = 7

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
