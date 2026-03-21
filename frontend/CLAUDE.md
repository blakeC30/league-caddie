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
│   ├── MyPicks.tsx         # Season pick history + stat cards
│   ├── Leaderboard.tsx     # Full standings table with tournament breakdown
│   ├── ManageLeague.tsx    # Manager panel — invite, settings, members, schedule (single checkbox per tournament), playoff config (auto-uses last N future tournaments as playoff rounds)
│   ├── ManagePlayoff.tsx   # Manager playoff panel — round operations (open/resolve/score/advance), override; no tournament assignment (auto-assigned at seeding)
│   ├── LeagueRules.tsx     # Read-only rules + league config view (all members) — shows league settings + game rules; playoffs section shown only when enabled
│   ├── PlayoffBracket.tsx  # Public bracket view — all rounds, pods, clickable pod cards
│   ├── PlayoffDraft.tsx    # Per-pod draft — submission status, preference editor, resolved picks
│   ├── JoinLeague.tsx      # Invite-link landing page (auth gate + confirm form)
│   ├── Settings.tsx        # User account settings — display name, league membership
│   ├── Pricing.tsx         # Public pricing tiers — standalone page (no Layout), reads ?league_id=
│   ├── BillingSuccess.tsx  # Post-Stripe success page — standalone (no Layout), reads ?session_id & ?league_id
│   ├── BillingCanceled.tsx # Post-Stripe cancel page — standalone (no Layout), reads ?league_id
│   └── PlatformAdmin.tsx   # Platform admin only — data sync trigger
├── components/
│   ├── Layout.tsx          # Auth-guarded shell — top nav, mobile bottom tab bar, auth gate
│   ├── LeagueCard.tsx      # League card on Leagues page (rank, points, tournament info)
│   ├── PickForm.tsx        # Golfer selection (used by MakePick)
│   ├── GolferCard.tsx      # Selectable golfer row inside PickForm
│   ├── GolferAvatar.tsx    # Circular headshot from CDN with fallback initials
│   ├── StandingsTable.tsx  # Standings table (used by Dashboard + Leaderboard)
│   ├── TournamentBadge.tsx # Status/major badge for a tournament
│   └── FlagIcon.tsx        # Golf flag SVG icon used in nav and empty states
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
/leagues                        → Leagues (auth required)
/leagues/:leagueId              → Dashboard
/leagues/:leagueId/pick         → MakePick
/leagues/:leagueId/picks        → MyPicks
/leagues/:leagueId/leaderboard  → Leaderboard
/leagues/:leagueId/rules        → LeagueRules (all members — read-only rules + league config)
/leagues/:leagueId/manage       → ManageLeague (manager only — self-redirects non-managers)
/leagues/:leagueId/manage/playoff → ManagePlayoff (manager only — playoff config + round operations)
/leagues/:leagueId/playoff      → PlayoffBracket (all members — scrollable bracket view)
/leagues/:leagueId/playoff/draft/:podId → PlayoffDraft (all members — submission status + preference editor)
/leagues/new                    → CreateLeague (auth required — create a new league with schedule)
/settings                       → Settings (auth required — display name, leave leagues)
/admin                          → PlatformAdmin (platform admin only)
/pricing                        → Pricing (public — standalone, no Layout; ?league_id= optional to pre-select league for checkout)
/billing/success                → BillingSuccess (public — standalone; ?session_id & ?league_id)
/billing/canceled               → BillingCanceled (public — standalone; ?league_id)
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

## UI/UX Standard

All UI work must be done as a **seasoned UI/UX engineer** would do it. Every screen should feel polished, intentional, and cohesive — not like a functional prototype. Apply these principles to every change:

- **Visual hierarchy**: use eyebrow labels (`text-xs font-bold uppercase tracking-[0.15em] text-green-700`), large headings (`text-3xl font-bold`), and subdued supporting text to guide the eye
- **Breathing room**: generous padding (`p-6`, `p-8`, `p-10`), section spacing (`space-y-8`), never cramped layouts
- **Rounded and soft**: `rounded-2xl` for cards and containers, `rounded-xl` for buttons and inputs
- **Depth and surface**: `shadow-sm` on cards, `shadow-lg` on elevated modals/confirmations, `border border-gray-200` for subtle separation
- **Gradient accents**: dark tournament/hero bands use `bg-gradient-to-r from-green-900 to-green-700` with white text; season-total cards use `bg-gradient-to-br from-green-900 via-green-800 to-green-700`
- **Empty states**: never just plain text — use a centered icon + heading + subtext + action link inside a `bg-gray-50 rounded-2xl p-16 text-center` container
- **Buttons**: primary = `bg-green-800 hover:bg-green-700 text-white font-semibold py-3 px-6 rounded-xl shadow-sm`; secondary/ghost = `border border-gray-300 hover:border-green-400 text-gray-700 rounded-xl`; destructive = `text-red-500 hover:text-red-700`
- **Section icon badges**: precede headings with `<div className="w-8 h-8 bg-green-50 text-green-700 rounded-lg flex items-center justify-center">` containing a small SVG
- **Overlay elements**: rings/outlines on focused/selected items need `p-1` buffer on the scroll container to avoid clipping

## Styling Conventions

- Color scheme: `green-800` (primary actions), `green-700` (hover), `green-50`/`green-100` (highlights), amber for warnings/majors
- Cards: `bg-white border border-gray-200 rounded-2xl p-6` (standard), `rounded-2xl p-10` (centered full-page cards)
- Primary button: `bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold py-3 px-6 rounded-xl shadow-sm`
- Text input: `w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500`
- Golf-style ranking: show `T2` for ties, no `#` prefix, first place as `1` (never `T1`)
- Use `tabular-nums` on numeric table columns for aligned digits
- Dates on dark backgrounds: `text-white/70` (not `text-green-300`, which is hard to read)

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
