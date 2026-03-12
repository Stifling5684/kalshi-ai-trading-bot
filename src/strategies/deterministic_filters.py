"""
Deterministic market filters for Phase 1 paper trading.

This module replaces all LLM/ensemble decision logic in the CLI-accessible
paper trading path with simple, auditable rules:

- Liquidity filter      (minimum volume)
- Spread filter         (implied spread between YES/NO legs)
- Time-to-expiry filter (min/max days)
- Imbalance/dislocation scoring

The output is a list of *paper-only* signal dicts ready to be logged by
`src.paper.tracker`.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List

from src.utils.database import DatabaseManager, Market
from src.utils.logging_setup import get_trading_logger


logger = get_trading_logger("deterministic_filters")


async def _load_candidate_markets(
    db_manager: DatabaseManager,
    min_volume: float,
    max_days_to_expiry: int,
) -> List[Market]:
    """
    Load candidate markets from the database using existing eligibility logic.
    """
    markets = await db_manager.get_eligible_markets(
        volume_min=int(min_volume),
        max_days_to_expiry=max_days_to_expiry,
    )
    logger.info(
        "Loaded candidate markets for deterministic filters",
        count=len(markets),
        min_volume=min_volume,
        max_days_to_expiry=max_days_to_expiry,
    )
    return markets


def _days_to_expiry(market: Market) -> float:
    try:
        now_ts = datetime.now().timestamp()
        return max(0.0, (market.expiration_ts - now_ts) / 86400.0)
    except Exception:
        return 0.0


def _implied_spread(market: Market) -> float:
    """
    Approximate spread using YES/NO prices on a 0–1 scale:
      spread ~= 1 - (yes_price + no_price)
    """
    try:
        spread = 1.0 - float(market.yes_price + market.no_price)
        return max(0.0, spread)
    except Exception:
        return 1.0


def _dislocation_score(market: Market) -> float:
    """
    Simple dislocation / imbalance score:
      - Measure distance of YES price from 0.5 (fair coin) and scale by volume.
    """
    try:
        yes_price = float(market.yes_price)
        volume = float(market.volume)
        dislocation = abs(yes_price - 0.5)
        # Scale and squash into [0, 1]
        raw = dislocation * (volume ** 0.5) / 100.0
        return max(0.0, min(1.0, raw))
    except Exception:
        return 0.0


def _choose_side(market: Market) -> str:
    """
    Choose a side based on simple imbalance:
      - If YES is < 0.5, treat it as value and go YES.
      - If YES is > 0.5, fade the move and go NO.
    """
    try:
        return "YES" if float(market.yes_price) <= 0.5 else "NO"
    except Exception:
        return "NO"


async def generate_paper_signals(
    kalshi_client: Any,
    db_manager: DatabaseManager,
    trading_settings: Any,
) -> List[Dict[str, Any]]:
    """
    Generate deterministic paper-trading signals using simple filters.

    Returns a list of dicts with:
      - market_id
      - market_title
      - side ("YES"/"NO")
      - entry_price (0–1)
      - confidence (0–1 dislocation score)
      - reasoning (human-readable explanation)
      - strategy ("deterministic_filters")
    """
    min_volume = getattr(trading_settings, "min_volume", 500.0)
    max_days_to_expiry = getattr(trading_settings, "max_time_to_expiry_days", 30)
    max_spread = getattr(trading_settings, "max_bid_ask_spread", 0.15)

    markets = await _load_candidate_markets(
        db_manager=db_manager,
        min_volume=min_volume,
        max_days_to_expiry=max_days_to_expiry,
    )
    signals: List[Dict[str, Any]] = []

    for m in markets:
        try:
            days = _days_to_expiry(m)
            spread = _implied_spread(m)
            score = _dislocation_score(m)

            # Filters
            if m.volume < min_volume:
                continue
            if days <= 0.0 or days > max_days_to_expiry:
                continue
            if spread > max_spread:
                continue

            if score <= 0.2:
                # Require at least a modest dislocation to avoid noise.
                continue

            side = _choose_side(m)
            entry_price = float(m.yes_price if side == "YES" else m.no_price)

            reasoning = (
                f"Deterministic signal: volume={m.volume}, days_to_expiry={days:.1f}, "
                f"spread≈{spread:.2f}, dislocation_score={score:.2f}, side={side}"
            )

            signals.append(
                {
                    "market_id": m.market_id,
                    "market_title": m.title,
                    "side": side,
                    "entry_price": entry_price,
                    "confidence": score,
                    "reasoning": reasoning,
                    "strategy": "deterministic_filters",
                }
            )
        except Exception as e:
            logger.warning(f"Failed to build deterministic signal for {getattr(m, 'market_id', '?')}: {e}")
            continue

    logger.info("Deterministic filters produced paper signals", count=len(signals))
    return signals

