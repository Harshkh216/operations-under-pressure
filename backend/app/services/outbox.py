"""Transactional outbox processor.

A background asyncio task polls ``outbox_events`` for ``pending`` rows and
attempts delivery. For this demo the "delivery" is a no-op (configurable to
an HTTP POST via OUTBOX_SINK_URL); the point is to demonstrate the
at-least-once delivery pattern with retry and dead-letter (``failed``) on
exhaustion.

The processor is also exposed as a synchronous function ``drain_once`` so
the test suite can deterministically process the outbox without waiting for
the async loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import OutboxEvent

log = logging.getLogger("outbox")

_task: asyncio.Task | None = None


async def _deliver(event: OutboxEvent) -> None:
    """Perform the actual delivery. Raises on failure so the caller records it."""
    if settings.OUTBOX_SINK_URL:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                settings.OUTBOX_SINK_URL,
                json={"type": event.event_type, "key": event.idempotency_key, "payload": json.loads(event.payload)},
                headers={"Idempotency-Key": event.idempotency_key},
            )
            resp.raise_for_status()
    else:
        # Demo sink: log it. This is the "no-op webhook" used in dev/tests.
        log.info("outbox delivered event=%s key=%s payload=%s", event.id, event.idempotency_key, event.payload)


def drain_once() -> int:
    """Synchronously process up to ``MAX_PAGE_SIZE`` pending outbox rows.

    Returns the number of rows processed. Used by tests and by the async loop.
    Each row is handled in its own transaction so one failure does not roll
    back a batch of successes.
    """
    processed = 0
    max_attempts = settings.OUTBOX_MAX_ATTEMPTS
    while True:
        db = SessionLocal()
        try:
            event = db.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status == "pending")
                .order_by(OutboxEvent.created_at)
                .limit(1)
            ).scalars().first()
            if event is None:
                break

            event.attempts += 1
            try:
                # For the sync path we call the async deliver via asyncio.run
                # only when a real sink is configured; otherwise we skip the
                # event loop entirely for speed.
                if settings.OUTBOX_SINK_URL:
                    asyncio.run(_deliver(event))
                else:
                    log.info("outbox delivered event=%s key=%s", event.id, event.idempotency_key)
                event.status = "done"
                event.processed_at = datetime.now(timezone.utc)
            except Exception as exc:  # noqa: BLE001
                event.last_error = str(exc)[:500]
                if event.attempts >= max_attempts:
                    event.status = "failed"
            db.commit()
            processed += 1
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    return processed


async def _loop() -> None:
    while True:
        try:
            drain_once()
        except Exception as exc:  # noqa: BLE001
            log.exception("outbox drain failed: %s", exc)
        await asyncio.sleep(settings.OUTBOX_POLL_INTERVAL_SECONDS)


def start_outbox_processor() -> None:
    """Start the background loop if enabled and not already running."""
    global _task
    if not settings.OUTBOX_ENABLED:
        return
    if _task is not None and not _task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no running loop (e.g. sync test); skip
    _task = loop.create_task(_loop())


def stop_outbox_processor() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None


__all__ = ["start_outbox_processor", "stop_outbox_processor", "drain_once"]
