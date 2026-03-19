# Fantasy Golf Backend

FastAPI + Python + SQLAlchemy 2.0 app. See the root `CLAUDE.md` for project-wide rules and domain logic.

## Tech

- **FastAPI** — async HTTP framework, automatic OpenAPI at `/api/v1/docs` (DEBUG mode only)
- **SQLAlchemy 2.0** — ORM with `Mapped` / `mapped_column` typed columns
- **Alembic** — migrations (see Migration section below)
- **PostgreSQL** — primary DB
- **httpx** — sync HTTP client for ESPN API calls
- **APScheduler** (`BackgroundScheduler`) — time-driven sync jobs (schedule, field, live scores, finalization)
- **boto3** — AWS SDK; SQS client for publishing events (scraper) and consuming them (worker)
- **SQS** — event queue for playoff automation; LocalStack used locally (same code as production)
- **Ruff** — linting + formatting
- **pytest** — test runner

## Directory Structure

```
app/
├── main.py           # App init, router registration, CORS, lifespan (scheduler)
├── config.py         # Pydantic BaseSettings — reads .env; singleton `settings`
├── database.py       # SQLAlchemy engine + SessionLocal + get_db() dependency
├── dependencies.py   # FastAPI dependency functions (auth chain, league access chain)
├── scraper_main.py   # Scraper container entrypoint — starts APScheduler, blocks on signal
├── worker_main.py    # Worker container entrypoint — runs SQS consumer loop
├── models/           # SQLAlchemy ORM models
│   ├── user.py       # User
│   ├── league.py     # League, LeagueMember, LeagueMemberStatus, Season
│   ├── tournament.py # Tournament, TournamentEntry, TournamentStatus
│   ├── golfer.py     # Golfer
│   ├── pick.py       # Pick
│   ├── league_tournament.py  # LeagueTournament (join table)
│   ├── league_purchase.py    # StripeCustomer, LeaguePurchase, LeaguePurchaseEvent, StripeWebhookFailure
│   └── deleted_league.py     # DeletedLeague — audit snapshot written on league deletion; referenced by purchase tables
├── schemas/          # Pydantic request/response schemas
│   ├── auth.py       # RegisterRequest, LoginRequest, GoogleAuthRequest, TokenResponse
│   ├── user.py       # UserOut, UserUpdate
│   ├── league.py     # LeagueCreate/Update/Out, LeagueMemberOut, RoleUpdate,
│   │                 #   LeagueJoinPreview, LeagueRequestOut
│   ├── tournament.py # TournamentOut, LeagueTournamentOut (adds effective_multiplier + all_r1_teed_off), GolferInFieldOut (field endpoint — golfer + tee_time)
│   ├── golfer.py     # GolferOut
│   ├── pick.py       # PickCreate, PickUpdate, PickOut
│   ├── standings.py  # StandingsRow, StandingsResponse
│   └── stripe_schemas.py     # PricingTierOut, CheckoutSessionCreate/Out, LeaguePurchaseOut; PRICING_TIERS + TIER_ORDER constants
├── routers/
│   ├── auth.py       # /auth/*
│   ├── users.py      # /users/*
│   ├── leagues.py    # /leagues/*
│   ├── tournaments.py# /tournaments/*
│   ├── golfers.py    # /golfers/*
│   ├── picks.py      # /leagues/{league_id}/picks/*
│   ├── standings.py  # /leagues/{league_id}/standings
│   ├── playoff.py    # /leagues/{league_id}/playoff/* (config, bracket, draft, pods)
│   ├── stripe_router.py  # /stripe/* (pricing, checkout, webhook) + /leagues/{id}/purchase
│   └── admin.py      # /admin/* (platform admin only)
└── services/
    ├── auth.py       # hash_password, verify_password, create/decode JWT tokens, verify_google_id_token, generate/validate/consume_reset_token
    ├── email.py      # send_password_reset_email — AWS SES (LocalStack locally, real SES in prod)
    ├── picks.py      # validate_new_pick(), validate_pick_change(), all_r1_teed_off() — raises HTTPException
    ├── scoring.py    # calculate_standings() — returns list[dict]
    ├── scraper.py    # ESPN API client, upsert functions, full_sync / sync_tournament; publishes SQS events at status transitions
    ├── scheduler.py  # APScheduler setup — time-driven jobs only (schedule, field, live, finalization)
    ├── sqs.py        # boto3 SQS wrapper: publish(event_type, **payload) and consume(handler) — LocalStack locally, real SQS in prod
    └── playoff.py    # seed_playoff, resolve_draft, score_round, advance_bracket, override_result

alembic/
└── versions/         # Migration files — see Migration section
tests/
├── conftest.py                       # Test DB setup, fixtures (client, db, auth_headers, registered_user)
├── test_auth.py                      # Register, login, token refresh, /users/me
├── test_users.py                     # /users/me PATCH, /users/me/leagues
├── test_golfers.py                   # GET /golfers, GET /golfers/{id}
├── test_leagues.py                   # League CRUD, join flow, member mgmt, schedule
├── test_picks.py                     # Pick submission and validation
├── test_picks_extended.py            # My picks, all picks reveal rules, changes
├── test_scoring.py                   # Scoring arithmetic (pure unit tests)
├── test_standings.py                 # Season standings, ranking logic, tie-breaking
├── test_scraper.py                   # ESPN API parsing, upsert logic (unit, no HTTP)
├── test_password_reset.py            # forgot-password + reset-password flow (SES mocked)
├── test_accepting_requests.py        # leagues.accepting_requests flag enforcement
├── test_tournaments.py               # GET /tournaments, /field, /leaderboard, /sync-status
├── test_google_auth.py               # POST /auth/google (verify_google_id_token mocked)
├── test_league_ordering_and_caps.py  # League ordering, caps, request cancel/approve/deny, leave
├── test_playoff_service.py           # generate_draft_order, assign_pod_2, score_round, advance_bracket, resolve_draft, override_result (direct service calls)
└── test_playoff_api.py               # Playoff config CRUD, bracket seeding, full lifecycle (preferences → resolve → score → advance), manual override
```

## API Endpoints

All routes are prefixed with `/api/v1`.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/auth/register` | — | Returns access_token |
| POST | `/auth/login` | — | Sets httpOnly refresh_token cookie |
| POST | `/auth/google` | — | Google ID token → JWT pair |
| POST | `/auth/refresh` | cookie | Returns new access_token |
| POST | `/auth/logout` | token | Clears refresh cookie |
| POST | `/auth/forgot-password` | — | Send password reset email; always 200 (no email enumeration); 3/hour rate limit |
| POST | `/auth/reset-password` | — | Validate reset token, set new password, auto-login; 10/hour rate limit |
| GET | `/users/me` | token | Current user profile |
| PATCH | `/users/me` | token | Update display_name |
| GET | `/users/me/leagues` | token | User's approved leagues |
| POST | `/leagues` | token | Create league (creator → manager) |
| GET | `/leagues/join/{invite_code}` | token | Preview league (no side effects) |
| GET | `/leagues/my-requests` | token | User's pending requests |
| POST | `/leagues/join/{invite_code}` | token | Submit join request |
| GET | `/leagues/{league_id}` | member | League details |
| PATCH | `/leagues/{league_id}` | manager | Update name/penalty |
| GET | `/leagues/{league_id}/members` | member | Approved members only |
| PATCH | `/leagues/{league_id}/members/{user_id}/role` | manager | |
| DELETE | `/leagues/{league_id}/members/{user_id}` | manager | |
| GET | `/leagues/{league_id}/requests` | manager | Pending join requests |
| POST | `/leagues/{league_id}/requests/{user_id}/approve` | manager | |
| DELETE | `/leagues/{league_id}/requests/me` | token | User withdraws own request |
| DELETE | `/leagues/{league_id}/requests/{user_id}` | manager | Deny request |
| GET | `/leagues/{league_id}/tournaments` | member | League's selected tournaments (returns `LeagueTournamentOut` with `effective_multiplier` and `all_r1_teed_off`) |
| PUT | `/leagues/{league_id}/tournaments` | manager | Atomically replace schedule; body: `{tournaments: [{tournament_id, multiplier?}]}`; validates sufficient future tournaments for playoff config if pending |
| GET | `/tournaments` | token | All/filtered by status |
| GET | `/tournaments/{id}` | token | Tournament details |
| GET | `/tournaments/{id}/field` | token | Golfers in field — returns `GolferInFieldOut[]` (includes `tee_time`); WD golfers excluded; all others returned regardless of status so frontend can grey out teed-off golfers |
| GET | `/tournaments/{id}/leaderboard` | token | Full leaderboard with per-round data; includes `last_synced_at` (UTC ISO timestamp or null) set at end of each `sync_tournament` run |
| GET | `/tournaments/{id}/sync-status` | token | Lightweight: `{tournament_id, tournament_status, last_synced_at}` — poll every 30 s to detect new syncs without fetching full leaderboard |
| GET | `/golfers` | token | List/search golfers |
| GET | `/golfers/{id}` | token | Golfer details |
| POST | `/leagues/{league_id}/picks` | member | Submit pick |
| GET | `/leagues/{league_id}/picks/mine` | member | My picks this season |
| GET | `/leagues/{league_id}/picks` | member | All picks (completed tournaments only) |
| PATCH | `/leagues/{league_id}/picks/{pick_id}` | member | Change golfer |
| GET | `/leagues/{league_id}/standings` | member | Season standings |
| GET  | `/admin/stats` | platform_admin | Aggregated platform stats (counts only, no PII) |
| POST | `/admin/sync` | platform_admin | Full ESPN data sync |
| POST | `/admin/sync/{pga_tour_id}` | platform_admin | Sync single tournament |
| POST | `/leagues/{league_id}/playoff/config` | manager | Create playoff config for active season (always sets is_enabled=True) |
| GET | `/leagues/{league_id}/playoff/config` | member | Get playoff config |
| PATCH | `/leagues/{league_id}/playoff/config` | manager | Update config (only when status=pending) |
| GET | `/leagues/{league_id}/playoff/bracket` | member | Full bracket — all rounds, pods, picks |
| POST | `/leagues/{league_id}/playoff/rounds/{round_id}/open` | manager | Admin override: explicitly open draft for a round (no-op if already drafting). In normal flow this is not needed — bracket is auto-seeded when schedule locks and rounds start as "drafting"; subsequent rounds auto-open after advance |
| POST | `/leagues/{league_id}/playoff/rounds/{round_id}/resolve` | manager | Process preferences → picks (drafting→locked) |
| POST | `/leagues/{league_id}/playoff/rounds/{round_id}/score` | manager | Populate points_earned from tournament results |
| POST | `/leagues/{league_id}/playoff/rounds/{round_id}/advance` | manager | Determine winners, create next-round pods |
| GET | `/leagues/{league_id}/playoff/pods/{pod_id}` | member | Pod detail (members + picks) |
| GET | `/leagues/{league_id}/playoff/pods/{pod_id}/draft` | member | Draft status (who submitted, resolved picks) |
| GET | `/leagues/{league_id}/playoff/pods/{pod_id}/preferences` | member | My ranked preference list |
| PUT | `/leagues/{league_id}/playoff/pods/{pod_id}/preferences` | member | Submit/replace ranked preference list |
| POST | `/leagues/{league_id}/playoff/override` | manager | Manually set pod winner |
| GET | `/leagues/{league_id}/playoff/my-pod` | member | Lightweight playoff pod context for current user — always 200, returns `is_playoff_week=False` if no active playoff config; used by Dashboard/MakePick |
| GET | `/leagues/{league_id}/playoff/my-picks` | member | Current user's playoff picks per tournament (all rounds in active season) — own picks never hidden by R1 tee time check |
| GET | `/stripe/pricing` | — | List all four pricing tiers and their prices |
| POST | `/stripe/create-checkout-session` | manager | Create Stripe Checkout session; body: `{league_id, tier, upgrade?}` → returns `{url}` |
| POST | `/stripe/webhook` | — (Stripe sig) | Stripe webhook handler; handles `checkout.session.completed`; raw body required for signature verification |
| GET | `/leagues/{league_id}/purchase` | member | Current season purchase status for the league — NOT gated by require_active_purchase |

**Payment gating**: all operational endpoints (picks, standings, members, tournaments, playoff) require an active `LeaguePurchase.paid_at` for the current year. Returns HTTP 402 if unpurchased. Platform admin–created leagues are bypassed permanently; `require_active_purchase` returns `None` for them.

**CRITICAL — FastAPI route ordering**: Literal path segments must be defined BEFORE parameterized ones. Example in `leagues.py`:
```python
# These must come BEFORE /{league_id} and /{league_id}/requests/{user_id}
@router.get("/join/{invite_code}")
@router.get("/my-requests")
@router.delete("/{league_id}/requests/me")   # before /{league_id}/requests/{user_id}
```

## Dependency Chain

```
get_current_user          ← validates JWT access token from Authorization header
  └─ require_platform_admin   ← checks is_platform_admin
  └─ get_league_or_404    ← looks up league by league_id
       └─ require_league_member   ← checks approved membership
            └─ require_league_manager   ← checks manager role
            └─ require_active_purchase  ← 402 if no paid LeaguePurchase for current year;
                                           bypassed (returns None) when league creator OR
                                           current user is_platform_admin
  └─ get_active_season    ← gets active season for league
```

FastAPI caches dependency results within a single request — each runs once even if multiple route params depend on it.

## DB Session Pattern

```python
def my_route(db: Session = Depends(get_db)):
    obj = db.query(Model).filter_by(...).first()
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
```

Always call `db.commit()` explicitly. Never rely on auto-commit. Use `db.refresh(obj)` after insert to load server-generated fields (id, created_at).

## Models

### Key Column Types
- PKs: `UUID` with `default=uuid4`
- Auto-increment PKs (join tables): `Integer`, `autoincrement=True`
- Timestamps: `DateTime(timezone=True)`, `server_default=func.now()`
- Status enums: stored as plain strings (`String(20)`), not PostgreSQL ENUMs

### Schema Summary

| Table | Key Columns |
|-------|-------------|
| `users` | id (UUID), email (unique), password_hash (nullable), google_id (nullable), display_name, is_platform_admin |
| `password_reset_tokens` | id (UUID), user_id (FK→users, CASCADE), token_hash (SHA-256 hex, indexed), expires_at, used_at (nullable — set on redemption), created_at |
| `leagues` | id (UUID), name, invite_code (unique, 16-char token), is_public, no_pick_penalty (default=-50000) — no description column |
| `league_members` | league_id, user_id, role ("manager"\|"member"), status ("pending"\|"approved") |
| `seasons` | league_id, year (int), is_active; UNIQUE(league_id, year) |
| `tournaments` | pga_tour_id (unique), name, start_date, end_date, multiplier (float, default=1.0), status, competition_id (nullable), is_team_event (bool) |
| `tournament_entries` | tournament_id, golfer_id, tee_time, earnings_usd, finish_position, team_competitor_id (nullable) |
| `tournament_entry_rounds` | tournament_entry_id (FK→tournament_entries.id), round_number (int), tee_time (UTC, nullable), score (int, nullable), score_to_par (int, nullable), position (str(10), nullable), is_playoff (bool); UNIQUE(tournament_entry_id, round_number) |
| `golfers` | pga_tour_id (unique), name, world_ranking, country |
| `picks` | league_id, season_id, user_id, tournament_id, golfer_id, points_earned (nullable); UNIQUE(league_id, season_id, user_id, tournament_id) |
| `league_tournaments` | league_id, tournament_id, multiplier (float nullable); UNIQUE(league_id, tournament_id) |
| `playoff_configs` | id (UUID), league_id, season_id, is_enabled, playoff_size, draft_style, picks_per_round (JSON int array, one entry per round), status, seeded_at; UNIQUE(league_id, season_id) |
| `playoff_rounds` | id (int), playoff_config_id, round_number, tournament_id (nullable), draft_opens_at, draft_resolved_at, status; UNIQUE(playoff_config_id, round_number) |
| `playoff_pods` | id (int), playoff_round_id, bracket_position, winner_user_id (nullable), status; UNIQUE(playoff_round_id, bracket_position) |
| `playoff_pod_members` | id (int), pod_id, user_id, seed, draft_position, total_points (nullable), is_eliminated; UNIQUE(pod_id, user_id) |
| `playoff_picks` | id (UUID), pod_id, pod_member_id, golfer_id, tournament_id, draft_slot, points_earned; UNIQUE(pod_id, golfer_id) |
| `playoff_draft_preferences` | id (UUID), pod_id, pod_member_id, golfer_id, rank; UNIQUE(pod_member_id, golfer_id) |
| `stripe_customers` | id (UUID), user_id (FK→users, unique, CASCADE), stripe_customer_id (VARCHAR 64, unique), created_at |
| `deleted_leagues` | id (UUID, same as original league), name, created_by (UUID, no FK), created_at, deleted_at, deleted_by (UUID, no FK) — pure audit table, no FK constraints |
| `league_purchases` | id (UUID), league_id (FK→leagues SET NULL, nullable), deleted_league_id (FK→deleted_leagues RESTRICT, nullable), season_year (int), tier (VARCHAR 16), member_limit (int), stripe_customer_id, stripe_payment_intent_id, stripe_checkout_session_id, amount_cents, paid_at (nullable — null = unpaid/admin-exempt), created_at; UNIQUE(league_id, season_year) |
| `league_purchase_events` | id (UUID), league_id (FK→leagues SET NULL, nullable), deleted_league_id (FK→deleted_leagues RESTRICT, nullable), season_year (int), tier, member_limit, stripe IDs, amount_cents, event_type ("purchase"\|"upgrade"\|"initial"), paid_at, created_at; INDEX(league_id, season_year) |

### Points Formula
```
effective_multiplier = league_tournaments.multiplier  (if not NULL)
                     ?? tournament.multiplier           (global default)
points_earned = tournament_entry.earnings_usd × effective_multiplier
```
`tournament.multiplier` is the global default (1.0 standard, 2.0 majors, 1.5 The Players). League managers can override per-tournament via `league_tournaments.multiplier`. NULL means inherit the global default. `score_picks` resolves `effective_multiplier` per pick by looking up the `LeagueTournament` row.

## Migrations

**Local dev (docker-compose):** Apply via `psql` directly — avoid running alembic inside the container:

```bash
docker exec league-caddie-postgres-1 psql -U league_caddie -d league_caddie_dev -c "
  -- your DDL here
  UPDATE alembic_version SET version_num = '<new_revision>';
"
```

**Kubernetes (Helm):** The `migrate-job.yaml` Helm hook runs `alembic upgrade head` automatically as a pre-install/pre-upgrade Job. Helm waits for the Job to succeed before deploying application pods. No manual psql needed in K8s.

Existing migration files (in order):
1. `99fbdae03d30` — initial schema
2. `6ae0425f23c9` — expand golfer.country to 100 chars
3. `b721c01b567f` — add league_tournaments table
4. `a3f9c2b1d8e5` — remove slug, add invite_code
5. `1be05745ead6` — add invite_code, is_public, member status
6. `b7d4e1f2a9c3` — add is_team_event, competition_id, team_competitor_id
7. `c4e8a2f1b9d6` — rename admin role → manager
8. `d2e5f8a3c1b7` — add `league_tournaments.multiplier` (per-league override)
9. `e3f7a1c2d9b8` — add `tournament_entry_round_times` table (per-round tee times)
10. `f1a4b7c9e2d3` — replace `tournament_entry_round_times` with `tournament_entry_rounds` (full per-round data: score, score_to_par, position, tee_time, is_playoff)
11. `c9d3f2a8e5b1` — add `tournament_entries.is_tied` (bool, default false); finish_position now stores computed display position accounting for ties
12. `a1b2c3d4e5f6` — add playoff tables (playoff_configs, playoff_rounds, playoff_pods, playoff_pod_members, playoff_picks, playoff_draft_preferences)
13. `d4f6a2e8b1c9` — add `league_tournaments.is_playoff` (bool, default false)
14. `e5f1a9b2c3d4` — drop `league_tournaments.is_playoff` — playoff rounds are now auto-selected as the last N scheduled tournaments in the league's schedule
15. `e5g9b3c7f2a1` — replace `playoff_configs.round1_picks_per_player` + `subsequent_picks_per_player` with `picks_per_round` (JSONB int array, one element per round)
16. `g3h5i7j9k1l2` — drop `leagues.description` column
17. `h4i6j8k0l2m3` — add `tournaments.last_synced_at` (DateTime, nullable) — set by scraper after each full sync_tournament completes
18. `i5j7k9l1m3n5` — add `password_reset_tokens` table (forgot-password flow)
19. `j6k8l0m2n4o6` — add CHECK constraint `ck_users_has_auth_method` on `users` (password_hash IS NOT NULL OR google_id IS NOT NULL)
20. `k7l9m1n3o5p7` — replace `ix_users_email` (case-sensitive btree) with `ix_users_email_lower` (UNIQUE on LOWER(email))
21. `l8m0n2o4p6q8` — add `pick_reminders` table and `users.pick_reminders_enabled`
22. `m9n1o3p5q7r9` — add `leagues.accepting_requests` (BOOLEAN NOT NULL DEFAULT TRUE); when False, new join requests are blocked at the API level
23. `n0o2p4q6r8s0` — add `stripe_customers`, `league_purchases`, `league_purchase_events` tables; data migration backfills all existing leagues as Elite tier for 2026 at no cost
24. `o1p3q5r7s9t1` — preserve financial records on league deletion: add `deleted_leagues` audit table; `league_purchases.league_id` + `league_purchase_events.league_id` changed to nullable with `ON DELETE SET NULL`; `deleted_league_id` FK column added to both tables

New migrations still go in `alembic/versions/` with correct `down_revision` chaining.
- Local dev: apply manually via psql (above)
- Kubernetes: `helm upgrade` triggers the migration Job automatically

## Scraper

ESPN unofficial API — no auth required, but undocumented and may change.

- `sync_schedule(db, year)` — fetch PGA Tour schedule for a year, upsert Tournaments; also trims any post-Tour-Championship rows
- `sync_tournament(db, pga_tour_id)` — sync field + score picks; routes to team or individual path based on `is_team_event`
- `full_sync(db, year)` — sync schedule then all in-progress/completed + next scheduled tournament
- `score_picks(db, tournament)` — populate `picks.points_earned` for completed tournament
- `_trim_post_championship_tournaments(db)` — deletes any Tournament rows starting after the Tour Championship ends (called by `sync_schedule`)

**Tour Championship cutoff:** The Tour Championship is the last valid fantasy-season event. `parse_schedule_response` filters out any ESPN events that start after it ends. `sync_schedule` also calls `_trim_post_championship_tournaments` to clean up any rows that slipped in before this rule existed. Post-Tour-Championship tournaments cannot be added to any league schedule.

**Team events (Zurich Classic):** `competition_id` on Tournament may differ from `pga_tour_id`. Earnings fetched via `team_competitor_id` (stored on TournamentEntry), then divided by 2 for per-golfer share.

Manual trigger via `POST /admin/sync` (calls scraper functions directly, works from either container).

## Container Architecture

| Container | Entrypoint | Purpose |
|---|---|---|
| API | `app/main.py` (uvicorn) | HTTP API — no scheduler, no SQS |
| Scraper | `app/scraper_main.py` | APScheduler time-driven sync jobs; publishes SQS events |
| Worker | `app/worker_main.py` | SQS consumer loop; handles playoff finalization |
| Postgres | — | Database |
| LocalStack | — | Local SQS emulation (dev only, docker-compose) |

All containers connect to the same PostgreSQL DB. The scraper only writes; it serves no HTTP requests. The worker only consumes from SQS and writes to the DB.

### APScheduler Jobs (in `app/services/scheduler.py`)

All scheduling is **status-driven, not calendar-driven** — no hardcoded weekdays.

| Job ID | Schedule | Sync type | Fires when… | Skips when… | Data updated |
|---|---|---|---|---|---|
| `schedule_sync` | Daily 06:00 UTC | **Hard** (via `full_sync`) | Always | Never | Tournament names, dates, status, purse; removes post-Tour-Championship rows; force-clears and re-fetches round data for all in-progress/completed tournaments; publishes `TOURNAMENT_COMPLETED` SQS events |
| `field_sync_d2` | Daily 14:00 UTC | **Hard** | A SCHEDULED tournament's `start_date` == today+2 | No tournament starting in 2 days | Golfer roster, tee times, per-round data, purse — stale withdrawn golfers are removed |
| `field_sync_d1` | Daily 18:00 UTC | **Hard** | A SCHEDULED tournament's `start_date` == today+1 | No tournament starting tomorrow | Same as above — catches late withdrawals and alternates |
| `field_sync_d0` | Daily 11:00 UTC | **Hard** | A SCHEDULED tournament's `start_date` == today | No tournament starting today | Same as above — confirms final tee times (used for pick-locking) |
| `live_score_sync` | Every 5 minutes | Soft | `tournament.status == "in_progress"` AND within play window | No IN_PROGRESS tournament; outside play window; or `end_date` >3 days past | Per-round scores (strokes, score-to-par), finish positions, earnings, golfer status (CUT/WD/etc.); publishes `TOURNAMENT_IN_PROGRESS` while playoff rounds are unresolved |
| `results_finalization` | Daily 09:00, 15:00, 21:00 UTC | **Hard** | A COMPLETED tournament has at least one pick with `points_earned = NULL` | All picks already scored | Force-syncs the tournament first (fresh earnings), then sets `picks.points_earned` (golfer earnings × multiplier); safety net if SQS `TOURNAMENT_COMPLETED` pipeline missed anything |
| `pick_reminder_send` | Wednesday 12:00 UTC | N/A | Always — looks for upcoming tournaments in next 7 days | Leagues with no active season (silently skipped) | Creates `PickReminder` rows; sends reminder emails to members who haven't picked |

**Live sync play window:** Computed from `tournament_entry_rounds.tee_time` values stored in the DB (UTC-aware). If no tee times yet: wide fallback `[10:00–07:00 UTC]` covers all PGA Tour locations (US East through Hawaii). No day-of-week restriction — Monday weather carryovers continue syncing automatically.

**Results finalization:** 3× daily so any finish time on any day is caught. Acts as a safety net if the SQS `TOURNAMENT_COMPLETED` pipeline missed anything.

### SQS Worker (in `app/worker_main.py`)

The worker handles event-triggered operations that don't belong on a clock.

| Event | Published by | Consumer action |
|---|---|---|
| `TOURNAMENT_IN_PROGRESS` | `sync_tournament()` (every 5 min while in_progress + unresolved rounds) | `resolve_draft()` for any "drafting" playoff rounds once `any_r1_teed_off()` returns True |
| `TOURNAMENT_COMPLETED` | `sync_schedule()` on status transition | `score_picks()` → `score_round()` → `advance_bracket()` in order |

All handlers are **idempotent** — SQS at-least-once delivery is safe. The visibility timeout (120 s) prevents two worker pods from processing the same message simultaneously.

**Local dev:** LocalStack emulates SQS locally. Queue auto-created by `localstack-init/create-queues.sh`. Set `SQS_QUEUE_URL` env var (see docker-compose.yml). If `SQS_QUEUE_URL` is unset, publish calls are silently skipped.

**Production:** EC2 instance profile provides SQS credentials — no access keys in env vars. `AWS_ENDPOINT_URL` is absent in production; boto3 uses real AWS. Queue names: `league-caddie-events-prod` / `league-caddie-events-prod-dlq`. See `SQS.md` in the project root for AWS setup steps.

**DLQ monitoring:** After 3 failed delivery attempts a message moves to the DLQ. Non-zero DLQ depth means a finalization step failed permanently and needs manual investigation.

## Testing

```bash
# Run all tests
docker compose exec backend python -m pytest tests/ -v

# Run specific file
docker compose exec backend python -m pytest tests/test_scoring.py -v
```

Test DB: `league_caddie_test` (separate from dev). Fixtures in `conftest.py` truncate tables after every test. Key fixtures: `client` (FastAPI TestClient), `db` (SQLAlchemy session), `auth_headers` (Authorization header dict), `registered_user` (creates user + returns token).

Coverage baseline: **62%** (enforced by `fail_under = 62` in pyproject.toml). Untested areas: scraper HTTP calls (19%), SQS worker (0%), email service (21%), APScheduler jobs (0%), pick_reminders service (0%).

## Error Handling

```python
raise HTTPException(status_code=422, detail="Tournament is not in this league's schedule")
```

- Use `422` for business rule violations (invalid pick, wrong status, etc.)
- Use `404` for resource not found
- Use `403` for authorization failures
- Use `401` for authentication failures
- Services raise `HTTPException` directly — routers don't need try/catch for expected failures
