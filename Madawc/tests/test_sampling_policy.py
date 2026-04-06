"""Pruebas unitarias para política de sampling adaptativo y señal."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Madawc_v2.models import BookLevel, ClassificationStatus, ClassifiedMarket, MarketRecord, OrderBookSnapshot
from Madawc_v2.runtime import TimeSync
from Madawc_v2.signal import SamplingMode, SignalConfig, SignalEngine, sampling_mode


def _classified_market() -> ClassifiedMarket:
    now = datetime.now(timezone.utc)
    market = MarketRecord(
        market_id="m-sampling",
        event_id="e-sampling",
        question="BTC Up or Down",
        slug="btc-updown",
        token_ids=("tok-1",),
        end_time=now + timedelta(minutes=2),
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
    )
    return ClassifiedMarket(
        market=market,
        status=ClassificationStatus.CANDIDATE_5M,
        confidence=1.0,
        method="test",
    )


def test_sampling_mode_aggressive_when_order_open_and_very_close_to_expiry() -> None:
    assert sampling_mode(seconds_to_end=25, has_open_limit_order=True) == SamplingMode.AGGRESSIVE


def test_sampling_mode_watch_when_near_expiry_without_open_order() -> None:
    assert sampling_mode(seconds_to_end=90, has_open_limit_order=False) == SamplingMode.WATCH


def test_sampling_mode_idle_when_far_from_expiry() -> None:
    assert sampling_mode(seconds_to_end=300, has_open_limit_order=False) == SamplingMode.IDLE


def test_signal_engine_skips_when_visible_depth_is_below_min_operational_size() -> None:
    now = datetime.now(timezone.utc)
    market = _classified_market()
    book = OrderBookSnapshot(
        token_id="tok-1",
        bids=(BookLevel(price=0.04, size=10.0),),
        asks=(BookLevel(price=0.05, size=2.0),),
        ts_ms=int(now.timestamp() * 1000),
    )
    engine = SignalEngine(
        SignalConfig(
            entry_price=0.05,
            entry_seconds_threshold=600,
            min_operational_size=5.0,
            min_order_size=1.0,
            max_stake_per_trade=1.0,
        )
    )
    time_sync = TimeSync()
    time_sync.sync(int(now.timestamp() * 1000))
    end_epoch_ms = int((now + timedelta(minutes=2)).timestamp() * 1000)

    signal, reason = engine.evaluate(
        market=market,
        token_id="tok-1",
        book=book,
        end_epoch_ms=end_epoch_ms,
        time_sync=time_sync,
        available_cash=1000.0,
    )

    assert signal is None
    assert reason == "skipped_insufficient_depth"
