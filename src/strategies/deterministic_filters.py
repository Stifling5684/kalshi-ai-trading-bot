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


async def _refresh_active_markets_from_kalshi(
    kalshi_client: Any,
    db_manager: DatabaseManager,
    max_pages: int = 3,
    per_page: int = 100,
) -> int:
    """
    Fetch a reasonable slice of active markets from Kalshi and upsert into the DB.

    Phase 1 uses this *read-only* ingestion path instead of the old ingest/AI
    pipeline. It never places orders.
    """
    total_fetched = 0
    page = 0
    cursor = None

    from datetime import datetime as _dt

    while page < max_pages:
        page += 1
        try:
            response = await kalshi_client.get_markets(limit=per_page, cursor=cursor, status="active")
        except Exception as e:
            logger.warning("Failed to fetch markets page from Kalshi", page=page, error=str(e))
            break

        markets_page = response.get("markets", []) or []
        if not markets_page:
            logger.info("No markets returned from Kalshi on page", page=page)
            break

        active_markets_data = [m for m in markets_page if m.get("status") == "active"]
        total_fetched += len(active_markets_data)

        markets: List[Market] = []
        for m in active_markets_data:
            try:
                yes_price = (m.get("yes_bid", 0) + m.get("yes_ask", 0)) / 2
                no_price = (m.get("no_bid", 0) + m.get("no_ask", 0)) / 2
                volume = int(m.get("volume", 0))
                expiration_ts = int(
                    _dt.fromisoformat(m["expiration_time"].replace("Z", "+00:00")).timestamp()
                )

                markets.append(
                    Market(
                        market_id=m["ticker"],
                        title=m.get("title", m["ticker"]),
                        yes_price=yes_price / 100 if yes_price else 0.0,
                        no_price=no_price / 100 if no_price else 0.0,
                        volume=volume,
                        expiration_ts=expiration_ts,
                        category=m.get("category", "unknown"),
                        status=m.get("status", "unknown"),
                        last_updated=_dt.now(),
                        has_position=False,
                    )
                )
            except Exception as e:
                logger.warning("Failed to map market from Kalshi", ticker=m.get("ticker"), error=str(e))
                continue

        if markets:
            await db_manager.upsert_markets(markets)
            logger.info(
                "Upserted active markets from Kalshi for Phase 1",
                page=page,
                fetched=len(active_markets_data),
                upserted=len(markets),
                total_fetched=total_fetched,
            )

        cursor = response.get("cursor")
        if not cursor:
            break

    logger.info("Finished refreshing active markets from Kalshi", total_fetched=total_fetched)
    return total_fetched


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

    # 0. Refresh a slice of active markets from Kalshi into the local DB (read-only).
    refreshed = await _refresh_active_markets_from_kalshi(
        kalshi_client=kalshi_client,
        db_manager=db_manager,
    )
    logger.info("Refreshed active markets from Kalshi", count=refreshed)

    # 1. Load eligible markets from DB using deterministic eligibility logic.
    markets = await _load_candidate_markets(
        db_manager=db_manager,
        min_volume=min_volume,
        max_days_to_expiry=max_days_to_expiry,
    )
    signals: List[Dict[str, Any]] = []
    rejected_volume = rejected_expiry = rejected_spread = rejected_score = 0

    for m in markets:
        try:
            days = _days_to_expiry(m)
            spread = _implied_spread(m)
            score = _dislocation_score(m)

            # Filters
            if m.volume < min_volume:
                rejected_volume += 1
                continue
            if days <= 0.0 or days > max_days_to_expiry:
                rejected_expiry += 1
                continue
            if spread > max_spread:
                rejected_spread += 1
                continue

            if score <= 0.2:
                # Require at least a modest dislocation to avoid noise.
                rejected_score += 1
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
            logger.warning(
                f"Failed to build deterministic signal for {getattr(m, 'market_id', '?')}: {e}"
            )
            continue

    logger.info(
        "Deterministic filters produced paper signals",
        total_candidates=len(markets),
        produced=len(signals),
        rejected_volume=rejected_volume,
        rejected_expiry=rejected_expiry,
        rejected_spread=rejected_spread,
        rejected_score=rejected_score,
    )
    return signals

