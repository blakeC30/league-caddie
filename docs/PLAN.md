# Fantasy Golf Website — Implementation Plan

## Context

Modernize a private fantasy golf league from spreadsheets/Google Forms to a full web application. The app supports multiple independent leagues from day one. Stack: React + TypeScript (frontend), FastAPI + Python (backend), PostgreSQL, Docker, K3s (Kubernetes), Helm, GitHub Actions (CI/CD), AWS (free tier). Cost is the primary constraint — must stay as close to free as possible.

---

## Architecture Overview

```
Browser → Nginx (frontend) → FastAPI (backend) → PostgreSQL
                                    ↑
                    SQS Event Bus ──┤
                    (LocalStack)    │
                         ↑          │
                    Scraper ────────┘
                  (APScheduler)
                         │
                    SQS Worker
               (playoff automation)
```

All components run in Docker (locally) and in K3s on EC2 (dev + prod). Dev and prod run on **separate EC2 instances** — a t2.micro (free tier) for dev and a t3a.small for prod. There are **three backend processes** — they share one codebase and Docker image but run different entrypoints:

| Container | Entrypoint | Purpose |
|---|---|---|
| `backend` | `uvicorn app.main:app` | HTTP API — all user-facing endpoints |
| `scraper` | `python -m app.scraper_main` | APScheduler jobs — ESPN sync, live scores |
| `worker` | `python -m app.worker_main` | SQS consumer — playoff automation triggers |

This separation means scraper failures cannot take down the API, and the three can be deployed/restarted independently.

---

## Cost Plan

### During AWS Free Tier (first 12 months after account creation)
| Resource | Cost |
|---|---|
| EC2 t2.micro — dev (K3s, all dev services) | FREE (750 hrs/month) |
| EC2 t3a.small — prod (K3s, all prod services) | ~$14/month |
| ECR (container registry) | FREE (500 MB storage) |
| SES (email) | FREE (3,000 emails/month first 12 months) |
| SQS | FREE (1M requests/month free tier) |
| GitHub Actions (public repo) | FREE (unlimited minutes) |
| **Total** | **~$15/month** |

### After Free Tier (month 13+)
| Resource | Est. Cost |
|---|---|
| EC2 t2.micro — dev | ~$8.50/month |
| EC2 t3a.small — prod | ~$14/month |
| SES | $0.10/1,000 emails (effectively $0 at this scale) |
| SQS | $0.40/1M requests (effectively $0 at this scale) |
| **Total** | **~$23.50/month** |

> **Note:** Dev uses a t2.micro (free tier, 1 GB RAM, 1 vCPU). Prod uses a t3a.small (2 GB RAM, 2 vCPU, AMD EPYC — ~10% cheaper than t3.small for equivalent specs) for headroom running 2 backend replicas + scraper + worker + Postgres + Nginx simultaneously.

> **Note:** The dev EC2 can be terminated later to cut costs — when ready, push directly to `main` and deploy to prod only.

> **Note:** EKS costs $0.10/hr for the control plane alone ($72/month). We use K3s on EC2 — identical Kubernetes experience at zero extra cost.

> **Note:** AWS credentials are empty on both instances — the EC2 IAM instance role automatically provides credentials for SES and SQS. Only `AWS_REGION` and `SES_FROM_EMAIL` need to be configured in the Helm chart secrets.

---

## Phase 0: Foundation & Project Setup ✅ COMPLETE

Monorepo initialized at `FantasyGolf/` with `frontend/` and `backend/` as siblings.

- Git repo initialized and pushed to GitHub (public)
- `.gitignore`, `.editorconfig` in place
- Backend: Python project with `uv` + `pyproject.toml`; all dependencies installed
- Frontend: Vite + React + TypeScript; all packages installed
- `docker-compose.yml` at repo root for local development

---

## Phase 1: Database Design & Migrations ✅ COMPLETE

### 19 ORM Models (SQLAlchemy 2.0)

| Model | Key Columns |
|---|---|
| **User** | id (UUID), email (unique), password_hash (nullable), google_id (nullable, unique), display_name, is_platform_admin |
| **PasswordResetToken** | id, user_id (FK cascade), token_hash (SHA-256, indexed), expires_at, used_at (nullable) |
| **League** | id, name, invite_code (unique, 22-char), is_public, no_pick_penalty (int, default −50000), created_by |
| **LeagueMember** | league_id + user_id (unique), role (manager/member), status (pending/approved) |
| **Season** | league_id + year (unique), is_active (partial unique index) |
| **Tournament** | pga_tour_id (unique), name, start_date, end_date, multiplier, purse_usd, status, competition_id, is_team_event, last_synced_at |
| **TournamentEntry** | tournament_id + golfer_id (unique), tee_time (R1 UTC), finish_position, is_tied, earnings_usd, status, team_competitor_id |
| **TournamentEntryRound** | tournament_entry_id + round_number (unique), tee_time, score, score_to_par, position, is_playoff, thru, started_on_back |
| **Golfer** | pga_tour_id (unique), name, world_ranking, country |
| **Pick** | league_id + season_id + user_id + tournament_id (unique), golfer_id, points_earned (float, nullable) |
| **LeagueTournament** | league_id + tournament_id (unique), multiplier (float, nullable — NULL inherits global) |
| **PlayoffConfig** | league_id + season_id (unique), is_enabled, playoff_size, draft_style (snake), picks_per_round (JSON), status |
| **PlayoffRound** | playoff_config_id + round_number (unique), tournament_id (FK, nullable), draft_opens_at, draft_resolved_at, status |
| **PlayoffPod** | playoff_round_id + bracket_position (unique), winner_user_id (nullable), status |
| **PlayoffPodMember** | pod_id + user_id (unique), seed, draft_position, total_points, is_eliminated |
| **PlayoffPick** | pod_id + golfer_id (unique), pod_member_id, tournament_id, draft_slot, points_earned |
| **PlayoffDraftPreference** | pod_member_id + golfer_id (unique), pod_member_id + rank (unique) |

### 18 Alembic Migrations (applied)

| # | Revision | Description |
|---|---|---|
| 1 | `99fbdae03d30` | Initial schema (users, leagues, seasons, tournaments, golfers, entries, picks) |
| 2 | `6ae0425f23c9` | Expand golfer.country to 100 chars |
| 3 | `b721c01b567f` | Add league_tournaments table |
| 4 | `a3f9c2b1d8e5` | Remove slug, add invite_code |
| 5 | `1be05745ead6` | Add is_public, member status (pending/approved) |
| 6 | `b7d4e1f2a9c3` | Add is_team_event, competition_id, team_competitor_id |
| 7 | `c4e8a2f1b9d6` | Rename admin role → manager |
| 8 | `d2e5f8a3c1b7` | Add league_tournaments.multiplier |
| 9 | `e3f7a1c2d9b8` | Add tournament_entry_round_times table (interim) |
| 10 | `f1a4b7c9e2d3` | Replace with tournament_entry_rounds (full per-round data) |
| 11 | `c9d3f2a8e5b1` | Add tournament_entries.is_tied |
| 12 | `a1b2c3d4e5f6` | Add all 6 playoff tables |
| 13 | `d4f6a2e8b1c9` | Add league_tournaments.is_playoff (interim) |
| 14 | `e5f1a9b2c3d4` | Drop is_playoff (auto-select playoffs at seeding) |
| 15 | `e5g9b3c7f2a1` | Replace round1/subsequent picks → picks_per_round (JSON array) |
| 16 | `g3h5i7j9k1l2` | Drop leagues.description |
| 17 | `h4i6j8k0l2m3` | Add tournaments.last_synced_at |
| 18 | `i5j7k9l1m3n5` | Add password_reset_tokens table |

**Run migrations:** `docker compose exec backend alembic upgrade head`

---

## Phase 2: Backend Core — Auth & API ✅ COMPLETE

### Directory Structure (actual)

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, rate limiter, router registration
│   ├── config.py            # Pydantic BaseSettings (env vars)
│   ├── database.py          # SQLAlchemy engine + session
│   ├── dependencies.py      # get_db, get_current_user, require_league_member, require_league_manager, etc.
│   ├── limiter.py           # slowapi rate limiter
│   ├── scraper_main.py      # APScheduler entrypoint (scraper container)
│   ├── worker_main.py       # SQS consumer entrypoint (worker container)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── password_reset_token.py
│   │   ├── league.py
│   │   ├── season.py
│   │   ├── tournament.py
│   │   ├── golfer.py
│   │   ├── pick.py
│   │   └── playoff.py
│   ├── schemas/
│   │   ├── auth.py, user.py, league.py, tournament.py, golfer.py, pick.py, standings.py, playoff.py
│   ├── routers/
│   │   ├── auth.py          # register, login, google, refresh, logout, forgot-password, reset-password
│   │   ├── users.py
│   │   ├── leagues.py
│   │   ├── tournaments.py
│   │   ├── golfers.py
│   │   ├── picks.py
│   │   ├── standings.py
│   │   ├── playoff.py
│   │   └── admin.py
│   └── services/
│       ├── auth.py          # bcrypt hashing, JWT, Google token verify, reset tokens
│       ├── email.py         # AWS SES (LocalStack in dev), HTML + plain text email
│       ├── picks.py         # Pick validation, tee-off lock, no-repeat enforcement
│       ├── scoring.py       # Season standings calculation
│       ├── scraper.py       # ESPN API client, upsert functions, sync orchestration
│       ├── scheduler.py     # APScheduler job definitions
│       ├── sqs.py           # boto3 SQS publish/consume
│       └── playoff.py       # Playoff lifecycle (seed, draft, score, advance, override)
├── alembic/
│   ├── env.py
│   └── versions/            # 18 migration files
├── tests/
│   ├── conftest.py          # Test DB + fixtures
│   ├── test_auth.py
│   ├── test_picks.py
│   ├── test_scraper.py
│   └── test_scoring.py
├── Dockerfile               # Multi-stage production image
├── Dockerfile.dev           # Dev image (no multi-stage, volume mounts)
└── pyproject.toml
```

### Auth Flow

**Email/Password:**
1. `POST /auth/register` → hash password (bcrypt), create user, issue JWT pair
2. `POST /auth/login` → verify password, return access token (15min) + refresh token (7 day httpOnly cookie)

**Google OAuth (ID token flow):**
1. Frontend renders Google Sign-In button via `@react-oauth/google`
2. User clicks → Google popup → `credential` (ID token) returned to frontend
3. `POST /auth/google` → backend verifies with `google-auth`, find-or-create user, issue JWT pair

**Password Reset:**
1. `POST /auth/forgot-password` → always 200; if email/password account exists, generates SHA-256-hashed token, sends HTML email via AWS SES (URL also logged for local dev); rate limited 3/hour
2. `POST /auth/reset-password` → validates token (1 hour TTL, single-use), updates password, marks token used, auto-logs user in by returning new JWT pair; rate limited 10/hour

**Token rotation:** `POST /auth/refresh` reads httpOnly cookie, returns new access token.

### All API Endpoints

```
# Auth
POST  /auth/register               # Email/password registration (min 8 char password)
POST  /auth/login                  # Email/password login
POST  /auth/google                 # Google ID token → find/create user → issue JWT
POST  /auth/refresh                # Rotate access token via httpOnly refresh cookie
POST  /auth/logout                 # Clear refresh cookie
POST  /auth/forgot-password        # Request password reset email (always 200)
POST  /auth/reset-password         # Redeem token, set new password, auto-login

# Users
GET   /users/me                    # Current user profile
PATCH /users/me                    # Update display name
GET   /users/me/leagues            # User's approved leagues (for header)

# Leagues
POST  /leagues                     # Create league (creator becomes manager)
GET   /leagues/{id}                # League detail
PATCH /leagues/{id}                # Update name/penalty (manager only)
DELETE /leagues/{id}               # Delete league (manager only)
GET   /leagues/{id}/members        # All approved members
PATCH /leagues/{id}/members/{uid}/role   # Change member role (manager only)
DELETE /leagues/{id}/members/{uid}       # Remove member (manager only)
GET   /leagues/{id}/requests       # Pending join requests (manager only)
POST  /leagues/{id}/requests/{uid}/approve
DELETE /leagues/{id}/requests/{uid}
GET   /leagues/join/{invite_code}  # Preview invite (name, member count)
POST  /leagues/join/{invite_code}  # Submit join request
GET   /leagues/{id}/tournaments    # League's selected tournaments
PUT   /leagues/{id}/tournaments    # Update tournament selections + per-league multipliers (manager only)

# Tournaments
GET   /tournaments                 # List all (filter: status, or "all")
GET   /tournaments/{id}
GET   /tournaments/{id}/field      # Golfers in field with R1 tee times
GET   /tournaments/{id}/leaderboard  # Live/final leaderboard with per-round data
GET   /tournaments/{id}/sync-status  # Polling endpoint for live sync state
GET   /tournaments/{id}/golfers/{gid}/scorecard  # Per-golfer, per-round scorecard

# Golfers
GET   /golfers                     # List/search by name
GET   /golfers/{id}

# Picks
POST  /leagues/{id}/picks          # Submit pick (enforces no-repeat, deadline, tee-off lock)
PATCH /leagues/{id}/picks/{pick_id}  # Change pick (same rules as submit)
PUT   /leagues/{id}/picks/admin-override   # Manager force-set a pick
GET   /leagues/{id}/picks/mine     # My picks this season
GET   /leagues/{id}/picks          # All picks (completed tournaments only)
GET   /leagues/{id}/picks/tournament/{tid}  # Summary: who picked whom + points

# Standings
GET   /leagues/{id}/standings      # Season standings with tie handling + penalties

# Playoffs
POST  /leagues/{id}/playoff/config   # Create playoff config (manager only)
GET   /leagues/{id}/playoff/config
PATCH /leagues/{id}/playoff/config   # Update config (manager only)
GET   /leagues/{id}/playoff/bracket  # Full bracket (all rounds, pods, members)
GET   /leagues/{id}/playoff/my-pod   # Current user's active pod
GET   /leagues/{id}/playoff/my-picks # User's playoff picks
POST  /leagues/{id}/playoff/rounds/{rid}/open     # Open draft window (manager)
POST  /leagues/{id}/playoff/rounds/{rid}/resolve  # Resolve draft → assign picks (manager)
POST  /leagues/{id}/playoff/rounds/{rid}/score    # Score round (manager)
POST  /leagues/{id}/playoff/rounds/{rid}/advance  # Advance winners (manager)
GET   /leagues/{id}/playoff/pods/{pid}
GET   /leagues/{id}/playoff/pods/{pid}/draft-status
GET   /leagues/{id}/playoff/pods/{pid}/preferences  # My preference list
PUT   /leagues/{id}/playoff/pods/{pid}/preferences  # Submit ranked preference list
POST  /leagues/{id}/playoff/override   # Override a result (manager)

# Admin (platform admin only)
POST  /admin/sync                  # Full ESPN sync (all tournaments)
POST  /admin/sync/{pga_tour_id}    # Single tournament sync (optional force-refresh)

# Health
GET   /health                      # Kubernetes liveness probe
```

---

## Phase 3: Web Scraping & Data Integration ✅ COMPLETE

### ESPN API Integration

**Endpoints used:**
- `site.api.espn.com/.../pga/scoreboard?dates={YYYY}` — full year schedule
- Core API: `/events/{id}/competitions/{comp_id}/competitors?limit=200` — field
- Core API: `/competitors/{id}/roster` — team rosters (Zurich Classic)
- Core API: `/competitors/{id}/statistics` — earnings (officialAmount ÷2 for teams)
- Core API: `/competitors/{id}/linescores` — per-round data (tee time, score, position, playoff flag)
- Core API: `/athletes/{id}` — golfer name + country

### Scraper Architecture

Pure parsing functions (no DB side effects) are separated from upsert functions for testability:

```
parse_schedule_response()   → extract tournaments, trim post-Tour-Championship
parse_field_response()      → extract golfers, tee times, team competitors
parse_results_response()    → extract finish positions, earnings, withdrawals
upsert_tournaments()        → create/update Tournament rows
upsert_field()              → create/update TournamentEntry + Golfer rows
upsert_round_data()         → populate TournamentEntryRound per-round data
score_picks()               → Pick.points_earned = earnings × effective_multiplier
sync_schedule(db, year)     → full year schedule sync
sync_tournament(db, id)     → sync field + score picks for one tournament
full_sync(db, year)         → sync schedule + in_progress/completed + next scheduled
```

### Scheduler Jobs (APScheduler — scraper container)

| Job | Schedule | Purpose |
|---|---|---|
| schedule_sync | Daily 06:00 UTC | Full schedule sync; publishes TOURNAMENT_COMPLETED on status transitions |
| field_sync_d2 | Daily 14:00 UTC, T−2 days | Sync field + tee times |
| field_sync_d1 | Daily 18:00 UTC, T−1 day | Sync field + tee times |
| field_sync_d0 | Daily 11:00 UTC, T−0 | Sync field + tee times |
| live_score_sync | Every 5 minutes | In-progress tournaments; publishes TOURNAMENT_IN_PROGRESS for unresolved playoff rounds |
| results_finalization | Daily 09:00, 15:00, 21:00 UTC | Safety net: score picks if SQS worker missed it |

**Live sync window:** Computed from TournamentEntryRound.tee_time values. Fallback: 10:00–07:00 UTC (covers US East through Hawaii).

### SQS Event Pipeline

| Event | Published By | Handler (worker container) |
|---|---|---|
| TOURNAMENT_IN_PROGRESS | live_score_sync (every 5 min) | resolve_draft() when R1 tee-offs detected in "drafting" playoff rounds |
| TOURNAMENT_COMPLETED | schedule_sync on status transition | score_picks() → score_round() → advance_bracket() |

LocalStack emulates SQS locally (same boto3 code, no real AWS cost). Queue: `fantasy-golf-events-dev` with DLQ after 3 retries.

---

## Phase 4: Frontend — React Application ✅ COMPLETE

### Directory Structure (actual)

```
frontend/src/
├── main.tsx
├── App.tsx                         # All route definitions
├── api/
│   ├── client.ts                   # Axios instance — NEVER import axios elsewhere
│   └── endpoints.ts                # All typed API functions + TypeScript interfaces
├── store/
│   └── authStore.ts                # Zustand: { token, user, setAuth, setToken, clearAuth }
├── hooks/
│   ├── useAuth.ts                  # login, register, loginWithGoogle, logout, bootstrap
│   ├── useLeague.ts                # All league/membership/tournament-schedule hooks
│   ├── usePick.ts                  # Tournaments, picks, standings, leaderboard
│   ├── usePlayoff.ts               # Playoff config, bracket, draft, pod, preferences
│   └── useDropdownDirection.ts     # Viewport overflow detection for dropdowns
├── pages/
│   ├── Welcome.tsx                 # Public landing — /
│   ├── Login.tsx                   # /login (email + Google OAuth button)
│   ├── Register.tsx                # /register (email + Google + confirm password)
│   ├── ForgotPassword.tsx          # /forgot-password (always 200 response shown)
│   ├── ResetPassword.tsx           # /reset-password?token=... (auto-login on success)
│   ├── JoinLeague.tsx              # /join/:inviteCode
│   ├── Leagues.tsx                 # /leagues
│   ├── CreateLeague.tsx            # /leagues/new (multi-step wizard)
│   ├── Dashboard.tsx               # /leagues/:leagueId
│   ├── MakePick.tsx                # /leagues/:leagueId/pick
│   ├── MyPicks.tsx                 # /leagues/:leagueId/picks
│   ├── TournamentDetail.tsx        # /leagues/:leagueId/tournaments/:tournamentId
│   ├── Leaderboard.tsx             # /leagues/:leagueId/leaderboard
│   ├── ManageLeague.tsx            # /leagues/:leagueId/manage (manager only)
│   ├── PlayoffBracket.tsx          # /leagues/:leagueId/playoff
│   ├── PlayoffDraft.tsx            # /leagues/:leagueId/playoff/pod/:podId
│   ├── Settings.tsx                # /settings
│   └── PlatformAdmin.tsx           # /admin (platform admin only)
└── components/
    ├── Layout.tsx                  # Auth guard + top nav + mobile tab bar
    ├── LeagueCard.tsx
    ├── PickForm.tsx
    ├── GolferCard.tsx
    ├── GolferAvatar.tsx
    ├── StandingsTable.tsx
    ├── TournamentBadge.tsx
    ├── PlayoffBracketCard.tsx
    ├── PlayoffPreferenceEditor.tsx
    └── FlagIcon.tsx
```

### Routes

```
/                                       → Welcome (public)
/login                                  → Login
/register                               → Register
/forgot-password                        → Forgot Password
/reset-password?token=<tok>             → Reset Password
/join/:inviteCode                       → Join League (auth-guarded)
/leagues                                → Leagues hub
/leagues/new                            → Create League wizard
/leagues/:leagueId                      → Dashboard
/leagues/:leagueId/pick                 → Make Pick
/leagues/:leagueId/picks                → My Picks
/leagues/:leagueId/tournaments/:tid     → Tournament Detail
/leagues/:leagueId/leaderboard          → Leaderboard
/leagues/:leagueId/manage               → Manage League
/leagues/:leagueId/playoff              → Playoff Bracket
/leagues/:leagueId/playoff/pod/:podId   → Playoff Draft
/settings                               → User Settings
/admin                                  → Platform Admin
/*                                      → Redirect to /
```

### Mobile-First Layout

- Fixed bottom tab bar (`sm:hidden fixed bottom-0`) on league pages — replaces header nav links
- Desktop nav uses `hidden sm:flex`
- Add `pb-24 sm:pb-8` to league page content to clear tab bar
- Test at 390×844 (iPhone 14 Pro) before marking any UI change done

---

## Phase 5: Docker Containerization ✅ COMPLETE

### Local Dev (`docker-compose.yml`) — 6 Services

| Service | Image | Port | Purpose |
|---|---|---|---|
| `postgres` | postgres:15-alpine | 5432 | Local DB (`league_caddie_dev`) |
| `localstack` | localstack/localstack:3 | 4566 | Local AWS (SQS + SES emulation) |
| `backend` | Dockerfile.dev | 8000 | FastAPI HTTP API (hot reload) |
| `scraper` | Dockerfile.dev | — | APScheduler jobs (hot reload) |
| `worker` | Dockerfile.dev | — | SQS consumer loop (hot reload) |
| `frontend` | Dockerfile.dev | 5173 | Vite dev server (hot reload) |

### LocalStack Init (`localstack-init/create-queues.sh`)

```sh
# SQS queues
awslocal sqs create-queue --queue-name fantasy-golf-events-dev-dlq
awslocal sqs create-queue --queue-name fantasy-golf-events-dev \
  --attributes VisibilityTimeout=120,RedrivePolicy=...

# SES sender identity
awslocal ses verify-email-identity --email-address noreply@league-caddie.com
```

### Production Dockerfiles

- `backend/Dockerfile` — multi-stage Python build (slim runtime, no dev tools)
- `frontend/Dockerfile` — multi-stage Node build → Nginx alpine serving `/dist`

> **Important:** The frontend Nginx does **not** proxy `/api` requests. In production, Traefik ingress handles routing at the cluster level — `/api/*` goes to the backend service, `/*` goes to the frontend service. Nginx in the frontend container never sees API traffic, which is why `nginx.conf` has no proxy block.

### Environment Variables

**Backend:**
| Variable | Dev Value | Prod Value |
|---|---|---|
| DATABASE_URL | postgresql://...@postgres:5432/league_caddie_dev | postgresql://...@postgres:5432/league_caddie_prod |
| SECRET_KEY | any random string | from K8s secret |
| GOOGLE_CLIENT_ID | real client ID | same |
| FRONTEND_URL | http://localhost:5173 | https://yourdomain.com |
| AWS_REGION | us-east-1 | us-east-1 |
| AWS_ENDPOINT_URL | http://localstack:4566 | (empty — use EC2 IAM role) |
| AWS_ACCESS_KEY_ID | test | (empty — use EC2 IAM role) |
| AWS_SECRET_ACCESS_KEY | test | (empty — use EC2 IAM role) |
| SES_FROM_EMAIL | noreply@league-caddie.com | noreply@league-caddie.com |

**Frontend:**
| Variable | Dev Value | Prod Value |
|---|---|---|
| VITE_API_TARGET | http://backend:8000 | (baked into Nginx proxy at build time) |

---

## Phase 6: Kubernetes & Helm Charts ✅ DONE

### Goal

Helm chart that deploys the full application to K3s, with separate values files for dev and prod.

### Chart Structure

```
helm/
└── fantasy-golf/
    ├── Chart.yaml
    ├── values.yaml           # Shared defaults
    ├── values-dev.yaml       # Dev overrides
    ├── values-prod.yaml      # Prod overrides
    └── templates/
        ├── _helpers.tpl
        ├── backend/
        │   ├── deployment.yaml       # backend container (uvicorn)
        │   └── service.yaml
        ├── scraper/
        │   └── deployment.yaml       # scraper container (APScheduler)
        ├── worker/
        │   └── deployment.yaml       # worker container (SQS consumer)
        ├── frontend/
        │   ├── deployment.yaml
        │   └── service.yaml
        ├── postgres/
        │   ├── deployment.yaml       # Single Postgres pod
        │   ├── service.yaml          # Internal ClusterIP only
        │   └── pvc.yaml              # PersistentVolumeClaim (EBS-backed)
        ├── ingress.yaml              # Routes /api → backend, / → frontend
        ├── configmap.yaml            # Non-secret config (AWS_REGION, FRONTEND_URL, etc.)
        └── secrets.yaml              # DB password, JWT secret, GOOGLE_CLIENT_ID, SES_FROM_EMAIL
```

### Deployment Design Notes

- **Scraper and worker**: 1 replica only (never scale above 1 — APScheduler must not run duplicate jobs; SQS consumer handles at-least-once via idempotent handlers, but duplicate consumers = wasted work)
- **Backend**: 1 replica dev, 2 replicas prod (stateless, safe to scale)
- **Frontend**: 1–2 replicas (static Nginx, trivially stateless)
- **Postgres**: 1 replica per instance (single-writer; data on PVC backed by EC2 EBS volume)
- **SQS**: Use real AWS SQS in K8s (not LocalStack); credentials provided by EC2 IAM instance role (no AWS keys needed in K8s secrets)

### Dev vs Prod Instances

| | Dev | Prod |
|---|---|---|
| EC2 instance | t2.micro (free tier) | t3a.small (~$14/month) |
| K8s cluster | Separate K3s instance | Separate K3s instance |
| Database | `league_caddie_dev` | `league_caddie_prod` |
| Deploy trigger | push to `main` + approval (gate #1) | push to `main` + approval (gate #2, after dev) |
| Image tag | `latest` | `latest` |
| Backend replicas | 1 | 2 |
| URL | `dev.yourdomain.com` | `yourdomain.com` |

### K3s on EC2

- K3s is certified Kubernetes — full `kubectl` + Helm 3 support
- Install on each instance: `curl -sfL https://get.k3s.io | sh -`
- Built-in: Traefik ingress controller, local path provisioner (for Postgres PVC)
- Each EC2 instance runs its own independent K3s cluster — no shared state between dev and prod

### Tasks

1. Create `helm/fantasy-golf/Chart.yaml`
2. Write templates for all 5 services: backend, scraper, worker, frontend, postgres
3. Write `pvc.yaml` for Postgres data
4. Write `ingress.yaml` (Traefik routes: `/api/*` → backend, `/*` → frontend)
5. Write `configmap.yaml` and `secrets.yaml`
6. Create `values.yaml`, `values-dev.yaml`, `values-prod.yaml`
7. Test chart locally with `k3d` or a local K3s instance:
   ```sh
   helm upgrade --install fantasy-golf ./helm/fantasy-golf \
     -f helm/fantasy-golf/values-dev.yaml \
     --namespace dev --create-namespace
   ```
8. Verify all 5 services come up and the app is accessible

---

## Phase 7: CI/CD Pipeline with GitHub Actions

### Goal

Automated pipeline: test on PRs, build + deploy on merge to `main`.

### Branching Strategy

Single long-lived branch: `main`. All changes come in via PRs (or direct commits for trivial fixes). There is no `dev` branch — the K8s `dev` namespace serves as a staging environment that must be deployed and verified before prod can be deployed.

### Workflow Triggers

| Trigger | Jobs Run |
|---|---|
| Pull request (to `main`) | lint + test + helm lint + docker build (no push) |
| Push to `main` branch | lint + test + helm lint + build + scan + push to ECR → **approve dev** → deploy to dev → **approve prod** → deploy to prod |

### Manual Approval Gates

Two sequential gates enforce the rule that dev must be deployed before prod can be deployed. Both use GitHub Environments with required reviewers.

**How it works:**
- Create two GitHub Environments in repo Settings → Environments: `dev` and `prod`
- Add yourself as a required reviewer on both
- `deploy-dev` targets `environment: dev` — GitHub pauses and waits for approval before deploying to the dev namespace
- `deploy-prod` targets `environment: prod` AND has `needs: deploy-dev` — it cannot run until `deploy-dev` has succeeded
- This makes it structurally impossible to deploy to prod without first deploying to dev in the same pipeline run

**Cost:** Free — GitHub Environments with required reviewers are available on public repos.

### Pipeline Jobs

```yaml
jobs:
  test-backend:
    - Install deps (uv sync)
    - ruff check (lint + format check)
    - pytest (unit + integration tests against test DB)

  test-frontend:
    - npm ci
    - npm run lint (ESLint)
    - npm run type-check (tsc --noEmit)

  helm-lint:
    - helm lint helm/league-caddie -f helm/league-caddie/values-dev.yaml
    - helm lint helm/league-caddie -f helm/league-caddie/values-prod.yaml

  build:
    needs: [test-backend, test-frontend, helm-lint]
    # On PRs: build all 4 images but do NOT push (validates Dockerfiles)
    # On push to main: build + push to ECR tagged `latest`
    - aws ecr get-login-password | docker login  (push only)
    - docker build all 4 images
    - docker push all 4 images  (push only)
    - Each push overwrites the previous `latest` tag — only one image version stored per repo at any time

  scan:
    needs: build
    if: github.ref == 'refs/heads/main'
    # Trivy scans the pushed images for known CVEs
    - trivy image --exit-code 1 --severity CRITICAL <ecr-url>/backend:latest
    - trivy image --exit-code 1 --severity CRITICAL <ecr-url>/frontend:latest
    # exit-code 1 = fail the pipeline on any CRITICAL severity finding

  deploy-dev:
    needs: scan
    environment: dev   # approval gate #1 — must be approved before dev deploys
    - helm upgrade --install targeting dev namespace
    - kubectl rollout status -n dev (wait for healthy)

  deploy-prod:
    needs: deploy-dev  # structurally blocked until deploy-dev succeeds
    environment: prod  # approval gate #2 — approve only after verifying dev
    - helm upgrade --install targeting prod namespace
    - kubectl rollout status -n prod (wait for healthy)
```

### GitHub Secrets Required

| Secret | Used For |
|---|---|
| `AWS_ACCESS_KEY_ID` | ECR push (CI/CD only — NOT used by running app) |
| `AWS_SECRET_ACCESS_KEY` | ECR push |
| `AWS_ACCOUNT_ID` | Construct ECR image URL |
| `EC2_HOST_DEV` | SSH target — dev EC2 Elastic IP |
| `EC2_HOST_PROD` | SSH target — prod EC2 Elastic IP |
| `EC2_SSH_KEY` | Private key for SSH into EC2 |
| `KUBECONFIG_DEV` | Kubectl/helm access for dev K3s cluster |
| `KUBECONFIG_PROD` | Kubectl/helm access for prod K3s cluster |
| `JWT_SECRET_DEV` / `JWT_SECRET_PROD` | K8s secret values injected at deploy |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `DATABASE_URL_DEV` / `DATABASE_URL_PROD` | Per-environment DB connection strings |

### AWS IAM for CI/CD

Create a dedicated IAM user `fantasy-golf-deploy` with a minimal policy — ECR push only. The running EC2 instance uses an IAM instance role (not this user) for SES and SQS access at runtime.

```json
{
  "Effect": "Allow",
  "Action": [
    "ecr:GetAuthorizationToken",
    "ecr:BatchCheckLayerAvailability",
    "ecr:PutImage",
    "ecr:InitiateLayerUpload",
    "ecr:UploadLayerPart",
    "ecr:CompleteLayerUpload"
  ],
  "Resource": "*"
}
```

### Tasks

1. Write `.github/workflows/ci-cd.yml`
2. Set up all GitHub repository secrets
3. Create IAM user `fantasy-golf-deploy` with ECR-push-only policy
4. Test: open a PR → tests run; merge to `main` → approve dev deploy → verify dev → approve prod deploy

---

## Phase 8: AWS Setup

### Goal

Provision all AWS resources needed for production (and dev). Use only free-tier or near-free services.

### Resources to Create

1. **IAM**
   - Root: enable MFA immediately, never use for daily work
   - User `fantasy-golf-deploy` (programmatic only): ECR push policy (above)
   - EC2 instance role `fantasy-golf-ec2-role`: policies for SES send + SQS full access

2. **ECR (Elastic Container Registry)**
   - Create four repositories: `backend`, `fantasy-golf-scraper`, `fantasy-golf-worker`, `frontend`
   - Free tier: 500 MB/month storage
   - **Tag strategy: `latest` (prod) and `dev-latest` (dev) only** — each push overwrites the previous tag, keeping storage at a minimum. Rollback = push a revert commit and redeploy.

3. **SQS**
   - Create queue: `fantasy-golf-events-prod` (same config as dev)
   - Create DLQ: `fantasy-golf-events-prod-dlq`
   - Free tier: 1M requests/month — more than enough

4. **SES (Simple Email Service)**
   - Verify sender identity: `noreply@league-caddie.com` (or verify the domain)
   - **Important:** SES starts in sandbox mode — only verified email addresses can receive emails
   - Before sending to arbitrary users: request SES sandbox exit via AWS Support (takes 1–3 days)
   - IAM role (not keys) handles credentials on EC2

5. **EC2 — Dev instance (`t2.micro`)**
   - Launch `t2.micro` with Amazon Linux 2023 (free tier eligible)
   - 20 GB EBS gp3 volume (free tier: 30 GB included)
   - Assign Elastic IP (free while instance is running)
   - Attach IAM instance role `fantasy-golf-ec2-role`
   - Install K3s on first boot: `curl -sfL https://get.k3s.io | sh -`
   - Security group: 22 (SSH from your IP only), 80 (HTTP public), 443 (HTTPS public)

6. **EC2 — Prod instance (`t3a.small`)**
   - Launch `t3a.small` with Amazon Linux 2023 (2 vCPU, 2 GB RAM, AMD EPYC — ~$13.70/month)
   - 30 GB EBS gp3 volume (more headroom for prod Postgres data)
   - Assign Elastic IP (free while instance is running)
   - Attach IAM instance role `fantasy-golf-ec2-role`
   - Install K3s on first boot: `curl -sfL https://get.k3s.io | sh -`
   - Security group: same as dev — 22 (SSH from your IP only), 80 (HTTP public), 443 (HTTPS public)
   - **Note:** t3a.small is not free-tier eligible; dev instance (t2.micro) stays free for 12 months

7. **DNS & TLS (optional, ~$12/year for domain)**
   - Register domain via Route53 or Namecheap
   - A record → Elastic IP
   - TLS via cert-manager + Let's Encrypt (free) inside K3s — auto-renews

### AWS SES Production Checklist

Before deploying:
1. Verify `noreply@league-caddie.com` as a sender identity in the SES console
2. Request SES sandbox exit so emails reach unverified recipients
3. Leave `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` **empty** in prod Helm values — EC2 IAM role provides credentials automatically

### Tasks

1. Create AWS account (use personal email, enables full free tier 12 months)
2. Enable root MFA
3. Create IAM user (`fantasy-golf-deploy`) + EC2 role (`fantasy-golf-ec2-role`)
4. Create ECR repositories (`backend`, `fantasy-golf-scraper`, `fantasy-golf-worker`, `frontend`)
5. Create SQS queues (`fantasy-golf-events-prod`, `-dlq`)
6. Verify SES sender identity; request sandbox exit
7. Launch EC2 instances (t2.micro for dev, t3a.small for prod), assign Elastic IPs, attach IAM role to each
8. Install K3s on EC2
9. Create K8s namespaces: `kubectl create namespace dev && kubectl create namespace prod`
10. Initial deploy: `helm upgrade --install fantasy-golf ./helm/fantasy-golf -f values-prod.yaml --namespace prod`
11. (Optional) Configure domain + cert-manager for HTTPS

---

## Phase 9: Dev & Production Environments

### Goal

Two isolated environments on the same K3s cluster, each with its own database. `main` is the only branch — dev is deployed manually when needed for cluster testing.

### Environment Separation

| | Dev | Prod |
|---|---|---|
| K8s namespace | `dev` | `prod` |
| Database | `league_caddie_dev` | `league_caddie_prod` |
| Deploy trigger | manual (`helm upgrade` CLI) | push to `main` + approval |
| Image tag | `latest` | `latest` |
| Backend replicas | 1 | 2 |
| Scraper replicas | 1 | 1 (never scale above 1) |
| Worker replicas | 1 | 1 (never scale above 1) |
| URL | `dev.yourdomain.com` | `yourdomain.com` |

### Promotion Flow

1. Develop feature locally (`docker compose up`)
2. Open a PR → CI runs lint + test + helm lint + docker build (no push)
3. Merge PR to `main` → CI builds + scans
4. Approve gate #1 → deploys to dev namespace
5. Verify the feature on `dev.yourdomain.com`
6. Approve gate #2 → deploys to prod namespace

### Postgres on K8s

Both `league_caddie_dev` and `league_caddie_prod` run as separate databases on the same Postgres pod (single K8s Deployment, single PVC). Migrations are run manually (or as a K8s Job on deploy) per environment:

```sh
# Dev
kubectl exec -n dev deploy/backend -- alembic upgrade head

# Prod
kubectl exec -n prod deploy/backend -- alembic upgrade head
```

### Tasks

1. Confirm K8s namespaces exist: `dev` and `prod`
2. Configure Helm `values-dev.yaml` and `values-prod.yaml` with correct DB names, replica counts, and URLs
3. Set up ingress rules for `dev.*` and root domain
4. Run initial migration in both namespaces
5. Verify full stack in dev → promote to prod

---

## Implementation Order

```
Phase 0  → Foundation (local tooling + docker-compose)             ✅ DONE
Phase 1  → Database schema + migrations                             ✅ DONE
Phase 2  → Backend core (auth + API + all routers/services)         ✅ DONE
Phase 5  → Docker (containerize early; local dev via docker-compose) ✅ DONE
Phase 3  → Web scraping (ESPN API, APScheduler, SQS pipeline)       ✅ DONE
Phase 4  → Frontend (18 pages, all features)                        ✅ DONE
Phase 6  → Helm charts (define K8s deployment)                      ✅ DONE
Phase 8  → AWS setup (EC2, ECR, SQS, SES, IAM, K3s install)
Phase 7  → CI/CD pipeline (GitHub Actions)
Phase 9  → Dev/prod environments (namespaces, migrations, ingress)
Phase 10 → Monetization, Legal & Business Setup (before public launch)
```

---

## Phase 10: Monetization, Legal & Business Setup

> **Do this before public launch.** Phase 10 can be worked in parallel with Phases 6–9 for the non-code items (LLC, legal docs, Stripe account). The technical integration (Stripe in-app) should be completed before opening the site to the public.

---

### 10.1 Form an LLC

**Why:** An LLC separates your personal assets from the business. Without it, a lawsuit or unpaid debt against "League Caddie" is a lawsuit against you personally. It also makes the business look legitimate to users and payment processors.

**Recommended state:** Your home state (simpler) or Delaware (if you plan to raise investment — not necessary here). Delaware LLCs have a $300/year franchise tax that makes them worse for small solo founders.

**How to form:**
1. Choose a name — confirm it's available in your state's business registry
2. File Articles of Organization online through your state's Secretary of State website
3. Get an EIN (Employer Identification Number) from IRS.gov — free, instant, needed for Stripe and taxes
4. Open a **dedicated business bank account** — never mix personal and business money (this is essential for LLC protection to hold up)
5. Draft a simple Operating Agreement (one-person LLC template is fine; templates are free online)

**Cost:** $50–$300 state filing fee (one-time). Annual report fee varies by state ($25–$100/year).

**Timeline:** Approved in 1–10 business days depending on state. Some states (e.g., Kentucky) take 1 day.

**Do NOT use:** LegalZoom/ZenBusiness are fine but charge $150+ on top of state fees for something you can DIY in 30 minutes.

---

### 10.2 Legal Documents (Required Before Public Launch)

All legal pages should be accessible from the site footer. They do not require a lawyer for a solo B2C SaaS at this stage — use a reputable template generator (Termly, Iubenda, or TermsFeed are widely used) and customize. Review with a lawyer if/when you start making significant revenue.

#### Terms of Service

Key clauses to include:

- **Eligibility** — users must be 13+ (18+ to participate in leagues involving money)
- **Account responsibility** — users are responsible for their account activity; sharing credentials is prohibited
- **Acceptable use** — no harassment, no manipulation of picks, no fake accounts
- **League commissioner responsibilities** — commissioners (managers) are responsible for their league's rules and any prize arrangements between members
- **No prize/gambling liability** — League Caddie facilitates score tracking only. Any money changing hands between league members is a private arrangement between those users. League Caddie is not a party to any wagering, does not hold or distribute prize money, and is not responsible for payment disputes between members.
- **Data accuracy disclaimer** — earnings and scoring data is sourced from an unofficial third-party API (ESPN). Data may be delayed or inaccurate. League Caddie is not affiliated with the PGA Tour or ESPN.
- **Intellectual property** — you own the platform; users own their data; you grant yourself a license to display their content (picks, league names)
- **Account termination** — you reserve the right to suspend or terminate accounts violating ToS
- **Limitation of liability** — platform is provided "as is"; liability capped at amount paid in the last 12 months
- **Governing law** — specify your state
- **Changes to ToS** — you may update with 30 days notice
- **Dispute resolution** — binding arbitration clause (standard for consumer SaaS; reduces class action exposure)

#### Privacy Policy

Required by law (GDPR if EU users, CCPA if California users). Key sections:

- **Data collected:** email, display name, Google profile (if OAuth), pick history, IP address
- **How it's used:** to operate the service, send transactional emails (password reset, notifications), improve the product
- **Third parties:** Stripe (payment data — they are the data controller for card info, not you), Google OAuth, AWS (infrastructure)
- **Cookies:** session cookie (JWT refresh token) + any analytics cookies. If using Google Analytics, this section becomes more detailed.
- **User rights (GDPR):** right to access, correct, delete their data. Provide a delete-account flow.
- **Data retention:** how long you keep data after account deletion
- **Contact:** privacy@ email address
- **Do not sell** (CCPA): confirm you do not sell personal data

**Practical:** Add a `DELETE /users/me` endpoint so users can delete their own account (required for GDPR compliance and App Store submission if you go mobile later).

#### Disclaimer Page

- PGA Tour earnings data is sourced from an unofficial API and is **not official PGA Tour data**
- League Caddie is **not affiliated with, endorsed by, or sponsored by** the PGA Tour, ESPN, or any professional golf organization
- This platform is for **entertainment and score-tracking purposes only**
- All financial decisions (buy-ins, prizes) between league members are the responsibility of those members

#### Age Restriction

- Minimum age: **13 years old** to create an account (COPPA compliance — under 13 requires verifiable parental consent, which is operationally complex)
- **18+ recommendation** for leagues involving money — state this clearly in ToS
- Registration flow: add a checkbox "I confirm I am at least 13 years old" before account creation
- **Do NOT add an age-gate landing page** (birth date entry) — it's trivially bypassed and adds friction without protection. A checkbox ToS agreement is the industry standard.

#### Cookie Consent (GDPR)

If you serve European users, you technically need cookie consent for non-essential cookies. The **only** cookie League Caddie sets today is the httpOnly JWT refresh token — this is a strictly necessary session cookie and is exempt from consent requirements under GDPR. If you add analytics (Google Analytics, Mixpanel, etc.) in the future, you will need a cookie consent banner at that time. For now, you do not need one.

---

### 10.3 Pricing Strategy

**Model: Paid-only, per-league seasonal purchase scaled by member count**

Every league requires a purchase to operate. There is no free tier. Pricing scales with league size so small private groups pay less and larger leagues pay proportionally more — but the per-member cost decreases at scale, rewarding growth.

The commissioner (league manager) makes the purchase. All features are available to all paid leagues — no feature gating by tier.

**Member limit:** 500 members per league (hard platform limit).

| Tier | Members included | Price/season | Effective per-member |
|---|---|---|---|
| **Starter** | Up to 20 | $50 | $2.50 |
| **Standard** | Up to 50 | $90 | $1.80 |
| **Pro** | Up to 150 | $150 | $1.00 |
| **Elite** | Up to 500 | $250 | $0.50 |

**Rationale:**
- Most private leagues are 8–20 people — $50 is an easy sell ($2.50/person for a full season)
- Per-member cost drops at scale, which feels fair to commissioners of larger leagues
- Charging the **commissioner**, not each member, means one purchase per league regardless of size
- Fantasy golf is seasonal — a one-time per-season purchase aligns cost with when the product is valuable
- No free tier: the app requires ESPN data, AWS infrastructure, and SES email — these are real costs. The $50 entry point is low enough to not need a free tier.

**Upgrading mid-season:** Commissioners can upgrade to a higher tier at any time during the season — for example when their league grows past the current member limit or they just want more capacity. Upgrades cost the full price of the new tier (no credit for what was already paid — proration adds complexity not worth it at this stage). Downgrading is not allowed mid-season; a commissioner can choose a lower tier when they renew next year.

**Future pricing ideas (post-launch):**
- League Caddie Plus for members (tournament leaderboard notifications, pick reminders)
- White-label / custom branding for large private tournaments

---

### 10.4 Stripe Integration

**Why Stripe:** Industry standard, no monthly fee, excellent developer docs, handles PCI compliance so you never touch raw card data. Cost: 2.9% + $0.30 per successful charge.

**Payment model:** One-time purchase per league per season, with price determined by the chosen member-count tier. No subscriptions, no automatic renewals. A commissioner selects their tier, pays once, and the league is active for that season. The following season requires a new purchase — nothing charges automatically.

**Stripe products to use:**
- **Stripe Checkout** (hosted payment page) — simplest, handles all card UI, no frontend payment form to build
- **Stripe Webhooks** — Stripe pushes the `checkout.session.completed` event to your backend when payment succeeds

No Stripe Billing (subscriptions), no Customer Portal — those are only needed for recurring charges.

#### Pricing Tiers → Stripe Price IDs

Create four separate **one-time Prices** under a single Product ("League Caddie Season Pass") in the Stripe dashboard:

| Tier | Member limit | Price | Config key |
|---|---|---|---|
| Starter | 20 | $50.00 | `STRIPE_PRICE_ID_STARTER` |
| Standard | 50 | $90.00 | `STRIPE_PRICE_ID_STANDARD` |
| Pro | 150 | $150.00 | `STRIPE_PRICE_ID_PRO` |
| Elite | 500 | $250.00 | `STRIPE_PRICE_ID_ELITE` |

#### New DB Tables

**`stripe_customers`**
```
id UUID PK
user_id UUID FK (users.id, unique)
stripe_customer_id VARCHAR (e.g. cus_abc123)
created_at TIMESTAMP
```

**`league_purchases`**
```
id UUID PK
league_id UUID FK (leagues.id)
season_year INTEGER                -- e.g. 2026; UNIQUE with league_id (one row per league per year)
tier VARCHAR(16)                   -- "starter" | "standard" | "pro" | "elite" — updated in place on upgrade
member_limit INTEGER               -- 20 | 50 | 150 | 500 — updated in place on upgrade
stripe_customer_id VARCHAR
stripe_payment_intent_id VARCHAR   -- NOT unique; overwritten on upgrade
stripe_checkout_session_id VARCHAR -- NOT unique; overwritten on upgrade; stored for reference only
amount_cents INTEGER               -- most recent charge amount (upgrades overwrite)
paid_at TIMESTAMP                  -- most recent payment timestamp
created_at TIMESTAMP
```

One row per `(league_id, season_year)` — unique constraint enforced. The row is created on first purchase and **updated in place** on each subsequent upgrade during the same season. `stripe_checkout_session_id` and `stripe_payment_intent_id` are stored for reference but are **not unique** — they get overwritten on upgrade (each checkout session has a unique ID within Stripe; we only need the latest for reference).

**`league_purchase_events`** *(append-only audit log)*
```
id UUID PK
league_id UUID FK (leagues.id)
season_year INTEGER
tier VARCHAR(16)                   -- tier purchased in this transaction
member_limit INTEGER               -- member limit granted by this transaction
stripe_customer_id VARCHAR
stripe_payment_intent_id VARCHAR   -- unique per transaction (Stripe guarantees this)
stripe_checkout_session_id VARCHAR -- unique per transaction
amount_cents INTEGER               -- amount charged in this transaction
event_type VARCHAR(16)             -- "initial" | "upgrade"
paid_at TIMESTAMP
created_at TIMESTAMP
```

One row per Stripe payment — never updated, only inserted. Initial purchases write `event_type = "initial"`; upgrades write `event_type = "upgrade"`. This gives a complete payment history per league independent of the `league_purchases` active-state row, which is the source of truth for the current tier and member limit.

**Upgrade flow:** Commissioner selects a higher tier → new Stripe Checkout session → on `checkout.session.completed`, the webhook does two writes atomically:
1. `UPDATE league_purchases` — overwrite `tier`, `member_limit`, `amount_cents`, `paid_at`, and Stripe IDs
2. `INSERT INTO league_purchase_events` — append a permanent record of this payment

The new `member_limit` takes effect immediately after the UPDATE — pending member requests can now be approved.

**Downgrade:** Not allowed mid-season. The UI should only offer tiers higher than the current one during the season. At renewal time (next season's purchase), the commissioner can freely choose any tier.

#### New Backend Code

**New dependency:** `stripe` Python package (add to `pyproject.toml`)

**New config vars (`app/config.py`):**
```python
STRIPE_SECRET_KEY: str = ""
STRIPE_PUBLISHABLE_KEY: str = ""
STRIPE_WEBHOOK_SECRET: str = ""
STRIPE_PRICE_ID_STARTER: str = ""    # price_... ($50, up to 20 members)
STRIPE_PRICE_ID_STANDARD: str = ""   # price_... ($90, up to 50 members)
STRIPE_PRICE_ID_PRO: str = ""        # price_... ($150, up to 150 members)
STRIPE_PRICE_ID_ELITE: str = ""      # price_... ($250, up to 500 members)
```

**Tier metadata (hardcoded constant, not in DB):**
```python
PRICING_TIERS = {
    "starter":  {"price_id": settings.STRIPE_PRICE_ID_STARTER,  "member_limit": 20,  "amount_cents": 5000},
    "standard": {"price_id": settings.STRIPE_PRICE_ID_STANDARD, "member_limit": 50,  "amount_cents": 9000},
    "pro":      {"price_id": settings.STRIPE_PRICE_ID_PRO,      "member_limit": 150, "amount_cents": 15000},
    "elite":    {"price_id": settings.STRIPE_PRICE_ID_ELITE,    "member_limit": 500, "amount_cents": 25000},
}
```

**New router: `app/routers/stripe.py`**
```
POST /stripe/create-checkout-session   # Body: { league_id, tier } → returns { url }
POST /stripe/webhook                   # Stripe sends events here (no auth — verified by signature)
GET  /leagues/{id}/purchase            # Current purchase status for this league + season
GET  /stripe/pricing                   # Returns tier list with limits + prices (for frontend)
```

**Webhook events to handle:**
| Event | Action |
|---|---|
| `checkout.session.completed` | (1) Upsert `league_purchases`: INSERT on first purchase, UPDATE in place on upgrade. (2) Always INSERT into `league_purchase_events` with `event_type = "initial"` or `"upgrade"`. Both writes are committed atomically. |

No `invoice.*` or `customer.subscription.*` events — there are no recurring charges.

**Middleware / dependency:** `require_active_purchase(league_id)` checks that a `league_purchases` row exists with `paid_at IS NOT NULL` and `season_year = current_year`. Member approval additionally checks `approved_member_count < purchase.member_limit` — if the league is at its limit, the commissioner must upgrade their tier before approving more members.

**Upgrade endpoint:** `POST /stripe/create-checkout-session` accepts an optional `upgrade=true` flag. When upgrading, the backend looks up the current tier and only accepts a `tier` value that is strictly higher. The Stripe Checkout session is created the same way — the webhook handler does an UPDATE instead of INSERT upon completion.

#### New Frontend Code

**New pages:**
- `Pricing.tsx` — `/pricing` (public) — four-tier pricing table, "Start your season" CTA for each tier → Stripe Checkout
- `BillingSuccess.tsx` — `/billing/success?session_id=...` — Stripe redirects here after payment; shows confirmation + tier purchased, link back to league
- `BillingCanceled.tsx` — `/billing/canceled` — Stripe redirects here if user closes checkout

**New endpoints in `endpoints.ts`:**
```ts
stripeApi.createCheckoutSession(leagueId: string, tier: string) → { url: string }
stripeApi.getPricing() → PricingTier[]            // tier name, member limit, amount_cents
leagueApi.getPurchase(leagueId: string) → LeaguePurchaseStatus
```

**Gate in UI:** When a league has no active purchase (`paid_at` null or `season_year` ≠ current year), show a "Purchase a season pass to activate this league" prompt in ManageLeague and anywhere else league features are used. When a league is at its member limit, show an "Upgrade your plan to approve more members" prompt in the member management UI — clicking it opens the tier selector showing only tiers above the current one and redirects to Stripe Checkout. After a successful upgrade, the member limit increases immediately and pending requests can be approved.

**No "manage billing" link** — there is no subscription to manage. Commissioners simply buy again next season when they're ready.

#### Local Dev with Stripe

1. Use `sk_test_` keys — no real charges
2. Use Stripe CLI to forward webhooks locally: `stripe listen --forward-to localhost:8000/stripe/webhook`
3. Add `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and all four `STRIPE_PRICE_ID_*` keys to `docker-compose.yml` backend env (test keys only)
4. Test card: `4242 4242 4242 4242`, any future date, any CVC
5. Create one Product ("League Caddie Season Pass") with four **one-time Prices** in the Stripe test dashboard — one per tier

#### Migration #19

```python
def upgrade():
    op.create_table("stripe_customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("stripe_customer_id", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table("league_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("league_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(16), nullable=True),              # null until first payment confirmed; updated in place on upgrade
        sa.Column("member_limit", sa.Integer(), nullable=True),       # null until first payment confirmed; updated in place on upgrade
        sa.Column("stripe_customer_id", sa.String(64), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(64), nullable=True),   # NOT unique — overwritten on upgrade
        sa.Column("stripe_checkout_session_id", sa.String(64), nullable=True), # NOT unique — overwritten on upgrade
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # One active purchase row per league per season year. Upgrades update this row in place.
    op.create_unique_constraint("uq_league_purchase_year", "league_purchases", ["league_id", "season_year"])

    op.create_table("league_purchase_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("league_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("member_limit", sa.Integer(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(64), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(64), nullable=True, unique=True),   # unique per Stripe transaction
        sa.Column("stripe_checkout_session_id", sa.String(64), nullable=False, unique=True), # unique per Stripe transaction
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),  # "initial" | "upgrade"
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Index for looking up payment history by league
    op.create_index("ix_league_purchase_events_league_year", "league_purchase_events", ["league_id", "season_year"])

def downgrade():
    op.drop_table("league_purchase_events")
    op.drop_table("league_purchases")
    op.drop_table("stripe_customers")
```

---

### 10.5 Business & Tax Tracking

**Critical rule:** Keep all business finances completely separate from personal finances. Open a dedicated business checking account and route all Stripe payouts and AWS charges through it.

#### Revenue Tracking (Stripe handles this automatically)

Stripe Dashboard gives you:
- Monthly recurring revenue (MRR)
- Subscriber count and churn
- Gross/net revenue after Stripe fees
- Downloadable CSV reports for tax filing
- **1099-K:** Stripe will issue a 1099-K if you receive >$600/year in payments (US law). This means you owe income tax on that revenue.

#### Expense Tracking

Keep a simple spreadsheet (or use free Wave Accounting) logging every business expense:

| Category | Examples | Tax Deductible? |
|---|---|---|
| Cloud infrastructure | AWS EC2, ECR, SQS, SES | ✅ Yes |
| Domain & DNS | Route53, Namecheap | ✅ Yes |
| LLC formation | State filing fee, EIN | ✅ Yes (startup cost) |
| Software & tools | GitHub Pro (if upgraded), Stripe fees | ✅ Yes |
| Home office | Percentage of rent/utilities if working from home | ✅ Yes (calculate carefully) |
| Professional services | Lawyer review of ToS, accountant | ✅ Yes |

**Stripe fees** (2.9% + $0.30/transaction) are a business expense — deduct them.

#### Tax Filing

- **Entity type:** Single-member LLC → taxed as a **sole proprietor** by default (Schedule C on your personal 1040). No separate corporate tax return needed unless you elect S-Corp status (not worth it until ~$60k+ profit/year).
- **Quarterly estimated taxes:** Once you're earning, you must pay estimated taxes quarterly (April 15, June 15, Sept 15, Jan 15) to avoid IRS underpayment penalties. Use IRS Form 1040-ES.
- **Self-employment tax:** You owe both employer and employee portions of Social Security + Medicare (15.3%) on net profit. Factor this into pricing.
- **Sales tax on SaaS:** Most US states do not tax SaaS subscriptions, but laws vary. Check your state. At small revenue levels, this is not a priority.

#### Bookkeeping Tools (choose one)

| Tool | Cost | Best For |
|---|---|---|
| Spreadsheet (Google Sheets) | Free | Under $10k/year revenue |
| Wave Accounting | Free | $10k–$50k/year |
| QuickBooks Self-Employed | ~$15/month | If you want automated mileage + quarterly tax estimates |

Start with a spreadsheet. Migrate to Wave when the spreadsheet gets unwieldy.

---

### 10.6 Gambling & Regulatory Considerations

Fantasy sports with money prizes exist in a legal gray area in the US. The short version:

**Season-long private fantasy leagues are generally NOT regulated gambling** in most US states. Courts and legislators have repeatedly found that season-long fantasy sports are predominantly skill-based (not chance-based). This is the same category as your friendly office bracket or poker night.

**Daily fantasy (DraftKings/FanDuel style) IS regulated** in many states. League Caddie is season-long — this is the safer category.

**What you MUST do regardless:**
1. Do not hold or distribute prize money on behalf of leagues — users handle that themselves. The platform is score-tracking software only.
2. Clearly state in ToS that the platform is not a gambling site and does not facilitate wagering.
3. Add the disclaimer to your Terms of Service (already covered in 10.2).

**States with notable restrictions on fantasy sports:** Arizona, Hawaii, Idaho, Montana, Nevada, Washington — if you get users there, be aware. Nevada requires a gambling license for most fantasy sports. If you ever see users from Nevada participating in money leagues, consult a lawyer.

**Do not expand into daily fantasy** (weekly or daily pick contests with entry fees) without proper legal review — that triggers state-by-state licensing requirements.

---

### 10.7 Phase 10 Task Checklist

#### Legal (do before launch)
- [ ] Form LLC in your state — file Articles of Organization online
- [ ] Get EIN from IRS.gov (free, 5 minutes)
- [ ] Open business checking account
- [ ] Generate Terms of Service using Termly or TermsFeed — customize with the clauses from 10.2
- [ ] Generate Privacy Policy — customize to list Stripe, Google OAuth, AWS as data processors
- [ ] Write Disclaimer page (data accuracy + no PGA Tour affiliation)
- [ ] Add age confirmation checkbox to registration flow (backend + frontend)
- [ ] Add `DELETE /users/me` endpoint (GDPR account deletion)
- [ ] Add legal pages to site footer: Terms, Privacy, Disclaimer
- [ ] Add footer links to existing `Layout.tsx`

#### Stripe (technical — do before launch)
- [ ] Create Stripe account, complete business verification
- [ ] Create one Product ("League Caddie Season Pass") with four **one-time Prices** in Stripe dashboard: Starter $50, Standard $90, Pro $150, Elite $250
- [ ] Add `stripe` to `pyproject.toml` and `uv.lock`
- [ ] Add `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, and `STRIPE_PRICE_ID_STARTER/STANDARD/PRO/ELITE` to `app/config.py`
- [ ] Write Alembic migration #19 (`stripe_customers`, `league_purchases`, `league_purchase_events` tables)
- [ ] Write `app/models/league_purchase.py` ORM models (`LeaguePurchase` + `LeaguePurchaseEvent`)
- [ ] Write `app/routers/stripe.py` (checkout session with tier param, webhook, pricing endpoint)
- [ ] Add `require_active_purchase` dependency to gated endpoints; add member-limit check to member approval
- [ ] Build `Pricing.tsx`, `BillingSuccess.tsx`, `BillingCanceled.tsx` pages
- [ ] Register new routes in `App.tsx`
- [ ] Gate league features in UI when no active purchase; show member-limit upgrade prompt in member management
- [ ] Add Stripe CLI to dev workflow; document in `docker-compose.yml` comments
- [ ] Add all four Stripe price IDs + secret key to K8s Helm secrets (`values-prod.yaml`)
- [ ] Test all four tier checkout flows in Stripe test mode before going live

#### Business / Tax
- [ ] Set up business expense tracking spreadsheet (or Wave)
- [ ] Configure Stripe to deposit payouts to business bank account
- [ ] Set a reminder for quarterly estimated tax payments
- [ ] Save receipt/invoice for every business expense (AWS console, domain registrar, etc.)

---

## Technology Decisions Summary

| Concern | Choice | Reason |
|---|---|---|
| Frontend | React + TypeScript + Vite | Industry standard, fast HMR |
| Styling | Tailwind CSS | Utility-first, no component library |
| State | Zustand | Simple, enough for auth-only global state |
| Data fetching | React Query (TanStack Query) | Caching, loading/error states, polling |
| Backend | FastAPI + Python | Async, automatic OpenAPI docs, fast |
| ORM | SQLAlchemy 2.0 | Standard Python ORM, type-safe |
| Migrations | Alembic | Works with SQLAlchemy, reversible |
| Auth | JWT (15min access + 7day refresh httpOnly cookie) | Stateless, no Redis needed |
| Google OAuth | ID token flow (`@react-oauth/google` + `google-auth` Python) | No redirect/callback URL needed |
| Password reset | SHA-256 token hash in DB, AWS SES email | Secure, single-use, 1-hour TTL |
| Scheduler | APScheduler (scraper container) | In-process, no Celery/Redis |
| Scraping | httpx + ESPN unofficial API | Async, no browser |
| Event pipeline | AWS SQS (LocalStack in dev) | Decouples scraper → playoff automation |
| Email | AWS SES + HTML template | Free tier, no third-party service |
| DB | PostgreSQL in K3s (PVC-backed) | No RDS cost; persists on EBS |
| Containers | Docker multi-stage | Small prod images |
| Orchestration | K3s (not EKS) | Full Kubernetes, zero extra cost |
| Helm | Helm 3 | K8s package management, env-specific values |
| CI/CD | GitHub Actions | Free for public repos |
| Registry | AWS ECR | Integrates with EC2/K3s, 500 MB free |
| Cloud | AWS Free Tier (EC2 t2.micro) | Full 12 months free |
| Linting (BE) | Ruff | Fast Python linter + formatter |
| Testing (BE) | pytest | Standard, excellent ecosystem |
| Testing (FE) | Vitest | Vite-native, fast |
| Rate limiting | slowapi | FastAPI-native, Redis-free |
| Payments | Stripe (Checkout + Webhooks) | No monthly fee, PCI handled by Stripe, one-time per-league per-season purchase with 4 member-count tiers |
| Business entity | Single-member LLC | Personal liability protection, pass-through taxes |
| Legal docs | Terms of Service, Privacy Policy, Disclaimer | Termly/TermsFeed templates + customization |
| Bookkeeping | Spreadsheet → Wave Accounting | Free, sufficient for early-stage |
