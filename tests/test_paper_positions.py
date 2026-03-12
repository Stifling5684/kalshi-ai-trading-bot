import pytest

from src.utils.database import DatabaseManager, Position
from paper_trader import scan_and_log


@pytest.mark.asyncio
async def test_paper_signals_create_open_positions(tmp_path, monkeypatch):
    """
    End-to-end Phase 1 check:
    - deterministic_filters generates at least one signal (already covered elsewhere)
    - scan_and_log persists accepted signals as non-live, open positions
    """
    # Use a temporary trading_system.db
    db_path = tmp_path / "test_trading_system.db"
    db = DatabaseManager(db_path=str(db_path))
    await db.initialize()

    # Monkeypatch DatabaseManager used inside scan_and_log to use our temp DB.
    async def _db_init(self, db_path_override=str(db_path)):
        self.db_path = db_path_override
        self.logger.info("Initializing database manager", db_path=self.db_path)

    monkeypatch.setattr(DatabaseManager, "__init__", lambda self, db_path="trading_system.db": _db_init(self))

    # Monkeypatch KalshiClient to avoid real API calls and feed a known-good market.
    class DummyKalshiClient:
        async def get_markets(self, limit=100, cursor=None, status=None):
            return {
                "markets": [
                    {
                        "ticker": "TEST-MKT-1",
                        "title": "Test market 1",
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

        async def close(self):
            return

    from src.clients import kalshi_client as kc

    monkeypatch.setattr(kc, "KalshiClient", DummyKalshiClient)

    # Run a single scan; this should generate at least one signal and create positions.
    await scan_and_log()

    open_positions = await db.get_open_positions()
    assert len(open_positions) >= 1
    for p in open_positions:
        assert p.live is False
        assert p.status == "open"
        assert p.strategy == "deterministic_filters"

