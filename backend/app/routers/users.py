"""
Users router — /users/*

Endpoints:
  GET   /users/me                  Return the current user's profile
  PATCH /users/me                  Update display name
  GET   /users/me/leagues          Return all leagues the current user belongs to
  GET   /users/me/league-summaries Batch league summaries for Leagues page
"""

import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models import (
    League,
    LeagueMember,
    LeagueMemberStatus,
    LeagueTournament,
    Pick,
    PlayoffConfig,
    PlayoffPick,
    PlayoffPod,
    PlayoffPodMember,
    PlayoffRound,
    Season,
    Tournament,
    TournamentStatus,
    User,
)
from app.schemas.league import LeagueOut
from app.schemas.user import (
    LeagueSummaryOut,
    LeagueSummaryPick,
    LeagueSummaryPlayoffPick,
    LeagueSummaryTournament,
    UserOut,
    UserUpdate,
)
from app.services.picks import all_r1_teed_off as _all_r1_teed_off
from app.services.scoring import calculate_standings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.display_name is not None:
        current_user.display_name = body.display_name
    if body.pick_reminders_enabled is not None:
        current_user.pick_reminders_enabled = body.pick_reminders_enabled
    db.commit()
    db.refresh(current_user)
    log.info("User profile updated: user=%s", current_user.id)
    return current_user


@router.get("/me/leagues", response_model=list[LeagueOut])
def get_my_leagues(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all leagues where the current user is an approved member."""
    memberships = (
        db.query(LeagueMember)
        .filter_by(user_id=current_user.id, status=LeagueMemberStatus.APPROVED.value)
        .options(joinedload(LeagueMember.league))
        .order_by(LeagueMember.joined_at)
        .all()
    )
    return [m.league for m in memberships]


@router.get("/me/league-summaries", response_model=list[LeagueSummaryOut])
def get_league_summaries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Batch endpoint returning league summary data for the Leagues page.

    Replaces 9 independent API calls per LeagueCard with a single request.
    """
    log.debug("League summaries requested: user=%s", current_user.id)
    # 1. Get all approved memberships
    memberships = (
        db.query(LeagueMember)
        .filter_by(user_id=current_user.id, status=LeagueMemberStatus.APPROVED.value)
        .options(joinedload(LeagueMember.league))
        .order_by(LeagueMember.joined_at)
        .all()
    )

    if not memberships:
        return []

    league_ids = [m.league_id for m in memberships]
    leagues_by_id: dict[uuid.UUID, League] = {m.league.id: m.league for m in memberships}

    # 2. Get active seasons for all leagues
    seasons = (
        db.query(Season).filter(Season.league_id.in_(league_ids), Season.is_active.is_(True)).all()
    )
    season_by_league: dict[uuid.UUID, Season] = {s.league_id: s for s in seasons}

    # 3. Get all league tournaments for all leagues (batch)
    league_tournaments = (
        db.query(LeagueTournament)
        .filter(LeagueTournament.league_id.in_(league_ids))
        .options(joinedload(LeagueTournament.tournament))
        .all()
    )

    # Group by league_id
    lt_by_league: dict[uuid.UUID, list[LeagueTournament]] = {}
    for lt in league_tournaments:
        lt_by_league.setdefault(lt.league_id, []).append(lt)

    # 4. Global tournament state (query ONCE)
    global_in_progress = (
        db.query(Tournament).filter(Tournament.status == TournamentStatus.IN_PROGRESS.value).all()
    )
    has_global_in_progress = len(global_in_progress) > 0

    global_scheduled = (
        db.query(Tournament)
        .filter(Tournament.status == TournamentStatus.SCHEDULED.value)
        .order_by(Tournament.start_date.asc())
        .all()
    )
    globally_next_id = global_scheduled[0].id if global_scheduled else None

    # All non-completed global tournaments for the "preceding tournament" check
    all_global_non_completed = (
        db.query(Tournament)
        .filter(Tournament.status != TournamentStatus.COMPLETED.value)
        .order_by(Tournament.start_date.asc())
        .all()
    )

    # 5. Batch-load picks for all leagues
    season_ids = [s.id for s in seasons]
    all_picks: list[Pick] = []
    if season_ids:
        all_picks = (
            db.query(Pick)
            .filter(
                Pick.league_id.in_(league_ids),
                Pick.season_id.in_(season_ids),
                Pick.user_id == current_user.id,
            )
            .options(joinedload(Pick.golfer), joinedload(Pick.tournament))
            .all()
        )

    # Index picks by (league_id, tournament_id)
    picks_by_lt: dict[tuple[uuid.UUID, uuid.UUID], Pick] = {}
    for p in all_picks:
        picks_by_lt[(p.league_id, p.tournament_id)] = p

    # 6. Batch-load playoff configs
    playoff_configs: list[PlayoffConfig] = []
    if season_ids:
        playoff_configs = (
            db.query(PlayoffConfig)
            .filter(
                PlayoffConfig.league_id.in_(league_ids),
                PlayoffConfig.season_id.in_(season_ids),
            )
            .all()
        )
    config_by_league: dict[uuid.UUID, PlayoffConfig] = {c.league_id: c for c in playoff_configs}

    # 7. Build summaries
    results: list[LeagueSummaryOut] = []
    for m in memberships:
        league = leagues_by_id[m.league_id]
        season = season_by_league.get(m.league_id)
        is_manager = m.role == "manager"

        # -- Standings --
        rank = None
        is_tied = False
        total_points = None
        member_count = 0

        if season:
            standings = calculate_standings(db, league, season)
            member_count = len(standings)
            for i, row in enumerate(standings):
                if str(row["user_id"]) == str(current_user.id):
                    # Compute rank (1-based) and detect ties
                    r = i + 1
                    pts = row["total_points"]
                    # Check for ties: same total_points as any neighbor
                    tied = False
                    if i > 0 and standings[i - 1]["total_points"] == pts:
                        tied = True
                        r = i  # look backwards for first with same score
                        while r > 0 and standings[r - 1]["total_points"] == pts:
                            r -= 1
                        r += 1
                    if i < len(standings) - 1 and standings[i + 1]["total_points"] == pts:
                        tied = True
                        # Find the first occurrence
                        r = i + 1
                        while r > 1 and standings[r - 2]["total_points"] == pts:
                            r -= 1

                    rank = r
                    is_tied = tied
                    total_points = int(pts)
                    break

        # -- Current tournament --
        lts = lt_by_league.get(m.league_id, [])
        # Sort by start_date
        lts_sorted = sorted(lts, key=lambda x: x.tournament.start_date)
        current_lt: LeagueTournament | None = None
        for lt in lts_sorted:
            if lt.tournament.status == TournamentStatus.IN_PROGRESS.value:
                current_lt = lt
                break
        if current_lt is None:
            for lt in lts_sorted:
                if lt.tournament.status == TournamentStatus.SCHEDULED.value:
                    current_lt = lt
                    break

        current_tournament_out: LeagueSummaryTournament | None = None
        my_pick_out: LeagueSummaryPick | None = None
        pick_window_open = False
        preceding_tournament_name: str | None = None

        if current_lt is not None:
            t = current_lt.tournament
            effective_multiplier = (
                current_lt.multiplier if current_lt.multiplier is not None else t.multiplier
            )
            check_tee_times = t.status in (
                TournamentStatus.IN_PROGRESS.value,
                TournamentStatus.SCHEDULED.value,
            )
            r1_teed_off = _all_r1_teed_off(db, t.id) if check_tee_times else False

            current_tournament_out = LeagueSummaryTournament(
                id=t.id,
                name=t.name,
                start_date=str(t.start_date),
                end_date=str(t.end_date),
                status=t.status,
                purse_usd=t.purse_usd,
                effective_multiplier=effective_multiplier,
                all_r1_teed_off=r1_teed_off,
            )

            # Pick for current tournament
            pick = picks_by_lt.get((m.league_id, t.id))
            if pick is not None:
                my_pick_out = LeagueSummaryPick(
                    golfer_name=pick.golfer.name,
                    is_locked=pick.is_locked,
                )

            # Pick window open
            pick_window_open = t.status == TournamentStatus.IN_PROGRESS.value or (
                not has_global_in_progress and t.id == globally_next_id
            )

            # Preceding tournament name (for "Picks open after X" message)
            if not pick_window_open and t.status == TournamentStatus.SCHEDULED.value:
                # Find the global tournament immediately before this one that's not completed
                preceding = None
                for gt in all_global_non_completed:
                    if (
                        gt.start_date < t.start_date
                        and gt.status != TournamentStatus.COMPLETED.value
                    ):
                        preceding = gt  # keep last one before current
                if preceding is None and global_in_progress:
                    preceding = global_in_progress[0]
                if preceding is not None:
                    preceding_tournament_name = preceding.name

        # -- Playoff context --
        is_playoff_week = False
        is_in_playoffs = False
        my_playoff_picks_out: list[LeagueSummaryPlayoffPick] = []

        config = config_by_league.get(m.league_id)
        if config and config.playoff_size > 0 and current_lt is not None:
            t = current_lt.tournament
            # Check if this tournament is assigned to an active playoff round
            active_round = (
                db.query(PlayoffRound)
                .filter(
                    PlayoffRound.playoff_config_id == config.id,
                    PlayoffRound.tournament_id == t.id,
                    PlayoffRound.status.in_(["pending", "drafting", "locked"]),
                )
                .first()
            )
            if active_round:
                is_playoff_week = True
                # Check if current user is in a pod
                pod_member = (
                    db.query(PlayoffPodMember)
                    .join(PlayoffPod, PlayoffPodMember.pod_id == PlayoffPod.id)
                    .filter(
                        PlayoffPod.playoff_round_id == active_round.id,
                        PlayoffPodMember.user_id == current_user.id,
                    )
                    .first()
                )
                if pod_member:
                    is_in_playoffs = True
                    # Get playoff picks for current tournament
                    playoff_picks = (
                        db.query(PlayoffPick)
                        .filter(
                            PlayoffPick.pod_member_id == pod_member.id,
                            PlayoffPick.tournament_id == t.id,
                        )
                        .options(joinedload(PlayoffPick.golfer))
                        .order_by(PlayoffPick.draft_slot)
                        .all()
                    )
                    my_playoff_picks_out = [
                        LeagueSummaryPlayoffPick(golfer_name=pp.golfer.name) for pp in playoff_picks
                    ]

        results.append(
            LeagueSummaryOut(
                league_id=league.id,
                league_name=league.name,
                rank=rank,
                is_tied=is_tied,
                total_points=total_points,
                member_count=member_count,
                is_manager=is_manager,
                current_tournament=current_tournament_out,
                my_pick=my_pick_out,
                is_playoff_week=is_playoff_week,
                is_in_playoffs=is_in_playoffs,
                my_playoff_picks=my_playoff_picks_out,
                pick_window_open=pick_window_open,
                preceding_tournament_name=preceding_tournament_name,
            )
        )

    return results
