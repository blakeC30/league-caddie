# Fantasy Golf League — Playoff Feature Design

**Document version:** 1.0
**Date:** 2026-03-10
**Status:** Implementation-ready

---

## Table of Contents

1. [Database Schema](#1-database-schema)
2. [Seeding Algorithm](#2-seeding-algorithm)
3. [Draft Slot Computation](#3-draft-slot-computation)
4. [Draft Resolution](#4-draft-resolution)
5. [Bracket Generation](#5-bracket-generation)
6. [Backend — FastAPI](#6-backend--fastapi)
7. [Frontend — React/TypeScript](#7-frontend--reacttypescript)
8. [Concerns and Edge Cases](#8-concerns-and-edge-cases)
9. [Implementation Order](#9-implementation-order)

---

## 1. Database Schema

All new tables use the same conventions as the existing codebase:
- UUID primary keys with `default=uuid.uuid4` (except auto-increment join tables)
- `DateTime(timezone=True)` for all timestamps
- Status stored as plain `String`, not PostgreSQL ENUM
- `from_attributes=True` on all Pydantic output schemas

### 1.1 `playoff_configs`

One row per league per season. This is the single source of truth for whether playoffs are enabled and how they are structured.

```
Table: playoff_configs
```

| Column | Type | Constraints | Rationale |
|--------|------|-------------|-----------|
| `id` | `UUID` | PK, `default=uuid4` | Stable identifier |
| `league_id` | `UUID` | FK `leagues.id`, NOT NULL | Playoff belongs to one league |
| `season_id` | `Integer` | FK `seasons.id`, NOT NULL | Playoff belongs to one active season |
| `is_enabled` | `Boolean` | NOT NULL, default `false` | Manager toggle — off by default |
| `playoff_size` | `Integer` | NOT NULL, default `16` | Must be power of 2: 4, 8, 16, 32, 64 |
| `draft_style` | `String(30)` | NOT NULL, default `'snake'` | `snake`, `linear`, `top_seed_priority` — applied at resolution time, not during the submission window |
| `round1_picks_per_player` | `Integer` | NOT NULL, default `2` | Golfers per player in round 1 (pod format) |
| `subsequent_picks_per_player` | `Integer` | NOT NULL, default `4` | Golfers per player in rounds 2+ (1v1) |
| `status` | `String(20)` | NOT NULL, default `'pending'` | `pending`, `seeded`, `active`, `completed` |
| `seeded_at` | `DateTime(tz=True)` | nullable | When admin ran seed_playoff() |
| `created_at` | `DateTime(tz=True)` | `server_default=func.now()` | Audit timestamp |
| `updated_at` | `DateTime(tz=True)` | `server_default=func.now()`, `onupdate=func.now()` | Last config change |

**Constraints:**
- `UNIQUE(league_id, season_id)` — one playoff config per league per season
- `CHECK(playoff_size IN (4, 8, 16, 32, 64))` — enforced in the Pydantic validator (not DB CHECK, consistent with codebase pattern)
- `CHECK(status IN ('pending', 'seeded', 'active', 'completed'))` — enforced in service layer

**Rationale:** Keeping configuration in its own table (rather than columns on `seasons`) means playoff settings are self-contained and can be added without touching the existing seasons table. The `status` column drives what operations are available (e.g., admin cannot change `playoff_size` once status is `seeded`).

---

### 1.2 `playoff_rounds`

One row per bracket round. Stores which PGA tournament the round is played against and when the draft window opens.

```
Table: playoff_rounds
```

| Column | Type | Constraints | Rationale |
|--------|------|-------------|-----------|
| `id` | `Integer` | PK, autoincrement | Internal join table PK |
| `playoff_config_id` | `UUID` | FK `playoff_configs.id`, NOT NULL | Belongs to one playoff |
| `round_number` | `Integer` | NOT NULL | 1 = first round, 2, 3, 4 ... |
| `tournament_id` | `UUID` | FK `tournaments.id`, nullable | Assigned by admin; null until assigned |
| `draft_opens_at` | `DateTime(tz=True)` | nullable | When the preference submission window opens; null until admin sets it |
| `draft_resolved_at` | `DateTime(tz=True)` | nullable | Set by the system when admin triggers "Resolve Draft"; null until resolved |
| `status` | `String(20)` | NOT NULL, default `'pending'` | `pending`, `drafting`, `locked`, `scoring`, `completed` |
| `created_at` | `DateTime(tz=True)` | `server_default=func.now()` | |

**Constraints:**
- `UNIQUE(playoff_config_id, round_number)`

**Round count derivation:** For a bracket of size N, total rounds = `log2(N)`. A 32-player bracket has 5 rounds: round 1 (8 pods of 4) + rounds 2–5 (1v1). Rounds are created by `seed_playoff()` when the admin triggers seeding.

**Rationale:** Each round is assigned its own PGA tournament independently. The draft deadline is always `tournament.start_date` — there is no computed `draft_closes_at` column. `draft_resolved_at` is set when the admin manually triggers resolution, providing a clear audit trail of when picks were finalized.

---

### 1.3 `playoff_pods`

One row per pod/matchup per round. In round 1, each pod has 4 players. In rounds 2+, each pod has 2 players (a 1v1 matchup). The term "pod" is used uniformly across all rounds for simplicity.

```
Table: playoff_pods
```

| Column | Type | Constraints | Rationale |
|--------|------|-------------|-----------|
| `id` | `Integer` | PK, autoincrement | |
| `playoff_round_id` | `Integer` | FK `playoff_rounds.id`, NOT NULL | Belongs to one round |
| `bracket_position` | `Integer` | NOT NULL | 1-indexed position in the bracket for this round (see section 5) |
| `winner_user_id` | `UUID` | FK `users.id`, nullable | Populated by `advance_bracket()` after scoring |
| `status` | `String(20)` | NOT NULL, default `'pending'` | `pending`, `drafting`, `scoring`, `completed` |
| `created_at` | `DateTime(tz=True)` | `server_default=func.now()` | |

**Constraints:**
- `UNIQUE(playoff_round_id, bracket_position)` — each bracket position appears once per round

**Rationale:** `bracket_position` is the integer that drives the entire bracket progression formula (see section 5). Keeping it on the pod row means no bracket-traversal queries are needed to find which pods play each other.

---

### 1.4 `playoff_pod_members`

Which players are in which pod, and their seeding/draft position within the pod. This table is the join between users and pods.

```
Table: playoff_pod_members
```

| Column | Type | Constraints | Rationale |
|--------|------|-------------|-----------|
| `id` | `Integer` | PK, autoincrement | |
| `pod_id` | `Integer` | FK `playoff_pods.id`, NOT NULL | Belongs to one pod |
| `user_id` | `UUID` | FK `users.id`, NOT NULL | The league member |
| `seed` | `Integer` | NOT NULL | Overall bracket seed (1 = best regular-season record) |
| `draft_position` | `Integer` | NOT NULL | 1-indexed position within the pod for draft order calculation (1 = top seed in pod, 2 = second seed, etc.) |
| `total_points` | `Float` | nullable | Points earned in this pod's tournament; populated by `score_round()` |
| `is_eliminated` | `Boolean` | NOT NULL, default `false` | Set true when `advance_bracket()` runs and player did not win |
| `created_at` | `DateTime(tz=True)` | `server_default=func.now()` | |

**Constraints:**
- `UNIQUE(pod_id, user_id)` — a user appears once per pod
- `UNIQUE(pod_id, draft_position)` — no two members share the same draft position in a pod
- `UNIQUE(pod_id, seed)` — no two members share the same overall seed within a pod

**Rationale:** Storing `draft_position` (intra-pod rank) separately from `seed` (league-wide rank) is critical. The draft order formulas (snake, linear, top_seed_priority) all operate on `draft_position` within the pod, not on the global seed. Storing `total_points` here (not only on `playoff_picks`) avoids a sum query every time the frontend renders a bracket card.

---

### 1.5 `playoff_picks`

One row per golfer assigned per member per pod. Rows are created at resolution time (when admin triggers "Resolve Draft"), not during the submission window. This is structurally analogous to the existing `picks` table but scoped to a playoff pod rather than a regular-season tournament.

```
Table: playoff_picks
```

| Column | Type | Constraints | Rationale |
|--------|------|-------------|-----------|
| `id` | `UUID` | PK, `default=uuid4` | Stable identifier; consistent with `picks` PK style |
| `pod_id` | `Integer` | FK `playoff_pods.id`, NOT NULL | Belongs to one pod |
| `pod_member_id` | `UUID` | FK `playoff_pod_members.id`, NOT NULL | Which pod member this pick belongs to |
| `golfer_id` | `UUID` | FK `golfers.id`, NOT NULL | Which golfer was assigned |
| `tournament_id` | `UUID` | FK `tournaments.id`, NOT NULL | Denormalized from the pod's round's tournament; allows direct joins to `tournament_entries` |
| `draft_slot` | `Integer` | NOT NULL | The sequential slot number this pick fills, as determined by the resolution algorithm (1 = first slot in draft order) |
| `points_earned` | `Float` | nullable | `earnings_usd * round.tournament.multiplier`; populated by `score_round()` |
| `created_at` | `DateTime(tz=True)` | `server_default=func.now()` | When the pick was created at resolution time |

**Constraints:**
- `UNIQUE(pod_id, golfer_id)` — the shared-pool rule: each golfer may only be assigned once per pod across all members
- `UNIQUE(pod_id, pod_member_id, draft_slot)` — one pick per slot per member per pod
- `CHECK` on `draft_slot > 0` — enforced in service layer

**Why `tournament_id` is denormalized here:** The `playoff_picks` table needs to join `tournament_entries` to get earnings data, exactly as `picks` does via its `entry` viewonly relationship. Storing `tournament_id` directly avoids a three-table join through `playoff_pods → playoff_rounds → tournaments` on every scoring query. This is consistent with how `picks.tournament_id` works.

**Why no `is_auto_picked`:** In the slow draft model there is no auto-pick. Picks are only created during admin-triggered resolution. A player who submitted no preference list simply receives no picks — there is no system-generated fallback.

**Why no `season_id`:** The playoff is already scoped to a season through `playoff_config → seasons`. Adding `season_id` here would be redundant. The playoff no-repeat rule (full reset) means there is no cross-reference to the regular-season `picks` table needed at write time.

---

### 1.6 `playoff_draft_preferences`

One row per golfer ranked per pod member. Players submit and update their ranked preference list anytime while the draft is open (after `draft_opens_at`, before `tournament.start_date`). These rows are the input to the resolution algorithm; they are not picks.

```
Table: playoff_draft_preferences
```

| Column | Type | Constraints | Rationale |
|--------|------|-------------|-----------|
| `id` | `UUID` | PK, `default=uuid4` | |
| `pod_id` | `uuid` | FK `playoff_pods.id`, NOT NULL | Denormalized for efficient queries and cascade delete |
| `pod_member_id` | `UUID` | FK `playoff_pod_members.id`, NOT NULL | Which player this preference belongs to |
| `golfer_id` | `UUID` | FK `golfers.id`, NOT NULL | The golfer being ranked |
| `rank` | `Integer` | NOT NULL | Player's preference rank (1 = most wanted) |
| `created_at` | `DateTime(tz=True)` | `server_default=func.now()` | |
| `updated_at` | `DateTime(tz=True)` | `server_default=func.now()`, `onupdate=func.now()` | |

**Constraints:**
- `UNIQUE(pod_member_id, golfer_id)` — a player can rank each golfer only once
- `UNIQUE(pod_member_id, rank)` — no duplicate rank positions per player

**Rationale:** Separating preferences from resolved picks keeps the draft state clean. Before resolution, only `playoff_draft_preferences` has data. After resolution, `playoff_picks` is populated. This makes it trivial to check "has this round been resolved?" (check if any picks exist). The full preference list is replaced atomically on each PUT submission — the service deletes all existing preferences for the member and re-inserts the new list in a single transaction, which avoids partial-update inconsistencies.

---

### Schema Diagram (Relationships)

```
seasons ──────────────── playoff_configs
                               │
                    ┌──────────┼──────────┐
                    │                     │
              playoff_rounds         (status, draft_style, etc.)
                    │
              playoff_pods
                  /    \
  playoff_pod_members   playoff_picks
       │      │               │
      users   │            golfers
              │                │
  playoff_draft_preferences    │
              │          tournament_entries
           golfers             │
                          tournaments
```

---

## 2. Seeding Algorithm

### 2.1 Selecting Playoff Members

When the admin triggers "Seed Playoff", `seed_playoff()` calls `calculate_standings()` (the existing scoring service in `app/services/scoring.py`) to get the current regular-season standings for the active season. The returned list is already sorted by `total_points` descending with ties broken by `display_name` ascending.

```python
standings = calculate_standings(db, league=league, season=season)
# standings[0] = 1st place, standings[1] = 2nd place, etc.
```

The top `playoff_config.playoff_size` members are taken in order. If fewer approved members exist than `playoff_size`, the behavior is described in section 8. Each member's 1-indexed position in this sorted list becomes their **seed**.

```python
seeded_members = standings[:playoff_config.playoff_size]
# seeded_members[0].seed = 1, seeded_members[1].seed = 2, ...
```

### 2.2 Pod Assignment Formula — Round 1

Round 1 uses pods of 4 players each (for a 32-player bracket: 8 pods). The classic snake seeding formula distributes the best players evenly across pods:

```
Number of pods in round 1 = playoff_size / 4  (or playoff_size / 2 for 4-player brackets)
```

For a 32-player bracket with 8 pods of 4:

| Pod (bracket_position) | Seeds |
|------------------------|-------|
| 1 | 1, 16, 17, 32 |
| 2 | 2, 15, 18, 31 |
| 3 | 3, 14, 19, 30 |
| 4 | 4, 13, 20, 29 |
| 5 | 5, 12, 21, 28 |
| 6 | 6, 11, 22, 27 |
| 7 | 7, 10, 23, 26 |
| 8 | 8, 9, 24, 25 |

**General formula:** With P pods and playoff_size N (N = 4P):

```python
def assign_pod(seed: int, num_pods: int, playoff_size: int) -> int:
    """
    Returns the 1-indexed pod (bracket_position) for a given seed.
    Works for any power-of-2 bracket with pods-of-4.
    """
    # Seeds are split into four "tiers" of num_pods each.
    # Tier 1: seeds 1..P         (top seeds)
    # Tier 2: seeds P+1..2P      (second tier, reversed)
    # Tier 3: seeds 2P+1..3P     (third tier, same direction as tier 1)
    # Tier 4: seeds 3P+1..4P     (bottom seeds, reversed)
    tier_size = num_pods  # = playoff_size // 4
    tier = (seed - 1) // tier_size  # 0-indexed tier: 0, 1, 2, 3
    position_in_tier = (seed - 1) % tier_size  # 0-indexed within tier

    if tier % 2 == 0:
        # Tiers 0 and 2: pod number = position_in_tier + 1
        return position_in_tier + 1
    else:
        # Tiers 1 and 3: pod number is reversed
        return tier_size - position_in_tier
```

**Validation:** seed=1 → pod 1, seed=16 → pod 1, seed=17 → pod 1, seed=32 → pod 1. seed=2 → pod 2, seed=15 → pod 2. Correct.

**For smaller brackets (playoff_size = 4, 8, 16):** The same formula applies. A 16-player bracket has 4 pods of 4. An 8-player bracket has 4 pods of 2 (1v1 from round 1). A 4-player bracket has 2 pods of 2.

> Note: For `playoff_size` values where `playoff_size / 4 < 2`, round 1 uses pods of 2 (1v1). The `round1_picks_per_player` config still applies to determine how many golfers each player picks.

### 2.3 `draft_position` Within a Pod

Within each pod, players are ordered by their overall seed. The player with the lowest seed number in the pod gets `draft_position = 1` (picks first in a linear draft).

```python
# Within a pod, sort the assigned members by their seed ascending.
pod_members_sorted = sorted(pod_members, key=lambda m: m.seed)
for i, member in enumerate(pod_members_sorted):
    member.draft_position = i + 1  # 1, 2, 3, 4
```

For a pod with seeds 1, 16, 17, 32:
- Seed 1 → draft_position 1
- Seed 16 → draft_position 2
- Seed 17 → draft_position 3
- Seed 32 → draft_position 4

---

## 3. Draft Slot Computation

### 3.1 Total Slots Per Pod

```python
# Round 1: 4 players × round1_picks_per_player
# Rounds 2+: 2 players × subsequent_picks_per_player
picks_per_player = config.round1_picks_per_player if round_number == 1 else config.subsequent_picks_per_player
players_in_pod = len(pod_members)  # 4 for round 1, 2 for rounds 2+
total_slots = picks_per_player * players_in_pod
```

### 3.2 Draft Order by Style

The draft order maps each slot number to a `(draft_position, pick_number)` tuple.

#### Snake Draft (default)

Round 1 (4 players, 2 picks each = 8 total slots):

```
Slot 1 → draft_position 1, pick 1   (forward)
Slot 2 → draft_position 2, pick 1
Slot 3 → draft_position 3, pick 1
Slot 4 → draft_position 4, pick 1   (end of round 1 of draft)
Slot 5 → draft_position 4, pick 2   (reverse: snake back)
Slot 6 → draft_position 3, pick 2
Slot 7 → draft_position 2, pick 2
Slot 8 → draft_position 1, pick 2
```

1v1 matchup (2 players, 4 picks each = 8 total slots):

```
Slot 1 → draft_position 1, pick 1
Slot 2 → draft_position 2, pick 1
Slot 3 → draft_position 2, pick 2   (snake back)
Slot 4 → draft_position 1, pick 2
Slot 5 → draft_position 1, pick 3
Slot 6 → draft_position 2, pick 3
...
```

```python
def generate_snake_order(num_players: int, picks_per_player: int) -> list[int]:
    """
    Returns a list of draft_position values (length = num_players * picks_per_player).
    Each element is the draft_position of the player who picks in that slot.
    Slot index (0-based) maps to draft_position.
    """
    order = []
    for round_idx in range(picks_per_player):
        positions = list(range(1, num_players + 1))
        if round_idx % 2 == 1:
            positions = list(reversed(positions))
        order.extend(positions)
    return order
```

#### Linear Draft

Always the same order every round:

```python
def generate_linear_order(num_players: int, picks_per_player: int) -> list[int]:
    order = []
    for _ in range(picks_per_player):
        order.extend(range(1, num_players + 1))
    return order
```

#### Top Seed Priority

Seed 1 picks all their golfers first, then seed 2, etc.:

```python
def generate_top_seed_priority_order(num_players: int, picks_per_player: int) -> list[int]:
    order = []
    for draft_position in range(1, num_players + 1):
        order.extend([draft_position] * picks_per_player)
    return order
```

### 3.3 Representing the Draft Order in the Database

`generate_draft_order()` returns a list of `draft_position` values indexed by slot (1-based). This list is not stored as a table column; it is computed on demand from the `draft_style` and the members in the pod. This keeps the schema simple and allows retroactive draft style changes while a pod is in `pending` status.

**How a slot maps to a user:**

```python
def draft_position_for_slot(slot: int, order: list[int]) -> int:
    """order is 0-indexed; slot is 1-indexed."""
    return order[slot - 1]

def user_for_slot(slot: int, pod_members: list[PlayoffPodMember], draft_style: str) -> PlayoffPodMember:
    order = generate_order(draft_style, len(pod_members), picks_per_player)
    target_draft_position = draft_position_for_slot(slot, order)
    return next(m for m in pod_members if m.draft_position == target_draft_position)
```

### 3.4 Current Active Slot

The current active slot in a pod is the minimum slot number that has no corresponding `playoff_picks` row:

```python
def get_active_slot(db: Session, pod_id: int, total_slots: int) -> int | None:
    """
    Returns the next unfilled slot number, or None if the draft is complete.
    """
    filled_slots = (
        db.query(PlayoffPick.draft_slot)
        .filter(PlayoffPick.pod_id == pod_id)
        .all()
    )
    filled_set = {row.draft_slot for row in filled_slots}
    for slot in range(1, total_slots + 1):
        if slot not in filled_set:
            return slot
    return None  # All slots filled
```

### 3.5 Draft Submission Window

Players can submit and update their preference list at any time after `draft_opens_at` and before `tournament.start_date`. There is no slot ordering during the submission window — all players submit independently and simultaneously. No player is waiting on another player to act.

Draft order (snake/linear/top_seed_priority) is only applied at resolution time when the admin triggers "Resolve Draft". The `draft_style` configuration determines which player's preference list is consulted first in each slot, but this calculation happens entirely within `resolve_draft()` — it has no real-time effect during the submission window.

The deadline is always `tournament.start_date`. There is no `draft_closes_at` computed field and no `slot_hours` concept. Once the tournament begins, the round status transitions to `locked` (set by `resolve_draft()`), and no further preference list updates are accepted.

The `get_active_slot()` function (section 3.4) is still used internally during resolution to track which slots have been filled, but it is no longer a real-time gate that blocks other players from submitting.

---

## 4. Draft Resolution

### 4.1 Trigger

Admin manually clicks "Resolve Draft" after the tournament has started. This calls:

```
POST /api/v1/leagues/{league_id}/playoff/rounds/{round_id}/resolve
```

There is no APScheduler job for draft resolution. Resolution is intentionally admin-triggered — it requires human confirmation that the tournament has started and the preference window is closed. No scheduler job is needed.

### 4.2 Resolution Algorithm

```python
def resolve_draft(db: Session, playoff_round: PlayoffRound) -> None:
    """
    Called by admin after tournament.start_date.
    Processes all submitted preference lists in draft order.
    Players with no submitted list get no picks (earn $0).
    """
    config = playoff_round.playoff_config

    for pod in playoff_round.pods:
        members_by_draft_position = sorted(pod.members, key=lambda m: m.draft_position)
        total_slots = len(pod.members) * (
            config.round1_picks_per_player if playoff_round.round_number == 1
            else config.subsequent_picks_per_player
        )
        slot_order = generate_draft_order(
            style=config.draft_style,
            n=len(pod.members),
            picks=total_slots // len(pod.members),
        )  # Returns list of draft_positions, one per slot

        claimed: set[uuid.UUID] = set()

        for slot_number, draft_position in enumerate(slot_order, start=1):
            member = next(m for m in pod.members if m.draft_position == draft_position)

            prefs = (
                db.query(PlayoffDraftPreference)
                .filter_by(pod_member_id=member.id)
                .order_by(PlayoffDraftPreference.rank)
                .all()
            )

            # Find best available pick from this player's preferences
            picked_golfer_id = next(
                (p.golfer_id for p in prefs if p.golfer_id not in claimed),
                None,
            )

            if picked_golfer_id is None:
                # No list submitted or all preferences claimed — no pick for this slot
                continue

            db.add(PlayoffPick(
                pod_id=pod.id,
                pod_member_id=member.id,
                golfer_id=picked_golfer_id,
                tournament_id=playoff_round.tournament_id,
                draft_slot=slot_number,
            ))
            claimed.add(picked_golfer_id)

        db.commit()

    playoff_round.draft_resolved_at = datetime.now(timezone.utc)
    playoff_round.status = "locked"
    db.commit()
```

### 4.3 Edge Case — Preference List Exhausted

If a player submitted a list but all their preferred golfers were claimed by earlier slots, they receive no pick for that slot (same outcome as no list submitted). Players should be encouraged to rank more golfers than their minimum pick count.

The UI should show a warning if a player has ranked fewer than 2× their pick count for the round (e.g., if each player picks 2 golfers, warn if they've ranked fewer than 4).

### 4.4 No Scheduler Job Needed

Unlike the previous auto-pick design, the slow draft requires no APScheduler job. Remove any reference to `playoff_auto_pick` from the scheduler. The scoring job (existing) handles result collection after the tournament completes; draft resolution is admin-triggered.

**Scheduler note:** No new APScheduler jobs are required for the playoff draft. The scoring job (existing) handles result collection; draft resolution is admin-triggered.

---

## 5. Bracket Generation

### 5.1 `bracket_position` Integer

The bracket is a standard single-elimination tree. Each pod in each round has a `bracket_position` integer (1-indexed per round). The total number of pods per round halves each round:

```
Round 1: playoff_size / 4 pods  (e.g., 32-player → 8 pods, positions 1..8)
Round 2: playoff_size / 8 pods  (e.g., 32-player → 4 pods, positions 1..4)
Round 3: playoff_size / 16 pods (e.g., 32-player → 2 pods, positions 1..2)
Round 4: 1 pod (the final),     position 1
```

### 5.2 Pod Winner Flow — The `bracket_position / 2` Formula

When `advance_bracket()` runs after round R, the winner of pod with `bracket_position` P in round R moves into the pod with `bracket_position = ceil(P / 2)` in round R+1.

```python
def advance_bracket(db: Session, playoff_round: PlayoffRound) -> None:
    """
    After scoring is complete for a round, determine winners and populate
    the next round's pods.
    """
    next_round = (
        db.query(PlayoffRound)
        .filter_by(
            playoff_config_id=playoff_round.playoff_config_id,
            round_number=playoff_round.round_number + 1,
        )
        .first()
    )

    for pod in playoff_round.pods:
        winner = _determine_pod_winner(db, pod)
        pod.winner_user_id = winner.user_id
        pod.status = "completed"

        # Mark all non-winners as eliminated
        for member in pod.members:
            if member.user_id != winner.user_id:
                member.is_eliminated = True

        if next_round:
            next_bracket_position = math.ceil(pod.bracket_position / 2)
            next_pod = (
                db.query(PlayoffPod)
                .filter_by(
                    playoff_round_id=next_round.id,
                    bracket_position=next_bracket_position,
                )
                .first()
            )
            if not next_pod:
                next_pod = PlayoffPod(
                    playoff_round_id=next_round.id,
                    bracket_position=next_bracket_position,
                )
                db.add(next_pod)
                db.flush()

            # Assign winner to next pod with their seed as draft_position context
            existing_seed = next(m for m in pod.members if m.user_id == winner.user_id).seed
            member_count_in_next = (
                db.query(PlayoffPodMember)
                .filter_by(pod_id=next_pod.id)
                .count()
            )
            next_member = PlayoffPodMember(
                pod_id=next_pod.id,
                user_id=winner.user_id,
                seed=existing_seed,
                draft_position=member_count_in_next + 1,  # temporary; re-sorted in open_draft
            )
            db.add(next_member)

    playoff_round.status = "completed"

    if next_round:
        # Re-sort draft_positions in next round pods by seed before draft opens
        _normalize_draft_positions(db, next_round)

    db.commit()
```

### 5.3 Scoring and Winner Determination

```python
def score_round(db: Session, playoff_round: PlayoffRound) -> None:
    """
    Populate points_earned for all playoff_picks in this round and
    update playoff_pod_members.total_points.
    Called by the scorer after the assigned tournament completes.
    """
    tournament = playoff_round.tournament
    multiplier = tournament.multiplier  # Use tournament's global multiplier

    for pod in playoff_round.pods:
        for member in pod.members:
            member_picks = (
                db.query(PlayoffPick)
                .filter_by(pod_id=pod.id, user_id=member.user_id)
                .all()
            )
            total = 0.0
            for pick in member_picks:
                entry = (
                    db.query(TournamentEntry)
                    .filter_by(tournament_id=tournament.id, golfer_id=pick.golfer_id)
                    .first()
                )
                earnings = entry.earnings_usd if entry and entry.earnings_usd else 0
                pick.points_earned = earnings * multiplier
                total += pick.points_earned
            member.total_points = total

    db.commit()
```

### 5.4 Winner Determination with Tie-breaking

```python
def _determine_pod_winner(db: Session, pod: PlayoffPod) -> PlayoffPodMember:
    """
    Winner = member with highest total_points.
    Tie-break: lower seed (higher seed number = worse seeding → loses).
    Higher seed (lower seed integer) always advances on a tie.
    """
    members_sorted = sorted(
        pod.members,
        key=lambda m: (-m.total_points, m.seed),  # total_points desc, seed asc (seed 1 wins ties)
    )
    return members_sorted[0]
```

**Tie-break rationale:** The design spec states "higher seed advances on tie." Seed 1 (best regular-season record) beats seed 2 in a tie. This is represented by sorting `seed` ascending so that seed 1 comes before seed 2.

---

## 6. Backend — FastAPI

### 6.1 New Model Files

#### `app/models/playoff.py`

```python
"""
Playoff models.

Five tables covering the full playoff lifecycle:
  playoff_configs       — settings per league per season
  playoff_rounds        — one row per bracket round, with assigned tournament
  playoff_pods          — one pod/matchup per round
  playoff_pod_members   — which players are in which pod
  playoff_picks         — golfer picks within a pod draft
"""

import math
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.golfer import Golfer
    from app.models.league import League
    from app.models.season import Season
    from app.models.tournament import Tournament
    from app.models.user import User


class PlayoffConfig(Base):
    __tablename__ = "playoff_configs"
    __table_args__ = (
        UniqueConstraint("league_id", "season_id", name="uq_playoff_config_league_season"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leagues.id"), nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    playoff_size: Mapped[int] = mapped_column(Integer, nullable=False, default=16, server_default="16")
    draft_style: Mapped[str] = mapped_column(String(30), nullable=False, default="snake", server_default="snake")
    round1_picks_per_player: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default="2")
    subsequent_picks_per_player: Mapped[int] = mapped_column(Integer, nullable=False, default=4, server_default="4")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    seeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    rounds: Mapped[list["PlayoffRound"]] = relationship(back_populates="playoff_config", cascade="all, delete-orphan")


class PlayoffRound(Base):
    __tablename__ = "playoff_rounds"
    __table_args__ = (
        UniqueConstraint("playoff_config_id", "round_number", name="uq_playoff_round_config_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    playoff_config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("playoff_configs.id"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tournament_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tournaments.id"), nullable=True)
    draft_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    draft_resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    playoff_config: Mapped["PlayoffConfig"] = relationship(back_populates="rounds")
    tournament: Mapped["Tournament | None"] = relationship()
    pods: Mapped[list["PlayoffPod"]] = relationship(back_populates="playoff_round", cascade="all, delete-orphan")


class PlayoffPod(Base):
    __tablename__ = "playoff_pods"
    __table_args__ = (
        UniqueConstraint("playoff_round_id", "bracket_position", name="uq_playoff_pod_round_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    playoff_round_id: Mapped[int] = mapped_column(ForeignKey("playoff_rounds.id"), nullable=False)
    bracket_position: Mapped[int] = mapped_column(Integer, nullable=False)
    winner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    playoff_round: Mapped["PlayoffRound"] = relationship(back_populates="pods")
    members: Mapped[list["PlayoffPodMember"]] = relationship(back_populates="pod", cascade="all, delete-orphan")
    picks: Mapped[list["PlayoffPick"]] = relationship(back_populates="pod", cascade="all, delete-orphan")
    draft_preferences: Mapped[list["PlayoffDraftPreference"]] = relationship(back_populates="pod", cascade="all, delete-orphan")
    winner: Mapped["User | None"] = relationship(foreign_keys=[winner_user_id])


class PlayoffPodMember(Base):
    __tablename__ = "playoff_pod_members"
    __table_args__ = (
        UniqueConstraint("pod_id", "user_id", name="uq_playoff_pod_member"),
        UniqueConstraint("pod_id", "draft_position", name="uq_playoff_pod_draft_position"),
        UniqueConstraint("pod_id", "seed", name="uq_playoff_pod_seed"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pod_id: Mapped[int] = mapped_column(ForeignKey("playoff_pods.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_position: Mapped[int] = mapped_column(Integer, nullable=False)
    total_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_eliminated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    pod: Mapped["PlayoffPod"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()
    draft_preferences: Mapped[list["PlayoffDraftPreference"]] = relationship(back_populates="pod_member", cascade="all, delete-orphan")


class PlayoffPick(Base):
    __tablename__ = "playoff_picks"
    __table_args__ = (
        UniqueConstraint("pod_id", "golfer_id", name="uq_playoff_pick_pod_golfer"),
        UniqueConstraint("pod_id", "pod_member_id", "draft_slot", name="uq_playoff_pick_pod_member_slot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pod_id: Mapped[int] = mapped_column(ForeignKey("playoff_pods.id"), nullable=False)
    pod_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("playoff_pod_members.id"), nullable=False)
    golfer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("golfers.id"), nullable=False)
    tournament_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tournaments.id"), nullable=False)
    draft_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    points_earned: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    pod: Mapped["PlayoffPod"] = relationship(back_populates="picks")
    pod_member: Mapped["PlayoffPodMember"] = relationship()
    golfer: Mapped["Golfer"] = relationship()
    tournament: Mapped["Tournament"] = relationship()


class PlayoffDraftPreference(Base):
    __tablename__ = "playoff_draft_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pod_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("playoff_pods.id"), nullable=False)
    pod_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("playoff_pod_members.id"), nullable=False)
    golfer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("golfers.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    pod: Mapped["PlayoffPod"] = relationship(back_populates="draft_preferences")
    pod_member: Mapped["PlayoffPodMember"] = relationship(back_populates="draft_preferences")
    golfer: Mapped["Golfer"] = relationship()

    __table_args__ = (
        UniqueConstraint("pod_member_id", "golfer_id", name="uq_pref_member_golfer"),
        UniqueConstraint("pod_member_id", "rank", name="uq_pref_member_rank"),
    )
```

---

### 6.2 Pydantic Schemas

#### `app/schemas/playoff.py`

```python
"""Playoff schemas — request/response types for all playoff endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Playoff Config
# ---------------------------------------------------------------------------

class PlayoffConfigCreate(BaseModel):
    is_enabled: bool = False
    playoff_size: int = 16
    draft_style: str = "snake"
    round1_picks_per_player: int = 2
    subsequent_picks_per_player: int = 4

    @field_validator("playoff_size")
    @classmethod
    def must_be_power_of_two(cls, v: int) -> int:
        if v not in (4, 8, 16, 32, 64):
            raise ValueError("playoff_size must be 4, 8, 16, 32, or 64")
        return v

    @field_validator("draft_style")
    @classmethod
    def must_be_valid_style(cls, v: str) -> str:
        if v not in ("snake", "linear", "top_seed_priority"):
            raise ValueError("draft_style must be snake, linear, or top_seed_priority")
        return v


class PlayoffConfigUpdate(BaseModel):
    is_enabled: bool | None = None
    playoff_size: int | None = None
    draft_style: str | None = None
    round1_picks_per_player: int | None = None
    subsequent_picks_per_player: int | None = None

    @field_validator("playoff_size")
    @classmethod
    def must_be_power_of_two(cls, v: int | None) -> int | None:
        if v is not None and v not in (4, 8, 16, 32, 64):
            raise ValueError("playoff_size must be 4, 8, 16, 32, or 64")
        return v


class PlayoffConfigOut(BaseModel):
    id: uuid.UUID
    league_id: uuid.UUID
    season_id: int
    is_enabled: bool
    playoff_size: int
    draft_style: str
    round1_picks_per_player: int
    subsequent_picks_per_player: int
    status: str
    seeded_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Playoff Round
# ---------------------------------------------------------------------------

class PlayoffRoundAssign(BaseModel):
    """Admin assigns a tournament and draft window to a round."""
    tournament_id: uuid.UUID
    draft_opens_at: datetime


class PlayoffRoundOut(BaseModel):
    id: int
    round_number: int
    tournament_id: uuid.UUID | None
    draft_opens_at: datetime | None
    draft_resolved_at: datetime | None
    status: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Playoff Pod
# ---------------------------------------------------------------------------

class PlayoffPodMemberOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    seed: int
    draft_position: int
    total_points: float | None
    is_eliminated: bool

    model_config = ConfigDict(from_attributes=True)


class PlayoffPickOut(BaseModel):
    id: uuid.UUID
    pod_member_id: uuid.UUID
    golfer_id: uuid.UUID
    golfer_name: str
    draft_slot: int
    points_earned: float | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlayoffPodOut(BaseModel):
    id: int
    bracket_position: int
    status: str
    winner_user_id: uuid.UUID | None
    members: list[PlayoffPodMemberOut]
    picks: list[PlayoffPickOut]
    active_draft_slot: int | None  # None when draft is complete or not started

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Bracket View
# ---------------------------------------------------------------------------

class BracketRoundOut(BaseModel):
    round_number: int
    status: str
    tournament_id: uuid.UUID | None
    tournament_name: str | None
    draft_opens_at: datetime | None
    draft_resolved_at: datetime | None
    pods: list[PlayoffPodOut]

    model_config = ConfigDict(from_attributes=True)


class BracketOut(BaseModel):
    playoff_config: PlayoffConfigOut
    rounds: list[BracketRoundOut]

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Draft Preferences
# ---------------------------------------------------------------------------

class PlayoffPreferenceSubmit(BaseModel):
    """Player submits their full ranked preference list (replaces any existing list)."""
    golfer_ids: list[uuid.UUID]  # Ordered list: index 0 = rank 1 (most preferred)


class PlayoffPreferenceOut(BaseModel):
    golfer_id: uuid.UUID
    golfer_name: str
    rank: int
    model_config = ConfigDict(from_attributes=True)


class PlayoffPodMemberDraftOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    seed: int
    draft_position: int
    has_submitted: bool
    preference_count: int

    model_config = ConfigDict(from_attributes=True)


class PlayoffDraftStatusOut(BaseModel):
    """Full draft state for a pod — what each player has submitted."""
    pod_id: uuid.UUID
    round_status: str  # drafting | locked
    deadline: datetime  # = tournament.start_date
    members: list[PlayoffPodMemberDraftOut]  # includes has_submitted flag + preference count
    resolved_picks: list[PlayoffPickOut]  # empty until resolved
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Admin Override
# ---------------------------------------------------------------------------

class PlayoffResultOverride(BaseModel):
    pod_id: int
    winner_user_id: uuid.UUID
```

---

### 6.3 Service Functions

#### `app/services/playoff.py`

```python
"""
Playoff service — all playoff business logic.

Key functions:
  seed_playoff(db, config)                  → Create rounds/pods/pod_members from standings
  generate_draft_order(style, n, picks)     → Returns list of draft_position values per slot
  open_round_draft(db, round_obj)           → Transition round from pending → drafting
  submit_preferences(db, pod_member, ids)   → Replace player's preference list (atomic)
  resolve_draft(db, playoff_round)          → Admin-triggered: process preferences → picks
  score_round(db, playoff_round)            → Populate points_earned from TournamentEntry
  advance_bracket(db, playoff_round)        → Set winners, create next-round pods
  override_result(db, pod, winner_id)       → Manager manual result override
"""
```

**`seed_playoff(db, config)`** steps:
1. Validate `config.status == "pending"`.
2. Validate `config.is_enabled == True`.
3. Call `calculate_standings(db, league, season)` to get ordered members.
4. If `len(standings) < config.playoff_size`, raise `HTTPException(422, "Not enough members...")`.
5. Take top `playoff_size` members; assign seeds 1..N.
6. Compute `num_rounds = int(math.log2(playoff_size))`.
7. Create `PlayoffRound` rows for rounds 1..num_rounds (status=`pending`, no tournament assigned yet).
8. For round 1: compute pod assignments using the pod formula, create `PlayoffPod` rows, create `PlayoffPodMember` rows with `seed` and `draft_position`.
9. Set `config.status = "seeded"`, `config.seeded_at = now`.
10. Commit.

**`submit_preferences(db, pod_member, golfer_ids)`** steps:
1. Validate the round status is `"drafting"` (not `"locked"` or later).
2. Validate the tournament has not yet started (`now < tournament.start_date`).
3. Validate all `golfer_id` values exist in the tournament field (`TournamentEntry` rows exist).
4. Delete all existing `PlayoffDraftPreference` rows for this `pod_member_id` in a single statement.
5. Insert new `PlayoffDraftPreference` rows in the order provided (index 0 → rank 1).
6. Commit atomically (delete + insert in one transaction).
7. Return the new preference list.

**`resolve_draft(db, playoff_round)`** steps: see Section 4.2 for the full algorithm.

**Concurrency:** Preference submission is per-player (each player only writes their own rows), so there are no cross-player race conditions during the submission window. The resolution algorithm runs in a single admin-triggered transaction and is not concurrent with itself.

---

### 6.4 Router: `app/routers/playoff.py`

All routes are prefixed with `/leagues/{league_id}/playoff`.

```
POST   /api/v1/leagues/{league_id}/playoff/config                             Create or upsert playoff config (manager)
GET    /api/v1/leagues/{league_id}/playoff/config                             Get playoff config (member)
PATCH  /api/v1/leagues/{league_id}/playoff/config                             Update config (manager; only in pending/seeded status)
POST   /api/v1/leagues/{league_id}/playoff/seed                               Trigger seeding (manager; status must be pending)
GET    /api/v1/leagues/{league_id}/playoff/bracket                            Full bracket view (member)
PATCH  /api/v1/leagues/{league_id}/playoff/rounds/{round_id}                  Assign tournament + draft window (manager)
POST   /api/v1/leagues/{league_id}/playoff/rounds/{round_id}/open             Open draft for round (manager)
POST   /api/v1/leagues/{league_id}/playoff/rounds/{round_id}/resolve          Resolve draft — admin only; runs resolve_draft()
GET    /api/v1/leagues/{league_id}/playoff/pods/{pod_id}/preferences          My current preference list (member)
PUT    /api/v1/leagues/{league_id}/playoff/pods/{pod_id}/preferences          Submit/replace full preference list (member; PlayoffPreferenceSubmit)
GET    /api/v1/leagues/{league_id}/playoff/pods/{pod_id}/draft                Full draft status — all members' submission status (member)
GET    /api/v1/leagues/{league_id}/playoff/pods/{pod_id}                      Get pod detail with picks (member)
POST   /api/v1/leagues/{league_id}/playoff/rounds/{round_id}/score            Trigger scoring for round (manager/platform_admin)
POST   /api/v1/leagues/{league_id}/playoff/rounds/{round_id}/advance          Advance bracket after scoring (manager)
PUT    /api/v1/leagues/{league_id}/playoff/pods/{pod_id}/result               Override result (manager; safety valve)
```

**Endpoint details:**

| Method | Path | Auth | Body | Response | Notes |
|--------|------|------|------|----------|-------|
| `POST` | `.../playoff/config` | manager | `PlayoffConfigCreate` | `PlayoffConfigOut` | Creates config if none exists; 409 if already exists |
| `GET` | `.../playoff/config` | member | — | `PlayoffConfigOut` | 404 if no config |
| `PATCH` | `.../playoff/config` | manager | `PlayoffConfigUpdate` | `PlayoffConfigOut` | 422 if status is `active` or `completed` |
| `POST` | `.../playoff/seed` | manager | — | `BracketOut` | Idempotent if already seeded (returns existing bracket) |
| `GET` | `.../playoff/bracket` | member | — | `BracketOut` | Full bracket with all rounds, pods, picks, scores |
| `PATCH` | `.../playoff/rounds/{round_id}` | manager | `PlayoffRoundAssign` | `PlayoffRoundOut` | 422 if round draft has opened |
| `POST` | `.../playoff/rounds/{round_id}/open` | manager | — | `PlayoffRoundOut` | Sets status=`drafting`; validates tournament assigned and field released |
| `POST` | `.../playoff/rounds/{round_id}/resolve` | manager | — | `PlayoffRoundOut` | Calls `resolve_draft()`; 422 if tournament has not started yet |
| `GET` | `.../playoff/pods/{pod_id}/preferences` | member | — | `list[PlayoffPreferenceOut]` | Returns calling user's ranked preference list; empty list if none submitted |
| `PUT` | `.../playoff/pods/{pod_id}/preferences` | member | `PlayoffPreferenceSubmit` | `list[PlayoffPreferenceOut]` | Replaces full list atomically; 422 if round is locked |
| `GET` | `.../playoff/pods/{pod_id}/draft` | member | — | `PlayoffDraftStatusOut` | Shows has_submitted + preference_count for all members; does not expose rankings until resolved |
| `GET` | `.../playoff/pods/{pod_id}` | member | — | `PlayoffPodOut` | Always returns full pick list (visible to all; populated after resolution) |
| `POST` | `.../playoff/rounds/{round_id}/score` | manager | — | `PlayoffRoundOut` | Calls `score_round()`; 422 if tournament not completed |
| `POST` | `.../playoff/rounds/{round_id}/advance` | manager | — | `BracketOut` | Calls `advance_bracket()`; 422 if not all pods scored |
| `PUT` | `.../playoff/pods/{pod_id}/result` | manager | `PlayoffResultOverride` | `PlayoffPodOut` | Bypasses all scoring; sets winner directly |

**Privacy note:** The `GET .../draft` endpoint reveals whether a teammate has submitted (`has_submitted: bool`) and how many golfers they ranked (`preference_count: int`), but not the actual rankings. Actual rankings are only visible after the admin resolves the draft (at which point `PlayoffPickOut` rows appear on the pod detail). This adds a small strategic element — players know whether teammates have submitted but cannot copy their list.

**Route ordering note** (following existing CLAUDE.md convention): Literal segments (`/config`, `/seed`, `/bracket`) must be registered before parameterized ones (`/{round_id}`, `/{pod_id}`). In FastAPI, this means `router.post("/config")` before `router.patch("/rounds/{round_id}")`.

---

### 6.5 Alembic Migration

New migration file: `app/alembic/versions/<hash>_add_playoff_tables.py`

```python
"""add playoff tables

Revision ID: a1b2c3d4e5f6
Revises: c9d3f2a8e5b1
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "c9d3f2a8e5b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE playoff_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            league_id UUID NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            season_id INTEGER NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            is_enabled BOOLEAN NOT NULL DEFAULT false,
            playoff_size INTEGER NOT NULL DEFAULT 16,
            draft_style VARCHAR(30) NOT NULL DEFAULT 'snake',
            round1_picks_per_player INTEGER NOT NULL DEFAULT 2,
            subsequent_picks_per_player INTEGER NOT NULL DEFAULT 4,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            seeded_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_playoff_config_league_season UNIQUE (league_id, season_id)
        );

        CREATE TABLE playoff_rounds (
            id SERIAL PRIMARY KEY,
            playoff_config_id UUID NOT NULL REFERENCES playoff_configs(id) ON DELETE CASCADE,
            round_number INTEGER NOT NULL,
            tournament_id UUID REFERENCES tournaments(id),
            draft_opens_at TIMESTAMPTZ,
            draft_resolved_at TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_playoff_round_config_number UNIQUE (playoff_config_id, round_number)
        );

        CREATE TABLE playoff_pods (
            id SERIAL PRIMARY KEY,
            playoff_round_id INTEGER NOT NULL REFERENCES playoff_rounds(id) ON DELETE CASCADE,
            bracket_position INTEGER NOT NULL,
            winner_user_id UUID REFERENCES users(id),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_playoff_pod_round_position UNIQUE (playoff_round_id, bracket_position)
        );

        CREATE TABLE playoff_pod_members (
            id SERIAL PRIMARY KEY,
            pod_id INTEGER NOT NULL REFERENCES playoff_pods(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id),
            seed INTEGER NOT NULL,
            draft_position INTEGER NOT NULL,
            total_points DOUBLE PRECISION,
            is_eliminated BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_playoff_pod_member UNIQUE (pod_id, user_id),
            CONSTRAINT uq_playoff_pod_draft_position UNIQUE (pod_id, draft_position),
            CONSTRAINT uq_playoff_pod_seed UNIQUE (pod_id, seed)
        );

        CREATE TABLE playoff_picks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pod_id INTEGER NOT NULL REFERENCES playoff_pods(id) ON DELETE CASCADE,
            pod_member_id INTEGER NOT NULL REFERENCES playoff_pod_members(id) ON DELETE CASCADE,
            golfer_id UUID NOT NULL REFERENCES golfers(id),
            tournament_id UUID NOT NULL REFERENCES tournaments(id),
            draft_slot INTEGER NOT NULL,
            points_earned DOUBLE PRECISION,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_playoff_pick_pod_golfer UNIQUE (pod_id, golfer_id),
            CONSTRAINT uq_playoff_pick_pod_member_slot UNIQUE (pod_id, pod_member_id, draft_slot)
        );

        CREATE TABLE playoff_draft_preferences (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pod_id INTEGER NOT NULL REFERENCES playoff_pods(id) ON DELETE CASCADE,
            pod_member_id INTEGER NOT NULL REFERENCES playoff_pod_members(id) ON DELETE CASCADE,
            golfer_id UUID NOT NULL REFERENCES golfers(id) ON DELETE CASCADE,
            rank INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_pref_member_golfer UNIQUE (pod_member_id, golfer_id),
            CONSTRAINT uq_pref_member_rank UNIQUE (pod_member_id, rank)
        );

        -- Indexes for common query patterns
        CREATE INDEX ix_playoff_rounds_config ON playoff_rounds(playoff_config_id);
        CREATE INDEX ix_playoff_pods_round ON playoff_pods(playoff_round_id);
        CREATE INDEX ix_playoff_pod_members_pod ON playoff_pod_members(pod_id);
        CREATE INDEX ix_playoff_pod_members_user ON playoff_pod_members(user_id);
        CREATE INDEX ix_playoff_picks_pod ON playoff_picks(pod_id);
        CREATE INDEX ix_playoff_picks_pod_member ON playoff_picks(pod_member_id);
        CREATE INDEX ix_playoff_draft_prefs_pod_member ON playoff_draft_preferences(pod_member_id);
        CREATE INDEX ix_playoff_draft_prefs_pod ON playoff_draft_preferences(pod_id);

        UPDATE alembic_version SET version_num = 'a1b2c3d4e5f6';
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS playoff_draft_preferences;
        DROP TABLE IF EXISTS playoff_picks;
        DROP TABLE IF EXISTS playoff_pod_members;
        DROP TABLE IF EXISTS playoff_pods;
        DROP TABLE IF EXISTS playoff_rounds;
        DROP TABLE IF EXISTS playoff_configs;

        UPDATE alembic_version SET version_num = 'c9d3f2a8e5b1';
    """)
```

**Apply manually (per CLAUDE.md convention):**

```bash
docker exec league_caddie-postgres-1 psql -U league_caddie -d league_caddie_dev -f /path/to/migration.sql
```

---

### 6.6 `app/models/__init__.py` Addition

Add to the imports block:

```python
from app.models.playoff import PlayoffConfig, PlayoffRound, PlayoffPod, PlayoffPodMember, PlayoffPick, PlayoffDraftPreference
```

Add to `__all__`:

```python
"PlayoffConfig", "PlayoffRound", "PlayoffPod", "PlayoffPodMember", "PlayoffPick", "PlayoffDraftPreference",
```

---

## 7. Frontend — React/TypeScript

### 7.1 New Routes in `App.tsx`

```tsx
// Inside the <Layout> guarded section:
<Route path="/leagues/:leagueId/playoff" element={<PlayoffBracket />} />
<Route path="/leagues/:leagueId/playoff/draft/:podId" element={<PlayoffDraft />} />
<Route path="/leagues/:leagueId/manage/playoff" element={<ManagePlayoff />} />
```

**Note:** `/leagues/:leagueId/manage/playoff` is nested under the manage section to keep playoff configuration alongside other manager tools. It is accessible from `ManageLeague.tsx` via a tab or link — it does not replace `ManageLeague`, it extends it.

---

### 7.2 New Pages

#### `src/pages/PlayoffBracket.tsx`

Full-league-visible bracket view. Shows all rounds as columns, pods within each round, member names, scores, and winner callouts. Non-playoff members can view but there are no interactive elements for them. Uses the `useBracket(leagueId)` hook.

Layout: horizontal scrollable bracket (desktop: all rounds side by side; mobile: swipeable tabs per round to avoid horizontal overflow).

#### `src/pages/PlayoffDraft.tsx`

Per-pod draft interface. Two views depending on round status:

**While status is `drafting` (submission window open):**
- Tournament info banner (which PGA tournament, deadline = `tournament.start_date`)
- Pod member submission summary: each member's name + "Submitted (N golfers)" or "Not yet submitted" badge — actual rankings not shown
- Tournament field list: all golfers in the round's tournament
- Player can drag/reorder golfers into their preference ranking (or use up/down arrow buttons)
- "Submit Rankings" button saves their list via `PUT .../preferences`; can be updated anytime before deadline
- Warning banner if the player has ranked fewer than 2× their pick count for the round

**After admin resolves (status is `locked` or later):**
- Final pick assignments shown with draft slot numbers
- Color-coded to show which slot each golfer was assigned via (e.g., "Slot 3")
- Players who received no picks shown with a note explaining why (no list submitted, or all preferences taken)

Route param: `podId`. Uses `usePodDraftStatus(leagueId, podId)`, `useMyPreferences(leagueId, podId)`, and `useSubmitPreferences(leagueId, podId)`.

#### `src/pages/ManagePlayoff.tsx`

Manager-only page. Sections:
1. **Enable/disable toggle** with size and style configuration
2. **Seed playoff** button (disabled until enough members; shows count)
3. **Round assignment table** — for each round: assign tournament, set draft open time
4. **Open draft** button per round (disabled until tournament assigned and field released)
5. **Resolve Draft** button per round — enabled only after `tournament.start_date`; shows a warning badge on the round card if status is still `drafting` after the deadline, prompting admin action
6. **Score round** and **Advance bracket** buttons (post-tournament)
7. **Manual result override** (emergency use; requires confirmation modal)

---

### 7.3 New Hooks: `src/hooks/usePlayoff.ts`

```typescript
/**
 * usePlayoff — React Query hooks for playoff endpoints.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { playoffApi } from "../api/endpoints";

// ── Config ──────────────────────────────────────────────────────────────────

export function usePlayoffConfig(leagueId: string) {
  return useQuery({
    queryKey: ["playoffConfig", leagueId],
    queryFn: () => playoffApi.getConfig(leagueId),
    enabled: !!leagueId,
  });
}

export function useCreatePlayoffConfig(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PlayoffConfigCreate) => playoffApi.createConfig(leagueId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffConfig", leagueId] }),
  });
}

export function useUpdatePlayoffConfig(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PlayoffConfigUpdate) => playoffApi.updateConfig(leagueId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffConfig", leagueId] }),
  });
}

// ── Bracket ──────────────────────────────────────────────────────────────────

export function useBracket(leagueId: string) {
  return useQuery({
    queryKey: ["playoffBracket", leagueId],
    queryFn: () => playoffApi.getBracket(leagueId),
    enabled: !!leagueId,
    staleTime: 30_000,          // 30 sec — draft activity updates the bracket
    refetchInterval: 60_000,    // auto-refresh while draft is active
  });
}

// ── Seeding ───────────────────────────────────────────────────────────────────

export function useSeedPlayoff(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => playoffApi.seed(leagueId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] });
      qc.invalidateQueries({ queryKey: ["playoffConfig", leagueId] });
    },
  });
}

// ── Round management ─────────────────────────────────────────────────────────

export function useAssignRoundTournament(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ roundId, data }: { roundId: number; data: PlayoffRoundAssign }) =>
      playoffApi.assignRound(leagueId, roundId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] }),
  });
}

export function useOpenRoundDraft(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (roundId: number) => playoffApi.openDraft(leagueId, roundId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] }),
  });
}

export function useScoreRound(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (roundId: number) => playoffApi.scoreRound(leagueId, roundId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] }),
  });
}

export function useAdvanceBracket(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (roundId: number) => playoffApi.advance(leagueId, roundId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] }),
  });
}

// ── Draft preferences ─────────────────────────────────────────────────────────

export function usePodDetail(leagueId: string, podId: number | null) {
  return useQuery({
    queryKey: ["playoffPod", leagueId, podId],
    queryFn: () => playoffApi.getPod(leagueId, podId!),
    enabled: !!leagueId && podId !== null,
  });
}

export function usePodDraftStatus(leagueId: string, podId: number | null) {
  return useQuery({
    queryKey: ["playoffDraftStatus", leagueId, podId],
    queryFn: () => playoffApi.getDraftStatus(leagueId, podId!),
    enabled: !!leagueId && podId !== null,
    staleTime: 30_000,
    refetchInterval: (data) => {
      // Poll every 30 sec while draft window is open
      return data?.round_status === "drafting" ? 30_000 : false;
    },
  });
}

export function useMyPreferences(leagueId: string, podId: number | null) {
  return useQuery({
    queryKey: ["playoffPreferences", leagueId, podId],
    queryFn: () => playoffApi.getPreferences(leagueId, podId!),
    enabled: !!leagueId && podId !== null,
  });
}

export function useSubmitPreferences(leagueId: string, podId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (golfer_ids: string[]) => playoffApi.submitPreferences(leagueId, podId, golfer_ids),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["playoffPreferences", leagueId, podId] });
      qc.invalidateQueries({ queryKey: ["playoffDraftStatus", leagueId, podId] });
    },
  });
}

export function useResolveRoundDraft(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (roundId: number) => playoffApi.resolveDraft(leagueId, roundId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] });
    },
  });
}

// ── Admin override ────────────────────────────────────────────────────────────

export function useOverridePlayoffResult(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { pod_id: number; winner_user_id: string }) =>
      playoffApi.overrideResult(leagueId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] }),
  });
}
```

**React Query cache keys (add to `frontend/CLAUDE.md`):**

| Key | Hook |
|-----|------|
| `["playoffConfig", leagueId]` | `usePlayoffConfig(leagueId)` |
| `["playoffBracket", leagueId]` | `useBracket(leagueId)` |
| `["playoffPod", leagueId, podId]` | `usePodDetail(leagueId, podId)` |
| `["playoffDraftStatus", leagueId, podId]` | `usePodDraftStatus(leagueId, podId)` |
| `["playoffPreferences", leagueId, podId]` | `useMyPreferences(leagueId, podId)` |

---

### 7.4 API Additions: `src/api/endpoints.ts`

New TypeScript types to add:

```typescript
// ---------------------------------------------------------------------------
// Playoff types (mirror app/schemas/playoff.py)
// ---------------------------------------------------------------------------

export interface PlayoffConfigOut {
  id: string;
  league_id: string;
  season_id: number;
  is_enabled: boolean;
  playoff_size: number;
  draft_style: "snake" | "linear" | "top_seed_priority";
  round1_picks_per_player: number;
  subsequent_picks_per_player: number;
  status: "pending" | "seeded" | "active" | "completed";
  seeded_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlayoffConfigCreate {
  is_enabled?: boolean;
  playoff_size?: number;
  draft_style?: "snake" | "linear" | "top_seed_priority";
  round1_picks_per_player?: number;
  subsequent_picks_per_player?: number;
}

export interface PlayoffConfigUpdate extends Partial<PlayoffConfigCreate> {}

export interface PlayoffPodMemberOut {
  user_id: string;
  display_name: string;
  seed: number;
  draft_position: number;
  total_points: number | null;
  is_eliminated: boolean;
}

export interface PlayoffPickOut {
  id: string;
  pod_member_id: string;
  golfer_id: string;
  golfer_name: string;
  draft_slot: number;
  points_earned: number | null;
  created_at: string;
}

export interface PlayoffPodOut {
  id: number;
  bracket_position: number;
  status: "pending" | "drafting" | "scoring" | "completed";
  winner_user_id: string | null;
  members: PlayoffPodMemberOut[];
  picks: PlayoffPickOut[];
  active_draft_slot: number | null;
}

export interface PlayoffRoundOut {
  id: number;
  round_number: number;
  tournament_id: string | null;
  tournament_name: string | null;
  draft_opens_at: string | null;
  draft_resolved_at: string | null;
  status: "pending" | "drafting" | "locked" | "scoring" | "completed";
  pods: PlayoffPodOut[];
}

export interface BracketOut {
  playoff_config: PlayoffConfigOut;
  rounds: PlayoffRoundOut[];
}

export interface PlayoffRoundAssign {
  tournament_id: string;
  draft_opens_at: string; // ISO datetime
}

export interface PlayoffPreference {
  golfer_id: string;
  golfer_name: string;
  rank: number;
}

export interface PlayoffPodMemberDraft {
  user_id: string;
  display_name: string;
  seed: number;
  draft_position: number;
  has_submitted: boolean;
  preference_count: number;
}

export interface PlayoffDraftStatus {
  pod_id: string;
  round_status: string;
  deadline: string;
  members: PlayoffPodMemberDraft[];
  resolved_picks: PlayoffPick[];
}
```

New API group to add to `endpoints.ts`:

```typescript
// ---------------------------------------------------------------------------
// Playoff
// ---------------------------------------------------------------------------

export const playoffApi = {
  getConfig: (leagueId: string) =>
    api.get<PlayoffConfigOut>(`/leagues/${leagueId}/playoff/config`).then((r) => r.data),

  createConfig: (leagueId: string, data: PlayoffConfigCreate) =>
    api.post<PlayoffConfigOut>(`/leagues/${leagueId}/playoff/config`, data).then((r) => r.data),

  updateConfig: (leagueId: string, data: PlayoffConfigUpdate) =>
    api.patch<PlayoffConfigOut>(`/leagues/${leagueId}/playoff/config`, data).then((r) => r.data),

  seed: (leagueId: string) =>
    api.post<BracketOut>(`/leagues/${leagueId}/playoff/seed`).then((r) => r.data),

  getBracket: (leagueId: string) =>
    api.get<BracketOut>(`/leagues/${leagueId}/playoff/bracket`).then((r) => r.data),

  assignRound: (leagueId: string, roundId: number, data: PlayoffRoundAssign) =>
    api.patch<PlayoffRoundOut>(`/leagues/${leagueId}/playoff/rounds/${roundId}`, data).then((r) => r.data),

  openDraft: (leagueId: string, roundId: number) =>
    api.post<PlayoffRoundOut>(`/leagues/${leagueId}/playoff/rounds/${roundId}/open`).then((r) => r.data),

  resolveDraft: (leagueId: string, roundId: number) =>
    api.post<PlayoffRoundOut>(`/leagues/${leagueId}/playoff/rounds/${roundId}/resolve`).then((r) => r.data),

  scoreRound: (leagueId: string, roundId: number) =>
    api.post<PlayoffRoundOut>(`/leagues/${leagueId}/playoff/rounds/${roundId}/score`).then((r) => r.data),

  advance: (leagueId: string, roundId: number) =>
    api.post<BracketOut>(`/leagues/${leagueId}/playoff/rounds/${roundId}/advance`).then((r) => r.data),

  getPod: (leagueId: string, podId: number) =>
    api.get<PlayoffPodOut>(`/leagues/${leagueId}/playoff/pods/${podId}`).then((r) => r.data),

  getDraftStatus: (leagueId: string, podId: number) =>
    api.get<PlayoffDraftStatus>(`/leagues/${leagueId}/playoff/pods/${podId}/draft`).then((r) => r.data),

  getPreferences: (leagueId: string, podId: number) =>
    api.get<PlayoffPreference[]>(`/leagues/${leagueId}/playoff/pods/${podId}/preferences`).then((r) => r.data),

  submitPreferences: (leagueId: string, podId: number, golfer_ids: string[]) =>
    api.put<PlayoffPreference[]>(`/leagues/${leagueId}/playoff/pods/${podId}/preferences`, { golfer_ids }).then((r) => r.data),

  overrideResult: (leagueId: string, data: { pod_id: number; winner_user_id: string }) =>
    api.put<PlayoffPodOut>(`/leagues/${leagueId}/playoff/pods/${data.pod_id}/result`, data).then((r) => r.data),
};
```

---

### 7.5 Component: `PlayoffBracketCard`

**File:** `src/components/PlayoffBracketCard.tsx`

A single pod/matchup card used in the bracket view. Displays:
- Round label (e.g., "Round 1 · Pod 1")
- Member rows: name, seed badge, total_points (or "—" if not scored yet)
- Winner highlighted (green accent, trophy icon)
- Eliminated members shown muted
- "Draft active" pill badge if status is `drafting`
- Click navigates to `/leagues/:leagueId/playoff/draft/:podId` if the current user is in this pod

```tsx
interface PlayoffBracketCardProps {
  pod: PlayoffPodOut;
  leagueId: string;
  currentUserId: string;
  roundNumber: number;
}
```

Styling follows the existing card convention: `bg-white border border-gray-200 rounded-2xl p-4 shadow-sm`. The winner row uses `bg-green-50 border-l-4 border-green-600`. Eliminated member rows use `opacity-40`.

---

## 8. Concerns and Edge Cases

### 8.1 Golfer Not in Tournament Field After Draft Opens

**Scenario:** A golfer is drafted by a player but then withdraws from the tournament before it starts.

**Handling:**
- `PlayoffPick` rows with a withdrawn golfer will receive `points_earned = 0` during `score_round()` since the `TournamentEntry.earnings_usd` will be null (withdrawal, no cut money).
- No pick is removed or replaced. This is consistent with the regular-season behavior for the `picks` table, where withdrawn golfers also score zero.
- Admin can use `override_result()` to manually set a pod winner if a withdrawal causes an unfair outcome — see section 8.7.
- **No auto-replacement** is provided. Adding a replacement mechanic (re-drafting) is significantly complex and conflicts with the "no repeat" playoff rule reset. The admin override is the safety valve.

### 8.2 Fewer Members Than `playoff_size` at Seeding Time

**Scenario:** League has 20 approved members but `playoff_size = 32`.

**Handling in `seed_playoff()`:**
```python
approved_count = len(standings)
if approved_count < config.playoff_size:
    raise HTTPException(
        status_code=422,
        detail=(
            f"Cannot seed a {config.playoff_size}-player playoff: "
            f"league only has {approved_count} approved members. "
            f"Reduce playoff_size to {_largest_valid_size(approved_count)} or add more members."
        ),
    )
```

Where `_largest_valid_size(n)` returns the largest power of 2 that is `<= n` (e.g., 20 members → suggest 16).

**Frontend:** The "Seed Playoff" button shows a warning count when `member_count < playoff_size`, prompting the manager to adjust the size before proceeding.

### 8.3 Admin Reassigning Tournament After Draft Opens

**Scenario:** Admin tries to change the tournament on a round that is already in `drafting` status.

**Handling:**

```python
@router.patch("/rounds/{round_id}")
def assign_round(...):
    if round_obj.status != "pending":
        raise HTTPException(
            status_code=422,
            detail=(
                f"Cannot change tournament assignment — round is in '{round_obj.status}' status. "
                "Close the draft and delete all picks before reassigning."
            ),
        )
```

The UI disables the tournament assignment field once a round transitions to `drafting`. If the admin truly needs to change it (e.g., PGA tournament cancellation), they must use a support path: the design does not implement a "rollback draft" feature at V1. This is an explicit limitation.

### 8.4 Concurrent Preference Submissions

**Scenario:** Two browser tabs for the same player both submit their preference list simultaneously.

**Handling:** Preference submission is per-player only — each PUT replaces only that player's own rows. There is no cross-player conflict. The delete+insert transaction is idempotent: whichever request lands last wins, which is the correct behavior (the most recent submission is what the player intended).

No `IntegrityError` is expected in normal operation. If one does occur (e.g., two requests for the same player with identical rank values arrive concurrently), the DB's `UNIQUE(pod_member_id, rank)` constraint will reject one, and the handler returns a 409 prompting the client to retry. In practice this is extremely unlikely because only one player controls their own list.

### 8.5 What Members See at Each Stage

| Stage | Member (in playoff) | Member (not in playoff) | Manager |
|-------|---------------------|------------------------|---------|
| `pending` | Config summary, member count | Config summary | Full config UI + seed button |
| `seeded` | Bracket structure, own pod | Bracket structure | Round assignment panel |
| `drafting` | Bracket, pod draft page (submit/update preference list); can see teammates' submission status (has_submitted + count, not rankings) | Bracket, pod page | All + resolve draft button (enabled after tournament.start_date) |
| `locked` | Bracket, pod page (resolved picks shown with slot assignments) | Bracket, pod page | Score round button |
| `scoring` | Bracket, pod page with live points | Bracket, pod page with live points | Score round + advance buttons |
| `completed` | Full bracket with all results | Full bracket with all results | Override button |

**Key visibility rule:** Player preference lists (rankings) are private until the admin resolves the draft. After resolution, the assigned picks (and their draft slot numbers) are visible to all league members. This is enforced by the pod detail endpoint returning picks only after resolution, and the draft status endpoint returning only `has_submitted` + `preference_count` before resolution.

### 8.6 Can Admin Manually Override Results?

**Yes.** The `PUT /leagues/{league_id}/playoff/pods/{pod_id}/result` endpoint accepts a `winner_user_id` from the manager. This sets:
- `pod.winner_user_id = winner_user_id`
- `pod.status = "completed"`
- `member.is_eliminated = True` for all non-winners in the pod

It does **not** re-run `advance_bracket()` automatically. The admin must call the advance endpoint separately after overriding. This two-step design prevents accidental partial-state corruptions. The frontend presents a confirmation modal ("Are you sure? This will override the scored result and cannot be undone automatically.") before calling the API.

### 8.7 Bracket State Consistency on Advance

`advance_bracket()` validates that all pods in the round have a non-null `winner_user_id` before creating next-round pods. This prevents a partial advance where only some pods have been scored.

```python
def advance_bracket(db: Session, playoff_round: PlayoffRound) -> None:
    unsettled = [pod for pod in playoff_round.pods if pod.winner_user_id is None]
    if unsettled:
        raise HTTPException(
            status_code=422,
            detail=f"{len(unsettled)} pod(s) have not been scored yet. Score all pods before advancing.",
        )
```

### 8.8 Regular Season Data Untouched

The playoff system is entirely additive. Zero changes are made to:
- `picks` table or `Pick` model
- `scoring.py` / `calculate_standings()`
- `picks.py` router
- Any existing schema or endpoint

The playoff uses its own tables with their own FK relationships. The only bridge to existing tables is:
- `PlayoffConfig.league_id` → `leagues.id`
- `PlayoffConfig.season_id` → `seasons.id`
- `PlayoffPick.tournament_id` → `tournaments.id`
- `PlayoffPick.golfer_id` → `golfers.id`

These are all read-only references. The existing `picks` table is never read or written by any playoff service function.

### 8.9 Player Submits No Preference List

**Scenario:** A player never submits a preference list before `tournament.start_date`, and the admin resolves the draft.

**Handling:** The resolution algorithm finds no `PlayoffDraftPreference` rows for that member, so no `PlayoffPick` is created for any of their slots. They earn $0 for the entire round. This is by design — there is no auto-pick fallback. This outcome cannot be corrected after resolution.

**Admin guidance:** The `GET .../draft` status endpoint shows which members have not yet submitted. The `ManagePlayoff.tsx` page should display a clear warning if any member has `has_submitted: false` when the admin goes to click "Resolve Draft."

### 8.10 Player's Entire Preference List Is Taken

**Scenario:** A player submitted a list of 3 golfers, but earlier draft slots took all 3.

**Handling:** Same outcome as no list submitted — no pick is created for that player's slot(s). Players should be encouraged to rank many more golfers than their minimum pick count. The draft interface shows a warning if they've ranked fewer than 2× their pick count.

### 8.11 Admin Forgets to Resolve Draft

**Scenario:** The tournament has started, the preference window has closed, but the admin has not yet triggered "Resolve Draft."

**Handling:** Picks cannot be scored until resolution. Round status remains `drafting`. The admin UI (`ManagePlayoff.tsx`) shows a warning badge on any round where status is still `drafting` after `tournament.start_date`. Scoring is blocked until `round.status = "locked"`.

---

## 9. Implementation Order

This critical path minimizes rework by building each layer on the previous one before wiring up higher-level logic.

### Step 1: Migration (backend foundation)
Create `alembic/versions/a1b2c3d4e5f6_add_playoff_tables.py` and apply to dev database. Verify with `\dt` in psql.

### Step 2: Models
Create `app/models/playoff.py` with all five model classes. Add imports to `app/models/__init__.py`.

### Step 3: Schemas
Create `app/schemas/playoff.py` with all Pydantic classes.

### Step 4: Service — seed and draft order
Implement `app/services/playoff.py`:
- `generate_draft_order()`
- `assign_pod()`
- `seed_playoff()`
- `get_active_slot()`
- `submit_preferences()` (atomic delete+insert of a player's ranked list)

Write tests in `tests/test_playoff_seeding.py` and `tests/test_playoff_draft.py`.

### Step 5: Service — draft resolution and scoring
Implement in `app/services/playoff.py`:
- `resolve_draft()` (processes all preference lists into picks using draft order)
- `score_round()`
- `advance_bracket()`

No APScheduler jobs are needed for this step. Write tests in `tests/test_playoff_resolution.py`.

### Step 6: Router
Create `app/routers/playoff.py` with all endpoints. Register in `app/main.py`.

### Step 7: API types (frontend)
Add `PlayoffConfigOut`, `BracketOut`, `PlayoffPodOut`, `PlayoffPickOut`, and related types to `src/api/endpoints.ts`. Add `playoffApi` group.

### Step 8: Hooks
Create `src/hooks/usePlayoff.ts` with all hooks.

### Step 9: Admin config page
Build `src/pages/ManagePlayoff.tsx`. Link from `ManageLeague.tsx`.

### Step 10: Bracket view page
Build `src/pages/PlayoffBracket.tsx` and `src/components/PlayoffBracketCard.tsx`. Add route to `App.tsx`.

### Step 11: Draft interface
Build `src/pages/PlayoffDraft.tsx`. Wire polling, golfer selector, submit mutation, and auto-refresh.

### Step 12: CLAUDE.md updates
- Add new endpoints table to `backend/CLAUDE.md`
- Add new models and migration to `backend/CLAUDE.md`
- Add new routes, hooks, cache keys to `frontend/CLAUDE.md`

---

## Appendix: Data Flow Summary

```
Admin enables playoff
        ↓
Admin seeds (seed_playoff)
  → reads calculate_standings()
  → writes playoff_configs (status: seeded)
  → writes playoff_rounds (status: pending)
  → writes playoff_pods   (status: pending)
  → writes playoff_pod_members
        ↓
Admin assigns tournament + draft window to round 1
  → PATCH /playoff/rounds/{id}
        ↓
Admin opens round 1 draft
  → POST /playoff/rounds/{id}/open
  → playoff_round.status = drafting
  → playoff_pods[*].status = drafting
        ↓
Players submit preference lists (any time before tournament.start_date)
  → PUT /playoff/pods/{id}/preferences
  → playoff_draft_preferences rows replaced atomically per player
  → All players submit simultaneously; no one waits on anyone else
        ↓
Tournament starts (deadline passes — no more preference updates accepted)
Admin triggers resolve_draft
  → POST /playoff/rounds/{id}/resolve
  → playoff_picks rows created from preference lists in draft order
  → playoff_round.status = locked
  → playoff_round.draft_resolved_at = now
        ↓
PGA tournament completes (scraper scores regular picks)
Admin triggers score_round
  → POST /playoff/rounds/{id}/score
  → playoff_picks.points_earned populated
  → playoff_pod_members.total_points summed
        ↓
Admin triggers advance_bracket
  → POST /playoff/rounds/{id}/advance
  → playoff_pods.winner_user_id set (tie-break: lower seed integer wins)
  → playoff_pod_members.is_eliminated set
  → round 2 playoff_pods and playoff_pod_members created
        ↓
Repeat for rounds 2, 3, 4...
        ↓
Final advance: playoff_config.status = completed
```
```

---

This document is the complete, self-contained design. It is ready to be saved to `/Users/blakechambers/Documents/FantasyGolf/PLAYOFF_DESIGN.md`. Since this is a read-only planning session, the document is presented here for you to copy and save manually, or for a follow-up implementation session to write directly.

---

### Critical Files for Implementation

- `/Users/blakechambers/Documents/FantasyGolf/backend/app/models/__init__.py` - Must be updated to import the five new playoff models so Alembic and all `from app.models import ...` statements work correctly across the app.

- `/Users/blakechambers/Documents/FantasyGolf/backend/app/services/scoring.py` - The `calculate_standings()` function here is the direct dependency for `seed_playoff()`; the seeding algorithm calls it unchanged, so understanding its return shape (list of dicts with `user_id`, `total_points`, `display_name`) is critical to getting seed assignment right.

- `/Users/blakechambers/Documents/FantasyGolf/backend/app/services/scheduler.py` - No new APScheduler jobs are needed for the playoff draft. The existing scoring job pattern is unchanged. Do not add a `playoff_auto_pick` job.

- `/Users/blakechambers/Documents/FantasyGolf/frontend/src/api/endpoints.ts` - All new TypeScript types and the `playoffApi` group live here; this file is the single source of truth for frontend types and must stay in sync with backend Pydantic schemas.

- `/Users/blakechambers/Documents/FantasyGolf/frontend/src/App.tsx` - The three new routes (`/playoff`, `/playoff/draft/:podId`, `/manage/playoff`) must be added here for the bracket view, draft interface, and manager config pages to be reachable.
