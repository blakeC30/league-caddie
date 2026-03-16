# Fantasy Golf League Rules

Rules currently implemented in the application. This document covers all enforced gameplay rules — both regular season and playoffs.

---

## Regular Season

### Scoring
- **Points = golfer's tournament earnings × tournament multiplier**
- Tournament multiplier is `1.0` by default
- League managers can set any tournament in their schedule to `1.0×`, `1.5×`, or `2.0×`
- The multiplier is configured per league — different leagues can apply different multipliers to the same tournament
- Points accumulate across all tournaments in the season
- The player with the most total points at season end wins
- **Tie-breaking** (applied in order when total points are equal):
  1. **Most picks submitted** — the player who picked in more tournaments ranks higher (rewards consistent participation)
  2. **Highest single-tournament score** — the player with the better best individual week ranks higher (rewards peak performance)
  3. **Earliest league join date** — the player who joined the league first ranks higher (stable, ungameable last resort)

### Picks
- Each member submits **one pick per tournament** — a single golfer competing that week
- Picks are submitted per league; each league is independent
- **One pick per user per tournament per season per league** — no duplicate picks for the same tournament
- Picks for a tournament cannot be submitted until the **previous tournament in the league's schedule has completed and official earnings have been published** — if ESPN hasn't released prize money yet, the pick window stays closed to ensure members see accurate standings before choosing

### No-Repeat Rule
- During the regular season, a golfer can only be used once per season per league
- If a golfer has already been picked by a member in a regular season tournament, they cannot be picked again by that same member for any other regular season tournament that season
- This rule does **not** apply to the playoffs — golfers used during the regular season are eligible again in playoff rounds

### Pick Deadline and Locking

**Pre-tournament pick (submitted before the tournament starts):**
- The pick locks when the picked golfer's **Round 1 tee time passes**
- The member is stuck with that golfer once they tee off — even if the golfer withdraws mid-round or later

**Pre-tournament pick, golfer withdraws before teeing off:**
- The pick does **not** lock at the golfer's scheduled tee time
- The member may change their pick to any golfer who has not yet teed off
- This allows recovery when a golfer is a late scratch

**No pick before the tournament starts (missed the deadline):**
- As long as not every golfer in the field has teed off on Round 1, the member may still submit a pick
- The pick must be a golfer whose Round 1 tee time has not yet passed
- Once all golfers have teed off, no new pick can be submitted (no-pick penalty applies)

**Completed tournaments:** no picks or changes accepted under any circumstances

### No-Pick Penalty
- A penalty is applied when a member has no pick on record after the last Round 1 tee time has passed (i.e., once the pick window permanently closes for that tournament)
- A member who submits a late pick (after the tournament starts but before the last R1 tee time) is **not** penalized
- Default penalty: **-$50,000**
- The penalty amount is configurable per league by the league manager
- The penalty **only appears in standings once the tournament is completed** — it is not reflected during an in-progress tournament

### Pick Visibility
- A member's **own pick is always visible** to themselves
- **Other members' picks are hidden** until all Round 1 tee times have passed (i.e., the last golfer in the field has teed off on Thursday)
- This prevents members from copying each other's picks before the window closes
- Once all R1 tee times have passed, all picks become visible to everyone in the league

### Golfer Availability
- Before the official tournament field is released, any golfer in the database can be picked
- Once the field is released, only golfers **entered in that tournament** can be picked
- A golfer already used by a member this season (no-repeat rule) is never available to that member regardless of field status

### Tournament Eligibility
- Picks can only be made for tournaments that are in the **league's schedule**
- League managers control which tournaments are in the schedule
- **Only one tournament per calendar week** can be added to a league's schedule — when multiple PGA Tour events occur in the same week, the manager picks which one counts
- The schedule **locks after the last regular season tournament is completed** — no tournaments can be added or removed after that point

### Manager Overrides (Regular Season)

- The league manager may create, replace, or delete any approved member's regular season pick at any time **while the regular season is active** — the pick deadline and field eligibility rules are bypassed, but the **no-repeat rule is still enforced**: a manager cannot assign a golfer the member has already used in a different regular season tournament this season
- Once the **last regular season tournament has completed**, the regular season pick record is permanently locked — no further admin overrides are accepted for any regular season tournament
- Regular season pick overrides are not available for playoff-designated tournaments — those use the playoff pick system instead

---

## Playoffs

### Qualification
- Playoffs are **opt-in** — they are disabled by default and must be explicitly configured by the league manager
- The league manager sets the playoff size (number of qualifying players); playoff tournaments are automatically assigned — the last N tournaments in the league's schedule (by date) are reserved as playoff rounds, where N is the number of rounds required by the bracket size
- Valid playoff sizes: **0, 2, 4, 8, 16, or 32** — no other values are allowed (0 means playoffs are disabled)
- The top N players by season standings qualify, where N is the playoff size the manager configured
- The playoff bracket spans a maximum of **4 rounds** (4 tournaments)
- **Bracket seeding is automatic** — the projected bracket is visible throughout the season, calculated live from current standings and the playoff config; no manager action is required. The bracket is committed (seeded) automatically when all three conditions are met: (1) all regular-season tournaments have completed, (2) only the playoff-round tournaments remain as "scheduled", and (3) official earnings from the last regular-season tournament have been published. This ensures seedings reflect final standings. Once seeded, preference submission opens immediately

### Format — Pods
- Players are seeded by their regular season standings and placed into **pods** (matchup groups)
- The winner of each pod advances to the next round; all others are eliminated
- **Pod sizes by playoff size:**
  - **32-player bracket**: Round 1 uses pods of 4; all subsequent rounds use pods of 2
  - **All other sizes (2, 4, 8, 16)**: every round uses pods of 2
- Bracket structure by size:
  - 2 players → 1 round (1 pod of 2)
  - 4 players → 2 rounds (2 pods of 2 → 1 pod of 2)
  - 8 players → 3 rounds (4 → 2 → 1 pod of 2)
  - 16 players → 4 rounds (8 → 4 → 2 → 1 pod of 2)
  - 32 players → 4 rounds (8 pods of 4 → 4 → 2 → 1 pod of 2)

### Playoff Picks — Preference List
- Instead of picking a single golfer, each playoff member submits a **ranked preference list** of golfers before the playoff tournament begins
- Draft resolution happens **per pod** — each pod runs its own independent draft using only the preferences of its members
- Within a pod, picks are assigned in draft order using each member's highest-ranked available golfer
- The draft order algorithm is configured by the league manager (options: snake, linear, or top-seed priority)
- The **number of picks per member per round** is configured by the league manager as a list — one value per round (e.g., `[2, 1]` means 2 picks in round 1, 1 pick in round 2)
  - If fewer values are provided than there are rounds, the last value repeats for all remaining rounds (e.g., `[2]` means 2 picks in every round)
  - Each value must be a positive integer (minimum 1)
  - The manager sets this before the playoff is seeded; it cannot be changed once seeding begins
- **Required count**: members must rank exactly `pod_size × picks_per_round` golfers (e.g., a 4-person pod in a 2-pick round requires exactly 8 ranked golfers)
  - This ensures full coverage even if higher-ranked choices are taken by other members in the same pod

### Eligibility to Submit Preferences
- Only members who are **active in the current playoff round** may submit preference lists — eliminated members and non-playoff members cannot submit picks for any playoff tournament
- A member is eligible for a round only if they won their pod in the previous round (or qualified directly for Round 1)
- Eliminated members are permanently locked out of preference submission for all subsequent rounds

### Pick Submission Window
- Playoff preference lists can be submitted as soon as the **bracket is seeded** (regular-season schedule locks) for Round 1, or as soon as the **previous round is scored and winners are determined** for subsequent rounds — no manager action is required to open the window
- Preferences can be updated any number of times until the deadline
- The preference list **locks when the first Round 1 tee time of the playoff tournament passes** — unlike the regular season, the lock is triggered by the very first tee time, not the member's specific golfer's tee time
- Once any golfer in the field has teed off, no further changes to preference lists are accepted
- Picks are **resolved from preferences automatically** once the preference window closes

### Pick Visibility
- A member's **own picks are always visible** to themselves
- **Other members' resolved picks are hidden** until the first Round 1 tee time of the playoff tournament passes
- Once the first golfer in the field tees off, all picks in the pod become visible to everyone

### Golfer Availability in Playoffs
- Any golfer in the database can be ranked in a preference list at any time — there is no submission-time validation against the tournament field
- When the preference list is **resolved into picks**, only golfers who appear in the official tournament field are eligible to be assigned as a pick
- If a golfer in a member's preference list is not in the tournament field at resolution time, that golfer is silently skipped — the system moves to the next preference
- If all of a member's preferences are skipped (none are in the field and available), that member receives no pick for that slot and earns $0

### Playoff Scoring
- **Points = golfer's tournament earnings × tournament multiplier** — the same formula as the regular season, including any per-league multiplier override the manager has set for that tournament
- A playoff round **cannot be scored until official earnings are published** by ESPN — the system blocks scoring attempts while any pick's earnings are unavailable, preventing incorrect $0 scores from being locked in
- **Pod winners are determined after scoring** — the member with the highest total points in the pod advances; ties are broken by lower seed number (seed 1 beats seed 2 in a tie)
- Once winners are determined, the next round's preference window opens automatically

### Playoff No-Pick Penalty
- The no-pick penalty applies **per pick slot** in a playoff round
- If a member fails to submit a preference list before the window closes, the penalty is applied once per assigned pick slot (e.g., a 2-pick round results in 2 penalties)
- If a member submits a preference list but all of their preferences are ineligible at resolution time (golfers not in the field or already claimed), the penalty applies to each unresolved slot
- The penalty amount is the same as the regular season no-pick penalty (configurable per league by the manager)
- Penalty points are applied to the member's playoff pod total and count toward win/loss determination within the pod

### Playoff Pick Repeat Rule
- The regular season no-repeat rule does not carry over — any golfer may be ranked in a playoff preference list regardless of regular season usage
- Within a single playoff round, a golfer can only be assigned to one member in a pod (no two members in the same pod receive the same golfer)

### Manager Overrides (Playoffs)

**Individual pick revision (during the playoff tournament):**
- While a playoff tournament is **in progress**, the league manager may revise any pod member's assigned golfer
- The replacement golfer cannot already be assigned to another member in the same pod
- Individual pick revision is **not available once the tournament has completed** — no further changes to individual golfer assignments are accepted after the tournament ends

**Pod winner override (after the playoff tournament completes):**
- After a playoff tournament **completes** and the round has been **scored** (official earnings applied), the manager may override the pod winner for that round
- The override designates the winner and marks all other pod members as eliminated — it replaces the scoring-based result
- Override is only available for the round that has just been scored but **not yet advanced** — once `advance_bracket` is called and winners are propagated to the next round, the result is permanently locked
- Pod winner override is the **only** result-correction tool available after a tournament completes

**Bracket advancement after override:**
- When the manager advances the bracket after an override, the manually set winner is respected and propagated to the next round's pod
- The system does not re-determine the winner from scores when an override is in place

---

## League Management

### Membership
- Leagues are private by default — join requests require manager approval
- Each league has a unique invite link the manager shares with prospective members
- Members have one of two roles: **Manager** or **Member**
- Managers can approve/deny join requests, manage the tournament schedule, and configure playoff settings

### Member Removal
**During the regular season:**
- If a member leaves or is removed, all of their picks for the current season are deleted
- They are excluded from season standings

**During the playoffs — member is not in the playoffs:**
- Their regular season picks are deleted and they are excluded from season standings
- No impact on the playoff bracket

**During the playoffs — member is in the playoffs:**
- Their regular season picks are deleted and they are excluded from season standings
- Their playoff pod slot remains in the bracket — the bracket structure is **never** reshuffled when a member leaves
- They are **not** replaced by another member
- Any picks they had in the current round are deleted; all their pick slots are scored as no picks (the standard no-pick penalty applies per slot)
- Any preference list they had submitted is cleared
- They are permanently ineligible to win their pod — the vacant slot cannot advance to the next round under any circumstances
- Rounds that have already completed (scored and advanced) before the member left are unaffected

### Seasons
- Each league runs one active season at a time
- A season spans all scheduled tournaments for that year
- Season standings are calculated from all picks within the season
