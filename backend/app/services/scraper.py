"""
PGA Tour data scraper using the ESPN unofficial sports API.

Why ESPN? It requires no API key, has been stable for years, and returns
JSON — no HTML scraping needed. The downside is it's unofficial and
undocumented, so the response shape can change without notice. All
parsing is written defensively (.get() everywhere, sensible defaults).

Architecture
------------
The functions here are split into two clear layers:

  1. Parsing (pure functions):
     parse_schedule_response() takes the scoreboard JSON and returns clean
     tournament dicts. No DB access, so it's trivial to unit test.

  2. Database (upsert functions):
     upsert_tournaments(), upsert_field(), score_picks() take parsed dicts
     and write to the DB using SQLAlchemy sessions.

High-level orchestration functions (sync_schedule, sync_tournament,
full_sync) combine both layers and are what the scheduler and admin
endpoint call.

ESPN API endpoints used
-----------------------
  Schedule:  https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard
             ?dates={YYYY}  → all events for that calendar year

  Core API:  https://sports.core.api.espn.com/v2/sports/golf/leagues/pga/...
             /events/{id}/competitions/{competition_id}/competitors?limit=200
               → all golfers/teams in the field with finish order
             /competitions/{competition_id}/competitors/{team_id}/roster
               → individual athlete IDs for a team competitor (team events only)
             /events/{id}/competitions/{competition_id}/competitors/{competitor_id}/statistics
               → earnings for completed tournaments; team events use 'officialAmount'
               stat (used directly as earnings); individual events use 'amount'
             /events/{id}/competitions/{competition_id}/competitors/{competitor_id}/linescores
               → per-round data for each golfer: tee time, strokes, score-to-par,
               leaderboard position, and playoff flag. One call returns ALL rounds
               played so far, replacing the older /status endpoint (which only
               returned the current round's tee time). Stored in tournament_entry_rounds.
             /athletes/{athlete_id}
               → golfer name and country

  NOTE: For most tournaments, competition_id == pga_tour_id (event ID).
  Team-format events (e.g. Zurich Classic) use a DIFFERENT competition_id
  exposed in the scoreboard as competitions[0].id. The scraper stores this
  in Tournament.competition_id so subsequent calls use the correct ID.

Per-round data notes
--------------------
  The /linescores endpoint returns a paginated list of round objects for a
  competitor. Each item includes:
    period         → round number (1–4 regular, 5+ playoff)
    teeTime        → ISO 8601 UTC string for that round's start time
    value          → total strokes for the round (float, cast to int)
    displayValue   → score-to-par as string ("-2", "E", "+1") — parsed to int
    currentPosition→ leaderboard rank after this round (integer, stored as string)
    isPlayoff      → true for playoff rounds

  Tee times are only released Tuesday or Wednesday before the Thursday start.
  When linescores are empty or teeTime is absent, we store None and leave
  picks unlocked.

  tournament_entries.tee_time always holds Round 1's tee time and is never
  overwritten by later rounds. Pick-locking logic reads this field: once Round 1
  has started (tee_time <= now), the pick is locked for the entire tournament.

Note: The older summary endpoint (site.api.espn.com/...pga/summary?event=)
is no longer functional — it returns ESPN error code 2500 for all event IDs.
The core API endpoints above are the reliable replacement.
"""

import concurrent.futures
import logging
import uuid
from collections import Counter
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import and_, select, update
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.models import (
    Golfer,
    LeagueTournament,
    Pick,
    Season,
    Tournament,
    TournamentEntry,
    TournamentEntryRound,
    TournamentStatus,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ESPN API constants
# ---------------------------------------------------------------------------
_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard"
_CORE_API_BASE = "https://sports.core.api.espn.com/v2/sports/golf/leagues/pga"
_REQUEST_TIMEOUT = 30.0  # seconds

# Sent with every ESPN request. Accept-Encoding: gzip is honoured by both ESPN
# endpoints (site API and core API) and httpx decompresses transparently,
# reducing payload size by ~80%.
_ESPN_HEADERS = {"Accept-Encoding": "gzip"}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _get_json(url: str, params: dict | None = None) -> dict:
    """
    Make a synchronous GET request and return parsed JSON.

    Uses a short-lived httpx.Client (connection pooling within one call).
    Raises httpx.HTTPStatusError on 4xx/5xx, httpx.RequestError on network failure.
    """
    with httpx.Client(timeout=_REQUEST_TIMEOUT, headers=_ESPN_HEADERS) as client:
        resp = client.get(url, params=params or {})
        resp.raise_for_status()
        return resp.json()


_FETCH_WORKERS = 5  # concurrent threads for athlete lookups


def _fetch_athlete_info(athlete_id: str) -> dict:
    """
    Fetch one golfer's display name and country from the ESPN core API.
    Returns a dict with pga_tour_id, name, country. Safe to call concurrently.
    """
    url = f"{_CORE_API_BASE}/athletes/{athlete_id}"
    try:
        with httpx.Client(timeout=10.0, headers=_ESPN_HEADERS) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                d = resp.json()
                return {
                    "pga_tour_id": str(athlete_id),
                    "name": d.get("displayName", "Unknown"),
                    "country": d.get("citizenship") or None,
                }
    except httpx.RequestError as exc:
        log.warning("Could not fetch athlete %s: %s", athlete_id, exc)
    return {"pga_tour_id": str(athlete_id), "name": "Unknown", "country": None}


def _parse_score_to_par(display_value: str | None) -> int | None:
    """
    Convert ESPN's score-to-par display string to an integer.

    ESPN "displayValue" examples:
      "-2"  → -2   (under par)
      "E"   →  0   (even par)
      "+1"  → +1   (over par)
      "1"   →  1   (over par, no leading "+")

    Returns None if the value is absent or unparseable.
    """
    if not display_value:
        return None
    v = display_value.strip()
    if v.upper() == "E":
        return 0
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _fetch_competitor_rounds(
    pga_tour_id: str,
    competition_id: str,
    athlete_id: str,
) -> tuple[str, list[dict]]:
    """
    Fetch all per-round data for one competitor from the ESPN /linescores endpoint.

    ESPN linescores endpoint
    ------------------------
    URL:    /events/{pga_tour_id}/competitions/{competition_id}/competitors/{athlete_id}/linescores
    Returns a paginated list of round objects (one per round played).

    Per-round fields used
    ---------------------
    period         → round_number  (int, 1–4 standard, 5+ playoff)
    teeTime        → tee_time      (ISO 8601 UTC string, nullable)
    value          → score         (total strokes as float, cast to int, nullable)
    displayValue   → score_to_par  (string like "-2"/"E"/"+1", parsed to int, nullable)
    currentPosition→ position      (int rank after this round, stored as string, nullable)
    isPlayoff      → is_playoff    (bool, default False)

    The linescores array nested inside each round item contains hole-by-hole
    data (18 items per round). We do NOT store that level of detail — only the
    round summary fields listed above.

    This single endpoint call replaces the old /status endpoint call, which only
    returned the CURRENT round's tee time. The /linescores endpoint returns ALL
    rounds, giving us historical round data for display.

    Side-effect on tournament_entries.tee_time:
    The caller (upsert_field) reads the latest round's tee_time from the returned
    dicts and writes it back to tournament_entries.tee_time for pick-locking.

    Returns:
      (athlete_id, rounds) where rounds is a list of dicts ready to upsert into
      tournament_entry_rounds. An empty list means no linescores data available.
    """
    url = (
        f"{_CORE_API_BASE}/events/{pga_tour_id}"
        f"/competitions/{competition_id}/competitors/{athlete_id}/linescores"
    )
    try:
        with httpx.Client(timeout=10.0, headers=_ESPN_HEADERS) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return athlete_id, []
            data = resp.json()
    except httpx.RequestError as exc:
        log.warning("Could not fetch linescores for athlete %s: %s", athlete_id, exc)
        return athlete_id, []

    rounds: list[dict] = []
    for item in data.get("items", []):
        # ESPN "period" is the round number. Skip items without a valid period.
        raw_period = item.get("period")
        if raw_period is None:
            continue
        try:
            round_number = int(raw_period)
        except (ValueError, TypeError):
            log.warning(
                "Unexpected period value for athlete %s: %r — skipping round",
                athlete_id,
                raw_period,
            )
            continue

        # ESPN "isPlayoff": true only for playoff rounds.
        is_playoff = bool(item.get("isPlayoff", False))

        # Skip ESPN internal/aggregate entries: period numbers > 10 that aren't
        # flagged as playoff rounds are placeholder rows with no meaningful data
        # (e.g. period=402 seen in WM Phoenix Open responses).
        if round_number > 10 and not is_playoff:
            log.debug(
                "Skipping non-playoff period %d for athlete %s (likely ESPN internal row)",
                round_number,
                athlete_id,
            )
            continue

        # Parse tee_time from ISO 8601 UTC string (e.g. "2026-03-05T13:45Z").
        tee_time_utc: datetime | None = None
        raw_tee_time = item.get("teeTime")
        if raw_tee_time:
            try:
                dt = datetime.fromisoformat(raw_tee_time.replace("Z", "+00:00"))
                tee_time_utc = dt.astimezone(UTC)
            except (ValueError, TypeError):
                log.warning(
                    "Could not parse teeTime %r for athlete %s round %d",
                    raw_tee_time,
                    athlete_id,
                    round_number,
                )

        # ESPN "value" is strokes as a float (e.g. 70.0); cast to int.
        # score=0 means the player did not finish the hole (e.g. conceded in a
        # playoff once the opponent already won). Treat as None — the round row
        # still records that the player participated, but no stroke count is shown.
        raw_value = item.get("value")
        score: int | None = None
        if raw_value is not None:
            try:
                parsed_score = int(float(raw_value))
                score = parsed_score if parsed_score > 0 else None
            except (ValueError, TypeError):
                pass

        # ESPN "displayValue": score-to-par string for this round ("-2", "E", "+1").
        score_to_par = _parse_score_to_par(item.get("displayValue"))

        # ESPN "currentPosition": leaderboard rank after this round (integer).
        # Stored as a string to accommodate future positional formats (e.g. "T5").
        raw_pos = item.get("currentPosition")
        position: str | None = str(raw_pos) if raw_pos is not None else None

        # Determine thru (holes completed) for this round.
        #
        # ESPN hole-level `value` is score-to-par (-1=birdie, 0=par, +1=bogey),
        # NOT raw strokes. This means value=0 is valid for a played par hole AND
        # for an unplayed placeholder, so we cannot use value==0 to detect
        # unplayed holes. Instead we use `displayValue`: played holes always have
        # a non-empty displayValue (e.g. "E" for par, "-1" for birdie), while
        # unplayed placeholder entries have displayValue=None or displayValue="".
        # "thru" = 0 means the round is scheduled but not started; 18 = complete.
        #
        # ESPN quirks with the `value` field (total strokes):
        #   - During live play: running stroke total (e.g. 20 after 6 holes)
        #   - Completed round: final stroke total (e.g. 72 after 18 holes)
        #   - So `value` alone cannot determine completion.
        #
        # ESPN quirks with the linescores array:
        #   - During live play: accurate hole-by-hole for the current round
        #   - Completed rounds: sometimes full (18), sometimes partial (7),
        #     sometimes empty (0). Unreliable for completed prior rounds.
        #
        # Strategy: use linescores count as primary. When the count seems wrong
        # (e.g. 7 holes but score=75 — impossible mid-round), detect the
        # inconsistency and override to 18. The heuristic: if strokes per hole
        # > 5.0, the score is too high for that few holes, so the round must
        # be complete with a partial linescores array from ESPN.
        linescores = item.get("linescores", [])
        played = [h for h in linescores if h.get("displayValue") not in (None, "")]
        if linescores:
            thru: int | None = len(played)
            # Detect ESPN partial-array bug: a completed round reported with
            # fewer holes than 18. A score >= 54 is impossible through fewer
            # than 18 holes — 54 is the theoretical minimum for a full round
            # (birdie every hole on a par-72). Mid-round running totals through
            # e.g. 7 holes max out around 40-50 even in worst-case scenarios.
            if score is not None and 0 < thru < 18 and score >= 54:
                thru = 18
        elif score is not None or score_to_par is not None:
            # No hole data but round has summary data (strokes or score-to-par)
            # → ESPN only omits linescores for completed rounds → mark complete.
            thru = 18
        else:
            # No hole data, no summary data → round is upcoming or not started.
            thru = None

        # Detect back-nine starts: the first hole in the linescores array (in
        # playing order) has period >= 10 for back-nine starters.  Prefer the
        # first *played* hole (most accurate); fall back to the first placeholder
        # entry (displayValue="") which ESPN includes in playing order before the
        # round begins, allowing back-nine detection before a player has teed off.
        started_on_back: bool | None = None
        ref_hole = played[0] if played else (linescores[0] if linescores else None)
        if ref_hole:
            try:
                started_on_back = int(ref_hole.get("period")) >= 10
            except (TypeError, ValueError):
                pass

        # Track whether any linescore entry is a back-nine hole (period >= 10).
        # When a back-nine starter crosses to the front nine, ESPN resets the
        # linescores array to show only the current 9 (front-nine) holes.
        # Knowing whether back-nine holes were present lets us correct thru later.
        _has_back_nine_linescore = False
        for _h in linescores:
            try:
                if int(_h.get("period")) >= 10:
                    _has_back_nine_linescore = True
                    break
            except (TypeError, ValueError):
                pass

        rounds.append(
            {
                "round_number": round_number,
                "tee_time": tee_time_utc,
                "score": score,
                "score_to_par": score_to_par,
                "position": position,
                "is_playoff": is_playoff,
                "thru": thru,
                "started_on_back": started_on_back,
                "_has_back_nine_linescore": _has_back_nine_linescore,
            }
        )

    return athlete_id, rounds


def _fetch_competitor_status(
    event_id: str,
    competition_id: str,
    competitor_id: str,
) -> tuple[str, str | None, int | None, int | None]:
    """
    Fetch a competitor's current status from the ESPN /status sub-endpoint.

    Returns (competitor_id, short_detail, current_round, start_hole) where:
      short_detail is one of:
        "F"   → finished normally (active, no special status)
        "WD"  → withdrew before or during the tournament
        "CUT" → missed the cut after round 2
        "MDF" → made the cut, did not finish (rare format-specific cut)
        "DQ"  → disqualified
        None  → fetch failed or status unrecognised
      current_round is the ESPN "period" (round number) from the status response.
      start_hole is the hole number the golfer tees off from for the current round
        (1–9 = front nine, 10–18 = back nine). None if not available.
    """
    url = (
        f"{_CORE_API_BASE}/events/{event_id}"
        f"/competitions/{competition_id}/competitors/{competitor_id}/status"
    )
    try:
        with httpx.Client(timeout=10.0, headers=_ESPN_HEADERS) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return competitor_id, None, None, None
            data = resp.json()
            short_detail = data.get("type", {}).get("shortDetail")
            try:
                current_round = int(data["period"]) if data.get("period") is not None else None
            except (TypeError, ValueError):
                current_round = None
            try:
                start_hole = int(data["startHole"]) if data.get("startHole") is not None else None
            except (TypeError, ValueError):
                start_hole = None
            return competitor_id, short_detail, current_round, start_hole
    except httpx.RequestError as exc:
        log.warning("Could not fetch status for competitor %s: %s", competitor_id, exc)
        return competitor_id, None, None, None


def _fetch_tournament_data(
    pga_tour_id: str,
    known_golfer_ids: set[str] | None = None,
    fetch_round_data: bool = False,
    scoreboard_athletes: dict[str, dict] | None = None,
    fetch_earnings: bool = False,
) -> tuple[list[dict], list[dict]]:
    """
    Fetch the golfer field and finish order for one individual (non-team) tournament.

    Uses the ESPN core API competitors endpoint (event-specific, unlike the
    web scoreboard which ignores the event parameter). One request gets all
    competitor IDs and finish positions; athlete names are fetched concurrently
    for golfers not already cached in known_golfer_ids.

    When fetch_round_data=True, also fetches per-round data for each golfer
    from the /competitors/{id}/linescores endpoint concurrently. This returns
    all rounds played (tee time, strokes, score-to-par, position per round).
    Enabled for all tournament states (SCHEDULED, IN_PROGRESS, COMPLETED).

    When fetch_earnings=True, also fetches prize earnings from the /statistics
    endpoint for each golfer concurrently. Used for completed tournaments so
    that force syncs repopulate earnings in the same pass as field data.

    Args:
      pga_tour_id:       ESPN event ID for the tournament (also the competition ID
                         for individual tournaments).
      known_golfer_ids:  pga_tour_ids already in the DB; skips re-fetching them.
      fetch_round_data:  If True, fetch per-round linescores for every competitor.
      fetch_earnings:    If True, fetch earnings from /statistics for every competitor.

    Returns:
      golfers  — list of dicts ready to upsert as Golfer rows
      results  — list of dicts ready to upsert as TournamentEntry rows; each dict
                 includes a "rounds" key with a list of per-round dicts (may be
                 empty if fetch_round_data=False or no linescores available).
    """
    # Step 1: one request for the full competitor list (IDs + finish order).
    competitors_url = (
        f"{_CORE_API_BASE}/events/{pga_tour_id}/competitions/{pga_tour_id}/competitors"
    )
    data = _get_json(competitors_url, params={"limit": 200})
    competitors = data.get("items", [])

    if not competitors:
        log.warning("No competitors found for tournament %s", pga_tour_id)
        return [], []

    all_athlete_ids = [str(c["id"]) for c in competitors if c.get("id")]
    known = known_golfer_ids or set()
    sb = scoreboard_athletes or {}

    # Step 2: resolve athlete info — use scoreboard data first, then API fallback.
    # Athletes already in the DB (known_golfer_ids) are skipped entirely.
    # Athletes found in scoreboard data are used without an API call.
    # Only athletes missing from both require an individual /athletes/{id} call.
    athlete_info: dict[str, dict] = {}
    ids_to_fetch: list[str] = []
    for aid in all_athlete_ids:
        if aid in known:
            continue  # Already in DB — upsert_field will skip updating.
        if aid in sb:
            athlete_info[aid] = {"pga_tour_id": aid, **sb[aid]}
        else:
            ids_to_fetch.append(aid)

    # Deduplicate before fetching — ESPN responses can list the same athlete
    # multiple times (e.g. in different competition groups).
    ids_to_fetch = list(dict.fromkeys(ids_to_fetch))

    if ids_to_fetch:
        log.info(
            "Tournament %s: %d athletes from scoreboard, %d need API fetch",
            pga_tour_id,
            len(athlete_info),
            len(ids_to_fetch),
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            futures = {pool.submit(_fetch_athlete_info, aid): aid for aid in ids_to_fetch}
            for future in concurrent.futures.as_completed(futures):
                aid = futures[future]
                try:
                    info = future.result()
                    athlete_info[info["pga_tour_id"]] = info
                except Exception as exc:
                    log.warning("Athlete fetch failed for %s: %s", aid, exc)

    # Step 3 (optional): fetch per-round data from the /linescores endpoint.
    rounds_by_athlete: dict[str, list[dict]] = {}
    if fetch_round_data and all_athlete_ids:
        with concurrent.futures.ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            futures_rd = {
                pool.submit(_fetch_competitor_rounds, pga_tour_id, pga_tour_id, aid): aid
                for aid in all_athlete_ids
            }
            for future in concurrent.futures.as_completed(futures_rd):
                try:
                    aid, rounds = future.result()
                    rounds_by_athlete[aid] = rounds
                except Exception as exc:
                    log.warning("Round data fetch failed: %s", exc)
        non_empty = sum(1 for rds in rounds_by_athlete.values() if rds)
        log.info(
            "Tournament %s: fetched round data for %d competitors (%d with rounds)",
            pga_tour_id,
            len(rounds_by_athlete),
            non_empty,
        )

    # Step 4 (optional): fetch per-competitor status (WD / CUT / DQ / MDF / F)
    # and current-round startHole (for back-nine detection before tee-off).
    # Only fetched when round data is fetched (i.e. full sync, not schedule-only).
    #
    # Optimization: instead of fetching /status for all ~135 competitors, we
    # only fetch it for those who need it:
    #   - Competitors with fewer rounds than the max (potential CUT/WD/DQ)
    #   - Competitors with started_on_back=None on any round (need startHole)
    # This typically reduces ~135 status calls to ~20-30.
    _NOTABLE_STATUSES = {"WD", "CUT", "MDF", "DQ"}
    status_by_athlete: dict[str, str | None] = {}
    # Maps athlete_id → (current_round_number, start_hole) from the status endpoint.
    start_hole_by_athlete: dict[str, tuple[int, int]] = {}
    if fetch_round_data and all_athlete_ids:
        # Determine which competitors need a status fetch.
        max_rounds = max(
            (len(rounds_by_athlete.get(aid, [])) for aid in all_athlete_ids),
            default=0,
        )
        needs_status: set[str] = set()
        for aid in all_athlete_ids:
            rounds = rounds_by_athlete.get(aid, [])
            # Fewer rounds than peers → possible CUT/WD/DQ
            if len(rounds) < max_rounds:
                needs_status.add(aid)
            # Any round missing started_on_back → need startHole from status
            elif any(rd.get("started_on_back") is None for rd in rounds):
                needs_status.add(aid)

        log.info(
            "Tournament %s: fetching status for %d/%d competitors (targeted)",
            pga_tour_id,
            len(needs_status),
            len(all_athlete_ids),
        )

        if needs_status:
            with concurrent.futures.ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
                futures_st = {
                    pool.submit(_fetch_competitor_status, pga_tour_id, pga_tour_id, aid): aid
                    for aid in needs_status
                }
                for future in concurrent.futures.as_completed(futures_st):
                    try:
                        aid, short_detail, current_round, start_hole = future.result()
                        # Only store notable non-active statuses; active/finished = None.
                        status_by_athlete[aid] = (
                            short_detail if short_detail in _NOTABLE_STATUSES else None
                        )
                        if current_round is not None and start_hole is not None:
                            start_hole_by_athlete[aid] = (current_round, start_hole)
                    except Exception as exc:
                        log.warning("Status fetch failed: %s", exc)

    # Step 5 (optional): fetch earnings concurrently for completed tournaments.
    # This populates earnings_usd in the same pass as field data, so force syncs
    # repopulate earnings without needing a separate score_picks pre-step.
    earnings_by_athlete: dict[str, int | None] = {}
    if fetch_earnings and all_athlete_ids:
        log.info(
            "Tournament %s: fetching earnings for %d competitors",
            pga_tour_id,
            len(all_athlete_ids),
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            futures_earn = {
                pool.submit(_fetch_golfer_earnings, pga_tour_id, aid): aid
                for aid in all_athlete_ids
            }
            for future in concurrent.futures.as_completed(futures_earn):
                aid = futures_earn[future]
                try:
                    earnings_by_athlete[aid] = future.result()
                except Exception as exc:
                    log.warning("Earnings fetch failed for %s: %s", aid, exc)
        fetched_count = sum(1 for v in earnings_by_athlete.values() if v is not None)
        log.info(
            "Tournament %s: fetched earnings for %d/%d competitors",
            pga_tour_id,
            fetched_count,
            len(all_athlete_ids),
        )

    log.info(
        "Tournament %s: %d competitors, %d new athlete fetches",
        pga_tour_id,
        len(competitors),
        len(ids_to_fetch),
    )

    golfers: list[dict] = []
    results: list[dict] = []
    for c in competitors:
        athlete_id = str(c.get("id", ""))
        if not athlete_id:
            continue

        # Use freshly fetched info, or pass name=None for known golfers
        # (upsert_field will skip updating them).
        info = athlete_info.get(athlete_id)
        golfers.append(
            {
                "pga_tour_id": athlete_id,
                "name": info["name"] if info else None,
                "country": info["country"] if info else None,
            }
        )

        rounds = rounds_by_athlete.get(athlete_id, []) if fetch_round_data else []

        # Apply started_on_back from the /status endpoint for the current round.
        # The /linescores endpoint only includes hole data once a round has begun,
        # so for not-yet-started rounds (linescores=[]) we fall back to startHole
        # from /status which ESPN provides as soon as pairings are released.
        if athlete_id in start_hole_by_athlete:
            status_round, start_hole = start_hole_by_athlete[athlete_id]
            for rd in rounds:
                if rd["round_number"] == status_round and rd.get("started_on_back") is None:
                    rd["started_on_back"] = start_hole >= 10

        # Fix thru for back-nine starters on the front nine.
        # When ESPN resets linescores to only the current 9 (front-nine) holes,
        # thru reads 1–9 instead of 10–17.  If started_on_back is True but no
        # back-nine hole (period >= 10) appeared in linescores, the golfer has
        # crossed to the front nine and thru must be offset by +9.
        for rd in rounds:
            _has_back_nine = rd.pop("_has_back_nine_linescore", True)
            if (
                rd.get("started_on_back")
                and rd.get("thru") is not None
                and 0 < rd["thru"] < 10
                and not _has_back_nine
            ):
                rd["thru"] += 9

        # Derive tee_time for tournament_entries.tee_time from Round 1 only.
        # Once Thursday starts, the pick is locked for the whole tournament —
        # we never overwrite this with a later round's tee time.
        current_tee_time: datetime | None = next(
            (
                rd["tee_time"]
                for rd in rounds
                if rd["round_number"] == 1 and rd["tee_time"] is not None
            ),
            None,
        )

        results.append(
            {
                "pga_tour_id": athlete_id,
                "finish_position": c.get("order"),
                "earnings_usd": earnings_by_athlete.get(athlete_id),
                "status": status_by_athlete.get(athlete_id),
                "tee_time": current_tee_time,
                "rounds": rounds,
                "team_competitor_id": None,
            }
        )

    return golfers, results


def _fetch_team_roster(competition_id: str, team_competitor_id: str) -> list[str]:
    """
    Fetch the individual athlete IDs for one team competitor.

    The Zurich Classic (and any future team-format events) lists teams as
    competitors rather than individual golfers. This sub-endpoint expands a
    team into its individual player IDs so we can create proper Golfer rows.

    Returns a list of pga_tour_id strings (individual athlete IDs).
    """
    url = f"{_CORE_API_BASE}/competitions/{competition_id}/competitors/{team_competitor_id}/roster"
    try:
        data = _get_json(url)
        return [str(e["playerId"]) for e in data.get("entries", []) if e.get("playerId")]
    except (httpx.HTTPError, httpx.RequestError) as exc:
        log.warning(
            "Could not fetch roster for team %s in competition %s: %s",
            team_competitor_id,
            competition_id,
            exc,
        )
        return []


def _fetch_team_field(
    pga_tour_id: str,
    competition_id: str,
    known_golfer_ids: set[str] | None = None,
    fetch_round_data: bool = False,
    scoreboard_athletes: dict[str, dict] | None = None,
    fetch_earnings: bool = False,
) -> tuple[list[dict], list[dict]]:
    """
    Fetch the individual golfer field for a team-format tournament.

    Team events (e.g. Zurich Classic) list team competitors instead of
    individual athletes. This function:
      1. Fetches all team competitors for the competition.
      2. Expands each team into its two individual athlete IDs via the roster
         sub-endpoint.
      3. Fetches athlete info (name, country) concurrently for new golfers.
      4. Optionally fetches per-round linescores from the /linescores sub-endpoint
         when fetch_round_data=True (all tournament states).
      5. Optionally fetches earnings from the /statistics sub-endpoint when
         fetch_earnings=True (completed tournaments). Uses team_competitor_id
         as the competitor key and is_team_event=True for officialAmount stat.
      6. Returns golfers + results lists with team_competitor_id set on each entry.

    Args:
      pga_tour_id:       ESPN event ID (used in earnings API URL).
      competition_id:    ESPN competition ID (may differ from pga_tour_id for
                         team events — stored in Tournament.competition_id).
      known_golfer_ids:  pga_tour_ids already in the DB; skips re-fetching them.
      fetch_round_data:  If True, fetch per-round linescores for every golfer.
      fetch_earnings:    If True, fetch earnings from /statistics for every team.

    Returns:
      golfers  — list of dicts (one per individual golfer, not per team)
      results  — list of dicts (one per individual golfer, with team_competitor_id
                 and a "rounds" key with a list of per-round dicts)
    """
    competitors_url = (
        f"{_CORE_API_BASE}/events/{pga_tour_id}/competitions/{competition_id}/competitors"
    )
    data = _get_json(competitors_url, params={"limit": 200})
    team_competitors = data.get("items", [])

    if not team_competitors:
        log.warning(
            "No team competitors found for tournament %s (competition %s)",
            pga_tour_id,
            competition_id,
        )
        return [], []

    known = known_golfer_ids or set()

    # Expand each team into individual athlete IDs, preserving team_competitor_id.
    # team_entries: list of (athlete_id, team_competitor_id, finish_order)
    team_entries: list[tuple[str, str, int | None]] = []
    for team in team_competitors:
        team_id = str(team.get("id", ""))
        if not team_id:
            continue
        finish_order = team.get("order")
        athlete_ids = _fetch_team_roster(competition_id, team_id)
        for athlete_id in athlete_ids:
            team_entries.append((athlete_id, team_id, finish_order))

    # Resolve athlete info — use scoreboard data first, then API fallback.
    sb = scoreboard_athletes or {}
    athlete_info: dict[str, dict] = {}
    ids_to_fetch: list[str] = []
    for aid, _, _ in team_entries:
        if aid in known:
            continue
        if aid in sb:
            athlete_info[aid] = {"pga_tour_id": aid, **sb[aid]}
        elif aid not in athlete_info:  # avoid duplicates from same golfer on different teams
            ids_to_fetch.append(aid)

    if ids_to_fetch:
        log.info(
            "Team tournament %s: %d athletes from scoreboard, %d need API fetch",
            pga_tour_id,
            len(athlete_info),
            len(ids_to_fetch),
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            futures = {pool.submit(_fetch_athlete_info, aid): aid for aid in ids_to_fetch}
            for future in concurrent.futures.as_completed(futures):
                try:
                    info = future.result()
                    athlete_info[info["pga_tour_id"]] = info
                except Exception as exc:
                    log.warning("Athlete fetch failed: %s", exc)

    # Fetch per-round linescores for all individual golfers when requested.
    # For team events the /linescores URL uses the individual athlete_id, not the team_id.
    # rounds_by_athlete maps athlete_id → list of per-round dicts.
    all_athlete_ids_team = [aid for aid, _, _ in team_entries]
    rounds_by_athlete: dict[str, list[dict]] = {}
    status_by_athlete_team: dict[str, str | None] = {}
    if fetch_round_data and team_entries:
        with concurrent.futures.ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            futures_rd = {
                pool.submit(_fetch_competitor_rounds, pga_tour_id, competition_id, aid): aid
                for aid in all_athlete_ids_team
            }
            for future in concurrent.futures.as_completed(futures_rd):
                try:
                    aid, rounds = future.result()
                    rounds_by_athlete[aid] = rounds
                except Exception as exc:
                    log.warning("Round data fetch failed: %s", exc)
        non_empty = sum(1 for rds in rounds_by_athlete.values() if rds)
        log.info(
            "Team tournament %s: fetched round data for %d golfers (%d with rounds)",
            pga_tour_id,
            len(rounds_by_athlete),
            non_empty,
        )

        _NOTABLE_STATUSES_TEAM = {"WD", "CUT", "MDF", "DQ"}
        start_hole_by_athlete_team: dict[str, tuple[int, int]] = {}

        # Targeted status fetch — only competitors with anomalies.
        max_rounds_team = max(
            (len(rounds_by_athlete.get(aid, [])) for aid in all_athlete_ids_team),
            default=0,
        )
        needs_status_team: set[str] = set()
        for aid in all_athlete_ids_team:
            rounds = rounds_by_athlete.get(aid, [])
            if len(rounds) < max_rounds_team:
                needs_status_team.add(aid)
            elif any(rd.get("started_on_back") is None for rd in rounds):
                needs_status_team.add(aid)

        log.info(
            "Team tournament %s: fetching status for %d/%d golfers (targeted)",
            pga_tour_id,
            len(needs_status_team),
            len(all_athlete_ids_team),
        )

        if needs_status_team:
            with concurrent.futures.ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
                futures_st = {
                    pool.submit(_fetch_competitor_status, pga_tour_id, competition_id, aid): aid
                    for aid in needs_status_team
                }
                for future in concurrent.futures.as_completed(futures_st):
                    try:
                        aid, short_detail, current_round, start_hole = future.result()
                        status_by_athlete_team[aid] = (
                            short_detail if short_detail in _NOTABLE_STATUSES_TEAM else None
                        )
                        if current_round is not None and start_hole is not None:
                            start_hole_by_athlete_team[aid] = (current_round, start_hole)
                    except Exception as exc:
                        log.warning("Status fetch failed: %s", exc)

    # Fetch earnings concurrently for completed team tournaments.
    # Team events use the team_competitor_id (not athlete_id) with is_team_event=True
    # to get the officialAmount stat. Each team member shares the same earnings.
    earnings_by_team: dict[str, int | None] = {}
    if fetch_earnings and team_entries:
        # Deduplicate team IDs — each team has 2 athletes sharing one earnings value.
        unique_team_ids = list(dict.fromkeys(tid for _, tid, _ in team_entries))
        log.info(
            "Team tournament %s: fetching earnings for %d teams",
            pga_tour_id,
            len(unique_team_ids),
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            futures_earn = {
                pool.submit(
                    _fetch_golfer_earnings,
                    pga_tour_id,
                    tid,
                    competition_id=competition_id,
                    is_team_event=True,
                ): tid
                for tid in unique_team_ids
            }
            for future in concurrent.futures.as_completed(futures_earn):
                tid = futures_earn[future]
                try:
                    earnings_by_team[tid] = future.result()
                except Exception as exc:
                    log.warning("Team earnings fetch failed for %s: %s", tid, exc)
        fetched_count = sum(1 for v in earnings_by_team.values() if v is not None)
        log.info(
            "Team tournament %s: fetched earnings for %d/%d teams",
            pga_tour_id,
            fetched_count,
            len(unique_team_ids),
        )

    log.info(
        "Team tournament %s: %d teams → %d individual golfers, %d new athlete fetches",
        pga_tour_id,
        len(team_competitors),
        len(team_entries),
        len(ids_to_fetch),
    )

    golfers: list[dict] = []
    results: list[dict] = []
    for athlete_id, team_id, finish_order in team_entries:
        info = athlete_info.get(athlete_id)
        golfers.append(
            {
                "pga_tour_id": athlete_id,
                "name": info["name"] if info else None,
                "country": info["country"] if info else None,
            }
        )

        rounds = rounds_by_athlete.get(athlete_id, []) if fetch_round_data else []

        # Apply started_on_back from the /status endpoint (same logic as individual).
        if athlete_id in start_hole_by_athlete_team:
            status_round, start_hole = start_hole_by_athlete_team[athlete_id]
            for rd in rounds:
                if rd["round_number"] == status_round and rd.get("started_on_back") is None:
                    rd["started_on_back"] = start_hole >= 10

        # Fix thru for back-nine starters on the front nine (same logic as individual).
        for rd in rounds:
            _has_back_nine = rd.pop("_has_back_nine_linescore", True)
            if (
                rd.get("started_on_back")
                and rd.get("thru") is not None
                and 0 < rd["thru"] < 10
                and not _has_back_nine
            ):
                rd["thru"] += 9

        # Derive tee_time for tournament_entries.tee_time from Round 1 only.
        current_tee_time: datetime | None = next(
            (
                rd["tee_time"]
                for rd in rounds
                if rd["round_number"] == 1 and rd["tee_time"] is not None
            ),
            None,
        )

        results.append(
            {
                "pga_tour_id": athlete_id,
                "finish_position": finish_order,
                "earnings_usd": earnings_by_team.get(team_id),
                "status": status_by_athlete_team.get(athlete_id),
                "tee_time": current_tee_time,
                "rounds": rounds,
                "team_competitor_id": team_id,
            }
        )

    return golfers, results


def _fetch_golfer_earnings(
    pga_tour_id: str,
    competitor_id: str,
    competition_id: str | None = None,
    is_team_event: bool = False,
) -> int | None:
    """
    Fetch prize earnings for one pick from the ESPN core API.

    Called by score_picks() only for golfers that have actual picks — keeps
    total API requests low (one per league member who submitted a pick).

    For individual tournaments:
      - competitor_id is the golfer's pga_tour_id
      - stat name is 'amount'
      - competition_id defaults to pga_tour_id

    For team tournaments (e.g. Zurich Classic):
      - competitor_id is the team's ESPN competitor ID (team_competitor_id)
      - stat name is 'officialAmount' (ESPN sets 'amount' to 0 for team events)
      - earnings are the team's officialAmount, used directly (no division needed)
      - competition_id is the event's actual competition ID (stored in Tournament)

    Returns earnings in USD as an integer, or None if not found.
    """
    effective_competition_id = competition_id or pga_tour_id
    stats_url = (
        f"{_CORE_API_BASE}/events/{pga_tour_id}"
        f"/competitions/{effective_competition_id}/competitors/{competitor_id}/statistics"
    )
    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT, headers=_ESPN_HEADERS) as client:
            resp = client.get(stats_url)
            if resp.status_code != 200:
                return None
            stats_data = resp.json()
    except httpx.RequestError as exc:
        log.warning("Could not fetch earnings for competitor %s: %s", competitor_id, exc)
        return None

    stat_name = "officialAmount" if is_team_event else "amount"

    for cat in stats_data.get("splits", {}).get("categories", []):
        for stat in cat.get("stats", []):
            if stat.get("name") == stat_name:
                raw = stat.get("value")
                if raw is not None:
                    try:
                        val = int(float(raw))
                        # Only return positive earnings. ESPN returns amount=0.0
                        # for both "genuinely $0" (amateurs, CUT) AND "not yet
                        # published" (mid-field pros after completion). We can't
                        # distinguish the two, so we return None for both and let
                        # the earnings gate use a threshold to determine readiness.
                        if val > 0:
                            return val
                    except (ValueError, TypeError):
                        pass
    return None


# ---------------------------------------------------------------------------
# Parsing helpers  (pure — no DB access, easy to unit test)
# ---------------------------------------------------------------------------


def _map_espn_status(espn_status_name: str) -> str:
    """Convert ESPN status string to our TournamentStatus enum value."""
    return {
        "STATUS_SCHEDULED": TournamentStatus.SCHEDULED.value,
        "STATUS_IN_PROGRESS": TournamentStatus.IN_PROGRESS.value,
        # Suspended = weather delay or darkness; play will resume. Treat as
        # in_progress so live syncs continue and pick up updated data.
        "STATUS_SUSPENDED": TournamentStatus.IN_PROGRESS.value,
        "STATUS_FINAL": TournamentStatus.COMPLETED.value,
        # Treat cancelled events as completed so they don't surface as "upcoming"
        # in the pick form and don't get included in the next-scheduled sync.
        "STATUS_CANCELED": TournamentStatus.COMPLETED.value,
    }.get(espn_status_name, TournamentStatus.SCHEDULED.value)


def _check_schema_health(
    tournament_name: str,
    tournament_status: str,
    golfers: list[dict],
    results: list[dict],
) -> None:
    """
    Detect possible ESPN schema changes by checking for fields that are
    universally missing across a full sync.

    A few None values are normal (e.g. tee times not yet assigned for a
    scheduled tournament). But if ALL entries lack a field that should be
    populated for the tournament's status, ESPN likely renamed it. Log a
    warning so the issue is visible in CloudWatch.
    """
    total = len(results)
    if total < 10:
        return  # Too few entries to draw conclusions

    # Count how many entries have each key field populated.
    has_tee_time = sum(1 for r in results if r.get("tee_time") is not None)
    has_earnings = sum(1 for r in results if r.get("earnings_usd") is not None)
    has_position = sum(1 for r in results if r.get("finish_position") is not None)
    has_rounds = sum(1 for r in results if r.get("rounds"))
    has_name = sum(1 for g in golfers if g.get("name") is not None)

    # tee_time: expected for scheduled/in_progress tournaments (field release day+)
    if tournament_status in ("scheduled", "in_progress") and has_tee_time == 0:
        log.warning(
            "ESPN SCHEMA CHECK — '%s': 0/%d entries have tee_time data "
            "(status=%s). Possible field rename in ESPN API.",
            tournament_name,
            total,
            tournament_status,
        )

    # earnings: expected for completed tournaments
    if tournament_status == "completed" and has_earnings == 0:
        log.warning(
            "ESPN SCHEMA CHECK — '%s': 0/%d entries have earnings_usd "
            "(status=completed). Possible field rename in ESPN API.",
            tournament_name,
            total,
        )

    # finish_position: expected for in_progress and completed tournaments
    if tournament_status in ("in_progress", "completed") and has_position == 0:
        log.warning(
            "ESPN SCHEMA CHECK — '%s': 0/%d entries have finish_position "
            "(status=%s). Possible field rename in ESPN API.",
            tournament_name,
            total,
            tournament_status,
        )

    # rounds: expected for all statuses once fields are fetched
    if has_rounds == 0:
        log.warning(
            "ESPN SCHEMA CHECK — '%s': 0/%d entries have round data. "
            "Possible field rename in ESPN API /linescores endpoint.",
            tournament_name,
            total,
        )

    # golfer names: always expected
    if has_name == 0:
        log.warning(
            "ESPN SCHEMA CHECK — '%s': 0/%d golfers have name data. "
            "Possible field rename in ESPN API athlete endpoint.",
            tournament_name,
            len(golfers),
        )


def _parse_date(date_str: str | None) -> date | None:
    """Parse an ESPN ISO timestamp ('2025-04-10T10:00Z') to a Python date."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def parse_schedule_response(data: dict) -> tuple[list[dict], dict[str, dict]]:
    """
    Extract tournament records from an ESPN scoreboard API response.

    ESPN wraps events under either data['events'] or data['leagues'][i]['events'].
    We check both.

    Returns:
      tournaments — list of dicts ready to be upserted as Tournament rows
      scoreboard_athletes — dict mapping athlete pga_tour_id → {name, country}
        extracted from inline competitor data. This allows sync_tournament to
        skip individual /athletes/{id} API calls for known golfers.

    For each event we also extract:
      competition_id  — the ESPN competition ID, which may differ from the event ID
                        for team-format events (e.g. Zurich Classic uses "11450")
      is_team_event   — True if the scoreboard lists type="team" competitors

    These two fields allow sync_tournament to use the correct API endpoints
    without re-fetching the scoreboard on every field sync.
    """
    # Collect raw events from whichever nesting ESPN uses.
    raw_events: list[dict] = data.get("events", [])
    if not raw_events:
        for league in data.get("leagues", []):
            raw_events.extend(league.get("events", []))

    results = []
    # Extract athlete names and countries from inline competitor data across
    # all events. This avoids per-athlete API calls in sync_tournament.
    scoreboard_athletes: dict[str, dict] = {}

    for event in raw_events:
        event_id = event.get("id")
        if not event_id:
            continue

        # The competition object holds precise start/end dates.
        competitions = event.get("competitions") or [{}]
        comp = competitions[0]

        status_name = event.get("status", {}).get("type", {}).get("name", "STATUS_SCHEDULED")

        start_date = _parse_date(comp.get("startDate") or event.get("date"))
        end_date = _parse_date(comp.get("endDate"))
        if not start_date:
            continue
        if not end_date:
            end_date = start_date + timedelta(days=3)

        # Extract competition_id — for team events this differs from event_id.
        competition_id = str(comp.get("id") or event_id)

        # Detect team format: ESPN marks team-event competitors with type="team".
        competitors_sample = comp.get("competitors") or []
        is_team_event = bool(competitors_sample and competitors_sample[0].get("type") == "team")

        # Harvest athlete info from inline competitor data.
        for c in competitors_sample:
            aid = str(c.get("id", ""))
            if not aid:
                continue
            athlete = c.get("athlete") or {}
            name = athlete.get("fullName") or athlete.get("displayName")
            country = (athlete.get("flag") or {}).get("alt")
            if name and aid not in scoreboard_athletes:
                scoreboard_athletes[aid] = {"name": name, "country": country}

        results.append(
            {
                "pga_tour_id": str(event_id),
                "competition_id": competition_id,
                "is_team_event": is_team_event,
                "name": event.get("name") or event.get("shortName", "Unknown Tournament"),
                "start_date": start_date,
                "end_date": end_date,
                "status": _map_espn_status(status_name),
            }
        )

    # The Tour Championship (final FedEx Cup Playoffs event) is the last valid
    # fantasy-season event. Drop any tournaments that start after it ends.
    tour_champ = next(
        (r for r in results if "tour championship" in r["name"].lower()),
        None,
    )
    if tour_champ:
        cutoff = tour_champ["end_date"]
        results = [r for r in results if r["start_date"] <= cutoff]

    log.info(
        "Scoreboard: extracted %d athlete profiles from inline competitor data",
        len(scoreboard_athletes),
    )
    return results, scoreboard_athletes


# ---------------------------------------------------------------------------
# Database upsert helpers
# ---------------------------------------------------------------------------


def upsert_tournaments(
    db: Session, parsed: list[dict]
) -> tuple[int, int, list[tuple[str, str, str]]]:
    """
    Upsert Tournament rows. Returns (created, updated, transitions).

    transitions is a list of (tournament_id_str, old_status, new_status) for
    every row whose status changed in this call. The caller (sync_schedule) uses
    this to publish SQS events for meaningful status changes.

    Only mutable fields (name, end_date, status) are updated on an existing row.

    competition_id and is_team_event are set on creation and updated only if
    competition_id is not already set (safe to re-run; avoids overwriting
    manually corrected values).
    """
    created, updated = 0, 0
    transitions: list[tuple[str, str, str]] = []

    for item in parsed:
        existing = db.query(Tournament).filter_by(pga_tour_id=item["pga_tour_id"]).first()
        if existing:
            old_status = existing.status
            new_status = item["status"]
            existing.name = item["name"]
            existing.start_date = item["start_date"]
            existing.end_date = item["end_date"]
            existing.status = new_status
            # Only update team-event fields if not yet set (preserves manual corrections).
            if existing.competition_id is None:
                existing.competition_id = item.get("competition_id")
                existing.is_team_event = item.get("is_team_event", False)
            updated += 1
            if old_status != new_status:
                # db.flush so existing.id is available; commit happens below.
                db.flush()
                transitions.append((str(existing.id), old_status, new_status))
        else:
            db.add(
                Tournament(
                    pga_tour_id=item["pga_tour_id"],
                    competition_id=item.get("competition_id"),
                    is_team_event=item.get("is_team_event", False),
                    name=item["name"],
                    start_date=item["start_date"],
                    end_date=item["end_date"],
                    status=item["status"],
                )
            )
            created += 1
    db.commit()
    return created, updated, transitions


def upsert_field(
    db: Session,
    tournament: Tournament,
    golfers: list[dict],
    results: list[dict],
) -> tuple[int, int]:
    """
    Upsert Golfer and TournamentEntry rows for the tournament's field.
    Returns (golfers_synced, entries_synced).

    results is a parallel list to golfers (same pga_tour_id key links them).
    For team events each result dict includes team_competitor_id, which is
    stored on the entry so score_picks can call the correct earnings endpoint.
    """
    results_by_id = {r["pga_tour_id"]: r for r in results}

    golfers_synced = 0
    entries_synced = 0
    entry_by_pga_id: dict[str, TournamentEntry] = {}  # track for position recompute

    # ── Bulk pre-load existing data (3 queries instead of ~900) ──────────
    # 1. All golfers that appear in the incoming data, keyed by pga_tour_id.
    incoming_pga_ids = [g["pga_tour_id"] for g in golfers]
    existing_golfers: dict[str, Golfer] = {
        gl.pga_tour_id: gl
        for gl in db.query(Golfer).filter(Golfer.pga_tour_id.in_(incoming_pga_ids)).all()
    }

    # 2. All tournament entries for this tournament, keyed by golfer_id.
    existing_entries: dict[uuid.UUID, TournamentEntry] = {
        e.golfer_id: e
        for e in db.query(TournamentEntry).filter_by(tournament_id=tournament.id).all()
    }

    # 3. All entry rounds for this tournament's entries, keyed by (entry_id, round_number).
    entry_ids = [e.id for e in existing_entries.values()]
    existing_rounds: dict[tuple[int, int], TournamentEntryRound] = {}
    if entry_ids:
        for r in (
            db.query(TournamentEntryRound)
            .filter(TournamentEntryRound.tournament_entry_id.in_(entry_ids))
            .all()
        ):
            existing_rounds[(r.tournament_entry_id, r.round_number)] = r

    # ── Upsert loop (dict lookups, no per-row queries) ───────────────────
    new_golfers_added = False
    for g in golfers:
        # Upsert golfer profile.
        golfer = existing_golfers.get(g["pga_tour_id"])
        if golfer:
            if g["name"] is not None:
                golfer.name = g["name"]
            if g.get("country") is not None:
                golfer.country = g["country"]
        else:
            golfer = Golfer(
                pga_tour_id=g["pga_tour_id"],
                name=g["name"] or "Unknown",
                country=g.get("country"),
            )
            db.add(golfer)
            existing_golfers[g["pga_tour_id"]] = golfer
            new_golfers_added = True

    # Single flush to populate IDs for all new golfers at once.
    if new_golfers_added:
        db.flush()

    for g in golfers:
        golfer = existing_golfers[g["pga_tour_id"]]
        result = results_by_id.get(g["pga_tour_id"], {})

        # Upsert tournament entry.
        entry = existing_entries.get(golfer.id)
        if entry:
            if result.get("finish_position") is not None:
                entry.finish_position = result["finish_position"]
            if result.get("earnings_usd") is not None:
                entry.earnings_usd = result["earnings_usd"]
            entry.status = result.get("status")
            if result.get("tee_time") is not None:
                entry.tee_time = result["tee_time"]
            if result.get("team_competitor_id") is not None:
                entry.team_competitor_id = result["team_competitor_id"]
        else:
            entry = TournamentEntry(
                tournament_id=tournament.id,
                golfer_id=golfer.id,
                finish_position=result.get("finish_position"),
                earnings_usd=result.get("earnings_usd"),
                status=result.get("status"),
                tee_time=result.get("tee_time"),
                team_competitor_id=result.get("team_competitor_id"),
            )
            db.add(entry)
            existing_entries[golfer.id] = entry
            entries_synced += 1

        # Upsert per-round data.
        rounds = result.get("rounds", [])
        if rounds:
            if not entry.id:
                db.flush()  # populate entry.id for new entries
            for rd in rounds:
                round_row = existing_rounds.get((entry.id, rd["round_number"]))
                if round_row:
                    if rd.get("tee_time") is not None:
                        round_row.tee_time = rd["tee_time"]
                    if rd.get("score") is not None:
                        round_row.score = rd["score"]
                    if rd.get("score_to_par") is not None:
                        round_row.score_to_par = rd["score_to_par"]
                    if rd.get("position") is not None:
                        round_row.position = rd["position"]
                    round_row.is_playoff = rd.get("is_playoff", False)
                    round_row.thru = rd.get("thru")
                    if rd.get("started_on_back") is not None:
                        round_row.started_on_back = rd["started_on_back"]
                else:
                    new_round = TournamentEntryRound(
                        tournament_entry_id=entry.id,
                        round_number=rd["round_number"],
                        tee_time=rd.get("tee_time"),
                        score=rd.get("score"),
                        score_to_par=rd.get("score_to_par"),
                        position=rd.get("position"),
                        is_playoff=rd.get("is_playoff", False),
                        thru=rd.get("thru"),
                        started_on_back=rd.get("started_on_back"),
                    )
                    db.add(new_round)

        entry_by_pga_id[g["pga_tour_id"]] = entry
        golfers_synced += 1

    # For SCHEDULED tournaments, remove TournamentEntry rows for golfers that
    # ESPN no longer includes in the field response.  This handles the case where
    # a golfer withdraws *before* the tournament starts and ESPN silently drops
    # them from the field list (rather than marking them WD).  We must not do
    # this for IN_PROGRESS or COMPLETED tournaments: a golfer who teed off and
    # then withdrew or was DQ'd must keep their entry so that picks made against
    # them still display correctly.
    if tournament.status == TournamentStatus.SCHEDULED.value:
        espn_pga_ids = {g["pga_tour_id"] for g in golfers}
        stale_entries = (
            db.query(TournamentEntry)
            .join(Golfer, TournamentEntry.golfer_id == Golfer.id)
            .filter(
                TournamentEntry.tournament_id == tournament.id,
                ~Golfer.pga_tour_id.in_(espn_pga_ids),
            )
            .all()
        )
        for stale in stale_entries:
            db.query(TournamentEntryRound).filter_by(tournament_entry_id=stale.id).delete(
                synchronize_session=False
            )
            db.delete(stale)
        if stale_entries:
            log.info(
                "Removed %d stale field entr%s for scheduled tournament %s",
                len(stale_entries),
                "y" if len(stale_entries) == 1 else "ies",
                tournament.pga_tour_id,
            )

    # Recompute display positions from score_to_par totals so that tied golfers
    # share the same finish_position (e.g. T6 → all get 6, is_tied=True).
    # ESPN's "order" field is sequential and never repeats for ties, so we
    # ignore it and compute our own ranks from the round data we just upserted.
    stp_by_pga_id: dict[str, int | None] = {}
    for result in results:
        pid = result["pga_tour_id"]
        rounds = result.get("rounds", [])
        valid_stps = [r["score_to_par"] for r in rounds if r.get("score_to_par") is not None]
        stp_by_pga_id[pid] = sum(valid_stps) if valid_stps else None

    stp_counts: Counter[int] = Counter(stp for stp in stp_by_pga_id.values() if stp is not None)
    sorted_pga_ids = sorted(
        stp_by_pga_id.keys(),
        key=lambda pid: (
            stp_by_pga_id[pid] is None,
            stp_by_pga_id[pid] if stp_by_pga_id[pid] is not None else 0,
        ),
    )
    rank = 1
    for i, pid in enumerate(sorted_pga_ids):
        stp = stp_by_pga_id[pid]
        if i > 0:
            prev_stp = stp_by_pga_id[sorted_pga_ids[i - 1]]
            if prev_stp != stp:
                rank = i + 1
        entry = entry_by_pga_id.get(pid)
        if entry is None:
            continue
        if stp is not None:
            entry.finish_position = rank
            entry.is_tied = stp_counts[stp] > 1
        else:
            # No round data yet — leave ESPN order in place, not tied
            entry.is_tied = False

    # Break ties that were resolved by a playoff.
    #
    # The score-to-par recomputation above correctly marks regulation ties as
    # is_tied=True, but a playoff winner and loser share the same regulation
    # score-to-par so they end up tied too. ESPN's "order" field IS updated
    # after the playoff to reflect the final result (1st, 2nd, …), so we use
    # it to split any tied group that includes players with playoff round data.
    espn_order_by_pga_id: dict[str, int | None] = {
        r["pga_tour_id"]: r.get("finish_position") for r in results
    }
    has_playoff_by_pga_id: dict[str, bool] = {
        r["pga_tour_id"]: any(rd.get("is_playoff") for rd in r.get("rounds", [])) for r in results
    }
    # Collect tied groups that contain at least one playoff participant.
    playoff_tie_groups: dict[int, list[str]] = {}
    for pid, stp in stp_by_pga_id.items():
        if stp is not None and has_playoff_by_pga_id.get(pid):
            entry = entry_by_pga_id.get(pid)
            if entry and entry.is_tied:
                playoff_tie_groups.setdefault(stp, []).append(pid)
    # Within each such group, reassign unique positions using ESPN's final order.
    for stp, pids in playoff_tie_groups.items():
        sorted_pids = sorted(pids, key=lambda p: espn_order_by_pga_id.get(p) or 9999)
        base_rank = entry_by_pga_id[sorted_pids[0]].finish_position
        for offset, pid in enumerate(sorted_pids):
            entry = entry_by_pga_id.get(pid)
            if entry:
                entry.finish_position = base_rank + offset
                entry.is_tied = False

    db.commit()
    return golfers_synced, entries_synced


def score_picks(
    db: Session,
    tournament: Tournament,
    *,
    league_id: uuid.UUID | None = None,
    skip_standings_refresh: bool = False,
) -> int:
    """
    Calculate and store points_earned for picks in a completed tournament.

    When league_id is provided, only scores picks for that league. When None,
    scores all picks across all leagues (used by the worker and safety nets).

    When skip_standings_refresh is True, the standings cache is NOT refreshed
    after scoring. Callers should refresh standings themselves — useful when
    batching multiple score_picks calls to avoid redundant recomputation.

    Uses bulk SQL updates instead of per-pick Python loops:
      1. Pre-step: fetch missing earnings from ESPN for entries with NULL earnings_usd
      2. Bulk UPDATE: join picks → tournament_entries → league_tournaments to compute
         points_earned = COALESCE(earnings_usd, 0) * COALESCE(lt.multiplier, 1.0)
      3. Zero-out: picks with no matching TournamentEntry get points_earned = 0

    Returns the number of picks scored.
    """
    if tournament.status != TournamentStatus.COMPLETED.value:
        log.warning("score_picks called on non-completed tournament %s", tournament.name)
        return 0

    # ── Pre-step: fetch missing earnings from ESPN ────────────────────────
    # Only entries with NULL earnings_usd need fetching. After backfill this
    # is typically 0 entries — this is a safety net for edge cases.
    null_entries = (
        db.query(TournamentEntry)
        .filter(
            TournamentEntry.tournament_id == tournament.id,
            TournamentEntry.earnings_usd.is_(None),
        )
        .all()
    )
    if null_entries:
        earnings_cache: dict[uuid.UUID, int | None] = {}
        for entry in null_entries:
            if entry.golfer_id in earnings_cache:
                raw = earnings_cache[entry.golfer_id]
            else:
                if tournament.is_team_event and entry.team_competitor_id:
                    competitor_id = entry.team_competitor_id
                else:
                    golfer = db.query(Golfer).filter_by(id=entry.golfer_id).first()
                    competitor_id = golfer.pga_tour_id if golfer else None

                raw = None
                if competitor_id:
                    raw = _fetch_golfer_earnings(
                        tournament.pga_tour_id,
                        competitor_id,
                        competition_id=tournament.competition_id,
                        is_team_event=tournament.is_team_event,
                    )
                earnings_cache[entry.golfer_id] = raw

            if raw is not None:
                entry.earnings_usd = raw
        db.flush()

    # ── Earnings completeness gate ───────────────────────────────────────
    # Defer scoring until all made-the-cut entries have earnings published.
    # CUT/WD/DQ players are excluded (they have entry.status set). This
    # prevents premature scoring when ESPN hasn't published all earnings yet.
    if not _all_earnings_available(db, str(tournament.id)):
        log.info(
            "Deferring scoring for '%s' — not all made-the-cut earnings available yet",
            tournament.name,
        )
        return 0

    # ── Bulk UPDATE: score all picks in one SQL statement ─────────────────
    # points_earned = COALESCE(te.earnings_usd, 0) * COALESCE(lt.multiplier, 1.0)
    # Multiplier comes exclusively from league_tournaments; defaults to 1.0
    # if the league didn't set one (tournament.multiplier is not used).

    # Alias for the picks table used in the subquery (avoids ambiguity with
    # the Pick table referenced in the outer UPDATE).
    p = Pick.__table__.alias("p")
    te = TournamentEntry.__table__
    lt = LeagueTournament.__table__

    earned_expr = sqlfunc.coalesce(te.c.earnings_usd, 0) * sqlfunc.coalesce(lt.c.multiplier, 1.0)

    sub_filters = [p.c.tournament_id == tournament.id]
    if league_id is not None:
        sub_filters.append(p.c.league_id == league_id)

    subq = (
        select(p.c.id.label("pick_id"), earned_expr.label("earned"))
        .select_from(
            p.join(
                te, and_(te.c.tournament_id == p.c.tournament_id, te.c.golfer_id == p.c.golfer_id)
            ).outerjoin(
                lt, and_(lt.c.league_id == p.c.league_id, lt.c.tournament_id == p.c.tournament_id)
            )
        )
        .where(and_(*sub_filters))
        .subquery("sub")
    )

    bulk_stmt = update(Pick).where(Pick.id == subq.c.pick_id).values(points_earned=subq.c.earned)
    result = db.execute(bulk_stmt)
    matched_count = result.rowcount

    # ── Zero-out: picks with no matching TournamentEntry ──────────────────
    # Covers golfers who withdrew before field sync (no entry row exists).
    zero_filters = [
        Pick.tournament_id == tournament.id,
        ~select(te.c.id)
        .where(and_(te.c.tournament_id == Pick.tournament_id, te.c.golfer_id == Pick.golfer_id))
        .correlate(Pick)
        .exists(),
    ]
    if league_id is not None:
        zero_filters.append(Pick.league_id == league_id)

    zero_stmt = update(Pick).where(and_(*zero_filters)).values(points_earned=0)
    zero_result = db.execute(zero_stmt)
    zero_count = zero_result.rowcount
    count = matched_count + zero_count

    # ── Refresh standings cache ───────────────────────────────────────────
    if count > 0 and not skip_standings_refresh:
        from app.services.scoring import refresh_standings_cache

        season_query = (
            db.query(Pick.season_id).filter(Pick.tournament_id == tournament.id).distinct()
        )
        if league_id is not None:
            season_query = season_query.filter(Pick.league_id == league_id)
        scored_season_ids = {row[0] for row in season_query.all()}

        for season in db.query(Season).filter(Season.id.in_(scored_season_ids)).all():
            refresh_standings_cache(db, season)

    db.commit()
    log.info("Scored %d picks for '%s'", count, tournament.name)

    return count


# ---------------------------------------------------------------------------
# High-level sync functions (HTTP + DB)
# ---------------------------------------------------------------------------


def _trim_post_championship_tournaments(db: Session) -> int:
    """
    Delete any Tournament rows that start after the Tour Championship ends.

    Run after every schedule sync to remove rows that may have been inserted
    before this cutoff rule existed. Safely skips any tournament that still has
    picks or league_tournament associations (those must be cleaned up manually).
    """
    tour_champ = (
        db.query(Tournament)
        .filter(Tournament.name.ilike("%tour championship%"))
        .order_by(Tournament.start_date.desc())
        .first()
    )
    if not tour_champ:
        return 0

    after_cutoff = db.query(Tournament).filter(Tournament.start_date > tour_champ.end_date).all()
    deleted = 0
    for t in after_cutoff:
        has_deps = (
            db.query(LeagueTournament).filter_by(tournament_id=t.id).first()
            or db.query(Pick).filter_by(tournament_id=t.id).first()
        )
        if has_deps:
            log.warning(
                "Skipping deletion of post-championship tournament '%s' — has active dependencies",
                t.name,
            )
            continue
        for entry in db.query(TournamentEntry).filter_by(tournament_id=t.id).all():
            db.delete(entry)
        db.delete(t)
        deleted += 1

    if deleted:
        db.commit()
        log.info("Trimmed %d post-Tour-Championship tournament(s)", deleted)
    return deleted


def _backfill_purse(db: Session) -> int:
    """
    Fetch purse from the ESPN core event endpoint for tournaments that don't
    have it yet. Returns the number of tournaments updated.

    Only fetches for scheduled tournaments — in_progress and completed
    tournaments already get purse from sync_tournament(). Failures are
    logged and skipped so one bad event doesn't block the rest.
    """
    missing = (
        db.query(Tournament)
        .filter(
            Tournament.purse_usd.is_(None),
            Tournament.status == TournamentStatus.SCHEDULED.value,
        )
        .all()
    )
    if not missing:
        return 0

    count = 0
    for t in missing:
        try:
            event_data = _get_json(f"{_CORE_API_BASE}/events/{t.pga_tour_id}")
            raw_purse = event_data.get("purse")
            if raw_purse is not None:
                t.purse_usd = int(raw_purse)
                count += 1
        except Exception as exc:
            log.warning("Purse backfill failed for %s: %s", t.pga_tour_id, exc)

    if count:
        db.commit()
        log.info("Purse backfilled for %d tournament(s)", count)

    return count


def sync_schedule(db: Session, year: int) -> dict:
    """
    Fetch the PGA Tour schedule for a calendar year and upsert tournaments.
    Returns a summary dict with counts.

    Publishes a TOURNAMENT_COMPLETED SQS event for every tournament that
    transitions to "completed" in this sync. This triggers the finalization
    pipeline (score_picks → score_round → advance_bracket) in the worker
    container. SQS is only available when SQS_QUEUE_URL is set in the
    environment — if it is absent (e.g. admin-triggered sync before the
    worker is deployed) the publish step is silently skipped.
    """
    log.info("Syncing schedule for year %d", year)
    try:
        data = _get_json(_SCOREBOARD_URL, params={"dates": str(year)})
    except httpx.HTTPError as exc:
        log.error("Failed to fetch schedule: %s", exc)
        raise

    parsed, scoreboard_athletes = parse_schedule_response(data)
    created, updated, transitions = upsert_tournaments(db, parsed)

    # Remove any rows that somehow slipped in past the Tour Championship cutoff.
    trimmed = _trim_post_championship_tournaments(db)

    log.info("Schedule sync: %d created, %d updated, %d trimmed", created, updated, trimmed)

    # Backfill purse for tournaments that don't have it yet.
    # The scoreboard endpoint doesn't include purse — it's only on the core
    # event endpoint. We fetch it individually for tournaments missing purse
    # so users see purse info on upcoming tournaments without waiting for
    # the field sync (which only runs 2 days before the start date).
    purse_filled = _backfill_purse(db)

    # Publish SQS events for status transitions detected in this sync.
    # We only publish TOURNAMENT_COMPLETED here; TOURNAMENT_IN_PROGRESS is
    # published from sync_tournament() so it fires within 5 minutes of the
    # first tee time rather than waiting for the next daily schedule sync.
    _publish_schedule_transitions(transitions, db=db)

    return {
        "year": year,
        "tournaments_created": created,
        "tournaments_updated": updated,
        "tournaments_trimmed": trimmed,
        "purse_backfilled": purse_filled,
        "scoreboard_athletes": scoreboard_athletes,
    }


_EARNINGS_READY_THRESHOLD = 0.80


def _all_earnings_available(db: Session, tournament_id: str) -> bool:
    """
    Check whether ESPN has published enough earnings to score a tournament.

    ESPN publishes earnings gradually after completion. The winner appears
    first, then other positions trickle in over 12-48 hours. Additionally,
    ESPN returns amount=0.0 for both "genuinely $0" (amateurs) AND "not yet
    published" — these are indistinguishable at the API level. So we use a
    threshold approach:

      1. Count "made-the-cut" entries: status IS NULL, has at least 1 round.
         (Excludes CUT/WD/DQ via status, excludes pre-WDs via round count.)
      2. Of those, count how many have earnings_usd > 0.
      3. If >= 80% have positive earnings, the remainder are likely amateurs
         or edge cases — scoring can proceed.
      4. If < 80%, ESPN probably hasn't published all earnings yet — defer.

    Includes a 72-hour escape hatch: if the tournament completed more than 3
    days ago, proceed regardless. COALESCE(NULL, 0) handles remaining NULLs.

    Returns True when scoring should proceed. Returns False to defer.
    """
    tournament = db.query(Tournament).filter_by(id=tournament_id).first()
    if not tournament:
        return False

    # Subquery: entries with at least 1 round played (excludes pre-tournament WDs).
    has_rounds_sq = (
        select(TournamentEntryRound.tournament_entry_id)
        .where(TournamentEntryRound.tournament_entry_id == TournamentEntry.id)
        .correlate(TournamentEntry)
        .exists()
    )

    # Total made-the-cut entries (status NULL = not CUT/WD/DQ, has rounds = played).
    total_made_cut = (
        db.query(TournamentEntry)
        .filter(
            TournamentEntry.tournament_id == tournament_id,
            TournamentEntry.status.is_(None),
            has_rounds_sq,
        )
        .count()
    )

    if total_made_cut == 0:
        return True

    # How many of those have positive earnings (> 0)?
    with_positive_earnings = (
        db.query(TournamentEntry)
        .filter(
            TournamentEntry.tournament_id == tournament_id,
            TournamentEntry.status.is_(None),
            TournamentEntry.earnings_usd > 0,
            has_rounds_sq,
        )
        .count()
    )

    ratio = with_positive_earnings / total_made_cut

    # Escape hatch: if tournament completed >72 hours ago, score anyway.
    if ratio < _EARNINGS_READY_THRESHOLD:
        if tournament.end_date and (date.today() - tournament.end_date).days >= 3:
            log.warning(
                "Earnings gate: tournament %s completed >72h ago "
                "(%.0f%% earnings available) — proceeding anyway",
                tournament_id,
                ratio * 100,
            )
            return True

        log.info(
            "Earnings gate: %.0f%% of made-the-cut entries have earnings "
            "for tournament %s (%d/%d) — deferring (need %.0f%%)",
            ratio * 100,
            tournament_id,
            with_positive_earnings,
            total_made_cut,
            _EARNINGS_READY_THRESHOLD * 100,
        )
        return False

    log.info(
        "Earnings gate: %.0f%% of made-the-cut entries have earnings "
        "for tournament %s (%d/%d) — proceeding",
        ratio * 100,
        tournament_id,
        with_positive_earnings,
        total_made_cut,
    )
    return True


def _publish_schedule_transitions(
    transitions: list[tuple[str, str, str]],
    db: Session | None = None,
) -> None:
    """
    Publish SQS events for status transitions returned by upsert_tournaments().

    Only fires when SQS_QUEUE_URL is present in the environment. Missing env
    var is treated as a graceful no-op (early dev, local without LocalStack).

    TOURNAMENT_COMPLETED is gated on the winner having earnings — if ESPN
    hasn't published prize money yet, the event is skipped and
    results_finalization will catch it later.
    """
    import os

    if not os.environ.get("SQS_QUEUE_URL"):
        return

    from app.services.sqs import publish

    for tournament_id, old_status, new_status in transitions:
        if new_status == "completed":
            # Gate on winner earnings to prevent premature scoring.
            if db is not None and not _all_earnings_available(db, tournament_id):
                log.info(
                    "Schedule sync: deferring TOURNAMENT_COMPLETED for %s — "
                    "earnings not yet published (results_finalization will retry)",
                    tournament_id,
                )
                continue

            log.info(
                "Schedule sync: publishing TOURNAMENT_COMPLETED for %s (%s → %s)",
                tournament_id,
                old_status,
                new_status,
            )
            try:
                publish("TOURNAMENT_COMPLETED", tournament_id=tournament_id)
            except Exception as exc:
                # SQS failure must not abort the sync — log and continue.
                log.error(
                    "Failed to publish TOURNAMENT_COMPLETED for %s: %s",
                    tournament_id,
                    exc,
                    exc_info=True,
                )


def _maybe_publish_in_progress(db: Session, tournament) -> None:
    """
    Publish TOURNAMENT_IN_PROGRESS if this tournament has at least one playoff
    round in "drafting" status with draft_resolved_at IS NULL.

    Called from sync_tournament() every ~5 minutes while live_score_sync is
    active. The publish stops once all linked playoff rounds are resolved, so
    the queue stays clean. SQS env vars must be present; if absent (no LocalStack
    locally or worker not yet deployed) this is a silent no-op.
    """
    import os

    if not os.environ.get("SQS_QUEUE_URL"):
        return

    from app.models import PlayoffRound

    unresolved = (
        db.query(PlayoffRound.id)
        .filter(
            PlayoffRound.tournament_id == tournament.id,
            PlayoffRound.status == "drafting",
            PlayoffRound.draft_resolved_at.is_(None),
        )
        .first()
    )
    if not unresolved:
        return  # Nothing to resolve — skip publish

    from app.services.sqs import publish

    try:
        publish("TOURNAMENT_IN_PROGRESS", tournament_id=str(tournament.id))
    except Exception as exc:
        log.error(
            "Failed to publish TOURNAMENT_IN_PROGRESS for %s: %s",
            tournament.id,
            exc,
            exc_info=True,
        )


def sync_tournament(
    db: Session,
    pga_tour_id: str,
    *,
    force: bool = False,
    scoreboard_athletes: dict[str, dict] | None = None,
) -> dict:
    """
    Sync the field and results for a single tournament using the ESPN core API.

    Routes to _fetch_team_field for team-format tournaments (is_team_event=True)
    or _fetch_tournament_data for standard individual tournaments. After upserting
    golfers and entries, scores any pending picks if the tournament is completed.

    Per-round data (tee times, strokes, score-to-par, position) is fetched for
    all tournament states using the ESPN /linescores endpoint. This single call
    covers tee times for upcoming rounds (for pick-locking) and historical
    round scores for completed tournaments.

    force=True: delete all TournamentEntryRound rows for this tournament before
    re-fetching. Use when ESPN has corrected data that is stale in the DB
    (e.g. wrong status, phantom rounds, missing playoff data).

    Returns a summary dict with counts.
    """
    tournament = db.query(Tournament).filter_by(pga_tour_id=pga_tour_id).first()
    if not tournament:
        raise ValueError(
            f"Tournament with pga_tour_id '{pga_tour_id}' not found in DB. Run sync_schedule first."
        )

    log.info(
        "Syncing tournament '%s' (id=%s, team=%s, force=%s)",
        tournament.name,
        pga_tour_id,
        tournament.is_team_event,
        force,
    )

    if force:
        # Delete all round rows for this tournament so stale ESPN data is fully replaced.
        # Entry-level fields (status, earnings, finish_position) are reset to None so
        # the upcoming upsert writes fresh values from ESPN unconditionally.
        entry_ids_sq = (
            db.query(TournamentEntry.id)
            .filter(TournamentEntry.tournament_id == tournament.id)
            .scalar_subquery()
        )
        rounds_deleted = (
            db.query(TournamentEntryRound)
            .filter(TournamentEntryRound.tournament_entry_id.in_(entry_ids_sq))
            .delete(synchronize_session=False)
        )
        entries_cleared = (
            db.query(TournamentEntry)
            .filter(TournamentEntry.tournament_id == tournament.id)
            .update(
                {
                    TournamentEntry.status: None,
                    TournamentEntry.finish_position: None,
                    TournamentEntry.earnings_usd: None,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        log.info(
            "Force sync: cleared %d entries (%d rounds) for '%s'",
            entries_cleared,
            rounds_deleted,
            tournament.name,
        )

    # Fetch purse and tournament status from the core event endpoint.
    # The site API scoreboard (used by sync_schedule) is the canonical status source,
    # but this endpoint also returns status — reading it here lets sync_tournament()
    # detect and apply the in_progress → completed transition without waiting for
    # the next daily schedule sync (which runs at 06:00 UTC).
    # Status update is outside the try/except so a purse fetch failure does not
    # silently block completion detection.
    event_data: dict = {}
    try:
        event_data = _get_json(f"{_CORE_API_BASE}/events/{pga_tour_id}")
        raw_purse = event_data.get("purse")
        if raw_purse is not None:
            tournament.purse_usd = int(raw_purse)
            db.commit()
    except Exception as exc:
        log.warning("Could not fetch event data for %s: %s", pga_tour_id, exc)

    # Apply status transition if ESPN reports a different status than what's in the DB.
    # _publish_schedule_transitions fires TOURNAMENT_COMPLETED via SQS so the worker
    # can run score_picks() — same path as the daily sync_schedule() transition.
    raw_espn_status = event_data.get("status", {}).get("type", {}).get("name")
    if raw_espn_status:
        new_status = _map_espn_status(raw_espn_status)
        if tournament.status != new_status:
            old_status = tournament.status
            tournament.status = new_status
            db.commit()
            log.info(
                "sync_tournament: status transition for '%s': %s → %s",
                tournament.name,
                old_status,
                new_status,
            )
            _publish_schedule_transitions([(str(tournament.id), old_status, new_status)], db=db)

    # Pass IDs of golfers already in DB so fetch functions skip re-fetching them.
    known_ids = {row[0] for row in db.query(Golfer.pga_tour_id).all()}

    # Fetch earnings concurrently for completed tournaments so that force syncs
    # repopulate earnings in the same pass as field data. For non-completed
    # tournaments, earnings are deferred to score_picks() (called after completion).
    should_fetch_earnings = tournament.status == TournamentStatus.COMPLETED.value

    try:
        if tournament.is_team_event:
            # Use the stored competition_id (may differ from pga_tour_id for team events).
            effective_competition_id = tournament.competition_id or pga_tour_id
            golfers, results = _fetch_team_field(
                pga_tour_id,
                effective_competition_id,
                known_golfer_ids=known_ids,
                fetch_round_data=True,
                scoreboard_athletes=scoreboard_athletes,
                fetch_earnings=should_fetch_earnings,
            )
        else:
            golfers, results = _fetch_tournament_data(
                pga_tour_id,
                known_golfer_ids=known_ids,
                fetch_round_data=True,
                scoreboard_athletes=scoreboard_athletes,
                fetch_earnings=should_fetch_earnings,
            )
    except (httpx.HTTPError, httpx.RequestError) as exc:
        log.error("Failed to fetch field for %s: %s", pga_tour_id, exc)
        raise

    golfers_synced, entries_synced = upsert_field(db, tournament, golfers, results)

    # ESPN schema change detection — warn if key fields are consistently missing.
    # A few None values are normal (e.g. tee times not yet assigned), but if ALL
    # entries lack a field that should be populated, ESPN likely renamed it.
    _check_schema_health(tournament.name, tournament.status, golfers, results)

    # Re-query to get the latest status after upsert.
    db.refresh(tournament)
    picks_scored = 0
    if tournament.status == TournamentStatus.COMPLETED.value:
        picks_scored = score_picks(db, tournament)

    # Stamp the tournament with the current time as a sync-completion marker.
    # This is the LAST write — after all upserts and pick scoring — so the frontend
    # can poll this value and only refresh the leaderboard when a full sync is done.
    tournament.last_synced_at = datetime.now(tz=UTC)
    db.commit()

    # If the tournament is in_progress and has unresolved playoff draft rounds,
    # publish TOURNAMENT_IN_PROGRESS so the worker can call resolve_draft() once
    # the first Round 1 tee time passes. This runs every 5 minutes via
    # live_score_sync, but stops publishing once all draft rounds are resolved
    # (the guard below returns early). The worker handler is idempotent —
    # receiving the same message multiple times is safe.
    if tournament.status == TournamentStatus.IN_PROGRESS.value:
        _maybe_publish_in_progress(db, tournament)

    log.info(
        "Tournament sync '%s': %d golfers, %d new entries, %d picks scored",
        tournament.name,
        golfers_synced,
        entries_synced,
        picks_scored,
    )
    return {
        "pga_tour_id": pga_tour_id,
        "name": tournament.name,
        "golfers_synced": golfers_synced,
        "entries_synced": entries_synced,
        "picks_scored": picks_scored,
    }


def full_sync(db: Session, year: int, *, force: bool = False) -> dict:
    """
    Run a complete sync for an entire year:
      1. Fetch the schedule and upsert all tournaments.
      2. For each IN_PROGRESS or COMPLETED tournament, sync its field + results.
      3. Also sync the single next SCHEDULED tournament so the pick form has
         a golfer list to show.

    force=True clears all existing round data before re-fetching (same as
    calling sync_tournament with force=True for each tournament).

    This is what the scheduler calls daily and what /admin/sync triggers.
    """
    schedule_result = sync_schedule(db, year)
    # Extract athlete data harvested from the scoreboard's inline competitors.
    # Passed to sync_tournament so it can skip individual /athletes/{id} API calls.
    sb_athletes = schedule_result.pop("scoreboard_athletes", {})

    # Sync field + results for active or finished tournaments.
    active_statuses = {
        TournamentStatus.IN_PROGRESS.value,
        TournamentStatus.COMPLETED.value,
    }
    tournaments_to_sync = db.query(Tournament).filter(Tournament.status.in_(active_statuses)).all()

    # Also sync the soonest upcoming scheduled tournament so the pick form works.
    next_scheduled = (
        db.query(Tournament)
        .filter(Tournament.status == TournamentStatus.SCHEDULED.value)
        .order_by(Tournament.start_date.asc())
        .first()
    )
    if next_scheduled and next_scheduled not in tournaments_to_sync:
        tournaments_to_sync = list(tournaments_to_sync) + [next_scheduled]

    tournaments = tournaments_to_sync

    # Capture identity info before parallelizing — ORM attributes may not be
    # accessible from a different session.
    sync_targets = [(t.pga_tour_id, t.name) for t in tournaments]

    tournament_results: list[dict] = []
    errors: list[dict] = []

    def _sync_one(pga_tour_id: str, name: str) -> dict:
        """Sync a single tournament in its own DB session."""
        from app.database import SessionLocal

        session = SessionLocal()
        try:
            result = sync_tournament(
                session, pga_tour_id, force=force, scoreboard_athletes=sb_athletes
            )
            session.commit()
            return result
        except Exception as exc:
            session.rollback()
            raise RuntimeError(f"{name}: {exc}") from exc
        finally:
            session.close()

    # Parallelize tournament syncs — each gets its own DB session and makes
    # independent ESPN API calls. Cap at 3 workers to avoid overwhelming
    # ESPN's API and the Postgres connection pool.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    max_workers = min(3, len(sync_targets)) or 1
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_name = {
            pool.submit(_sync_one, t_id, t_name): (t_id, t_name) for t_id, t_name in sync_targets
        }
        for future in as_completed(future_to_name):
            t_id, t_name = future_to_name[future]
            try:
                result = future.result()
                tournament_results.append(result)
            except Exception as exc:
                log.error("Failed to sync tournament '%s': %s", t_name, exc)
                errors.append({"pga_tour_id": t_id, "name": t_name, "error": str(exc)})

    # Publish TOURNAMENT_COMPLETED for any completed tournament that has
    # unscored playoff rounds. This covers the case where the original SQS
    # event was consumed but score_round failed (e.g. earnings not yet
    # available), or the admin triggered a manual sync after earnings appeared.
    _publish_completed_for_unscored_playoffs(db)

    return {
        "year": year,
        "schedule": schedule_result,
        "tournaments_synced": len(tournament_results),
        "errors": errors,
    }


def _publish_completed_for_unscored_playoffs(db: Session, tournament_id: str | None = None) -> None:
    """
    Find completed tournaments with locked (unscored) playoff rounds and
    publish TOURNAMENT_COMPLETED if earnings are available.

    When tournament_id is provided, only check that specific tournament.
    When None, check all completed tournaments (used by full_sync).

    This is a safety net for scenarios where the original event was consumed
    but the playoff pipeline didn't complete (e.g. earnings weren't available
    at the time, worker crashed mid-pipeline, or admin triggered a manual sync).
    """
    import os

    if not os.environ.get("SQS_QUEUE_URL"):
        return

    from app.models import PlayoffRound
    from app.services.sqs import publish

    query = (
        db.query(PlayoffRound)
        .join(Tournament, PlayoffRound.tournament_id == Tournament.id)
        .filter(
            Tournament.status == TournamentStatus.COMPLETED.value,
            PlayoffRound.status == "locked",
        )
    )
    if tournament_id is not None:
        query = query.filter(PlayoffRound.tournament_id == tournament_id)

    unscored_rounds = query.all()

    for pr in unscored_rounds:
        tid = str(pr.tournament_id)
        if not _all_earnings_available(db, tid):
            log.info(
                "Unscored playoff round %d: earnings not yet available — skipping",
                pr.round_number,
            )
            continue

        log.info(
            "Publishing TOURNAMENT_COMPLETED for unscored playoff round %d (tournament=%s)",
            pr.round_number,
            tid,
        )
        try:
            publish("TOURNAMENT_COMPLETED", tournament_id=tid)
        except Exception as exc:
            log.error(
                "Failed to publish TOURNAMENT_COMPLETED for playoff round %d: %s",
                pr.round_number,
                exc,
            )


# ---------------------------------------------------------------------------
# On-demand scorecard fetch (hole-by-hole via ESPN linescores)
# ---------------------------------------------------------------------------


def fetch_golfer_scorecard(
    tournament: Tournament,
    golfer: Golfer,
    round_number: int,
) -> dict:
    """Fetch hole-by-hole scoring for a golfer in a specific tournament round.

    Calls ESPN's /linescores endpoint for the competitor and extracts nested
    hole-level data if available.  Returns a dict matching ScorecardOut;
    ``holes`` will be an empty list if ESPN doesn't include hole-level data
    for this round (graceful degradation).
    """
    pga_tour_id = tournament.pga_tour_id
    competition_id = tournament.competition_id or pga_tour_id
    athlete_id = golfer.pga_tour_id

    url = (
        f"{_CORE_API_BASE}/events/{pga_tour_id}"
        f"/competitions/{competition_id}/competitors/{athlete_id}/linescores"
    )
    try:
        data = _get_json(url)
    except Exception as exc:
        log.warning(
            "Scorecard fetch failed for golfer %s round %d: %s",
            athlete_id,
            round_number,
            exc,
        )
        return {
            "golfer_id": str(golfer.id),
            "round_number": round_number,
            "holes": [],
            "total_score": None,
            "total_score_to_par": None,
        }

    holes: list[dict] = []
    total_score: int | None = None
    total_score_to_par: int | None = None

    # First pass: collect hole→par from ALL rounds in the response.
    # Par is a fixed course property — any round that has hole data gives us the par for each hole,
    # which we can reuse to populate par for holes not yet played in the current round.
    # Use int() with fallback so we always have integer keys regardless of what ESPN sends.
    hole_pars: dict[int, int] = {}
    for item in data.get("items", []):
        for hole_item in item.get("linescores", []):
            try:
                h = int(hole_item.get("period"))
                p = int(hole_item.get("par"))
                if h not in hole_pars:
                    hole_pars[h] = p
            except (TypeError, ValueError):
                pass

    # Second pass: process the requested round.
    # Keep the original simple append-per-hole approach (do NOT convert types here —
    # ESPN may return period/value as strings, and the frontend normalises with Number()).
    for item in data.get("items", []):
        if item.get("period") != round_number:
            continue

        # Round-level totals
        total_score = item.get("value")
        display = item.get("displayValue", "")
        try:
            total_score_to_par = 0 if display in ("E", "EVEN") else int(display.replace("+", ""))
        except (ValueError, AttributeError):
            total_score_to_par = None

        # Hole-level linescores — store exactly as ESPN sends them.
        for hole_item in item.get("linescores", []):
            hole_num = hole_item.get("period")
            score = hole_item.get("value")
            par = hole_item.get("par")
            stp: int | None = (score - par) if (score is not None and par is not None) else None
            result: str | None = None
            if stp is not None:
                if stp <= -2:
                    result = "eagle"
                elif stp == -1:
                    result = "birdie"
                elif stp == 0:
                    result = "par"
                elif stp == 1:
                    result = "bogey"
                elif stp == 2:
                    result = "double_bogey"
                else:
                    result = "triple_plus"
            holes.append(
                {
                    "hole": hole_num,
                    "par": par,
                    "score": score,
                    "score_to_par": stp,
                    "result": result,
                }
            )

        # Post-process: for standard rounds (1–4), add any holes that ESPN omitted
        # (i.e. not yet played) using the par data collected in the first pass.
        if round_number <= 4:
            played_nums: set[int] = set()
            for h in holes:
                try:
                    played_nums.add(int(h["hole"]))
                except (TypeError, ValueError):
                    pass
            for h in range(1, 19):
                if h not in played_nums and h in hole_pars:
                    holes.append(
                        {
                            "hole": h,
                            "par": hole_pars[h],
                            "score": None,
                            "score_to_par": None,
                            "result": None,
                        }
                    )
            holes.sort(key=lambda x: int(x["hole"]) if x["hole"] is not None else 99)

        break  # found the requested round; stop iterating

    return {
        "golfer_id": str(golfer.id),
        "round_number": round_number,
        "holes": holes,
        "total_score": total_score,
        "total_score_to_par": total_score_to_par,
    }
