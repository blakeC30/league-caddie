# Data Sync Design — ESPN API Integration

## Current State

The scraper (`app/services/scraper.py`) runs inside the FastAPI process via APScheduler with two jobs:
- **Daily at 06:00 UTC**: `full_sync()` — schedule + field + scores for active tournaments
- **Monday at 09:00 UTC**: same

All sync is one monolithic function. No live scoring during tournament rounds.

---

## Design Goals

1. Update leaderboard data frequently enough that users can track live results
2. Keep the ESPN API happy (no unofficial rate limit, but we should be respectful)
3. Isolate scraper failures from API availability
4. Keep infrastructure costs at zero (same t2.micro, same K3s cluster)

---

## Core Principle: Status-Driven, Not Calendar-Driven

**All scheduling decisions must be driven by data in the database — tournament status and stored tee times — not by hardcoded days of the week or static UTC time windows.**

Two failure modes this principle prevents:

**Time zone failure:** A static "11:00–01:00 UTC play window" assumes US Eastern tee times. PGA Tour events span multiple time zones:

| Location | UTC offset | 6:30am tee time in UTC | 8pm finish in UTC |
|---|---|---|---|
| US East (summer) | UTC-4 | 10:30 UTC | 00:00 UTC |
| US Pacific (summer) | UTC-7 | 13:30 UTC | 03:00 UTC |
| Hawaii | UTC-10 | 16:30 UTC | 06:00 UTC |
| UK/Ireland | UTC+0/+1 | 05:30 UTC | 19:00 UTC |

A static window centered on US Eastern time would completely miss a Hawaii or Europe event.

**Calendar failure:** Tournaments can and do run past Sunday. Rain delays, 36-hole days, and playoff carryovers all push play into Monday or even Tuesday. Hardcoding "Thu–Sun" for live sync and "Monday only" for finalization silently produces stale data when this happens.

---

## Decision 1: Separate Scraper Container

**Decision: Yes, extract the scraper into its own container.**

### Reasoning

The current design (APScheduler inside FastAPI) works for low-frequency syncs. Live tournament scoring changes the equation:

- During active rounds, we need to sync every 10 minutes
- Each sync makes ~200 HTTP calls to ESPN (one per golfer for linescores)
- Those 200 calls run in a thread pool inside the same process as the API
- If ESPN is slow, those threads are occupied — the API's request handling thread pool is shared

By splitting into a separate container:

| Concern | In-process (current) | Separate container |
|---|---|---|
| Scraper crash | Kills the API process | API unaffected |
| Live sync HTTP load | Competes with API threads | Fully isolated |
| Scraper deployment | Must redeploy API | Independent |
| Cost | No extra cost | No extra cost (same K8s node) |
| Complexity | Low | Slightly higher |

The last point is the only downside. The cost argument in favor of keeping it in-process doesn't apply here — another K8s pod on the same t2.micro node costs nothing extra.

### Architecture

The scraper container:
- Imports the same `app.services.scraper`, `app.models`, `app.database` modules (shared via the same Python package)
- Has no HTTP server — it only runs APScheduler and keeps the process alive
- Uses the same PostgreSQL connection config (shared env vars via K8s ConfigMap/Secrets)
- Has a separate Dockerfile: same Python base, same dependencies, different `CMD`

```
CMD ["python", "-m", "app.scraper_main"]
```

Where `scraper_main.py` starts the scheduler and blocks:

```python
# app/scraper_main.py
from app.services.scheduler import start_scheduler
import signal

start_scheduler()
signal.pause()  # block indefinitely; SIGTERM triggers clean shutdown
```

The API retains its existing admin endpoints (`POST /admin/sync`, `POST /admin/sync/{id}`) — these still call into the scraper service functions directly. They're useful for manual intervention and don't need to communicate with the scraper container.

---

## Decision 2: Sync Types

**Decision: Four distinct sync operations, each with its own schedule and overwrite policy.**

A single `full_sync()` that does everything is fine for daily background maintenance but wrong for live tournaments. Different data changes at different rates and requires different update policies.

### Sync Type 1: Schedule Sync

**Purpose:** Keep the tournament calendar current — names, dates, status transitions, team event flags.

**ESPN source:** `site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates={YYYY}`

**What it updates:**
- `tournaments.name`, `start_date`, `end_date`, `status`
- `tournaments.competition_id`, `is_team_event`
- Creates new tournament rows for newly announced events

**Overwrite policy:** Always overwrite. Tournaments get renamed (sponsor changes), rescheduled (weather, TV), and cancelled. Status transitions (scheduled → in_progress → completed) must always be reflected.

**Does NOT update:**
- `tournaments.multiplier` — this is platform-admin controlled, never overwritten by scraper
- `league_tournaments` rows — league-specific settings

**Schedule:**
- Daily at **06:00 UTC** — runs every day year-round
- Also: triggered manually via `POST /admin/sync`

**Rationale for daily:** PGA Tour sometimes announces schedule changes mid-week. Status transitions (in_progress on Thursday, completed on Sunday/Monday) need to flow through promptly.

---

### Sync Type 2: Field Sync

**Purpose:** Know which golfers are playing a specific tournament and when they tee off.

**ESPN source:** `/competitions/{competition_id}/competitors` + per-golfer `/linescores` for tee times

**What it updates:**
- `tournament_entries` rows (creates new entries for golfers in the field)
- `tournament_entries.tee_time` (Round 1 tee time — used for pick-locking)
- `tournament_entry_rounds` rows (Round 1 tee time row)
- Creates new `golfers` rows for previously-unknown golfers

**Overwrite policy:**
- Pre-tournament: fully additive/overwrite (fields change as players withdraw and alternates enter)
- Once in_progress: only add/update, never delete existing entries (a golfer who withdrew mid-round still has historical data)

**Schedule — relative to `start_date`, not day of week:**

The PGA Tour typically announces fields 2–3 days before play begins, and tee times confirm the morning of Round 1. Field sync must anchor to the tournament's `start_date` column, not a hardcoded weekday, because not all PGA events start on Thursday (e.g. WGC events, alternate-format events, and rained-out events sometimes start Wednesday or Saturday).

The pattern is:
- **`start_date - 2 days` at 14:00 UTC** — initial field release; most fields go out 2 days early
- **`start_date - 1 day` at 18:00 UTC** — catch late changes and alternates
- **`start_date` at 11:00 UTC** — final capture before first possible tee time; tee times are confirmed by now

The job implementation queries: "Is today within 2 days of any upcoming scheduled tournament's `start_date`?" and runs accordingly. If the answer is yes for multiple tournaments (simultaneous events), it runs for all of them.

**Rationale for three runs:** The PGA Tour releases fields incrementally. Alternates and last-minute entries can appear days after the initial announcement. The morning-of-start run is critical — tee times lock picks, so we need them before the round starts.

**What this does NOT do:** Update live scores. That's Sync Type 3.

---

### Sync Type 3: Live Score Sync

**Purpose:** Update leaderboard positions and per-round scores while a tournament is active.

**ESPN source:** `/competitions/{competition_id}/competitors` (positions, total score) + per-golfer `/linescores` (per-round detail)

**What it updates:**
- `tournament_entries.finish_position`, `is_tied`, `status`, `made_cut`, `total_score_to_par`
- `tournament_entry_rounds.score`, `score_to_par`, `position`, `is_playoff`

**Overwrite policy:** Always overwrite. Latest data replaces previous. This is idempotent.

---

#### Trigger: Status, Not Day of Week

Live sync runs whenever `tournament.status == "in_progress"`. There is no day-of-week filter.

This correctly handles:
- Standard Thu–Sun events
- Monday/Tuesday finishes due to weather delays
- Playoff carryovers (sudden death that wasn't resolved before dark)
- Any future format change

---

#### Play Window: Tee-Time-Driven with Wide Fallback

Rather than a static UTC window, the job dynamically computes today's expected play window from data already in the DB (`tournament_entry_rounds.tee_time` values, stored in UTC).

**Algorithm at the start of each run:**

```
1. Is there an in_progress tournament? If no → skip.

2. Query tournament_entry_rounds for tee times where:
      - tournament_id = active tournament
      - date(tee_time) = today (UTC date)
      - tee_time IS NOT NULL

3a. If tee times exist:
      play_start = min(tee_times) - 30 minutes   (buffer for pre-round coverage)
      play_end   = max(tee_times) + 5 hours       (generous finish buffer)
      → If current UTC time is outside [play_start, play_end]: skip this run

3b. If no tee times in DB yet (field not synced yet, or tee times not released):
      Use a wide conservative fallback window: 10:00–07:00 UTC (next day)
      This covers all possible PGA Tour locations:
        - US East summer (earliest): tees off ~10:30 UTC, finishes ~00:00 UTC
        - Hawaii (latest): tees off ~16:30 UTC, finishes ~06:00 UTC
      → If current UTC time is outside this window: skip
```

Once tee times are loaded into the DB (via the Thursday morning field sync), future runs tighten the window to the actual schedule. Until then, the wide fallback ensures no coverage gaps for any time zone.

**Why not just run 24/7 during tournament week?**
The skip-check is near-zero cost (one DB query). But running the actual sync when no one is on the course wastes ~200 ESPN calls for no user benefit. The tee-time-driven window avoids that without adding complexity.

---

#### Frequency

The scheduler fires the live sync job every **10 minutes**, unconditionally. The window check at the top of the job decides whether to do real work.

| Phase | Behavior |
|---|---|
| Within play window | Run full sync (~200 ESPN calls) |
| Outside play window, tournament in_progress | Skip (one DB query, nothing else) |
| No active tournament | Skip immediately |

**Off-season or between tournaments:** essentially zero ESPN calls.

**Why 10 minutes?** Users check in periodically — they're not watching a live ticker. 10 minutes feels live without excessive API load. Reducing to 5 minutes is a trivial config change if needed.

---

### Sync Type 4: Results Finalization

**Purpose:** Capture official final earnings after a tournament completes and trigger pick scoring.

**ESPN source:** `/competitions/{competition_id}/competitors/{competitor_id}/statistics` (earnings)

**What it updates:**
- `tournament_entries.earnings_usd` (official prize money)
- `tournament_entries.finish_position`, `made_cut`, `status` (final values)
- `picks.points_earned` for all picks in the tournament (via `score_picks()`)

**Overwrite policy:** Always overwrite. Official earnings sometimes differ from the in-progress estimate. Corrections to finish positions happen after review.

---

#### Trigger: Any Day a Tournament Completes, Not Just Monday

The old design ran finalization only on Monday mornings. This fails when:

- A rained-out event finishes Monday afternoon (after the 15:00 UTC run)
- A playoff carryover finishes Tuesday
- A weather-rescheduled event wraps up mid-week

**New approach: Run a finalization check three times daily, every day.**

The job logic:
```
1. Query for any tournament where:
      status == "completed"
      AND at least one pick exists with points_earned IS NULL

2. For each such tournament: run score_picks()
```

This job is fast when there's nothing to do (one DB query, returns empty). It self-heals for any finish time on any day of the week.

**Schedule:** 09:00, 15:00, and 21:00 UTC, every day.

| Run | What it catches |
|---|---|
| 09:00 UTC | Sunday night finishes (by Monday morning, ESPN earnings are official) |
| 15:00 UTC | Monday morning finishes, corrections posted mid-morning |
| 21:00 UTC | Monday afternoon finishes; any late-posted official results |

If a tournament finishes on a Tuesday (extreme delay), the 09:00 UTC Tuesday run catches it.

**Guard:** Before calling `score_picks()`, confirm `tournament.status == "completed"`. The daily schedule sync at 06:00 UTC updates status — so by the time the 09:00 finalization check runs, status is already current.

**Why separate from Live Score Sync?**
The earnings stat (`amount` or `officialAmount`) is only populated by ESPN after the tournament is officially complete. Calling the statistics endpoint during an `in_progress` tournament returns 0 or null. Running this separately prevents zeroing out pick scores with premature data.

---

## Sync Schedule Summary

| Sync Type | Frequency | Condition (from DB) |
|---|---|---|
| Schedule Sync | Daily, 06:00 UTC | Always |
| Field Sync | 3× before each tournament (`start_date - 2d`, `start_date - 1d`, `start_date` at 11:00 UTC) | Upcoming tournament within 2 days |
| Live Score Sync | Every 10 min, all days | `tournament.status == "in_progress"` AND within computed play window |
| Results Finalization | 3× daily (09:00, 15:00, 21:00 UTC) | Any completed tournament with unscored picks |

**No sync type uses a day-of-week constraint.** All conditions are derived from DB state.

---

## Decision 3: Overwrite Strategy Details

| Field | Overwrite? | Notes |
|---|---|---|
| `tournaments.name` | Yes | Sponsor changes |
| `tournaments.start_date` | Yes | Rescheduling |
| `tournaments.status` | Yes | State machine: scheduled → in_progress → completed |
| `tournaments.multiplier` | **Never** | Platform-admin controlled |
| `tournament_entries` rows | Add/update, no delete | Once created, entries stay |
| `tournament_entries.earnings_usd` | Only on finalization | Don't overwrite with nulls during live sync |
| `tournament_entry_rounds` | Yes during live sync | Latest scores replace previous |
| `golfers.name`, `country` | Yes | ESPN corrections |
| `golfers.world_ranking` | Yes | Changes weekly |
| `picks.points_earned` | Only when tournament completed | Never clear a scored pick |
| `league_tournaments.*` | **Never** | League-controlled settings |

---

## Decision 4: Manual Trigger Endpoints (unchanged)

The existing admin endpoints remain and work the same way:

| Endpoint | What it does |
|---|---|
| `POST /admin/sync` | Runs full_sync() — schedule + field + scores for active tournament |
| `POST /admin/sync/{pga_tour_id}` | Runs sync_tournament() for a specific tournament |

These call scraper functions directly (not via HTTP to the scraper container). Both the API and scraper containers import from the same `app.services.scraper` module. This is fine — the functions are stateless operations against the shared DB.

---

## Decision 5: Error Handling and Alerting

**Current:** Errors are logged but silently swallowed. The scraper never retries.

**New approach:**
- Each sync type catches exceptions, logs them with full traceback, and records a `last_error` and `last_error_at` timestamp in a new `sync_status` table (or a simple key/value settings table)
- No automatic retries on individual calls — if ESPN is flaky, the next scheduled run will self-heal
- The admin endpoints (`POST /admin/sync`) surface errors in the HTTP response rather than swallowing them, so platform admins can see what went wrong

We do NOT need an alerting system (PagerDuty, SNS email) for now — this is a private league app and the cost/complexity isn't justified. Log inspection via `kubectl logs` is sufficient.

---

## What Does NOT Change

- The ESPN API endpoints used (no changes to parsing logic)
- The `full_sync()` and `sync_tournament()` function signatures (used by admin endpoints)
- The DB schema (no new columns needed for this design)
- The frontend (leaderboard auto-refreshes every 60 seconds via React Query `refetchInterval` — no change needed)
- The `POST /admin/sync` endpoints

---

## Implementation Order (when we're ready to build)

1. Create `app/scraper_main.py` (entrypoint for scraper container)
2. Update `app/services/scheduler.py` — replace two jobs with four sync types + status-driven logic
3. Create `fantasy-golf-scraper/Dockerfile` (or add a second build stage)
4. Update `helm/` — add Scraper Deployment alongside existing API Deployment
5. Update CI/CD — build and push `fantasy-golf-scraper` image alongside `backend`
6. (Optional) Add `sync_status` table for error visibility

The scraper and API share the same Python source tree. No new package or microservice boundary is needed — just a different entrypoint.
