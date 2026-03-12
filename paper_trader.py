#!/usr/bin/env python3
"""
Paper Trader — Phase 1 deterministic, paper-only mode for the Kalshi bot.

Phase 1 removes all LLM/ensemble logic and **never** places live orders. It:
  - Scans markets using simple, deterministic filters (liquidity, spread, time-to-expiry).
  - Scores opportunities using a basic dislocation / imbalance heuristic.
  - Logs recommended paper signals to SQLite only.
  - Generates a static HTML dashboard for review.

Usage:
    python paper_trader.py                # Scan once, log signals, generate dashboard
    python paper_trader.py --settle       # Check settled markets and update outcomes
    python paper_trader.py --dashboard    # Regenerate the HTML dashboard only
    python paper_trader.py --loop         # Continuous scanning (Ctrl-C to stop)
    python paper_trader.py --stats        # Print stats to terminal
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime, timezone

from src.paper.tracker import (
    log_signal,
    settle_signal,
    get_pending_signals,
    get_all_signals,
    get_stats,
)
from src.paper.dashboard import generate_html
from src.config.settings import settings
from src.utils.logging_setup import setup_logging, get_trading_logger

logger = get_trading_logger("paper_trader")

DASHBOARD_OUT = os.path.join(os.path.dirname(__file__), "docs", "paper_dashboard.html")


# ---------------------------------------------------------------------------
# Scanning: reuse the existing ingestion + decision pipeline
# ---------------------------------------------------------------------------

async def scan_and_log() -> int:
    """
    Scan markets using deterministic filters and log any paper-only signals.

    This Phase 1 implementation:
      - Reads eligible markets via the database manager and Kalshi client.
      - Applies liquidity, spread, and time-to-expiry filters.
      - Scores simple dislocation / imbalance and logs high-score candidates
        as *paper* signals only.
    """
    from src.clients.kalshi_client import KalshiClient
    from src.utils.database import DatabaseManager
    from src.strategies.deterministic_filters import generate_paper_signals

    logger.info("📡 Scanning markets for deterministic paper trading signals…")

    kalshi = KalshiClient()
    db = DatabaseManager()

    try:
        signals = await generate_paper_signals(
            kalshi_client=kalshi,
            db_manager=db,
            trading_settings=settings.trading,
        )
    except Exception as e:
        logger.error(f"Deterministic scan failed: {e}")
        return 0

    signals_logged = 0
    for sig in signals:
        try:
            signal_id = log_signal(
                market_id=sig["market_id"],
                market_title=sig["market_title"],
                side=sig["side"],
                entry_price=sig["entry_price"],
                confidence=sig["confidence"],
                reasoning=sig["reasoning"],
                strategy=sig.get("strategy", "deterministic_filters"),
            )
            signals_logged += 1
            logger.info(
                f"📝 Signal #{signal_id}: {sig['side']} {sig['market_title']} "
                f"@ {sig['entry_price']:.0%} (score={sig['confidence']:.0%}) — {sig['reasoning'][:80]}"
            )
        except Exception as e:
            logger.warning(f"Failed to log signal for {sig.get('market_id')}: {e}")
            continue

    logger.info(f"✅ Logged {signals_logged} deterministic paper signals")
    return signals_logged


# ---------------------------------------------------------------------------
# Settlement: check outcomes for pending signals
# ---------------------------------------------------------------------------

async def check_settlements():
    """Check Kalshi for settled markets and update signal outcomes."""
    from src.clients.kalshi_client import KalshiClient

    pending = get_pending_signals()
    if not pending:
        logger.info("No pending signals to settle.")
        return 0

    kalshi = KalshiClient()
    settled_count = 0

    for sig in pending:
        try:
            market = await kalshi.get_market(sig["market_id"])
            if not market:
                continue

            status = market.get("status", "")
            result = market.get("result", "")

            if status not in ("settled", "finalized", "closed"):
                continue

            # result is typically "yes" or "no"
            settlement_price = 1.0 if result.lower() == "yes" else 0.0

            settle_signal(sig["id"], settlement_price)
            outcome = "WIN" if (
                (sig["side"] == "NO" and settlement_price <= 0.5) or
                (sig["side"] == "YES" and settlement_price >= 0.5)
            ) else "LOSS"
            logger.info(f"🏁 Signal #{sig['id']} settled: {outcome} — {sig['market_title']}")
            settled_count += 1

        except Exception as e:
            logger.warning(f"Settlement check failed for {sig['market_id']}: {e}")

    logger.info(f"✅ Settled {settled_count}/{len(pending)} pending signals")
    return settled_count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_stats():
    stats = get_stats()
    print("\n📊 Paper Trading Stats")
    print("=" * 40)
    print(f"  Total signals:  {stats['total_signals']}")
    print(f"  Settled:        {stats['settled']}")
    print(f"  Pending:        {stats['pending']}")
    print(f"  Wins:           {stats['wins']}")
    print(f"  Losses:         {stats['losses']}")
    print(f"  Win rate:       {stats['win_rate']}%")
    print(f"  Total P&L:      ${stats['total_pnl']:.2f}")
    print(f"  Avg return:     ${stats['avg_return']:.4f}")
    print(f"  Best trade:     ${stats['best_trade']:.2f}")
    print(f"  Worst trade:    ${stats['worst_trade']:.2f}")
    print()


async def main():
    parser = argparse.ArgumentParser(description="Paper Trader — Kalshi AI signal logger")
    parser.add_argument("--settle", action="store_true", help="Check settled markets")
    parser.add_argument("--dashboard", action="store_true", help="Regenerate HTML dashboard only")
    parser.add_argument("--stats", action="store_true", help="Print stats to terminal")
    parser.add_argument("--loop", action="store_true", help="Continuous scanning")
    parser.add_argument("--interval", type=int, default=900, help="Loop interval in seconds (default 15min)")
    args = parser.parse_args()

    setup_logging()

    if args.stats:
        print_stats()
        return

    if args.dashboard:
        generate_html(DASHBOARD_OUT)
        print(f"✅ Dashboard generated: {DASHBOARD_OUT}")
        return

    if args.settle:
        await check_settlements()
        generate_html(DASHBOARD_OUT)
        print(f"✅ Dashboard updated: {DASHBOARD_OUT}")
        return

    # Default: scan once (or loop)
    while True:
        await scan_and_log()
        await check_settlements()
        generate_html(DASHBOARD_OUT)
        logger.info(f"📊 Dashboard updated: {DASHBOARD_OUT}")

        if not args.loop:
            break

        logger.info(f"💤 Sleeping {args.interval}s until next scan…")
        await asyncio.sleep(args.interval)


if __name__ == "__main__":
    asyncio.run(main())
