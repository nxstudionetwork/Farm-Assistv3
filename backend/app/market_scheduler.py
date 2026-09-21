"""Scheduled background sync for market price data.

A single controlled background loop (started once from FastAPI startup) keeps
the market_prices table refreshed on the configured cadence. Design rules
(from the Market Prices spec):

* Runs automatically but never spins: between runs it sleeps for
  ``MARKET_PRICE_SCHEDULE_HOURS``.
* Skips a run when a successful sync is already newer than the interval
  (prevents duplicate imports / uncontrolled loop on restart).
* Retries transient failures with bounded exponential backoff.
* When no live source is configured it does nothing at all (no error noise).
* Every attempt is recorded in market_data_syncs with trigger="scheduler",
  identical to API / manual imports.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.config import settings
from app.database.connection import SessionLocal
from app.models.market_price import MarketDataSync
from app.services import market_price_service as svc

logger = logging.getLogger("market_scheduler")

_task = None


def _last_successful_sync(db) -> Optional[MarketDataSync]:
    return (
        db.query(MarketDataSync)
        .filter(MarketDataSync.status == "success")
        .order_by(MarketDataSync.synced_at.desc())
        .first()
    )


def _run_sync_once() -> dict:
    """Run one sync in a fresh session (called from a worker thread)."""
    db = SessionLocal()
    try:
        return svc.sync_from_source(db, trigger="scheduler", force=False)
    except Exception:  # pragma: no cover - defensive; loop handles retries
        logger.exception("Scheduled market data sync crashed")
        return {"ok": False, "reason": "error"}
    finally:
        db.close()


async def _attempt_sync_with_retries() -> None:
    """Run a sync, retrying transient failures with backoff."""
    retries = (300, 900, 1800)  # 5m, 15m, 30m
    try:
        run = await asyncio.get_running_loop().run_in_executor(None, _run_sync_once)
        if run.get("ok"):
            logger.info("Scheduled market data sync succeeded (%s).", run.get("message"))
            return
        for delay in retries:
            if not run.get("ok"):
                logger.warning("Scheduled market sync failed (%s); retrying in %ss.",
                               run.get("reason"), delay)
                await asyncio.sleep(delay)
                run = await asyncio.get_running_loop().run_in_executor(None, _run_sync_once)
                if run.get("ok"):
                    logger.info("Scheduled market data sync succeeded on retry.")
                    return
    except asyncio.CancelledError:
        raise
    except Exception:  # pragma: no cover - defensive
        logger.exception("Unexpected error during scheduled market data sync.")


async def _market_price_loop() -> None:
    # Give startup seeding a moment to finish before the first scheduled run.
    await asyncio.sleep(30)
    while True:
        try:
            now = datetime.utcnow()
            db = SessionLocal()
            try:
                fresh = False
                last = _last_successful_sync(db)
                if last and last.synced_at:
                    fresh = (now - last.synced_at) < timedelta(
                        hours=settings.MARKET_PRICE_SCHEDULE_HOURS
                    )
            finally:
                db.close()

            if not fresh and svc.source_configured():
                await _attempt_sync_with_retries()
            elif not svc.source_configured():
                logger.info("Market price live source not configured; scheduled sync idle.")
        except asyncio.CancelledError:
            break
        except Exception:  # pragma: no cover - defensive
            logger.exception("Market price scheduler iteration failed.")
        await asyncio.sleep(3600 * max(settings.MARKET_PRICE_SCHEDULE_HOURS, 0.5))


def start_market_price_scheduler() -> None:
    """Idempotently start the background sync loop (no-op when disabled)."""
    global _task
    if _task is not None or not settings.MARKET_PRICE_AUTO_UPDATE:
        return
    try:
        _task = asyncio.get_running_loop().create_task(_market_price_loop())
        logger.info("Market price auto-update scheduler started "
                    "(every %sh).", settings.MARKET_PRICE_SCHEDULE_HOURS)
    except RuntimeError:
        _task = None
        logger.warning("Market price scheduler could not start (no running event loop).")