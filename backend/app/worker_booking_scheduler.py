"""Background loop that keeps worker-booking statuses consistent.

The authoritative status logic lives in
``app.services.worker_booking_service``; this module only schedules that
logic on a cadence (mirroring ``app.market_scheduler``). Because the
overdue sweep is also invoked lazily on every booking read, the two layers
together guarantee that an overdue booking's status converges even if the
process is restarted or the loop is briefly unavailable.

The loop never "rewrites" bookings: ``run_overdue_sweep`` only changes rows
whose live status has genuinely expired, so repeated iterations are cheap.
"""

import asyncio
import logging
from datetime import datetime

from app.database.connection import SessionLocal
from app.services import worker_booking_service as svc

logger = logging.getLogger("worker_booking_scheduler")

_task = None

#: How often the overdue sweep runs (seconds). 30 minutes is a good balance
#: between freshness and load; every read also sweeps, so no booking waits
#: long to converge.
SWEEP_INTERVAL_SECONDS = 1800


def _run_sweep_once() -> dict:
    db = SessionLocal()
    try:
        return svc.run_overdue_sweep(db, now=datetime.utcnow())
    except Exception:  # pragma: no cover - defensive
        logger.exception("Worker booking overdue sweep crashed.")
        return {"inspected": 0, "missed": 0}
    finally:
        db.close()


async def _worker_booking_loop() -> None:
    # Give startup seeding a moment to finish before the first sweep.
    await asyncio.sleep(20)
    while True:
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None, _run_sweep_once
            )
            if result.get("missed"):
                logger.info(
                    "Worker booking sweep marked %s booking(s) as missed.",
                    result["missed"],
                )
        except asyncio.CancelledError:
            break
        except Exception:  # pragma: no cover - defensive
            logger.exception("Worker booking scheduler iteration failed.")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)


def start_worker_booking_scheduler() -> None:
    """Idempotently start the background overdue sweep."""
    global _task
    if _task is not None:
        return
    try:
        _task = asyncio.get_running_loop().create_task(_worker_booking_loop())
        logger.info("Worker booking status scheduler started (every %ss).", SWEEP_INTERVAL_SECONDS)
    except RuntimeError:
        _task = None
        logger.warning("Worker booking scheduler could not start (no running event loop).")


async def stop_worker_booking_scheduler() -> None:
    """Cancel and await the background overdue sweep during application shutdown."""
    global _task
    task = _task
    _task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass