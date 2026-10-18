/*
# Operations Under Pressure — initial schema

Creates the full data model for the Operations Under Pressure backend:
teams, users, team_members, work_items, comments, activity_events,
outbox_events, and idempotency_records.

## Tables

1. `teams` — operations teams (e.g. Team Alpha, Team Beta).
2. `users` — app users with email/password auth (bcrypt hash stored).
3. `team_members` — join table with per-team role (manager | contributor).
4. `work_items` — the operational queue items with status, priority,
   assignee, and a `version` integer for optimistic concurrency control.
5. `comments` — comments on a work item.
6. `activity_events` — immutable audit trail written in the same
   transaction as every state-changing work-item mutation.
7. `outbox_events` — transactional outbox for reliable downstream delivery.
8. `idempotency_records` — stores prior request results keyed by
   Idempotency-Key header so repeat requests replay the original response.

## Indexes

- `ix_users_email` — email lookups at login.
- `ix_work_items_team_status`, `ix_work_items_assignee_status`,
  `ix_work_items_priority_status` — the API filters/sorts by these.
- `ix_comments_work_item_id` — listing comments per item.
- `ix_activity_workitem_created` — timeline queries.
- `ix_outbox_status_created` — the background worker polls pending rows.
- `ix_outbox_event_type` — event-type filtering.

## Security

This schema is used by a custom FastAPI backend that enforces authorization
in application code (not via Supabase RLS). The frontend talks to the FastAPI
API, not directly to Postgres. RLS is not enabled because the app does its
own auth/team-isolation logic.

## Important notes

1. All foreign keys use ON DELETE CASCADE where the child has no independent
   meaning (team_members, comments, activity_events, outbox_events, idempotency_records).
2. `work_items.assignee_id` uses ON DELETE SET NULL so deleting a user does
   not lose their work items.
3. `work_items.version` starts at 1 and is bumped on every UPDATE; clients
   must send the version they read, and a mismatch yields HTTP 409.
4. `outbox_events.idempotency_key` is unique so consumers can dedupe
   redelivered events (at-least-once delivery).
*/

CREATE TABLE IF NOT EXISTS teams (
  id SERIAL PRIMARY KEY,
  name VARCHAR(120) NOT NULL UNIQUE,
  slug VARCHAR(60) NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  full_name VARCHAR(120) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);

CREATE TABLE IF NOT EXISTS team_members (
  id SERIAL PRIMARY KEY,
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role VARCHAR(20) NOT NULL,
  CONSTRAINT uq_team_members_team_user UNIQUE (team_id, user_id)
);

CREATE TABLE IF NOT EXISTS work_items (
  id SERIAL PRIMARY KEY,
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  title VARCHAR(200) NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status VARCHAR(20) NOT NULL DEFAULT 'open',
  priority VARCHAR(10) NOT NULL DEFAULT 'medium',
  assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  version INTEGER NOT NULL DEFAULT 1,
  due_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_work_items_team_status ON work_items (team_id, status);
CREATE INDEX IF NOT EXISTS ix_work_items_assignee_status ON work_items (assignee_id, status);
CREATE INDEX IF NOT EXISTS ix_work_items_priority_status ON work_items (priority, status);

CREATE TABLE IF NOT EXISTS comments (
  id SERIAL PRIMARY KEY,
  work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
  author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_comments_work_item_id ON comments (work_item_id);

CREATE TABLE IF NOT EXISTS activity_events (
  id SERIAL PRIMARY KEY,
  work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
  actor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  action VARCHAR(40) NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  version_after INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_activity_workitem_created ON activity_events (work_item_id, created_at);

CREATE TABLE IF NOT EXISTS outbox_events (
  id SERIAL PRIMARY KEY,
  event_type VARCHAR(60) NOT NULL,
  payload TEXT NOT NULL,
  idempotency_key VARCHAR(120) NOT NULL UNIQUE,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_outbox_status_created ON outbox_events (status, created_at);
CREATE INDEX IF NOT EXISTS ix_outbox_event_type ON outbox_events (event_type);

CREATE TABLE IF NOT EXISTS idempotency_records (
  id SERIAL PRIMARY KEY,
  key VARCHAR(160) NOT NULL UNIQUE,
  status_code INTEGER NOT NULL,
  response_body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- updated_at trigger: bump updated_at on every work_items UPDATE.
CREATE OR REPLACE FUNCTION bump_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_work_items_updated_at ON work_items;
CREATE TRIGGER trg_work_items_updated_at
  BEFORE UPDATE ON work_items
  FOR EACH ROW
  EXECUTE FUNCTION bump_updated_at();
