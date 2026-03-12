#!/usr/bin/env python3
"""
Kalshi AI Trading Bot -- Phase 1 (Paper-Only) CLI

This CLI has been refactored into a strict Phase 1 MVP with **paper trading only**:

    python cli.py run                 Run deterministic paper-trading cycle(s)
    python cli.py dashboard           Launch the paper-trading dashboard
    python cli.py status              Show portfolio balance, positions, and P&L
    python cli.py backtest            Run backtests (placeholder)
    python cli.py health              Verify API connections, database, and configuration
    python cli.py verify-paper-safety Confirm that CLI paths are paper-only and non-executing

Live trading, LLM/ensemble decisions, and market making are **disabled** from all
CLI-reachable paths in this phase.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> None:
    """
    Start the Phase 1 deterministic paper-trading loop.

    This command is **paper-only** and never places live orders. It reuses the
    paper trading tracker/dash logic from `paper_trader.py`.
    """
    from src.utils.logging_setup import setup_logging
    from paper_trader import scan_and_log, check_settlements, DASHBOARD_OUT
    from src.paper.dashboard import generate_html

    log_level = getattr(args, "log_level", "INFO")
    setup_logging(log_level=log_level)

    print("🚫 Live trading is DISABLED in Phase 1. Running in paper-trading mode only.\n")

    async def _run_once(loop: bool, interval: int) -> None:
        while True:
            await scan_and_log()
            await check_settlements()
            generate_html(DASHBOARD_OUT)
            print(f"📊 Paper dashboard updated at {DASHBOARD_OUT}")
            if not loop:
                break
            print(f"💤 Sleeping {interval}s until next paper scan…")
            await asyncio.sleep(interval)

    try:
        asyncio.run(_run_once(loop=getattr(args, "loop", False), interval=getattr(args, "interval", 900)))
    except KeyboardInterrupt:
        print("\nPaper trading loop stopped by user.")
    except Exception as exc:
        # Surface common auth/key errors in a friendly way for local dev.
        msg = str(exc)
        if "KALSHI_API_KEY" in msg or "Failed to load private key" in msg or "Private key file not found" in msg:
            print(
                "❌ Unable to start paper scan: Kalshi API key and private key are required "
                "for read-only market access.\n\n"
                "This is a Phase 1 requirement *only* for fetching markets; no live orders "
                "are ever placed.\n"
                "If you're just smoke-testing locally without keys, you can run:\n"
                "  python cli.py verify-paper-safety\n"
                "  python cli.py dashboard\n"
                "instead of the full paper scan."
            )
            sys.exit(1)
        raise


def cmd_dashboard(args: argparse.Namespace) -> None:
    """Launch the Streamlit monitoring dashboard."""
    import subprocess

    # Phase 1: always use paper dashboard HTML generation.
    from src.utils.logging_setup import setup_logging
    from paper_trader import DASHBOARD_OUT
    from src.paper.dashboard import generate_html

    setup_logging(log_level="INFO")
    generate_html(DASHBOARD_OUT)
    print(f"✅ Paper dashboard generated at {DASHBOARD_OUT}")


def cmd_status(args: argparse.Namespace) -> None:
    """Show current portfolio status: balance, positions, and P&L."""

    async def _status() -> None:
        from src.clients.kalshi_client import KalshiClient

        client = KalshiClient()
        try:
            # Fetch balance
            balance_resp = await client.get_balance()
            balance_cents = balance_resp.get("balance", 0)
            balance_usd = balance_cents / 100.0

            # Fetch positions
            positions_resp = await client.get_positions()
            positions = positions_resp.get("market_positions", [])

            # Display
            print("=" * 56)
            print("  PORTFOLIO STATUS")
            print("=" * 56)
            print(f"  Available Balance:  ${balance_usd:>10,.2f}")
            print(f"  Open Positions:     {len(positions):>10}")

            total_cost = 0.0
            total_market_value = 0.0

            if positions:
                print()
                print(f"  {'Ticker':<20} {'Side':<6} {'Qty':>5} {'Avg':>7} {'Value':>9}")
                print(f"  {'-'*20} {'-'*6} {'-'*5} {'-'*7} {'-'*9}")

                for pos in positions:
                    ticker = pos.get("ticker", "???")
                    # Kalshi positions may use different field names
                    side = "YES" if pos.get("position", 0) > 0 else "NO"
                    qty = abs(pos.get("position", pos.get("total_traded", 0)))
                    avg_price = pos.get("average_price", 0)
                    if isinstance(avg_price, (int, float)) and avg_price > 1:
                        avg_price = avg_price / 100.0  # convert cents to dollars
                    market_value = qty * avg_price
                    total_cost += market_value
                    total_market_value += market_value
                    print(
                        f"  {ticker:<20} {side:<6} {qty:>5} "
                        f"${avg_price:>5.2f} ${market_value:>7.2f}"
                    )

            print()
            print(f"  Position Cost:      ${total_cost:>10,.2f}")
            print(f"  Total Portfolio:    ${balance_usd + total_cost:>10,.2f}")
            print("=" * 56)
        finally:
            await client.close()

    try:
        asyncio.run(_status())
    except Exception as exc:
        print(f"Error fetching status: {exc}")
        sys.exit(1)


def cmd_backtest(args: argparse.Namespace) -> None:
    """Run backtests (placeholder)."""
    print("=" * 56)
    print("  BACKTESTING")
    print("=" * 56)
    print()
    print("  Backtesting engine coming soon.")
    print()
    print("  Planned features:")
    print("    - Historical market replay")
    print("    - Strategy parameter optimization")
    print("    - Walk-forward analysis")
    print("    - Monte Carlo simulation")
    print()
    print("=" * 56)


def cmd_inspect_market_pipeline(args: argparse.Namespace) -> None:
    """
    Diagnostic command: inspect the deterministic market pipeline for Phase 1.

    Runs a single refresh + candidate load + filter cycle and prints summary
    counts without logging any signals.
    """
    import asyncio as _asyncio

    from src.clients.kalshi_client import KalshiClient
    from src.utils.database import DatabaseManager
    from src.strategies.deterministic_filters import (
        _refresh_active_markets_from_kalshi,
        _load_candidate_markets,
    )
    from src.config.settings import settings as _settings
    from src.utils.logging_setup import setup_logging

    setup_logging(log_level="INFO")

    async def _run() -> None:
        try:
            kalshi = KalshiClient()
        except Exception as exc:
            msg = str(exc)
            if "KALSHI_API_KEY" in msg or "Failed to load private key" in msg or "Private key file not found" in msg:
                print(
                    "❌ Cannot inspect market pipeline: Kalshi API key and private key are required "
                    "for read-only market access.\n\n"
                    "You can still run without keys:\n"
                    "  python cli.py verify-paper-safety\n"
                    "  python cli.py dashboard"
                )
                return
            raise

        db = DatabaseManager()
        try:
            print("🔎 Refreshing active markets from Kalshi into local DB…")
            refreshed = await _refresh_active_markets_from_kalshi(
                kalshi_client=kalshi, db_manager=db
            )
            print(f"  Fetched/upserted markets: {refreshed}")

            trading = _settings.trading
            min_volume = getattr(trading, "min_volume", 500.0)
            max_days = getattr(trading, "max_time_to_expiry_days", 30)

            candidates = await _load_candidate_markets(
                db_manager=db,
                min_volume=min_volume,
                max_days_to_expiry=max_days,
            )
            print(f"  Eligible candidates in DB: {len(candidates)}")

            if candidates[:5]:
                print("\n  Sample candidates:")
                for m in candidates[:5]:
                    print(
                        f"   - {m.market_id}: {m.title} "
                        f"vol={m.volume}, exp_ts={m.expiration_ts}, "
                        f"yes={m.yes_price:.2f}, no={m.no_price:.2f}"
                    )
        finally:
            await kalshi.close()

    try:
        _asyncio.run(_run())
    except KeyboardInterrupt:
        print("\nInspection cancelled by user.")


def cmd_health(args: argparse.Namespace) -> None:
    """Run health checks on configuration, API, and database."""

    checks_passed = 0
    checks_failed = 0

    def ok(label: str, detail: str = "") -> None:
        nonlocal checks_passed
        checks_passed += 1
        suffix = f" -- {detail}" if detail else ""
        print(f"  [PASS] {label}{suffix}")

    def fail(label: str, detail: str = "") -> None:
        nonlocal checks_failed
        checks_failed += 1
        suffix = f" -- {detail}" if detail else ""
        print(f"  [FAIL] {label}{suffix}")

    print("=" * 56)
    print("  HEALTH CHECK")
    print("=" * 56)
    print()

    # 1. .env file
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        ok(".env file exists")
    else:
        fail(".env file missing", "copy env.template to .env and fill in keys")

    # 2. Required/optional environment variables
    from dotenv import load_dotenv
    load_dotenv()

    required_vars = ("KALSHI_API_KEY",)
    optional_ai_vars = ("XAI_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY")

    for var in required_vars:
        val = os.getenv(var, "")
        if val and val not in ("", "your_kalshi_api_key_here"):
            ok(f"{var} is set")
        else:
            fail(f"{var} is missing or placeholder")

    for var in optional_ai_vars:
        val = os.getenv(var, "")
        if val and val.strip():
            ok(f"{var} is set (optional for Phase 1)")
        else:
            ok(f"{var} not set (LLM features disabled in Phase 1)")

    # 3. Kalshi API connection
    async def _check_api() -> None:
        from src.clients.kalshi_client import KalshiClient
        client = KalshiClient()
        try:
            balance_resp = await client.get_balance()
            balance_usd = balance_resp.get("balance", 0) / 100.0
            ok("Kalshi API connection", f"balance=${balance_usd:,.2f}")
        except Exception as exc:
            fail("Kalshi API connection", str(exc))
        finally:
            await client.close()

    try:
        asyncio.run(_check_api())
    except Exception as exc:
        fail("Kalshi API connection", str(exc))

    # 4. Database
    db_path = Path(__file__).parent / "trading_system.db"
    try:
        import aiosqlite

        async def _check_db() -> None:
            from src.utils.database import DatabaseManager
            db_manager = DatabaseManager()
            await db_manager.initialize()
            ok("Database initialization", str(db_path))

        asyncio.run(_check_db())
    except Exception as exc:
        fail("Database initialization", str(exc))

    # 5. Python version
    if sys.version_info >= (3, 12):
        ok("Python version", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    else:
        fail("Python version", f"requires >=3.12, found {sys.version}")

    # Summary
    print()
    total = checks_passed + checks_failed
    print(f"  {checks_passed}/{total} checks passed")
    if checks_failed:
        print(f"  {checks_failed} issue(s) need attention")
    else:
        print("  All systems operational.")
    print("=" * 56)

    if checks_failed:
        sys.exit(1)


def _read_file_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def cmd_verify_paper_safety(args: argparse.Namespace) -> None:
    """
    Verify that CLI-accessible code paths are paper-only and non-executing.

    Checks:
      - No direct Kalshi order placement/cancellation calls in CLI-core modules.
      - Trading config does not enable live trading.
    """
    from src.config.settings import settings

    print("🔍 Verifying Phase 1 paper-safety invariants…")

    # 1. Config guard: live trading must be disabled
    live_enabled = getattr(getattr(settings, "trading", settings), "live_trading_enabled", False)
    if live_enabled:
        print("❌ settings.trading.live_trading_enabled is True – live trading must be disabled in Phase 1.")
        sys.exit(1)

    # 2. Scan core CLI modules for forbidden callsites
    repo_root = Path(__file__).parent
    core_paths: List[Path] = [
        repo_root / "cli.py",
        repo_root / "paper_trader.py",
        repo_root / "src" / "paper" / "tracker.py",
        repo_root / "src" / "paper" / "dashboard.py",
        repo_root / "src" / "utils" / "logging_setup.py",
        repo_root / "src" / "utils" / "database.py",
    ]
    # Build forbidden tokens without embedding them verbatim in this file,
    # so that this module itself does not trip the safety scan.
    forbidden = (
        "place_" + "order(",
        "cancel_" + "order(",
    )
    violations: List[str] = []

    for path in core_paths:
        if not path.exists():
            continue
        text = _read_file_text(path)
        for token in forbidden:
            if token in text:
                violations.append(f"{path}: contains forbidden token '{token}'")

    if violations:
        print("❌ Paper-safety verification failed. Forbidden Kalshi order calls found in CLI-core modules:")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)

    print("✅ Paper-safety verification passed: CLI-core modules are paper-only and live trading is disabled.")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kalshi-bot",
        description="Kalshi AI Trading Bot -- Phase 1 (paper-only, deterministic trading lab)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python cli.py run                 Start deterministic paper-trading loop\n"
            "  python cli.py dashboard           Generate the paper-trading dashboard\n"
            "  python cli.py status              Check portfolio balance and positions\n"
            "  python cli.py health              Verify all connections and config\n"
            "  python cli.py inspect-market-pipeline  Inspect deterministic market pipeline\n"
            "  python cli.py verify-paper-safety Confirm Phase 1 paper-only constraints\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- run (paper-only) ---
    p_run = subparsers.add_parser(
        "run",
        help="Start the paper-trading loop",
        description="Run the deterministic, filter-based paper-trading loop (no live orders).",
    )
    p_run.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity (default: INFO)",
    )
    p_run.add_argument(
        "--loop",
        action="store_true",
        help="Continuously run paper scans instead of a single pass.",
    )
    p_run.add_argument(
        "--interval",
        type=int,
        default=900,
        help="Loop interval in seconds for paper mode (default: 900).",
    )
    p_run.set_defaults(func=cmd_run)

    # --- dashboard ---
    p_dash = subparsers.add_parser(
        "dashboard",
        help="Launch the Streamlit monitoring dashboard",
        description="Open a real-time web dashboard showing portfolio performance, positions, risk metrics, and AI decision logs.",
    )
    p_dash.set_defaults(func=cmd_dashboard)

    # --- status ---
    p_status = subparsers.add_parser(
        "status",
        help="Show portfolio balance, positions, and P&L",
        description="Connect to the Kalshi API and display current account balance, open positions, and estimated portfolio value.",
    )
    p_status.set_defaults(func=cmd_status)

    # --- backtest ---
    p_bt = subparsers.add_parser(
        "backtest",
        help="Run backtests (coming soon)",
        description="Backtest trading strategies against historical market data. This feature is under development.",
    )
    p_bt.set_defaults(func=cmd_backtest)

    # --- health ---
    p_health = subparsers.add_parser(
        "health",
        help="Verify API connections, database, and configuration",
        description="Run a series of diagnostic checks: .env presence, API key configuration, Kalshi API connectivity, database initialization, and Python version.",
    )
    p_health.set_defaults(func=cmd_health)

    # --- inspect-market-pipeline (diagnostic) ---
    p_inspect = subparsers.add_parser(
        "inspect-market-pipeline",
        help="Inspect deterministic market ingestion/filtering pipeline",
        description="Run a single refresh + candidate load cycle and print diagnostics.",
    )
    p_inspect.set_defaults(func=cmd_inspect_market_pipeline)

    # --- verify-paper-safety ---
    p_verify = subparsers.add_parser(
        "verify-paper-safety",
        help="Verify that CLI-accessible code paths are paper-only and non-executing.",
        description="Run static checks to confirm Phase 1 safety invariants (no live trading, no Kalshi order calls in CLI-core modules).",
    )
    p_verify.set_defaults(func=cmd_verify_paper_safety)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
