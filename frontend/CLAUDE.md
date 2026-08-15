# Fantasy Golf Frontend

React + TypeScript + Vite app. See the root `CLAUDE.md` for project-wide rules and domain logic.

## Tech

- **React 18** + **TypeScript** + **Vite**
- **Tailwind CSS** — utility-first, no component library
- **Zustand** (`src/store/authStore.ts`) — auth state only (token + user), never localStorage
- **React Query / TanStack Query** — all server state
- **React Router v6** — file-based page components, `useParams` for `:leagueId`
- **Axios** (`src/api/client.ts`) — configured instance with JWT + refresh interceptors

## Directory Structure

```
src/
├── api/
│   ├── client.ts       # Axios instance — DO NOT import axios directly elsewhere
│   └── endpoints.ts    # All typed API functions + TypeScript interfaces
├── store/
│   └── authStore.ts    # Zustand: { token, user, setAuth, setToken, clearAuth }
├── hooks/
│   ├── useAuth.ts      # Auth actions (login, register, logout, session bootstrap)
│   ├── useLeague.ts    # All league/membership/join/tournament-schedule hooks
│   ├── usePick.ts      # Tournaments, picks, standings hooks
│   └── usePlayoff.ts   # Playoff config, bracket, draft, pod, preferences hooks
├── pages/
│   ├── Welcome.tsx         # Public landing page — shown at / for unauthenticated visitors
│   ├── Login.tsx
│   ├── Register.tsx
│   ├── ForgotPassword.tsx  # Request password reset email (public)
│   ├── ResetPassword.tsx   # Set new password via reset token from URL (public)
│   ├── Leagues.tsx         # Post-login landing — league list + create/join forms
│   ├── CreateLeague.tsx    # Multi-step league creation wizard (name, schedule, no-pick penalty)
│   ├── Dashboard.tsx       # Per-league home — current tournament, pick status, standings
│   ├── MakePick.tsx        # Golfer selection form for upcoming tournament
│   ├── Picks.tsx            # Season pick history + stat cards
│   ├── Standings.tsx        # Full standings table with tournament breakdown
│   ├── ManageLeague.tsx    # Manager panel — invite, settings, members, schedule, playoff config (auto-uses last N future tournaments as playoff rounds)
│   ├── LeagueRules.tsx     # Read-only rules + league config view (all members) — shows league settings + game rules; playoffs section shown only when enabled
│   ├── PlayoffBracket.tsx  # Full bracket view + per-pod draft (submission status, preference editor, resolved picks, pod detail modal)
│   ├── TournamentDetail.tsx # Tournament leaderboard with per-round data, pick distribution chart
│   ├── JoinLeague.tsx      # Invite-link landing page (auth gate + confirm form)
│   ├── Roster.tsx          # League member roster — display name, first/last name, email, join date
│   ├── Settings.tsx        # User account settings — display name, first/last name, league membership
│   ├── Pricing.tsx         # Public pricing tiers — standalone page (no Layout), reads ?league_id=
│   ├── BillingSuccess.tsx  # Post-Stripe success page — standalone (no Layout), reads ?session_id & ?league_id
│   ├── BillingCanceled.tsx # Post-Stripe cancel page — standalone (no Layout), reads ?league_id
│   ├── PrivacyPolicy.tsx   # Public legal page — standalone (no Layout)
│   ├── TermsOfService.tsx  # Public legal page — standalone (no Layout)
│   └── PlatformAdmin.tsx   # Platform admin only — data sync trigger
├── components/
│   ├── Layout.tsx              # Auth-guarded shell — top nav, mobile bottom tab bar, auth gate
│   ├── LeagueCard.tsx          # League card on Leagues page (rank, points, tournament info)
│   ├── PickForm.tsx            # Golfer selection (used by MakePick)
│   ├── GolferCard.tsx          # Selectable golfer row inside PickForm
│   ├── GolferAvatar.tsx        # Circular headshot from ESPN CDN with fallback initials
│   ├── StandingsTable.tsx      # Standings table (used by Dashboard + Leaderboard)
│   ├── TournamentBadge.tsx     # Status/multiplier/playoff badges + dates (compact mode for picks)
│   ├── FlagIcon.tsx            # Golf flag SVG icon used in nav and empty states
│   ├── Skeleton.tsx            # Skeleton loading components for all major pages
│   ├── Spinner.tsx             # Fallback loading spinner (secondary pages)
│   ├── ErrorBoundary.tsx       # React error boundary wrapper
│   ├── Toaster.tsx             # Toast notification system
│   ├── PlayoffBracketCard.tsx  # Pod card used in PlayoffBracket
│   ├── PlayoffPreferenceEditor.tsx # Reusable ranked preference list editor (supports team events)
│   ├── picks/                  # Pick-related sub-components
│   │   ├── PicksTable.tsx      # Season pick history cards with sort/filter
│   │   ├── SeasonTotalCard.tsx  # Gradient card showing season total points
│   │   ├── PicksStatCards.tsx   # Stat cards (submission rate, cuts, best pick, avg)
│   │   ├── MemberDropdown.tsx   # Member selector for viewing other members' picks
│   │   ├── StatCard.tsx         # Reusable stat card component
│   │   └── SortButton.tsx       # Sort toggle button
│   ├── leaderboard/            # Leaderboard sub-components
│   │   ├── StandingsTr.tsx      # Standings table row
│   │   ├── PickBarChart.tsx     # Pick distribution bar chart
│   │   ├── TournamentPicksSection.tsx # Tournament picks breakdown
│   │   ├── PlayoffRoundBreakdown.tsx  # Playoff round summary
│   │   ├── StatCard.tsx         # Leaderboard stat card
│   │   └── SortButton.tsx       # Sort toggle button
│   └── manage/                 # ManageLeague sub-components
│       ├── LeagueSettingsSection.tsx
│       ├── MembersSection.tsx
│       ├── JoinRequestsSection.tsx
│       ├── InviteLinkSection.tsx
│       ├── TournamentScheduleSection.tsx
│       ├── PlayoffConfigSection.tsx
│       ├── LeaguePlanSection.tsx
│       ├── RevisePickSection.tsx
│       ├── SendEmailSection.tsx
│       └── DangerZoneSection.tsx
└── App.tsx                 # Route definitions
```

## Routes

```
/                               → Welcome (public landing page; redirects to /leagues if already authenticated)
/login                          → Login (public)
/register                       → Register (public)
/forgot-password                → ForgotPassword (public — request reset email)
/reset-password?token=<tok>     → ResetPassword (public — set new password; token from email link)
/join/:inviteCode               → JoinLeague (public, but redirects to login if unauthenticated)
/billing/success                → BillingSuccess (public — standalone; ?session_id & ?league_id)
/billing/canceled               → BillingCanceled (public — standalone; ?league_id)
/privacy                        → PrivacyPolicy (public — standalone, no Layout)
/terms                          → TermsOfService (public — standalone, no Layout)
/leagues                        → Leagues (auth required)
/leagues/new                    → CreateLeague (auth required — create a new league with schedule)
/leagues/:leagueId              → Dashboard
/leagues/:leagueId/pick         → MakePick
/leagues/:leagueId/picks        → Picks
/leagues/:leagueId/tournaments/:tournamentId → TournamentDetail
/leagues/:leagueId/roster       → Roster (all members — name, email, join date table)
/leagues/:leagueId/standings     → Standings
/leagues/:leagueId/rules        → LeagueRules (all members — read-only rules + league config)
/leagues/:leagueId/manage       → ManageLeague (manager only — settings, members, schedule, playoff config)
/leagues/:leagueId/playoff      → PlayoffBracket (all members — bracket view, pod draft, preferences)
/settings                       → Settings (auth required — display name, first/last name, leagues)
/admin                          → PlatformAdmin (platform admin only)
/*                              → redirect to /
```

**Welcome page auth pattern**: `Welcome.tsx` reads `useAuthStore` directly (not `useAuth`) to avoid triggering session bootstrap on a public page. If a token is in memory, it redirects immediately to `/leagues`.

## React Query Cache Keys

Always use these exact key shapes — mismatches cause stale data:

| Key | Hook |
|-----|------|
| `["leagueSummaries"]` | `useLeagueSummaries()` — batch summary for Leagues page; invalidated alongside `myLeagues` |
| `["myLeagues"]` | `useMyLeagues()` |
| `["league", leagueId]` | `useLeague(leagueId)` |
| `["leagueMembers", leagueId]` | `useLeagueMembers(leagueId)` |
| `["roster", leagueId]` | `useRoster(leagueId)` |
| `["leagueTournaments", leagueId]` | `useLeagueTournaments(leagueId)` |
| `["pendingRequests", leagueId]` | `usePendingRequests(leagueId)` |
| `["myRequests"]` | `useMyRequests()` |
| `["myPicks", leagueId]` | `useMyPicks(leagueId)` |
| `["allPicks", leagueId]` | `useAllPicks(leagueId)` |
| `["standings", leagueId]` | `useStandings(leagueId)` |
| `["tournaments", status\|"all"]` | `useTournaments(status?)` |
| `["tournamentField", tournamentId]` | `useTournamentField(tournamentId)` |
| `["joinPreview", inviteCode]` | `useJoinPreview(inviteCode)` |
| `["playoffConfig", leagueId]` | `usePlayoffConfig(leagueId)` |
| `["playoffBracket", leagueId]` | `useBracket(leagueId)` — auto-refetches every 60s while active |
| `["playoffPod", leagueId, podId]` | `usePodDetail(leagueId, podId)` |
| `["playoffDraftStatus", leagueId, podId]` | `usePodDraftStatus(leagueId, podId)` — polls every 30s while drafting |
| `["playoffPreferences", leagueId, podId]` | `useMyPreferences(leagueId, podId)` |
| `["tournamentLeaderboard", tournamentId]` | `useTournamentLeaderboard(tournamentId)` — invalidated by sync-status polling, no self-refetch |
| `["tournamentSyncStatus", tournamentId]` | `useTournamentSyncStatus(tournamentId)` — polls every 30s when in_progress; on `last_synced_at` change, invalidates `tournamentLeaderboard` |
| `["leaguePurchase", leagueId]` | `useLeaguePurchase(leagueId)` — season pass purchase status; invalidated on BillingSuccess |
| `["leagueEmails", leagueId]` | `useLeagueEmails(leagueId)` — manager-sent email history (last 20); invalidated on send |
| `["stripePricing"]` | `stripeApi.getPricing()` — public pricing tiers; fetched directly in Pricing page |

## API Conventions

- **Never import axios directly** — always use `src/api/client.ts`
- All API functions live in `src/api/endpoints.ts`, grouped by domain (`authApi`, `leaguesApi`, `picksApi`, `stripeApi`, etc.)
- `stripeApi.getPricing()` → `GET /stripe/pricing` (public — no auth)
- `stripeApi.createCheckoutSession(leagueId, tier, upgrade?)` → `POST /stripe/create-checkout-session` → `{url}` (manager auth); redirect to `url`
- `authApi.forgotPassword(email)` → `POST /auth/forgot-password` — always resolves 200; catch is for network errors only
- `authApi.resetPassword(token, new_password)` → `POST /auth/reset-password` — returns `TokenResponse`; 400 = invalid/expired token
- All functions return unwrapped data (not the Axios response object)
- TypeScript interfaces in `endpoints.ts` mirror backend Pydantic schemas
- On 401, the Axios interceptor silently refreshes via the httpOnly cookie, then retries. If refresh fails, it clears auth and redirects to `/login` (skips redirect from public pages to avoid loops)

### `LeagueTournamentOut` notable fields

| Field | Type | Notes |
|---|---|---|
| `effective_multiplier` | `number` | League-level override or global tournament multiplier (e.g. `2.0` for majors) |
| `all_r1_teed_off` | `boolean` | `true` when status is `in_progress` AND every Round 1 tee time has already passed. When `true` and the member has no pick, the pick window is permanently closed — hide the pick button entirely and show "Pick window closed" instead. |

### `GolferInField` — field endpoint type

`GET /tournaments/{id}/field` returns `GolferInField[]` (not plain `Golfer[]`). `GolferInField` extends `Golfer` with:

| Field | Type | Notes |
|---|---|---|
| `tee_time` | `string \| null` | ISO datetime string (UTC). `null` when tee times haven't been assigned yet. Used by `MakePick` to compute `teedOffGolferIds` when `tournament.status === "in_progress"`. |

**Teed-off filter pattern** (in `MakePick.tsx`): golfers with a `tee_time` in the past are added to `teedOffGolferIds` and passed to `PickForm` → `GolferCard`. They are kept visible in the list but greyed out with a "Teed off" label — same visual treatment as "Used" golfers, but a different label and flag. The existing golfer's pick is always exempt from both flags so the user can still see their current selection.

## Auth Pattern

- `useAuth()` (from `src/hooks/useAuth.ts`) — the only hook components should call for auth
- `useAuthStore` (Zustand) — internal; don't call directly from pages/components
- `?next` param preserved through login → register cross-links so post-auth redirect lands correctly
- `bootstrapping` state = true while silent session restore is in flight; show a loading state, don't redirect

## Mobile-First Requirement

**Every UI change must work well on both mobile and desktop.** The desktop layout should never change as a side effect of mobile work, and mobile must never be an afterthought.

- Tailwind's breakpoint is `sm` = **640px** — use `sm:` to introduce desktop-only styles, not to hide mobile styles
- The app uses a **fixed bottom tab bar** (`sm:hidden fixed bottom-0`) for league navigation on mobile, replacing the desktop header nav links (`hidden sm:flex`). Add `pb-24 sm:pb-8` to page content inside a league to clear it
- The footer is hidden on mobile inside leagues (`hidden sm:block`) to avoid overlap with the tab bar
- **Table columns**: hide low-priority columns on mobile with `hidden sm:table-cell` on both `<th>` and `<td>`
- **Dropdowns and popovers**: use `w-full sm:w-auto` so they don't overflow the viewport on small screens
- **Points / numeric values**: abbreviate with M/K notation to prevent overflow in tight grid cells
- **Test at 390×844** (iPhone 14 Pro size) — if it looks cramped or broken at that size, fix it before finishing

## Design Language — read `DESIGN.md` first

All UI work follows **`frontend/DESIGN.md`** ("Pairings Sheet"). That document is
the authority on colour, type, shape, elevation and motion; this section only
summarises what you need to write a component. **If a value is not in
`DESIGN.md`, add it there before using it.**

Run the `unslop` skill (`.claude/skills/unslop/`) to audit a screen before
shipping it — `audit` is read-only and lists AI-slop tells with file:line.

### The short version

- **Tokens only.** Colour comes from `ink-*`, `fairway-*`, `flag-*`, `brass-*`,
  `page`, `sheet` — declared in `src/styles/theme.css`. No arbitrary hex, no
  hue outside those four ramps.
- **Type** is `font-display` (Archivo) for headings and figures, `font-sans`
  (Spline Sans) for everything else, `font-mono` (Spline Sans Mono) for
  in-table numerals. Size classes are `text-title`, `text-heading`,
  `text-subhead`, `text-body`, `text-ui`, `text-small`, `text-micro`,
  `text-figure`, `text-data` — not Tailwind's `text-xl`/`text-3xl`.
- **`text-micro uppercase` is the only uppercase style**, and it is a column
  header or a status mark. It is not a kicker above every heading.
- **Shape:** `rounded-xs` (2px) for buttons/inputs/chips, `rounded-sm` (3px) for
  panels, square for bands and table cells, `rounded-full` for circles only.
- **Elevation:** `shadow-sheet` or `shadow-raised`. There is no third option.
- **Separation ladder** — take the first rung that works: whitespace → the
  `page`→`sheet` background step → a `border-ink-200` horizontal rule →
  elevation → a full border. Rules divide; they do not enclose.
- **No gradients, no blurred decorative blobs, no dark mode, no centred hero,
  no three-up icon-card grid, no `hover:scale-*`.**
- **Motion** is `duration-[120ms] ease-board` on colour only, and it must
  survive `prefers-reduced-motion`.

### Primitives

`src/components/ui/index.tsx` exports `Button`, `ButtonLink`, `Panel`,
`SectionHeading`, `PageHeader`, `Board`, `Chip`, `Figure`, `Empty`, `Field`,
`Input`, `Rule`. Reach for these before writing new class strings.

### Required states

Every interactive element ships **hover, focus-visible, active, disabled**.
Every data surface ships **loading, empty, error**. Focus is handled globally by
the `:focus-visible` rule in `index.css` — do not remove outlines.

### Standing conventions

- Golf-style ranking: `T2` for ties, no `#` prefix, first place is `1` (never `T1`)
- `tabular-nums` on every numeric column
- Standings tables use the board header (`bg-fairway-900`); other tables use
  `text-micro` headers over a rule
- Text on the board: white for primary, `fairway-400` for meta

## Key Patterns

**Mutations always invalidate related queries:**
```ts
onSuccess: () => {
  queryClient.invalidateQueries({ queryKey: ["myLeagues"] });
}
```

**Nested `<a>` tags are invalid HTML** — if a whole card is a `<Link>`, use a `<button>` + `useNavigate()` for inner interactive elements, with `e.preventDefault()` to stop the outer link firing.

**Form inputs should not reset when React Query refetches** — initialize from loaded data with `useEffect` + a `initializedRef` boolean guard.

**Error messages from the backend** live at `err.response?.data?.detail`.

**`enabled: !!param`** on queries that depend on a route param to avoid fetching with `undefined`.
