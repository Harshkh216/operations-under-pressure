# Engineering Decisions

This document records five key engineering decisions for Operations Under Pressure, following the context / alternatives / chosen approach / trade-offs format.

---

## 1. Concurrency: Optimistic Concurrency Control via Version Counter

**Context:** Multiple users can view and edit the same work item simultaneously. Without a concurrency strategy, a contributor could overwrite a manager's reassignment, or two contributors could both claim the same item.

**Alternatives considered:**
- **Pessimistic locking** (`SELECT ... FOR UPDATE`): lock the row on read, release on commit. Prevents conflicts entirely but reduces throughput and can deadlock.
- **Last-write-wins**: no protection; the final save silently overwrites earlier ones. Simple but loses data.
- **Optimistic concurrency with version counter**: each row carries a `version` integer; the client sends the version it read; the server rejects a mismatch with HTTP 409.

**Chosen approach:** Optimistic concurrency with a version counter on `work_items`. Every UPDATE bumps `version` by 1. The PUT and transition endpoints require the client to send `version`; a mismatch yields `409 Conflict` with a human-readable message and the current version. The client is expected to refresh and retry.

**Trade-offs:**
- (+) No locks held between read and write, so no deadlock risk and high throughput for the common no-conflict case.
- (+) The 409 response includes the current version, so the UI can prompt "someone else modified this — refresh and retry."
- (−) The client must handle 409 retries; we handle this in the frontend by reloading the item on conflict.
- (−) Under heavy contention on a single item, clients may need several retries. For this workload (operations queue, not a counter), contention is rare.

---

## 2. Authorization: Application-Layer RBAC with Per-Team Roles

**Context:** Users belong to one or more teams with a per-team role (manager or contributor). A contributor on Team Alpha has no access to Team Beta's items. Managers can approve and reassign; contributors can claim and progress.

**Alternatives considered:**
- **Database-level RLS (PostgreSQL Row Level Security):** enforce isolation at the database. Powerful, but the FastAPI backend is the sole DB client (not the browser), so RLS would need a per-request DB role — complex with connection pooling.
- **A single global role column on users:** simpler but cannot model a user who is a manager on one team and a contributor on another.
- **Application-layer RBAC with a `team_members` join table:** each membership row carries a `role`; the API checks role + team membership per request.

**Chosen approach:** Application-layer RBAC. The `team_members` table stores `(team_id, user_id, role)`. Every endpoint that touches a work item first resolves the caller's membership for that item's team; a missing membership yields `403`. Role checks (e.g., "only managers can approve") are enforced in the workflow service. Team isolation is enforced at the query level: `WHERE team_id IN (user's team ids)`.

**Trade-offs:**
- (+) Rules are expressed in Python, unit-testable end-to-end via the TestClient.
- (+) Supports per-team roles (a user can be manager on one team, contributor on another).
- (+) Works identically on SQLite (tests) and PostgreSQL (production).
- (−) If the backend is bypassed (e.g., direct DB access), isolation is lost. In this architecture the browser never talks to the DB directly, so this is acceptable.
- (−) Every query must filter by team_ids; we mitigate with composite indexes on `(team_id, status)`.

---

## 3. Activity History: Transactional Write in the Same Unit of Work

**Context:** Every state-changing operation (create, update, claim, approve, etc.) must produce an immutable audit-trail entry. The history must never diverge from the current row state — no "orphaned" activity for a change that was rolled back, and no silent change without a history entry.

**Alternatives considered:**
- **Separate event log written after commit:** if the app crashes between commit and log-write, the history is lost. Unacceptable for an audit trail.
- **Database triggers:** write the activity row in an `AFTER UPDATE` trigger. Guaranteed transactional, but the logic (who acted, what action) lives in SQL, not the application — harder to test and maintain.
- **Application-layer write in the same SQLAlchemy session:** the activity row is added to the same session as the work-item mutation and committed together.

**Chosen approach:** The workflow service (`app/services/workflow.py`) adds an `ActivityEvent` row to the SQLAlchemy session in the same transaction as the work-item mutation. If the transaction commits, both the new state and the history are persisted. If it rolls back (e.g., on a 409 or IntegrityError), neither is — history and state never diverge.

**Trade-offs:**
- (+) Atomicity is guaranteed by the database transaction; no extra infrastructure.
- (+) The activity row includes `actor_id`, `action`, `detail`, and `version_after`, giving a complete timeline.
- (−) A failed transaction produces no history entry. This is intentional (the change didn't happen) but means failed attempts are not auditable. For this app, only committed changes matter.
- (−) One extra INSERT per mutation. Negligible for this workload.

---

## 4. Pagination: Server-Side with Total Count and Priority Ordering

**Context:** The work-item table can grow to hundreds or thousands of rows. The frontend needs paginated, searchable, filterable data with accurate page counts.

**Alternatives considered:**
- **Client-side pagination:** load all items, paginate in the browser. Simple but doesn't scale and sends unnecessary data.
- **Cursor-based pagination (keyset):** use `WHERE id > last_id LIMIT N`. Fast and stable but doesn't support jumping to arbitrary pages, and the total count requires a separate query.
- **Offset-based pagination with total count:** `SELECT ... OFFSET (page-1)*size LIMIT size` plus `SELECT COUNT(*)`. Supports page numbers and total count.

**Chosen approach:** Offset-based pagination with a separate count query. The API accepts `page` and `page_size` (capped at 100), returns `{ items, total, page, page_size }`. Ordering is by priority (urgent → low), then due date, then creation date. Filters support `status`, `priority`, `assignee_id`, `search` (ILIKE on title/description), and `view` (assigned_to_me, unassigned_urgent, awaiting_my_approval).

**Trade-offs:**
- (+) The frontend can render page numbers ("Page 2 of 7") and a Prev/Next control.
- (+) Filters and search are pushed to the database, not the client.
- (−) OFFSET on large tables is O(n) — the database skips rows. For this workload (hundreds, not millions, of items), this is fine. At scale, we would switch to keyset cursor pagination.
- (−) The COUNT(*) query doubles the query cost. We could cache it, but for now the simplicity wins.

---

## 5. Background Jobs: Transactional Outbox with Polling Worker

**Context:** When a work item changes state, downstream systems (notifications, audit pipelines, analytics) need to be informed. This must be reliable — no lost events even if the downstream is temporarily unavailable.

**Alternatives considered:**
- **Direct HTTP call after commit:** if the downstream is down, the event is lost. The business transaction has already committed.
- **Message queue (RabbitMQ / Kafka):** robust but adds infrastructure. Overkill for this challenge.
- **Transactional outbox pattern:** write an `outbox_events` row in the same DB transaction as the business change. A background worker polls for pending rows and attempts delivery with retry.

**Chosen approach:** Transactional outbox. The workflow service writes an `OutboxEvent` row (with a unique `idempotency_key` based on work-item ID + version + action) in the same transaction as the work-item mutation. A background asyncio task (`app/services/outbox.py`) polls every 2 seconds for `status='pending'` rows, attempts delivery (HTTP POST if `OUTBOX_SINK_URL` is set, log-only otherwise), and marks rows `done` or `failed` (after `max_attempts=5`). The `drain_once()` function is also exposed as an API endpoint for synchronous processing in tests.

**Trade-offs:**
- (+) Events are never lost: they're in the same transaction as the business change.
- (+) At-least-once delivery with idempotency keys for consumer-side deduplication.
- (+) No external infrastructure — the database is the queue.
- (−) Polling adds latency (up to 2s) vs. a push-based queue. Acceptable for this app; could be reduced with `LISTEN/NOTIFY` on PostgreSQL.
- (−) The worker runs in-process (asyncio task). If the process crashes, pending rows are simply picked up on restart — no data loss, but no parallelism. For higher throughput, a separate worker process could run `drain_once()`.
- (−) Failed events are marked `failed` and require manual intervention. A production system would alert on `failed` rows.
