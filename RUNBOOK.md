## Kalshi AI Trading Bot – Phase 1 Runbook (Paper-Only)

This runbook assumes:

- You are using **Phase 1** of the bot (paper-only).
- You want **minimal manual steps** and clear commands for local and VPS setups.

---

### 1. One-time setup (local dev or VPS)

From your home directory or project workspace:

```bash
git clone <YOUR_FORK_URL> kalshi-ai-trading-bot
cd kalshi-ai-trading-bot

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

cp env.template .env
```

At this point `.env` can be left empty or populated later with **demo/sandbox**
Kalshi credentials. Phase 1 does not place any live trades.

---

### 2. Safety and health checks

Run these after setup and after any code change:

```bash
# Verify paper-only safety invariants (no keys required)
python cli.py verify-paper-safety

# Regenerate the paper dashboard without touching Kalshi (no keys required)
python cli.py dashboard

# With Kalshi API key + private key configured, you can also:
# - Check .env, API connectivity (read-only), and database initialization
python cli.py health

# - Show current portfolio balance and positions (read-only)
python cli.py status
```

If `verify-paper-safety` fails, do **not** proceed until the reported issue is fixed.

---

### 3. Running paper trading

#### 3.1 Single paper-trading cycle

```bash
python cli.py run
```

This will:

- Scan markets using deterministic filters.
- Log paper-only signals into `data/paper_trades.db`.
- Regenerate the paper trading dashboard HTML.

If you run this **without** a Kalshi API key and private key file, it will
fail fast with a short message explaining that keys are required for
read-only market access in order to fetch markets. It still never places
live orders in Phase 1.

#### 3.2 Continuous paper-trading loop

```bash
python cli.py run --loop --interval 900
```

This:

- Repeats the paper scan every 900 seconds (15 minutes) by default.
- Updates the dashboard after each cycle.

Stop with `Ctrl-C`.

---

### 4. Inspecting the market pipeline (diagnostics)

If you ever see `count=0` candidate markets in the logs, you can run a
diagnostic pass to inspect the ingestion + filtering pipeline:

```bash
python cli.py inspect-market-pipeline
```

This will:

- Fetch a slice of active markets from Kalshi (read-only).
- Upsert them into the local SQLite database.
- Show how many markets are eligible after deterministic filters.
- Print a small sample of candidate markets.

This command is **paper-only** and never places orders.

---

### 5. Paper dashboard

To regenerate the dashboard without scanning:

```bash
python cli.py dashboard
```

The dashboard is written to:

- `docs/paper_dashboard.html`

You can open it in a browser locally or serve it via a static file host.

---

### 5. Paper trader utilities

You can also interact directly with the paper trader script:

```bash
# Scan once, log signals, and regenerate dashboard
python paper_trader.py

# Check resolved markets and update outcomes for existing signals
python paper_trader.py --settle

# Regenerate HTML dashboard only
python paper_trader.py --dashboard

# Print stats to terminal
python paper_trader.py --stats

# Continuous loop (similar to cli.py run --loop)
python paper_trader.py --loop --interval 900
```

All of these are **paper-only**.

---

### 6. Typical tmux / VPS layout

On a VPS, a common pattern is:

- **Terminal 1 (tmux pane 1)** – Long-running paper loop:

  ```bash
  cd ~/kalshi-ai-trading-bot
  source .venv/bin/activate
  python cli.py run --loop --interval 900
  ```

- **Terminal 2 (tmux pane 2 or your Mac)** – One-off commands:

  ```bash
  # SSH from your Mac
  ssh <user>@<vps-host>

  cd ~/kalshi-ai-trading-bot
  source .venv/bin/activate

  python cli.py verify-paper-safety
  python cli.py health
  python cli.py status
  python cli.py dashboard
  ```

---

### 7. When (and how) *not* to run this code

- Do **not**:
  - Add or enable any `--live` flag.
  - Manually toggle `settings.trading.live_trading_enabled` to `True`.
  - Wire `src/strategies/unified_trading_system.py`, `src/agents/*`,
    or `src/jobs/execute.py` into cronjobs or services.

If you later choose to reintroduce live trading in a separate phase, do it in a
new “Phase 2” branch with:

- Explicit mode flags (`paper` vs `live`).
- External risk limits and a separate safety verification command.

