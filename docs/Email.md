# Pick Reminder Emails — Implementation Plan

Automated emails reminding league members to submit their pick, sent every Wednesday before a tournament starts. Uses the existing SES + SQS + APScheduler stack — no new AWS services required.

---

## Background & Strategy

A single APScheduler job runs every Wednesday. It finds all upcoming tournaments starting that Thursday through the following Wednesday, creates a `PickReminder` record for each affected league (idempotent — UNIQUE constraint prevents duplicates), and immediately sends emails to any league member who hasn't picked yet.

**Why Wednesday?**
PGA Tour events typically start Thursday. Wednesday gives members ~12–24 hours to pick before Thursday morning tee times, while keeping email volume to exactly one reminder per tournament. This minimises SES cost.

**Why re-query unpicked members at send time (not at creation)?**
A member might pick between when the reminder was created and when it's due to send. Fetching live at send time avoids emailing people who have already picked.

---

## Concerns & Decisions

### Idempotency
A `UNIQUE(league_id, season_id, tournament_id)` constraint on `pick_reminders` ensures exactly one reminder record is ever created per tournament per league per season, even if the Wednesday job is somehow triggered more than once.

At send time, `sent_at IS NOT NULL` guards against re-sending if the APScheduler job fires twice in the same week.

### Out-of-Season Leagues
Reminders must only be sent when a league has an active season (`seasons.is_active = true`). A league with no active season is either between seasons or has never started one — members have no picks to submit, so emailing them would be confusing and wasteful.

`create_and_send_pick_reminders` enforces this at two points:
1. **Reminder creation**: only creates a `PickReminder` row if the league has an active season that includes the tournament in its schedule.
2. **Send step**: re-checks `is_active` before sending in case the season was deactivated between creation and send (unlikely but possible).

If a league has no active season, it is silently skipped — no error, no email, no reminder row.

### Pick Window Eligibility
Per the rules, picks can only be submitted after the previous tournament's earnings are published. If a member can't pick yet (window not open), a reminder is still useful — they should know the field is out and the window is coming — but the email copy should avoid implying they can submit right now. The send-time query checks the window status and adjusts the email CTA accordingly.

### SES Production Access
By default AWS SES is in sandbox mode, which only allows sending to pre-verified email addresses. **Before this feature can work in production, you must request SES production access (sandbox exit) from AWS.** This is a one-time manual approval that typically takes 24 hours. Also required: verify the `league-caddie.com` sending domain with DKIM/SPF DNS records so emails don't land in spam.

### Opt-Out / Unsubscribe
Pick reminders are notification emails, not purely transactional like password resets. CAN-SPAM requires a way to opt out. The plan adds a `pick_reminders_enabled` boolean preference per user (default `true`) and a simple toggle in account Settings. The send-time query filters out users who have opted out.

### Retry Handling
SES calls can fail transiently. Each reminder row tracks `attempt_count` and `max_attempts` (default 3). If a send fails, `attempt_count` is incremented and the record remains pending so the next scheduler run retries it. After `max_attempts` failures, `failed_at` is set so the record is skipped permanently. Failed reminders can be monitored by querying `pick_reminders WHERE failed_at IS NOT NULL`.

---

## Files to Create or Modify

| # | File | Action |
|---|------|--------|
| 1 | `alembic/versions/l8m0n2o4p6q8_add_pick_reminders.py` | **NEW** — migration #22 |
| 2 | `app/models/pick_reminder.py` | **NEW** — `PickReminder` ORM model |
| 3 | `app/models/__init__.py` | Export `PickReminder` |
| 4 | `app/models/user.py` | Add `pick_reminders_enabled` column + `pick_reminders` relationship |
| 5 | `app/models/league.py` | Add `pick_reminders` relationship |
| 6 | `app/models/tournament.py` | Add `pick_reminders` relationship |
| 7 | `app/models/season.py` | Add `pick_reminders` relationship |
| 8 | `app/services/pick_reminders.py` | **NEW** — `create_pick_reminders`, `send_pending_reminders` |
| 9 | `app/services/email.py` | Add `send_pick_reminder_email` |
| 10 | `app/services/scheduler.py` | Register `pick_reminder_send` APScheduler job (Wednesday noon UTC) |
| 11 | `app/schemas/user.py` | Add `pick_reminders_enabled` to `UserOut` + `UserUpdate` |
| 12 | `app/routers/users.py` | `PATCH /users/me` already handles `UserUpdate` — no router change needed |
| 13 | `fantasy-golf-frontend/src/pages/Settings.tsx` | Add opt-out toggle |
| 14 | `fantasy-golf-frontend/src/api/endpoints.ts` | Add `pick_reminders_enabled` to `User` interface |
| 15 | `fantasy-golf-backend/CLAUDE.md` | Document new model, service, scheduler job |
| 16 | `fantasy-golf-frontend/CLAUDE.md` | Document Settings toggle |

---

## 1. Migration #22

**File:** `alembic/versions/l8m0n2o4p6q8_add_pick_reminders.py`
**Revision:** `l8m0n2o4p6q8` | **Down revision:** `k7l9m1n3o5p7`

```sql
-- pick_reminders table
CREATE TABLE pick_reminders (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    league_id         UUID NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    season_id         INTEGER NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    tournament_id     UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    scheduled_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    sent_at           TIMESTAMP WITH TIME ZONE,
    failed_at         TIMESTAMP WITH TIME ZONE,
    error_message     TEXT,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    max_attempts      INTEGER NOT NULL DEFAULT 3,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_pick_reminders UNIQUE (league_id, season_id, tournament_id)
);

CREATE INDEX ix_pick_reminders_pending
    ON pick_reminders (scheduled_at)
    WHERE sent_at IS NULL AND failed_at IS NULL;

-- opt-out preference on users
ALTER TABLE users ADD COLUMN pick_reminders_enabled BOOLEAN NOT NULL DEFAULT TRUE;
```

Applied manually via psql per project convention — do not use `alembic upgrade head`.

---

## 2. ORM Model

**File:** `app/models/pick_reminder.py`

```python
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PickReminder(Base):
    __tablename__ = "pick_reminders"
    __table_args__ = (
        UniqueConstraint("league_id", "season_id", "tournament_id", name="uq_pick_reminders"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    tournament_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False)

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    league: Mapped["League"] = relationship(back_populates="pick_reminders")
    season: Mapped["Season"] = relationship(back_populates="pick_reminders")
    tournament: Mapped["Tournament"] = relationship(back_populates="pick_reminders")
```

Add `pick_reminders_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)` to `User`.

Add `pick_reminders: Mapped[list["PickReminder"]] = relationship(back_populates="league", cascade="all, delete-orphan")` to `League`, `Season`, and `Tournament`.

---

## 3. Pick Reminders Service

**File:** `app/services/pick_reminders.py`

### `create_pick_reminders(db, league_id, tournament) -> int`

Called from the Wednesday scheduler job. For the league:
- Fetch the active season (`is_active = true`); if none exists, return 0 immediately (out-of-season — skip silently)
- Confirm the tournament is in the league's schedule for that active season; if not, return 0
- Check if a `PickReminder` already exists (idempotency — UNIQUE constraint also protects this)
- Set `scheduled_at` to Wednesday noon UTC of the week the tournament starts (i.e. the Wednesday immediately before `tournament.start_date`)
- Insert the `PickReminder` row
- Return count of rows created

```python
def create_pick_reminders(db: Session, league_id, tournament: Tournament) -> int:
    ...
```

### `send_pending_reminders(db) -> dict`

Called by the APScheduler job twice daily. Finds all `PickReminder` rows where:
- `scheduled_at <= now()`
- `sent_at IS NULL`
- `failed_at IS NULL`
- `attempt_count < max_attempts`

For each pending reminder:
1. Load the tournament, season, and league
2. Query all approved `LeagueMember` rows for the league
3. For each member: skip if they already have a `Pick` for this tournament/season; skip if `user.pick_reminders_enabled` is `False`
4. Call `send_pick_reminder_email()` for each remaining member
5. On full success: set `sent_at = now()`, increment `attempt_count`
6. On failure: increment `attempt_count`; if `attempt_count >= max_attempts`, set `failed_at`

Returns `{"sent": int, "failed": int, "skipped": int, "errors": list}`.

```python
def send_pending_reminders(db: Session) -> dict:
    ...
```

---

## 4. Email Service Addition

**File:** `app/services/email.py`

Add alongside the existing `send_password_reset_email`. Same SES client (`_ses_client()`), same logging pattern.

```python
def send_pick_reminder_email(
    to_email: str,
    display_name: str,
    league_name: str,
    league_id: str,
    tournament_name: str,
    start_date: str,
    pick_window_open: bool,
) -> None:
```

**Email content:**
- Subject: `"Pick reminder: {tournament_name} starts {start_date}"`
- HTML + plain text bodies
- Green gradient header matching `send_password_reset_email` (`linear-gradient(to bottom right, #052e16, #14532d, #166534)`)
- Tournament name, start date, league name
- CTA button: "Submit your pick" → `{FRONTEND_URL}/leagues/{league_id}/pick` (only if `pick_window_open` is true; otherwise show "The pick window opens soon" message)
- Always log the email details at `INFO` level (essential for local dev with LocalStack)

---

## 5. Scheduler Integration

**File:** `app/services/scheduler.py`

Add a new job inside `start_scheduler()`:

```python
_scheduler.add_job(
    _run_send_pick_reminders,
    CronTrigger(day_of_week="wed", hour=12, minute=0),
    id="pick_reminder_send",
    replace_existing=True,
    misfire_grace_time=3600,
)
```

Add the job function:

```python
def _run_send_pick_reminders() -> None:
    """
    Every Wednesday at noon UTC: create reminder rows for this week's tournaments
    then immediately send to all unpicked members.
    """
    from app.database import SessionLocal
    from app.services.pick_reminders import create_and_send_pick_reminders

    db = SessionLocal()
    try:
        result = create_and_send_pick_reminders(db)
        log.info(
            "Pick reminders: sent=%d failed=%d skipped=%d",
            result["sent"], result["failed"], result["skipped"],
        )
        if result["errors"]:
            log.warning("Pick reminder errors: %s", result["errors"])
    except Exception as exc:
        log.error("Pick reminder job failed: %s", exc, exc_info=True)
    finally:
        db.close()
```

The job runs once per week — Wednesday at 12:00 UTC. It covers all tournaments starting Thursday through the following Wednesday (a full 7-day lookahead window). Because the job creates reminder rows then sends immediately in the same run, `scheduled_at` is set to "now" (Wednesday noon) rather than computed relative to `start_date`.

---

## 6. Frontend: Opt-Out Toggle

**File:** `src/pages/Settings.tsx`

Add a toggle in the existing Settings page (below the display name field):

```
Email notifications
[toggle] Remind me to pick every Wednesday before a tournament
```

- Reads `user.pick_reminders_enabled` from the auth store
- On toggle: calls `PATCH /users/me` with `{ pick_reminders_enabled: false }`
- Invalidates `["me"]` query on success

The `UserUpdate` schema and `PATCH /users/me` endpoint already exist — just add `pick_reminders_enabled: bool | None = None` to the schema and handle it in the route.

---

## 7. APScheduler Job Summary

| Job ID | Trigger | What it does |
|--------|---------|-------------|
| `pick_reminder_send` | Weekly Wednesday 12:00 UTC | Creates reminder rows for this week's tournaments and immediately sends to unpicked members |

All other existing jobs are unchanged.

---

## 8. Implementation Order

1. Write and apply migration #22 (adds `pick_reminders` table + `users.pick_reminders_enabled`)
2. Create `app/models/pick_reminder.py` + update `__init__.py`
3. Add relationship fields to `User`, `League`, `Season`, `Tournament`
4. Add `send_pick_reminder_email()` to `app/services/email.py`
5. Create `app/services/pick_reminders.py` (`create_and_send_pick_reminders` + `send_pending_reminders`)
6. Register `pick_reminder_send` job in `scheduler.py`
7. Add `pick_reminders_enabled` to `UserUpdate` schema + `UserOut` schema
8. Add opt-out toggle to `Settings.tsx`
9. Write tests (see below)
10. Update `fantasy-golf-backend/CLAUDE.md` and `fantasy-golf-frontend/CLAUDE.md`

---

## 9. Testing Checklist

- [ ] `create_and_send_pick_reminders` finds tournaments starting within the next 7 days
- [ ] `create_pick_reminders` skips leagues with no active season (`is_active = false` / no season row) — no reminder created, no email sent
- [ ] `create_pick_reminders` skips leagues where the active season does not include the tournament in its schedule
- [ ] `create_pick_reminders` is idempotent — calling twice creates only one row
- [ ] `send_pending_reminders` skips members who already have a pick
- [ ] `send_pending_reminders` skips members where `pick_reminders_enabled = false`
- [ ] `send_pending_reminders` increments `attempt_count` on failure
- [ ] `send_pending_reminders` sets `failed_at` after `max_attempts` failures
- [ ] `send_pending_reminders` sets `sent_at` on success
- [ ] `send_pending_reminders` does not email the same member twice (idempotent re-run)
- [ ] Settings toggle saves `pick_reminders_enabled = false` and persists across sessions

---

## 10. Pre-Deployment Checklist (Production Only)

- [ ] Request SES production access (sandbox exit) from AWS console — required before any emails reach non-verified addresses
- [ ] Verify `league-caddie.com` sender domain in SES (add DKIM + SPF DNS records) — prevents spam filtering
- [ ] Confirm `SES_FROM_EMAIL=noreply@league-caddie.com` is set in the K8s secret

---

## 11. Monitoring

After deployment, monitor via:

```sql
-- Pending (not yet sent)
SELECT COUNT(*) FROM pick_reminders WHERE sent_at IS NULL AND failed_at IS NULL;

-- Successfully sent
SELECT COUNT(*) FROM pick_reminders WHERE sent_at IS NOT NULL;

-- Permanently failed (needs investigation)
SELECT * FROM pick_reminders WHERE failed_at IS NOT NULL;
```

Permanently failed reminders mean a member did not receive their reminder. Manual follow-up (re-triggering the send or notifying the member another way) may be warranted depending on severity.
