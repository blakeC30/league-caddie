# Fantasy Golf — Frontend

React + TypeScript frontend for the Fantasy Golf League platform. Handles authentication, league management, pick submission, live tournament scoring, standings, and the full playoff bracket experience — across both desktop and mobile.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Local Development](#local-development)
- [Environment Variables](#environment-variables)
- [Routing](#routing)
- [Auth System](#auth-system)
- [API Layer](#api-layer)
- [Hooks](#hooks)
- [Pages](#pages)
- [Components](#components)
- [Styling Conventions](#styling-conventions)
- [Mobile Layout](#mobile-layout)
- [Key Patterns](#key-patterns)
- [Docker Setup](#docker-setup)

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| UI framework | React | 19.0.0 |
| Language | TypeScript | ~5.7 |
| Build tool | Vite | 6.0 |
| CSS | Tailwind CSS | 4.0 (via `@tailwindcss/vite`) |
| Routing | React Router | 7.1 |
| Server state | TanStack React Query | 5.62 |
| Client state | Zustand | 5.0 |
| HTTP client | Axios | 1.7 (with JWT + refresh interceptors) |
| Google OAuth | @react-oauth/google | 0.12 |
| Linting | ESLint 9 + typescript-eslint + prettier | — |
| Node version | 20 (see `.nvmrc`) | — |

---

## Project Structure

```
frontend/
├── Dockerfile               # Multi-stage production build (nginx)
├── Dockerfile.dev           # Development hot-reload container (node:20-alpine)
├── nginx.conf               # Production nginx config (SPA routing + /api proxy)
├── vite.config.ts           # Dev server (port 5173, /api proxy), React + Tailwind plugins
├── tsconfig.json            # Project references config
├── tsconfig.app.json        # App TypeScript config (strict, ES2020, react-jsx)
├── tsconfig.node.json       # Build tooling TypeScript config
├── eslint.config.js         # ESLint: typescript-eslint + react-hooks + prettier
├── .prettierrc              # Prettier formatting rules
├── .nvmrc                   # Node 20
├── package.json             # Dependencies + npm scripts
├── index.html               # HTML entry point
├── public/                  # Static assets (served as-is)
└── src/
    ├── main.tsx             # React root + providers (GoogleOAuthProvider, QueryClient, BrowserRouter)
    ├── App.tsx              # All route definitions (20 routes)
    ├── index.css            # Global Tailwind import (@import "tailwindcss")
    ├── types.ts             # Shared User + TokenResponse types (avoids circular imports)
    ├── utils.ts             # Utility functions (fmtTournamentName, isoWeekKey, etc.)
    ├── toast.ts             # Minimal singleton toast system (no context provider needed)
    ├── vite-env.d.ts        # Vite environment type declarations
    │
    ├── api/
    │   ├── client.ts        # Axios instance — base URL, credentials, JWT + refresh interceptors
    │   └── endpoints.ts     # All typed API functions + TypeScript interfaces (7 API groups)
    │
    ├── store/
    │   └── authStore.ts     # Zustand store: token (in-memory), user, setAuth/setToken/clearAuth
    │
    ├── hooks/
    │   ├── useAuth.ts               # Login, register, logout, Google OAuth, session bootstrap
    │   ├── useLeague.ts             # 11 league + membership + schedule hooks
    │   ├── usePick.ts               # Tournament, pick, standings, leaderboard, sync hooks
    │   ├── usePlayoff.ts            # 16 playoff config, bracket, pod, draft, preferences hooks
    │   └── useDropdownDirection.ts  # Detects if a dropdown would overflow the viewport bottom
    │
    ├── components/
    │   ├── Layout.tsx               # Auth-guarded shell: top nav + mobile bottom tab bar
    │   ├── LeagueCard.tsx           # Rich league card with standings, tournament, pick status
    │   ├── PickForm.tsx             # Golfer search + selection form
    │   ├── GolferCard.tsx           # Golfer row: avatar, name, country, status badges
    │   ├── GolferAvatar.tsx         # ESPN headshot with green-circle fallback
    │   ├── StandingsTable.tsx       # Golf-style rankings table (T2 ties, medal highlights)
    │   ├── TournamentBadge.tsx      # Status + major/multiplier/playoff badge
    │   ├── PlayoffBracketCard.tsx   # Bracket round/pod visualization
    │   ├── PlayoffPreferenceEditor.tsx # Ranked preference list editor
    │   ├── FlagIcon.tsx             # Golf flag SVG (brand icon)
    │   ├── Spinner.tsx              # Animated loading spinner
    │   └── Toaster.tsx              # Toast notification renderer
    │
    └── pages/
        ├── Welcome.tsx          # Public landing page (hero, features, CTAs)
        ├── Login.tsx            # Email/password login + Google OAuth
        ├── Register.tsx         # Create account + Google OAuth
        ├── ForgotPassword.tsx   # Request password reset email
        ├── ResetPassword.tsx    # Set new password via token from email link
        ├── Leagues.tsx          # League list + create/join + pending requests
        ├── CreateLeague.tsx     # Multi-step league creation wizard
        ├── Dashboard.tsx        # Per-league home: active tournament, standings preview
        ├── MakePick.tsx         # Golfer selection (regular season + playoff preferences)
        ├── MyPicks.tsx          # Season pick history + stat cards + member filter
        ├── Leaderboard.tsx      # Full standings table with tournament breakdown
        ├── TournamentDetail.tsx # Live leaderboard with expandable scorecards
        ├── LeagueRules.tsx      # Read-only rules + league config + playoff info
        ├── ManageLeague.tsx     # Manager panel: members, schedule, playoff config
        ├── PlayoffBracket.tsx   # Scrollable bracket view for all members
        ├── PlayoffDraft.tsx     # Per-pod draft submission + preference editor
        ├── JoinLeague.tsx       # Invite-link landing (auth gate + confirm form)
        ├── Settings.tsx         # Account settings: display name, leave leagues
        └── PlatformAdmin.tsx    # Platform admin: trigger ESPN data sync
```

---

## Local Development

### Prerequisites

- Node 20 (use `nvm use` if you have nvm installed)
- Docker + Docker Compose (for the full stack)

### Standalone (no Docker)

```bash
cd frontend
cp .env.example .env.local   # Edit with your values (see Environment Variables)
npm install
npm run dev
# App at http://localhost:5173
```

The Vite dev server proxies `/api` requests to the backend. Set `VITE_API_TARGET` in `.env.local` to point at your backend if it's not on `http://localhost:8000`.

### Full Stack (Docker Compose)

From the project root:

```bash
docker compose up
```

This starts the frontend at **http://localhost:5173**, the backend API at **http://localhost:8000**, and supporting services (postgres, localstack). The frontend container hot-reloads on source changes.

### npm Scripts

| Script | What it does |
|--------|-------------|
| `npm run dev` | Start Vite dev server on `http://0.0.0.0:5173` |
| `npm run build` | TypeScript check + production bundle to `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | Run ESLint across `src/` |
| `npm run format` | Run Prettier across `src/` |
| `npm run type-check` | TypeScript check without emit |

---

## Environment Variables

Variables are prefixed with `VITE_` to be accessible in the browser via `import.meta.env.*`. The `.env.example` file lists all required variables.

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_GOOGLE_CLIENT_ID` | Yes (for Google OAuth) | Google OAuth 2.0 client ID from Google Cloud Console |
| `VITE_API_TARGET` | Docker only | Backend base URL used as Vite proxy target (default: `http://localhost:8000`). Not needed in native dev. |

> **Note:** The Axios client uses `/api/v1` as its base URL (relative path), which is proxied to the backend in dev and reverse-proxied by nginx in production. `VITE_API_URL` is not used by the Axios client.

---

## Routing

All routes are defined in [src/App.tsx](src/App.tsx). Routes that require authentication are wrapped in `<Layout>`, which handles the auth guard and session bootstrap.

| Route | Component | Auth | Notes |
|-------|-----------|------|-------|
| `/` | `Welcome` | ❌ | Redirects to `/leagues` if already authenticated |
| `/login` | `Login` | ❌ | Email/password + Google OAuth; honors `?next=` redirect |
| `/register` | `Register` | ❌ | Create account; honors `?next=` redirect |
| `/forgot-password` | `ForgotPassword` | ❌ | Request password reset email |
| `/reset-password?token=…` | `ResetPassword` | ❌ | Set new password; token comes from email link |
| `/join/:inviteCode` | `JoinLeague` | ⚠️ | Public but redirects to login if unauthenticated |
| `/leagues` | `Leagues` | ✅ | League list, create, join, pending requests |
| `/leagues/new` | `CreateLeague` | ✅ | Multi-step league creation wizard |
| `/leagues/:leagueId` | `Dashboard` | ✅ | Per-league home with active tournament + standings |
| `/leagues/:leagueId/pick` | `MakePick` | ✅ | Golfer selection (regular season and playoff preferences) |
| `/leagues/:leagueId/picks` | `MyPicks` | ✅ | Season pick history with member filter |
| `/leagues/:leagueId/tournaments/:tournamentId` | `TournamentDetail` | ✅ | Live leaderboard + scorecards |
| `/leagues/:leagueId/leaderboard` | `Leaderboard` | ✅ | Full standings table |
| `/leagues/:leagueId/rules` | `LeagueRules` | ✅ | Read-only rules + league config |
| `/leagues/:leagueId/manage` | `ManageLeague` | ✅ | Manager panel (redirects non-managers away) |
| `/leagues/:leagueId/playoff` | `PlayoffBracket` | ✅ | Full bracket view for all members |
| `/leagues/:leagueId/playoff/pod/:podId` | `PlayoffDraft` | ✅ | Per-pod draft status + preference editor |
| `/settings` | `Settings` | ✅ | Account settings |
| `/admin` | `PlatformAdmin` | ✅ | Platform admin only (checked via `user.is_platform_admin`) |
| `*` | — | — | Catch-all redirect to `/` |

**Auth guard pattern:** `<Layout>` calls `useAuth()` on mount to attempt a silent session restore (via httpOnly refresh cookie). While the restore is in flight, a loading spinner is shown and navigation is blocked. On failure, the user is redirected to `/login` with the current path preserved as `?next=`.

**Public page pattern (Welcome):** `Welcome.tsx` reads `useAuthStore` directly — not `useAuth()` — to avoid triggering the session bootstrap on a public page. If a token is already in memory, it redirects to `/leagues` immediately.

---

## Auth System

### Zustand Store (`src/store/authStore.ts`)

The store holds only the in-memory access token and the current user object. It never touches `localStorage` or `sessionStorage`.

```typescript
interface AuthState {
  token: string | null;                           // JWT access token (in-memory only)
  user: User | null;                              // Current user profile
  setAuth: (user: User, token: string) => void;  // Set both after login/register
  setToken: (token: string) => void;             // Set token only (used by refresh interceptor)
  clearAuth: () => void;                         // Clear everything on logout/failure
}
```

### useAuth Hook (`src/hooks/useAuth.ts`)

The **only** hook pages and components should call for auth. Do not read `useAuthStore` directly from components.

| Export | Description |
|--------|-------------|
| `login(email, password)` | POST to `/auth/login`, store token + user, navigate to `?next` or `/leagues` |
| `loginWithGoogle(id_token)` | POST to `/auth/google` with Google ID token, same flow as login |
| `register(email, password, display_name)` | POST to `/auth/register`, same flow as login |
| `logout()` | POST to `/auth/logout` (clears httpOnly cookie), clear Zustand state, navigate to `/login` |
| `bootstrapping` | `true` while silent session restore is in flight — show loading state, don't redirect |
| `token` | Current access token from the store |
| `user` | Current user profile from the store |

### Session Bootstrap

On first mount of `<Layout>` (i.e., any protected route):

1. If a token is already in memory → skip (user is already logged in, e.g. navigated between routes)
2. Otherwise → call `POST /auth/refresh` using the httpOnly refresh cookie
   - **Success:** fetch `GET /users/me`, write token + user to the store, set `bootstrapping = false`
   - **Failure:** clear auth, set `bootstrapping = false` (redirect happens in the component)
3. Public pages bypass this entirely

Because the refresh token lives in an httpOnly cookie, a hard page refresh silently restores the session before the user sees anything — the experience is seamless.

### JWT Interceptors (`src/api/client.ts`)

| Trigger | Action |
|---------|--------|
| Every outgoing request | Attach `Authorization: Bearer {token}` header if a token is in memory |
| `401` response | Attempt one silent token refresh; retry the original request with the new token |
| Refresh succeeds | Update token in Zustand store via `setToken()`; retry the original request |
| Refresh fails | Call `clearAuth()`, redirect to `/login` (skipped on `/login`, `/register`, `/join` to avoid loops) |

Multiple concurrent requests that trigger a 401 share a single refresh promise — the token is only refreshed once even if several requests fail simultaneously.

---

## API Layer

### Axios Client (`src/api/client.ts`)

- **Base URL:** `/api/v1` (relative — proxied in dev, reverse-proxied by nginx in production)
- **`withCredentials: true`** — sends the httpOnly refresh cookie on every request
- **Timeout:** 30 seconds

**Never import `axios` directly.** Always use `src/api/client.ts`.

### API Functions (`src/api/endpoints.ts`)

All functions return unwrapped data (not the raw Axios response). TypeScript interfaces mirror the backend Pydantic schemas exactly.

#### `authApi`
| Function | Method + Path | Returns |
|----------|--------------|---------|
| `login(email, password)` | POST `/auth/login` | `TokenResponse` |
| `register(email, password, display_name)` | POST `/auth/register` | `TokenResponse` |
| `google(id_token)` | POST `/auth/google` | `TokenResponse` |
| `refresh()` | POST `/auth/refresh` | `TokenResponse` |
| `logout()` | POST `/auth/logout` | `void` |
| `forgotPassword(email)` | POST `/auth/forgot-password` | `void` (always 200) |
| `resetPassword(token, new_password)` | POST `/auth/reset-password` | `TokenResponse` |

#### `usersApi`
| Function | Method + Path | Returns |
|----------|--------------|---------|
| `me()` | GET `/users/me` | `User` |
| `updateMe(display_name)` | PATCH `/users/me` | `User` |
| `myLeagues()` | GET `/users/me/leagues` | `League[]` |

#### `leaguesApi`
| Function | Method + Path | Returns |
|----------|--------------|---------|
| `create(name, no_pick_penalty?)` | POST `/leagues` | `League` |
| `get(leagueId)` | GET `/leagues/{id}` | `League` |
| `update(leagueId, data)` | PATCH `/leagues/{id}` | `League` |
| `members(leagueId)` | GET `/leagues/{id}/members` | `LeagueMember[]` |
| `updateMemberRole(leagueId, userId, role)` | PATCH `/leagues/{id}/members/{uid}/role` | `LeagueMember` |
| `removeMember(leagueId, userId)` | DELETE `/leagues/{id}/members/{uid}` | `void` |
| `leaveLeague(leagueId)` | DELETE `/leagues/{id}/members/me` | `void` |
| `pendingRequests(leagueId)` | GET `/leagues/{id}/requests` | `LeagueRequest[]` |
| `approveRequest(leagueId, userId)` | POST `/leagues/{id}/requests/{uid}/approve` | `void` |
| `denyRequest(leagueId, userId)` | DELETE `/leagues/{id}/requests/{uid}` | `void` |
| `cancelMyRequest(leagueId)` | DELETE `/leagues/{id}/requests/me` | `void` |
| `joinPreview(inviteCode)` | GET `/leagues/join/{code}` | `LeagueJoinPreview` |
| `joinByCode(inviteCode)` | POST `/leagues/join/{code}` | `LeagueRequest` |
| `myRequests()` | GET `/leagues/my-requests` | `LeagueRequest[]` |
| `getTournaments(leagueId)` | GET `/leagues/{id}/tournaments` | `LeagueTournamentOut[]` |
| `updateTournaments(leagueId, tournaments)` | PUT `/leagues/{id}/tournaments` | `LeagueTournamentOut[]` |

#### `tournamentsApi`
| Function | Method + Path | Returns |
|----------|--------------|---------|
| `list(status?)` | GET `/tournaments` | `Tournament[]` |
| `get(tournamentId)` | GET `/tournaments/{id}` | `Tournament` |
| `field(tournamentId)` | GET `/tournaments/{id}/field` | `GolferInField[]` |
| `leaderboard(tournamentId)` | GET `/tournaments/{id}/leaderboard` | `Leaderboard` |
| `syncStatus(tournamentId)` | GET `/tournaments/{id}/sync-status` | `SyncStatus` |

#### `picksApi`
| Function | Method + Path | Returns |
|----------|--------------|---------|
| `submit(leagueId, tournament_id, golfer_id)` | POST `/leagues/{id}/picks` | `Pick` |
| `change(leagueId, pickId, golfer_id)` | PATCH `/leagues/{id}/picks/{pickId}` | `Pick` |
| `mine(leagueId)` | GET `/leagues/{id}/picks/mine` | `Pick[]` |
| `all(leagueId)` | GET `/leagues/{id}/picks` | `AllPicksResponse` |
| `adminOverride(leagueId, data)` | PUT `/leagues/{id}/picks/admin-override` | `Pick \| void` |

#### `standingsApi`
| Function | Method + Path | Returns |
|----------|--------------|---------|
| `get(leagueId)` | GET `/leagues/{id}/standings` | `StandingsResponse` |

#### `playoffApi`
| Function | Method + Path | Returns |
|----------|--------------|---------|
| `getConfig(leagueId)` | GET `/leagues/{id}/playoff/config` | `PlayoffConfigOut` |
| `createConfig(leagueId, data)` | POST `/leagues/{id}/playoff/config` | `PlayoffConfigOut` |
| `updateConfig(leagueId, data)` | PATCH `/leagues/{id}/playoff/config` | `PlayoffConfigOut` |
| `getBracket(leagueId)` | GET `/leagues/{id}/playoff/bracket` | `PlayoffBracketOut` |
| `openRoundDraft(leagueId, roundId)` | POST `/leagues/{id}/playoff/rounds/{rid}/open` | `void` |
| `resolveRoundDraft(leagueId, roundId)` | POST `/leagues/{id}/playoff/rounds/{rid}/resolve` | `void` |
| `scoreRound(leagueId, roundId)` | POST `/leagues/{id}/playoff/rounds/{rid}/score` | `void` |
| `advanceBracket(leagueId, roundId)` | POST `/leagues/{id}/playoff/rounds/{rid}/advance` | `void` |
| `getPod(leagueId, podId)` | GET `/leagues/{id}/playoff/pods/{podId}` | `PlayoffPodOut` |
| `getDraftStatus(leagueId, podId)` | GET `/leagues/{id}/playoff/pods/{podId}/draft` | `PlayoffDraftStatus` |
| `getPreferences(leagueId, podId)` | GET `/leagues/{id}/playoff/pods/{podId}/preferences` | `PlayoffPreference[]` |
| `submitPreferences(leagueId, podId, preferences)` | PUT `/leagues/{id}/playoff/pods/{podId}/preferences` | `PlayoffPreference[]` |
| `overrideResult(leagueId, data)` | POST `/leagues/{id}/playoff/override` | `void` |
| `getMyPod(leagueId)` | GET `/leagues/{id}/playoff/my-pod` | `MyPlayoffPodOut` |
| `getMyPicks(leagueId)` | GET `/leagues/{id}/playoff/my-picks` | `PlayoffMyPicksOut[]` |

#### `adminApi`
| Function | Method + Path | Returns |
|----------|--------------|---------|
| `fullSync(year?)` | POST `/admin/sync` | `void` |
| `syncTournament(pgaTourId)` | POST `/admin/sync/{pgaTourId}` | `void` |

### Key TypeScript Interfaces

| Interface | Key Fields |
|-----------|-----------|
| `User` | `id`, `email`, `display_name`, `is_platform_admin`, `created_at` |
| `League` | `id`, `name`, `invite_code`, `is_public`, `no_pick_penalty`, `created_at` |
| `Tournament` | `id`, `pga_tour_id`, `name`, `start_date`, `end_date`, `multiplier`, `purse_usd`, `status` |
| `LeagueTournamentOut` | Extends `Tournament` + `effective_multiplier`, `all_r1_teed_off`, `is_playoff_round` |
| `GolferInField` | Extends `Golfer` + `tee_time: string \| null` (UTC ISO datetime) |
| `Pick` | `id`, `tournament_id`, `golfer_id`, `golfer_name`, `points_earned`, `earnings_usd`, `is_locked`, `finish_position`, `is_tied`, `golfer_status` |
| `StandingsRow` | `rank`, `is_tied`, `user_id`, `display_name`, `total_points`, `pick_count`, `missed_count` |
| `Leaderboard` | `tournament_id`, `entries: LeaderboardEntry[]`, `last_synced_at` |
| `LeaderboardEntry` | `golfer_id`, `golfer_name`, `finish_position`, `is_tied`, `status`, `earnings_usd`, `total_score_to_par`, `rounds: RoundSummary[]`, `partner_name` |
| `PlayoffPodOut` | `id`, `bracket_position`, `status`, `winner_user_id`, `members[]`, `picks[]`, `active_draft_slot`, `is_picks_visible` |
| `MyPlayoffPodOut` | `is_playoff_week`, `is_in_playoffs`, `active_pod_id`, `tournament_id`, `round_status`, `has_submitted`, `required_preference_count`, `deadline` |

---

## Hooks

### `useLeague.ts`

| Hook | React Query Key | What it fetches |
|------|----------------|----------------|
| `useMyLeagues()` | `["myLeagues"]` | `GET /users/me/leagues` |
| `useLeague(leagueId)` | `["league", leagueId]` | `GET /leagues/{id}` |
| `useLeagueMembers(leagueId)` | `["leagueMembers", leagueId]` | `GET /leagues/{id}/members` |
| `useJoinPreview(inviteCode)` | `["joinPreview", inviteCode]` | `GET /leagues/join/{code}` |
| `useMyRequests()` | `["myRequests"]` | `GET /leagues/my-requests` |
| `useLeagueTournaments(leagueId)` | `["leagueTournaments", leagueId]` | `GET /leagues/{id}/tournaments` |
| `useCreateLeague()` | — | Mutation: `POST /leagues` |
| `useUpdateLeague(leagueId)` | — | Mutation: `PATCH /leagues/{id}` |
| `useJoinByCode()` | — | Mutation: `POST /leagues/join/{code}` |
| `useCancelMyRequest()` | — | Mutation: `DELETE /leagues/{id}/requests/me` |
| `useUpdateLeagueTournaments(leagueId)` | — | Mutation: `PUT /leagues/{id}/tournaments` |

### `usePick.ts`

| Hook | React Query Key | What it fetches | Notes |
|------|----------------|----------------|-------|
| `useTournaments(status?)` | `["tournaments", status\|"all"]` | `GET /tournaments` | — |
| `useTournamentField(tournamentId)` | `["tournamentField", tournamentId]` | `GET /tournaments/{id}/field` | — |
| `useAllGolfers()` | `["allGolfers"]` | `GET /golfers` | 5 min stale time |
| `useMyPicks(leagueId)` | `["myPicks", leagueId]` | `GET /leagues/{id}/picks/mine` | — |
| `useAllPicks(leagueId)` | `["allPicks", leagueId]` | `GET /leagues/{id}/picks` | — |
| `useTournamentPicksSummary(leagueId, tournamentId)` | `["tournamentPicksSummary", leagueId, tournamentId]` | `GET /leagues/{id}/picks/tournament/{tid}` | 1 min stale |
| `useStandings(leagueId)` | `["standings", leagueId]` | `GET /leagues/{id}/standings` | 5 min stale |
| `useTournamentLeaderboard(tournamentId)` | `["tournamentLeaderboard", tournamentId]` | `GET /tournaments/{id}/leaderboard` | Invalidated by sync-status changes |
| `useTournamentSyncStatus(tournamentId)` | `["tournamentSyncStatus", tournamentId]` | `GET /tournaments/{id}/sync-status` | **Polls every 30s while `in_progress`**; on `last_synced_at` change, invalidates leaderboard |
| `useSubmitPick(leagueId)` | — | Mutation: `POST /leagues/{id}/picks` | — |
| `useChangePick(leagueId)` | — | Mutation: `PATCH /leagues/{id}/picks/{pickId}` | — |
| `useAdminOverridePick(leagueId)` | — | Mutation: `PUT /leagues/{id}/picks/admin-override` | — |
| `useGolferScorecard(tournamentId, golferId, round)` | `["golferScorecard", tournamentId, golferId, round]` | `GET /tournaments/{id}/golfers/{gid}/scorecard` | Polls every 60s while live |

### `usePlayoff.ts`

| Hook | React Query Key | What it fetches | Notes |
|------|----------------|----------------|-------|
| `usePlayoffConfig(leagueId)` | `["playoffConfig", leagueId]` | `GET /leagues/{id}/playoff/config` | — |
| `useBracket(leagueId)` | `["playoffBracket", leagueId]` | `GET /leagues/{id}/playoff/bracket` | **Polls every 60s while active** |
| `usePodDetail(leagueId, podId)` | `["playoffPod", leagueId, podId]` | `GET /leagues/{id}/playoff/pods/{podId}` | — |
| `usePodDraftStatus(leagueId, podId)` | `["playoffDraftStatus", leagueId, podId]` | `GET /leagues/{id}/playoff/pods/{podId}/draft` | **Polls every 30s while drafting** |
| `useMyPreferences(leagueId, podId)` | `["playoffPreferences", leagueId, podId]` | `GET /leagues/{id}/playoff/pods/{podId}/preferences` | — |
| `useMyPlayoffPod(leagueId)` | `["myPlayoffPod", leagueId]` | `GET /leagues/{id}/playoff/my-pod` | Polls every 30s while drafting |
| `useMyPlayoffPicks(leagueId)` | `["myPlayoffPicks", leagueId]` | `GET /leagues/{id}/playoff/my-picks` | 1 min stale |
| `useCreatePlayoffConfig(leagueId)` | — | Mutation: `POST /leagues/{id}/playoff/config` | — |
| `useUpdatePlayoffConfig(leagueId)` | — | Mutation: `PATCH /leagues/{id}/playoff/config` | — |
| `useOpenRoundDraft(leagueId)` | — | Mutation: `POST /leagues/{id}/playoff/rounds/{rid}/open` | — |
| `useResolveRoundDraft(leagueId)` | — | Mutation: `POST /leagues/{id}/playoff/rounds/{rid}/resolve` | — |
| `useScoreRound(leagueId)` | — | Mutation: `POST /leagues/{id}/playoff/rounds/{rid}/score` | — |
| `useAdvanceBracket(leagueId)` | — | Mutation: `POST /leagues/{id}/playoff/rounds/{rid}/advance` | — |
| `useSubmitPreferences(leagueId, podId)` | — | Mutation: `PUT /leagues/{id}/playoff/pods/{podId}/preferences` | — |
| `useOverridePlayoffResult(leagueId)` | — | Mutation: `POST /leagues/{id}/playoff/override` | — |
| `useRevisePlayoffPick(leagueId)` | — | Mutation: `PATCH /leagues/{id}/playoff/picks/{pickId}` | — |

---

## Pages

### Public Pages

**`Welcome.tsx`** — Public landing page. Reads `useAuthStore` directly (not `useAuth`) to check for an existing token without triggering session bootstrap. Redirects to `/leagues` if authenticated. Displays a hero section, feature list, and sign-in / create-account CTAs.

**`Login.tsx`** — Email/password form + Google OAuth button. Calls `useAuth().login()` or `loginWithGoogle()`. Preserves `?next=` parameter and cross-links to `/register?next=...` so the destination is maintained across auth pages.

**`Register.tsx`** — Create account form (display name, email, password) + Google OAuth. Same `?next=` pattern as Login.

**`ForgotPassword.tsx`** — Single email input. On submit, calls `authApi.forgotPassword()` and always shows a neutral success message regardless of whether the email exists (prevents email enumeration). Links back to `/login`.

**`ResetPassword.tsx`** — Reads `token` from `useSearchParams()`. If absent, shows an error immediately with a link to request a new one. Two fields: new password (min 8 chars) + confirm password (client-side match check). On success, stores the returned access token and navigates to `/leagues` (auto-login). On `400`, shows "Invalid or expired link" with a link to `/forgot-password`.

**`JoinLeague.tsx`** — Invite-link landing. Reads `inviteCode` from `useParams()`, fetches a preview of the league (name, member count) without side effects, then shows a confirm form. Redirects to `/login?next=/join/:inviteCode` if unauthenticated.

### League Pages

**`Leagues.tsx`** — Shows all leagues the user belongs to as `LeagueCard` components. Includes a join-by-code input and a link to create a new league. Pending join requests are listed separately with a cancel button.

**`CreateLeague.tsx`** — Multi-step wizard: (1) league name + no-pick penalty, (2) tournament schedule selection. Creates the league and redirects to its Dashboard on completion.

**`Dashboard.tsx`** — Per-league home. Shows the current active tournament (pick status, tournament badge), a standings preview (top 5), and playoff context (draft status, pod info) when playoffs are active.

**`MakePick.tsx`** — Golfer selection for the current tournament. Fetches the tournament field and the user's pick history to determine which golfers are "used" (no-repeat rule) and which have "teed off" (locked). In playoff weeks, renders `PlayoffPreferenceEditor` instead of a standard golfer picker. Supports both submitting a new pick and changing an existing one.

**`MyPicks.tsx`** — Season pick history showing each tournament, the picked golfer, earnings, and whether picks are pending/hidden/visible. A member dropdown lets managers (or any user) view another member's picks. Stat cards at the top summarize total points, pick count, and missed picks. Handles both regular-season and playoff pick displays.

**`Leaderboard.tsx`** — Full standings table using `StandingsTable`. Shows rank, display name, total points, picks made, and missed picks. Medal highlights (gold/silver/bronze) for the top 3.

**`TournamentDetail.tsx`** — Live tournament leaderboard with position, golfer name, score-to-par, and earnings. Syncs automatically via `useTournamentSyncStatus` polling. Each row is expandable to show per-round hole-by-hole scorecards.

**`LeagueRules.tsx`** — Read-only page for all members. Shows league settings (name, no-pick penalty), the full game rules, and playoff configuration if enabled.

**`ManageLeague.tsx`** — Manager-only panel with tabs/sections for: invite link, pending join requests (approve/deny), member list (change roles, remove members), tournament schedule (checkboxes + per-tournament multiplier dropdowns), and playoff configuration (size, draft style, picks per round).

**`PlayoffBracket.tsx`** — Scrollable bracket view. Shows all rounds and pods. Bracket auto-refreshes every 60 seconds. Clicking a pod navigates to that pod's `PlayoffDraft` page.

**`PlayoffDraft.tsx`** — Shows draft status for a specific pod (who has submitted preferences, resolved pick assignments). Members submit a ranked preference list via `PlayoffPreferenceEditor`. Eliminated members and non-playoff members see a read-only view.

### Account Pages

**`Settings.tsx`** — Edit display name. Lists all leagues the user belongs to with a leave button for each.

**`PlatformAdmin.tsx`** — Platform-admin-only. Buttons to trigger a full ESPN data sync or sync a specific tournament by its ESPN ID. Shows sync progress and status.

---

## Components

### `Layout.tsx`

Auth-guarded shell. Handles:
- Session bootstrap on mount (calls `useAuth()`)
- Shows full-screen spinner while bootstrapping
- Redirects to `/login` if unauthenticated after bootstrap
- Renders top navigation bar (desktop) with league links
- Renders fixed bottom tab bar (mobile, inside league context)
- Renders `<Outlet />` for child routes

### `LeagueCard.tsx`

Rich card displayed on the Leagues page. Props: `league: League`. Renders:
- Green gradient header with league name and manager badge
- Stats row: user rank, total points, member count
- Active tournament section: tournament name, badge, current pick status
- "Pick" / "Change pick" quick-action button
- "Pick window closed" when `all_r1_teed_off` is true and no pick exists

### `PickForm.tsx`

Golfer search and selection form. Props:
- `field: GolferInField[]` — tournament field
- `usedGolferIds: string[]` — golfers used this season (no-repeat rule)
- `teedOffGolferIds: string[]` — golfers whose R1 tee time has passed
- `existingPick: Pick | null`
- `onSubmit: (golferId: string) => void`
- `submitting: boolean`, `error: string | null`

Search input filters the list in real time. Used/teed-off golfers are visible but greyed out and non-clickable. The existing pick is always visible and selectable regardless of tee-off status.

### `GolferCard.tsx`

Golfer selection row. Props: `golfer`, `selected?`, `alreadyUsed?`, `alreadyTeedOff?`, `onClick?`. Renders avatar, name, country, and status badges ("Used" or "Teed off"). Greyed out and non-interactive when either flag is set. Shows a green checkmark circle when selected.

### `GolferAvatar.tsx`

ESPN CDN headshot image (`https://a.espncdn.com/i/headshots/golf/players/full/{pga_tour_id}.png`). Falls back to a green circle containing the `fallback` prop (default `"—"`) on `onError`. Props: `pgaTourId`, `name`, `className?`, `fallback?: ReactNode`.

### `StandingsTable.tsx`

Golf-style standings table. Props: `rows: StandingsRow[]`, `limit?: number`. Features:
- Tied ranks shown as `T2`, `T3` etc. — first place always shown as `1` (never `T1`)
- Medal colors: gold for 1st, silver for 2nd, bronze for 3rd
- Current user's row highlighted
- `tabular-nums` on points column for digit alignment

### `TournamentBadge.tsx`

Compact tournament status display. Props: `tournament: LeagueTournamentOut`, `showDates?`, `isPlayoff?`. Renders status pill (Upcoming / Live / Final), date range, purse, and multiplier badge (2× for majors, 1.5× for The Players). Shows a playoff indicator when `isPlayoff` is true.

### `PlayoffBracketCard.tsx`

Visual representation of a single playoff pod within the bracket. Renders members' names, seeds, scores, and winner indicator. Clickable to navigate to the pod's draft page.

### `PlayoffPreferenceEditor.tsx`

Ranked preference list editor used in `MakePick.tsx` and `PlayoffDraft.tsx`. Lets members add golfers to a ranked list, reorder them, and remove them. Validates the required count before allowing submission.

### `FlagIcon.tsx`

Golf flag SVG used in the navigation and empty states. Props: `className?`.

### `Spinner.tsx`

Animated CSS spinner. Props: `className?` (default: `"w-5 h-5 text-green-600"`). Used throughout for loading states.

### `Toaster.tsx`

Renders queued toast notifications from the singleton `toast.ts` system. Mounted once in `main.tsx`. Toasts auto-dismiss after 3.5 seconds.

---

## Styling Conventions

The app uses **Tailwind CSS v4** (no `tailwind.config.js` — configured via the Vite plugin).

### Color Palette

| Purpose | Classes |
|---------|---------|
| Primary actions | `bg-green-800`, `hover:bg-green-700` |
| Highlights / surfaces | `bg-green-50`, `bg-green-100` |
| Eyebrow labels | `text-green-700`, `text-xs font-bold uppercase tracking-[0.15em]` |
| Warnings / majors | `amber-*` |
| Destructive actions | `text-red-500`, `hover:text-red-700` |
| Neutral borders | `border-gray-200` |
| Disabled / muted | `text-gray-400`, `bg-gray-50` |

Only green and amber are brand colors. **Blue should not appear** in the UI.

### Card Pattern

```
Standard:   bg-white border border-gray-200 rounded-2xl p-6 shadow-sm
Hero/dark:  bg-gradient-to-br from-green-900 via-green-800 to-green-700
```

### Button Pattern

```
Primary:    bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold py-3 px-6 rounded-xl shadow-sm
Secondary:  border border-gray-300 hover:border-green-400 text-gray-700 rounded-xl
Destructive: text-red-500 hover:text-red-700 (text-only, no background)
```

### Text Input Pattern

```
w-full border border-gray-300 rounded-lg px-3 py-2 text-sm
focus:outline-none focus:ring-2 focus:ring-green-500
```

### Spacing

- Cards: `p-6` standard, `p-10` for centered full-page cards
- Page sections: `space-y-8`
- Component gaps: `gap-4`, `gap-5`

### Empty States

```jsx
<div className="bg-gray-50 rounded-2xl p-10 text-center">
  <FlagIcon className="mx-auto mb-4 w-12 h-12 text-gray-300" />
  <h3 className="text-lg font-semibold text-gray-700">Heading</h3>
  <p className="text-sm text-gray-500">Supporting text with action link</p>
</div>
```

### Golf-Style Formatting

- Ranks: `T2`, `T3` for ties; `1` for sole leader (never `T1`)
- Points: M/K abbreviation for large values (e.g., `$1.2M`, `$450K`) in tight spaces
- `tabular-nums` on all numeric table columns for digit alignment
- Dates on dark backgrounds: `text-white/70` (not `text-green-300`)

---

## Mobile Layout

The app is **mobile-first**. Every screen must work well at 390×844 (iPhone 14 Pro) and scale up to desktop. The `sm` breakpoint (640px) is the transition point.

### Navigation

| Context | Mobile | Desktop |
|---------|--------|---------|
| Inside a league | Fixed bottom tab bar (`sm:hidden fixed bottom-0`) | Top nav links (`hidden sm:flex`) |
| Outside a league | Top nav only | Top nav only |

**Bottom tab bar tabs** (inside a league):
1. Dashboard
2. Picks
3. Leaderboard
4. Manage (if manager) / Settings (if member)

### Layout Rules

- **Page content** inside leagues: add `pb-24 sm:pb-8` to clear the bottom tab bar on mobile
- **Footer**: hidden on mobile inside leagues (`hidden sm:block`) to avoid overlap
- **Table columns**: low-priority columns use `hidden sm:table-cell` on both `<th>` and `<td>`
- **Dropdowns**: `w-full sm:w-auto` to prevent viewport overflow on mobile
- **Grids**: `grid sm:grid-cols-2` (stack on mobile, side-by-side on desktop)

---

## Key Patterns

### Mutations Always Invalidate Related Queries

```ts
const mutation = useMutation({
  mutationFn: (data) => picksApi.submit(leagueId, data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["myPicks", leagueId] });
    queryClient.invalidateQueries({ queryKey: ["standings", leagueId] });
  },
});
```

### Queries Depend on Route Params

Use `enabled: !!param` to prevent fetching with `undefined`:

```ts
const { data } = useQuery({
  queryKey: ["league", leagueId],
  queryFn: () => leaguesApi.get(leagueId!),
  enabled: !!leagueId,
});
```

### Form Inputs Don't Reset on Refetch

Initialize from loaded data using `useEffect` + a `initializedRef` guard:

```ts
const initializedRef = useRef(false);
useEffect(() => {
  if (data && !initializedRef.current) {
    setName(data.name);
    initializedRef.current = true;
  }
}, [data]);
```

### Nested Interactive Elements Inside Links

Nested `<a>` tags are invalid HTML. When a whole card is a `<Link>`, inner interactive elements use a `<button>` + `useNavigate()` with `e.preventDefault()` to stop the outer link from firing:

```tsx
<Link to={`/leagues/${league.id}`}>
  <button onClick={(e) => { e.preventDefault(); navigate(`/leagues/${league.id}/pick`); }}>
    Make pick
  </button>
</Link>
```

### Error Messages from the Backend

```ts
const message = err.response?.data?.detail ?? "Something went wrong.";
```

### Pick Window Closed Detection

`LeagueTournamentOut.all_r1_teed_off` is `true` once every Round 1 tee time has passed. When this is true and the user has no pick, the pick button is hidden and "Pick window closed" is shown instead.

### Tee-Time Locking (MakePick)

`GolferInField.tee_time` is a UTC ISO datetime string (or `null` before tee times are published). `MakePick` compares each golfer's tee time to `Date.now()` to build `teedOffGolferIds`. Golfers in this set are greyed out with a "Teed off" label. The existing pick is always exempt.

### Live Leaderboard Sync

`useTournamentSyncStatus` polls every 30 seconds while the tournament is `in_progress`. When `last_synced_at` changes (new data from ESPN), it invalidates `["tournamentLeaderboard", tournamentId]`, which triggers a re-fetch of the leaderboard. This avoids fetching leaderboard data on every poll — only re-fetches when the backend has new data.

### Toast Notifications

```ts
import { toast } from "../toast";

toast.success("Pick saved!");
toast.error("Something went wrong.");
```

No context provider required. `<Toaster />` is mounted once at the app root in `main.tsx`.

---

## Docker Setup

**Development (`Dockerfile.dev`):**

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

Source code is mounted as a volume (`./frontend:/app`) for hot-reload. An anonymous volume (`/app/node_modules`) preserves installed packages inside the container so the host `node_modules` doesn't shadow them.

**Production (`Dockerfile`):**

Multi-stage build:
1. **Build stage:** Node 20 Alpine — installs deps, runs `npm run build`, outputs `dist/`
2. **Serve stage:** nginx Alpine — copies `dist/` and `nginx.conf`; serves the SPA with history-mode fallback; proxies `/api` to the backend service

**nginx.conf highlights:**
- All routes fall back to `index.html` (React Router history mode)
- `/api` location proxied to backend
- Gzip compression enabled for JS/CSS/HTML assets
