# Email System

Transactional and notification emails sent via **Resend** (replaced AWS SES). When `RESEND_API_KEY` is empty (local dev), emails are logged at INFO level but not sent.

---

## Email Types

| Email | Sent by | Trigger |
|-------|---------|---------|
| Password reset | API container | `POST /auth/forgot-password` |
| Pick reminder | Worker container | `PICK_REMINDER_SEND` SQS event (Wednesday 18:00 UTC) |

## Configuration

| Env var | Container | Source |
|---------|-----------|--------|
| `RESEND_API_KEY` | API, Worker | Kubernetes secret |
| `EMAIL_FROM` | API, Worker | ConfigMap (`League Caddie <noreply@league-caddie.com>`) |
| `FRONTEND_URL` | API, Worker | ConfigMap (used for CTA links in emails) |

## Pick Reminder Flow

**Phase 1 — Detection (scraper, APScheduler):**
1. Wednesday 18:00 UTC (1 PM CDT): `_run_pick_reminder_send()` fires
2. `create_pick_reminders(db)` finds all scheduled tournaments starting within 7 days
3. For each tournament × league (with active season), creates a `PickReminder` row (idempotent via UNIQUE constraint)
4. Publishes a single `PICK_REMINDER_SEND` SQS trigger event (no payload)

**Phase 2 — Sending (worker, SQS):**
1. Worker receives `PICK_REMINDER_SEND` event
2. `send_pick_reminders(db)` queries all unsent `PickReminder` rows (`sent_at IS NULL AND failed_at IS NULL`)
3. For each reminder, finds unpicked, opted-in (`pick_reminders_enabled = true`), approved members
4. **Aggregates by user** — a user in 3 leagues gets **one email** listing all their unpicked leagues/tournaments
5. Sends via `send_pick_reminder_email()` (Resend)
6. Marks all related `PickReminder` rows as `sent_at = now()`
7. On failure: increments `attempt_count`; after `max_attempts` (3), sets `failed_at` permanently

**Email content:**
- Single league: subject = "Pick reminder: {tournament} starts {date}", body = single CTA button
- Multiple leagues: subject = "Pick reminder: N picks needed this week", body = table listing each league/tournament with individual "Pick now →" links
- Pick window closed: shows "Opens soon" instead of CTA button

## Opt-Out

Users toggle `pick_reminders_enabled` in Settings (`PATCH /users/me`). The send-time query filters out opted-out users. Default is `true`.

## Monitoring

```sql
-- Pending (not yet sent)
SELECT COUNT(*) FROM pick_reminders WHERE sent_at IS NULL AND failed_at IS NULL;

-- Successfully sent
SELECT COUNT(*) FROM pick_reminders WHERE sent_at IS NOT NULL;

-- Permanently failed
SELECT * FROM pick_reminders WHERE failed_at IS NOT NULL;
```

## Password Reset Flow

1. `POST /auth/forgot-password` → generates token, sends reset email via Resend
2. Email contains link to `{FRONTEND_URL}/reset-password?token={token}`
3. Token: `secrets.token_urlsafe(32)` raw, SHA-256 hash stored in DB; 1-hour TTL; single-use
4. `POST /auth/reset-password` validates token, sets new password, auto-logs in

## Local Development

`RESEND_API_KEY` is empty by default in `.env`. All emails are logged to the backend/worker console with full details (recipient, subject, URL) but not actually sent. To test locally: copy the URL from the console log and paste in browser.
