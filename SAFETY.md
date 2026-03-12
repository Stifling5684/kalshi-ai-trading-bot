## Kalshi AI Trading Bot – Phase 1 Safety Model

Phase 1 of this project is a **paper-trading-only lab**. All CLI-accessible
paths are designed to be safe to run with *no* live trading, *no* LLM or
ensemble decisions, and *no* market making.

### Guarantees in Phase 1

- **Paper-only trading**
  - `python cli.py run` runs a **deterministic, filter-based paper loop**.
  - No live orders are sent to Kalshi; signals are written to SQLite only.

- **No live trading from the CLI**
  - `--live` is **removed** from the CLI.
  - `settings.trading.live_trading_enabled` must remain `False`.
  - `python cli.py verify-paper-safety` fails if this is violated.

- **No LLM / ensemble in CLI paths**
  - The Phase 1 CLI and `paper_trader.py` no longer import:
    - `src.clients.xai_client`
    - `src.clients.openai_client`
    - `src.clients.openrouter_client`
    - `src.clients.model_router`
    - `src.agents.*`
    - `src/strategies/unified_trading_system`
  - Deterministic rules in `src/strategies/deterministic_filters.py` are used instead.

- **No market making in Phase 1**
  - `src/strategies/market_making.py` and related orchestration are not
    imported by any CLI command.

- **No autonomous live trading**
  - The unified “Beast Mode” system (`beast_mode_bot.py`,
    `src/strategies/unified_trading_system.py`) is **not** used from the CLI.
  - There is no background process that will start live trading on its own.

### What is considered “safe” to run

From the repo root, after creating a virtualenv and installing dependencies:

- **Setup & diagnostics**
  - `python cli.py health`
  - `python cli.py status`
  - `python cli.py verify-paper-safety`

- **Paper-only trading and dashboard**
  - `python cli.py run`
  - `python cli.py run --loop --interval 900`
  - `python cli.py dashboard`
  - `python paper_trader.py` and its flags (`--loop`, `--settle`, `--dashboard`, `--stats`)

All of the above operate in **paper mode only**.

### Modules that remain off-limits in Phase 1

These modules are kept for future work but should **not** be used or imported
from any production CLI or scheduler in Phase 1:

- `beast_mode_bot.py`
- `beast_mode_dashboard.py`
- `src/strategies/unified_trading_system.py`
- `src/strategies/market_making.py`
- `src/agents/*`
- `src/clients/xai_client.py`
- `src/clients/openai_client.py`
- `src/clients/openrouter_client.py`
- `src/clients/model_router.py`
- `src/jobs/decide.py`
- `src/jobs/execute.py`

If you fork this repo and reintroduce live trading in a later phase, you must:

1. Re-add an explicit **mode flag** (`paper` vs `live`) and default to **paper**.
2. Add account-level and per-trade risk limits you are comfortable with.
3. Update `cli.py verify-paper-safety` to reflect the new invariants.

