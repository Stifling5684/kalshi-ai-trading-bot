import asyncio
from types import SimpleNamespace

import pytest

from src.strategies import deterministic_filters
from src.utils.database import DatabaseManager


class DummyKalshiClient:
    def __init__(self):
        self.calls = 0

    async def get_markets(self, limit=100, cursor=None, status=None):
        self.calls += 1
        return {
            "markets": [
                {
                    "ticker": "TEST-MKT-1",
                    "title": "Test market 1",
                    # Use *_dollars and *_fp-style fields as on real Kalshi payloads.
                    # Choose an obviously mispriced, high-liquidity market so it
                    # clearly passes the deterministic score threshold.
                    "yes_bid_dollars": "0.10",
                    "yes_ask_dollars": "0.10",
                    "no_bid_dollars": "0.90",
                    "no_ask_dollars": "0.90",
                    "volume_fp": "100000.00",
                    "expiration_time": "2030-12-31T23:59:59Z",
                    "category": "test",
                    "status": "active",
                }
            ],
            "cursor": None,
        }


@pytest.mark.asyncio
async def test_refresh_and_generate_signals_produces_candidates(tmp_path):
    """
    End-to-end smoke test for deterministic ingestion + filtering:
    - Use DummyKalshiClient to feed one active market.
    - Ensure at least one signal is produced.
    """
    db_path = tmp_path / "test_trading.db"
    db = DatabaseManager(db_path=str(db_path))
    await db.initialize()

    dummy_client = DummyKalshiClient()
    trading_settings = SimpleNamespace(
        min_volume=10.0,
        max_time_to_expiry_days=3650,
        max_bid_ask_spread=0.5,
    )

    signals = await deterministic_filters.generate_paper_signals(
        kalshi_client=dummy_client,
        db_manager=db,
        trading_settings=trading_settings,
    )

    assert dummy_client.calls >= 1
    assert len(signals) >= 1

