"""
Service-level unit tests for the playoff system.

Covers:
  - generate_draft_order (pure: snake, linear, top_seed_priority)
  - assign_pod_2 (pure: head-to-head bracket seeding)
  - score_round  (DB: earnings → points, multiplier, no-pick penalty)
  - advance_bracket (DB: winner selection, loser elimination, next-round promotion)
  - resolve_draft (DB: preference list → picks in draft order)
  - override_result (DB: manager manual winner override)

All DB tests build their fixtures directly without going through the HTTP API,
so they stay fast and isolated from router concerns.
"""

import uuid
from datetime import UTC, date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import (
    Golfer,
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    LeagueTournament,
    PlayoffConfig,
    PlayoffDraftPreference,
    PlayoffPick,
    PlayoffPod,
    PlayoffPodMember,
    PlayoffRound,
    Season,
    Tournament,
    TournamentEntry,
    User,
)
from app.services.auth import hash_password
from app.services.playoff import (
    _build_partner_map,
    advance_bracket,
    assign_pod,
    assign_pod_2,
    generate_draft_order,
    override_result,
    resolve_draft,
    score_round,
    submit_preferences,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_user(db: Session, email: str, display_name: str = "Player") -> User:
    user = User(email=email, password_hash=hash_password("password123"), display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_league(db: Session, manager: User) -> tuple[League, Season]:
    league = League(name="Test League", created_by=manager.id)
    db.add(league)
    db.flush()
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=manager.id,
            role=LeagueMemberRole.MANAGER.value,
            status=LeagueMemberStatus.APPROVED.value,
        )
    )
    season = Season(league_id=league.id, year=date.today().year, is_active=True)
    db.add(season)
    db.commit()
    db.refresh(league)
    db.refresh(season)
    return league, season


def _make_golfer(db: Session, name: str = "Test Golfer") -> Golfer:
    g = Golfer(pga_tour_id=f"T{uuid.uuid4().hex[:6]}", name=name)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def _make_tournament(
    db: Session,
    league: League,
    status: str = "completed",
    multiplier: float = 1.0,
    days_ago: int = 7,
    is_team_event: bool = False,
) -> Tournament:
    start = date.today() - timedelta(days=days_ago)
    t = Tournament(
        pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
        name="Test Open",
        start_date=start,
        end_date=start + timedelta(days=3),
        status=status,
        is_team_event=is_team_event,
    )
    db.add(t)
    db.flush()
    db.add(LeagueTournament(league_id=league.id, tournament_id=t.id, multiplier=multiplier))
    db.commit()
    db.refresh(t)
    return t


def _make_config(
    db: Session,
    league: League,
    season: Season,
    playoff_size: int = 4,
    draft_style: str = "snake",
    picks_per_round: list[int] | None = None,
) -> PlayoffConfig:
    config = PlayoffConfig(
        league_id=league.id,
        season_id=season.id,
        is_enabled=True,
        playoff_size=playoff_size,
        draft_style=draft_style,
        picks_per_round=picks_per_round or [1],
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def _make_round(
    db: Session,
    config: PlayoffConfig,
    tournament: Tournament,
    round_number: int = 1,
    status: str = "locked",
) -> PlayoffRound:
    r = PlayoffRound(
        playoff_config_id=config.id,
        round_number=round_number,
        tournament_id=tournament.id,
        status=status,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _make_pod(
    db: Session,
    round_obj: PlayoffRound,
    bracket_position: int = 1,
    status: str = "drafting",
) -> PlayoffPod:
    pod = PlayoffPod(
        playoff_round_id=round_obj.id, bracket_position=bracket_position, status=status
    )
    db.add(pod)
    db.commit()
    db.refresh(pod)
    return pod


def _make_pod_member(
    db: Session,
    pod: PlayoffPod,
    user: User,
    seed: int,
    draft_position: int,
    total_points: float | None = None,
    is_eliminated: bool = False,
) -> PlayoffPodMember:
    m = PlayoffPodMember(
        pod_id=pod.id,
        user_id=user.id,
        seed=seed,
        draft_position=draft_position,
        total_points=total_points,
        is_eliminated=is_eliminated,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _make_playoff_pick(
    db: Session,
    pod: PlayoffPod,
    pod_member: PlayoffPodMember,
    golfer: Golfer,
    tournament: Tournament,
    draft_slot: int = 1,
) -> PlayoffPick:
    pick = PlayoffPick(
        pod_id=pod.id,
        pod_member_id=pod_member.id,
        golfer_id=golfer.id,
        tournament_id=tournament.id,
        draft_slot=draft_slot,
    )
    db.add(pick)
    db.commit()
    db.refresh(pick)
    return pick


def _make_entry(
    db: Session,
    tournament: Tournament,
    golfer: Golfer,
    earnings_usd: float | None = None,
    team_competitor_id: str | None = None,
) -> TournamentEntry:
    entry = TournamentEntry(
        tournament_id=tournament.id,
        golfer_id=golfer.id,
        earnings_usd=earnings_usd,
        team_competitor_id=team_competitor_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _make_preference(
    db: Session,
    pod: PlayoffPod,
    pod_member: PlayoffPodMember,
    golfer: Golfer,
    rank: int,
) -> PlayoffDraftPreference:
    pref = PlayoffDraftPreference(
        pod_id=pod.id,
        pod_member_id=pod_member.id,
        golfer_id=golfer.id,
        rank=rank,
    )
    db.add(pref)
    db.commit()
    db.refresh(pref)
    return pref


def _reload_round(db: Session, round_id: int) -> PlayoffRound:
    """Re-fetch a PlayoffRound with all relationships lazily loadable."""
    db.expire_all()
    return db.query(PlayoffRound).filter_by(id=round_id).first()


def _reload_pod(db: Session, pod_id: int) -> PlayoffPod:
    db.expire_all()
    return db.query(PlayoffPod).filter_by(id=pod_id).first()


# ---------------------------------------------------------------------------
# Pure unit tests — generate_draft_order
# ---------------------------------------------------------------------------


class TestGenerateDraftOrder:
    def test_snake_two_players_two_picks(self):
        """Snake draft: player order alternates each round."""
        order = generate_draft_order("snake", n=2, picks=2)
        # Round 1: 1,2 | Round 2 (reversed): 2,1
        assert order == [1, 2, 2, 1]

    def test_snake_four_players_one_pick(self):
        """Snake with one pick per player is just linear order."""
        order = generate_draft_order("snake", n=4, picks=1)
        assert order == [1, 2, 3, 4]

    def test_snake_two_players_three_picks_alternates_correctly(self):
        """Snake draft with 3 rounds: 1,2 | 2,1 | 1,2."""
        order = generate_draft_order("snake", n=2, picks=3)
        assert order == [1, 2, 2, 1, 1, 2]

    def test_linear_two_players_two_picks(self):
        """Linear draft: same order every round."""
        order = generate_draft_order("linear", n=2, picks=2)
        assert order == [1, 2, 1, 2]

    def test_linear_three_players_two_picks(self):
        order = generate_draft_order("linear", n=3, picks=2)
        assert order == [1, 2, 3, 1, 2, 3]

    def test_top_seed_priority_two_players_two_picks(self):
        """Top seed priority: seed 1 gets all their picks before seed 2 drafts."""
        order = generate_draft_order("top_seed_priority", n=2, picks=2)
        assert order == [1, 1, 2, 2]

    def test_top_seed_priority_three_players_two_picks(self):
        order = generate_draft_order("top_seed_priority", n=3, picks=2)
        assert order == [1, 1, 2, 2, 3, 3]

    def test_total_length_is_n_times_picks(self):
        """The returned list always has exactly n × picks entries."""
        for style in ("snake", "linear", "top_seed_priority"):
            order = generate_draft_order(style, n=3, picks=4)
            assert len(order) == 12, f"Failed for style={style!r}"

    def test_every_player_appears_picks_times(self):
        """Each draft_position appears exactly `picks` times in the output."""
        for style in ("snake", "linear", "top_seed_priority"):
            order = generate_draft_order(style, n=3, picks=2)
            for pos in range(1, 4):
                assert order.count(pos) == 2, f"Failed for style={style!r}, pos={pos}"

    def test_invalid_style_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown draft style"):
            generate_draft_order("random", n=2, picks=1)


# ---------------------------------------------------------------------------
# Pure unit tests — assign_pod_2 (head-to-head seeding)
# ---------------------------------------------------------------------------


class TestAssignPod2:
    def test_eight_player_bracket_standard_matchups(self):
        """8-player bracket (4 pods): 1v8, 2v7, 3v6, 4v5."""
        num_pods = 4
        # seed 1 faces seed 8 → both in pod 1
        assert assign_pod_2(1, num_pods) == 1
        assert assign_pod_2(8, num_pods) == 1
        # seed 2 faces seed 7 → both in pod 2
        assert assign_pod_2(2, num_pods) == 2
        assert assign_pod_2(7, num_pods) == 2
        # seed 3 faces seed 6 → both in pod 3
        assert assign_pod_2(3, num_pods) == 3
        assert assign_pod_2(6, num_pods) == 3
        # seed 4 faces seed 5 → both in pod 4
        assert assign_pod_2(4, num_pods) == 4
        assert assign_pod_2(5, num_pods) == 4

    def test_four_player_bracket_standard_matchups(self):
        """4-player bracket (2 pods): 1v4, 2v3."""
        num_pods = 2
        assert assign_pod_2(1, num_pods) == 1
        assert assign_pod_2(4, num_pods) == 1
        assert assign_pod_2(2, num_pods) == 2
        assert assign_pod_2(3, num_pods) == 2

    def test_two_player_bracket(self):
        """2-player bracket (1 pod): both seeds go into pod 1."""
        assert assign_pod_2(1, 1) == 1
        assert assign_pod_2(2, 1) == 1


# ---------------------------------------------------------------------------
# DB tests — score_round
# ---------------------------------------------------------------------------


class TestScoreRound:
    def _setup(self, db: Session, earnings_a: float, earnings_b: float, multiplier: float = 1.0):
        """Build minimal playoff state for a 2-player pod with 1 pick each."""
        manager = _make_user(db, "mgr_score@test.com")
        league, season = _make_league(db, manager)

        player_a = _make_user(db, "pa_score@test.com")
        player_b = _make_user(db, "pb_score@test.com")
        for u in (player_a, player_b):
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
        db.commit()

        golfer_a = _make_golfer(db, "Golfer A")
        golfer_b = _make_golfer(db, "Golfer B")

        tournament = _make_tournament(db, league, status="completed", multiplier=multiplier)
        # Add golfer entries with earnings
        _make_entry(db, tournament, golfer_a, earnings_usd=earnings_a)
        _make_entry(db, tournament, golfer_b, earnings_usd=earnings_b)

        config = _make_config(db, league, season, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="locked")
        pod = _make_pod(db, round_obj, status="locked")
        member_a = _make_pod_member(db, pod, player_a, seed=1, draft_position=1)
        member_b = _make_pod_member(db, pod, player_b, seed=2, draft_position=2)
        _make_playoff_pick(db, pod, member_a, golfer_a, tournament, draft_slot=1)
        _make_playoff_pick(db, pod, member_b, golfer_b, tournament, draft_slot=2)

        return round_obj, member_a, member_b

    def test_sets_total_points_from_earnings(self, db):
        """score_round writes earnings_usd to points_earned and sums into total_points."""
        round_obj, member_a, member_b = self._setup(db, earnings_a=100_000, earnings_b=50_000)
        score_round(db, _reload_round(db, round_obj.id))

        db.refresh(member_a)
        db.refresh(member_b)
        assert member_a.total_points == pytest.approx(100_000.0)
        assert member_b.total_points == pytest.approx(50_000.0)

    def test_applies_tournament_multiplier(self, db):
        """A 2× multiplier (major) doubles all earned points."""
        round_obj, member_a, member_b = self._setup(
            db, earnings_a=200_000, earnings_b=80_000, multiplier=2.0
        )
        score_round(db, _reload_round(db, round_obj.id))

        db.refresh(member_a)
        db.refresh(member_b)
        assert member_a.total_points == pytest.approx(400_000.0)
        assert member_b.total_points == pytest.approx(160_000.0)

    def test_applies_league_multiplier_override(self, db):
        """League-level multiplier override takes precedence over tournament.multiplier."""
        manager = _make_user(db, "mgr_lmo@test.com")
        league, season = _make_league(db, manager)

        player = _make_user(db, "p_lmo@test.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=player.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        golfer = _make_golfer(db, "Override Golfer")
        start = date.today() - timedelta(days=7)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Major Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status="completed",
        )
        db.add(t)
        db.flush()
        lt = LeagueTournament(
            league_id=league.id, tournament_id=t.id, multiplier=1.5
        )  # league overrides to 1.5x
        db.add(lt)
        db.commit()
        db.refresh(t)

        _make_entry(db, t, golfer, earnings_usd=100_000)
        config = _make_config(db, league, season, picks_per_round=[1])
        round_obj = _make_round(db, config, t, status="locked")
        pod = _make_pod(db, round_obj, status="locked")
        member = _make_pod_member(db, pod, player, seed=1, draft_position=1)
        _make_playoff_pick(db, pod, member, golfer, t, draft_slot=1)

        score_round(db, _reload_round(db, round_obj.id))

        db.refresh(member)
        # Must use 1.5x (league override), not 2.0x (tournament default)
        assert member.total_points == pytest.approx(150_000.0)

    def test_applies_no_pick_penalty_for_missed_slots(self, db):
        """When a member has fewer picks than picks_per_round, the penalty is applied."""
        manager = _make_user(db, "mgr_npp@test.com")
        league, season = _make_league(db, manager)
        # Set the league penalty to a known value for the assertion
        league.no_pick_penalty = -10_000
        db.commit()

        player = _make_user(db, "p_npp@test.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=player.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        golfer = _make_golfer(db, "Solo Golfer")
        tournament = _make_tournament(db, league, status="completed")
        _make_entry(db, tournament, golfer, earnings_usd=50_000)

        # picks_per_round=2 but player only gets 1 pick (one slot is empty)
        config = _make_config(db, league, season, picks_per_round=[2])
        round_obj = _make_round(db, config, tournament, status="locked")
        pod = _make_pod(db, round_obj, status="locked")
        member = _make_pod_member(db, pod, player, seed=1, draft_position=1)
        _make_playoff_pick(db, pod, member, golfer, tournament, draft_slot=1)
        # draft_slot=2 is intentionally missing

        score_round(db, _reload_round(db, round_obj.id))

        db.refresh(member)
        # 50_000 earned + (-10_000) penalty for 1 missed slot
        assert member.total_points == pytest.approx(40_000.0)

    def test_raises_if_round_not_locked(self, db):
        """score_round raises 422 when the round is still in 'drafting' status."""
        from fastapi import HTTPException

        manager = _make_user(db, "mgr_rnl@test.com")
        league, season = _make_league(db, manager)
        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season)
        # Create round in drafting status (not locked)
        round_obj = _make_round(db, config, tournament, status="drafting")
        _make_pod(db, round_obj, status="drafting")

        with pytest.raises(HTTPException) as exc:
            score_round(db, _reload_round(db, round_obj.id))
        assert exc.value.status_code == 422
        assert "locked" in exc.value.detail.lower()

    def test_raises_if_tournament_not_completed(self, db):
        """score_round raises 422 when the tournament is still in progress."""
        from fastapi import HTTPException

        manager = _make_user(db, "mgr_tnc@test.com")
        league, season = _make_league(db, manager)
        tournament = _make_tournament(db, league, status="in_progress")
        config = _make_config(db, league, season)
        round_obj = _make_round(db, config, tournament, status="locked")
        _make_pod(db, round_obj)

        with pytest.raises(HTTPException) as exc:
            score_round(db, _reload_round(db, round_obj.id))
        assert exc.value.status_code == 422
        assert "completed" in exc.value.detail.lower()

    def test_raises_if_earnings_not_published(self, db):
        """score_round aborts with 422 if any assigned pick's golfer has null earnings_usd."""
        from fastapi import HTTPException

        manager = _make_user(db, "mgr_enp@test.com")
        league, season = _make_league(db, manager)
        tournament = _make_tournament(db, league, status="completed")
        golfer = _make_golfer(db)
        # Entry exists but earnings not published yet
        _make_entry(db, tournament, golfer, earnings_usd=None)

        config = _make_config(db, league, season, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="locked")
        pod = _make_pod(db, round_obj, status="locked")
        player = _make_user(db, "p_enp@test.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=player.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()
        member = _make_pod_member(db, pod, player, seed=1, draft_position=1)
        _make_playoff_pick(db, pod, member, golfer, tournament, draft_slot=1)

        with pytest.raises(HTTPException) as exc:
            score_round(db, _reload_round(db, round_obj.id))
        assert exc.value.status_code == 422
        assert "earnings" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# DB tests — advance_bracket
# ---------------------------------------------------------------------------


class TestAdvanceBracket:
    def _setup_scored_pod(self, db, round_obj, user_a, user_b, pts_a, pts_b, bracket_pos=1):
        """Create a pod with two scored members, ready for advance_bracket."""
        pod = _make_pod(db, round_obj, bracket_position=bracket_pos, status="locked")
        ma = _make_pod_member(db, pod, user_a, seed=1, draft_position=1, total_points=pts_a)
        mb = _make_pod_member(db, pod, user_b, seed=2, draft_position=2, total_points=pts_b)
        return pod, ma, mb

    def test_marks_winner_and_eliminates_loser(self, db):
        """The higher-scoring member wins; the lower-scoring is marked is_eliminated."""
        manager = _make_user(db, "mgr_mwel@test.com")
        league, season = _make_league(db, manager)
        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, round_number=1, status="locked")
        # No next round: this is the final round
        player_a = _make_user(db, "pa_mwel@test.com")
        player_b = _make_user(db, "pb_mwel@test.com")
        pod, ma, mb = self._setup_scored_pod(db, round_obj, player_a, player_b, 200_000, 100_000)

        advance_bracket(db, _reload_round(db, round_obj.id))

        db.refresh(pod)
        db.refresh(ma)
        db.refresh(mb)
        assert pod.winner_user_id == player_a.id  # higher score wins
        assert pod.status == "completed"
        assert ma.is_eliminated is False
        assert mb.is_eliminated is True

    def test_seed_based_tiebreaking(self, db):
        """When total_points are equal, the lower seed number (better seed) wins."""
        manager = _make_user(db, "mgr_sbt@test.com")
        league, season = _make_league(db, manager)
        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, round_number=1, status="locked")
        player_a = _make_user(db, "pa_sbt@test.com")  # seed 1
        player_b = _make_user(db, "pb_sbt@test.com")  # seed 2
        pod, ma, mb = self._setup_scored_pod(
            db,
            round_obj,
            player_a,
            player_b,
            75_000,
            75_000,  # exact tie
        )

        advance_bracket(db, _reload_round(db, round_obj.id))

        db.refresh(pod)
        assert pod.winner_user_id == player_a.id  # seed 1 beats seed 2 in a tie

    def test_winner_promoted_to_next_round_pod(self, db):
        """The pod winner is added as a PlayoffPodMember in the next round."""
        manager = _make_user(db, "mgr_wnr@test.com")
        league, season = _make_league(db, manager)
        t1 = _make_tournament(db, league, status="completed", days_ago=14)
        t2 = _make_tournament(db, league, status="scheduled", days_ago=-7)
        config = _make_config(db, league, season, picks_per_round=[1])
        r1 = _make_round(db, config, t1, round_number=1, status="locked")
        r2 = _make_round(db, config, t2, round_number=2, status="pending")
        player_a = _make_user(db, "pa_wnr@test.com")
        player_b = _make_user(db, "pb_wnr@test.com")
        self._setup_scored_pod(db, r1, player_a, player_b, 200_000, 50_000)

        advance_bracket(db, _reload_round(db, r1.id))

        # Verify winner appears in round 2 pods
        r2_pods = db.query(PlayoffPod).filter_by(playoff_round_id=r2.id).all()
        assert len(r2_pods) >= 1
        next_pod = r2_pods[0]
        members = db.query(PlayoffPodMember).filter_by(pod_id=next_pod.id).all()
        member_user_ids = [m.user_id for m in members]
        assert player_a.id in member_user_ids  # winner promoted
        assert player_b.id not in member_user_ids  # loser stays out

    def test_respects_manual_override_winner(self, db):
        """If pod.winner_user_id is pre-set by manager override, it is not recalculated."""
        manager = _make_user(db, "mgr_rmow@test.com")
        league, season = _make_league(db, manager)
        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, round_number=1, status="locked")
        player_a = _make_user(db, "pa_rmow@test.com")  # lower score
        player_b = _make_user(db, "pb_rmow@test.com")  # higher score
        pod, ma, mb = self._setup_scored_pod(db, round_obj, player_a, player_b, 10_000, 200_000)

        # Manager manually overrides to player_a (lower score) as the winner
        pod.winner_user_id = player_a.id
        db.commit()

        advance_bracket(db, _reload_round(db, round_obj.id))

        db.refresh(pod)
        # Override is respected — player_a wins even with lower score
        assert pod.winner_user_id == player_a.id

    def test_raises_if_round_not_locked(self, db):
        """advance_bracket raises 422 if the round is not in 'locked' status."""
        from fastapi import HTTPException

        manager = _make_user(db, "mgr_rinl@test.com")
        league, season = _make_league(db, manager)
        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season)
        round_obj = _make_round(db, config, tournament, status="drafting")

        with pytest.raises(HTTPException) as exc:
            advance_bracket(db, _reload_round(db, round_obj.id))
        assert exc.value.status_code == 422

    def test_raises_if_member_unscored(self, db):
        """advance_bracket raises 422 if any pod member has total_points=None."""
        from fastapi import HTTPException

        manager = _make_user(db, "mgr_muns@test.com")
        league, season = _make_league(db, manager)
        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="locked")
        player_a = _make_user(db, "pa_muns@test.com")
        player_b = _make_user(db, "pb_muns@test.com")
        pod = _make_pod(db, round_obj, status="locked")
        _make_pod_member(db, pod, player_a, seed=1, draft_position=1, total_points=50_000)
        _make_pod_member(db, pod, player_b, seed=2, draft_position=2, total_points=None)  # unscored

        with pytest.raises(HTTPException) as exc:
            advance_bracket(db, _reload_round(db, round_obj.id))
        assert exc.value.status_code == 422
        assert "unscored" in exc.value.detail.lower()

    def test_eliminated_member_cannot_win(self, db):
        """is_eliminated=True members are never selected as winners."""
        manager = _make_user(db, "mgr_emcw@test.com")
        league, season = _make_league(db, manager)
        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season)
        round_obj = _make_round(db, config, tournament, status="locked")
        player_a = _make_user(db, "pa_emcw@test.com")
        player_b = _make_user(db, "pb_emcw@test.com")
        pod = _make_pod(db, round_obj, status="locked")
        # player_a has more points but is eliminated (vacated slot)
        _make_pod_member(
            db, pod, player_a, seed=1, draft_position=1, total_points=999_999, is_eliminated=True
        )
        _make_pod_member(db, pod, player_b, seed=2, draft_position=2, total_points=1_000)

        advance_bracket(db, _reload_round(db, round_obj.id))

        db.refresh(pod)
        assert pod.winner_user_id == player_b.id  # lower score wins because player_a is eliminated


# ---------------------------------------------------------------------------
# DB tests — resolve_draft
# ---------------------------------------------------------------------------


class TestResolveDraft:
    def test_converts_preferences_to_picks_in_snake_draft_order(self, db):
        """
        With snake draft, player at draft_position=1 picks first.
        Both players submit preferences; the resolution should honour order.
        """
        manager = _make_user(db, "mgr_res@test.com")
        league, season = _make_league(db, manager)
        player_a = _make_user(db, "pa_res@test.com")
        player_b = _make_user(db, "pb_res@test.com")
        for u in (player_a, player_b):
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
        db.commit()

        golfer_1 = _make_golfer(db, "Top Choice")
        golfer_2 = _make_golfer(db, "Second Choice")
        golfer_3 = _make_golfer(db, "Third Choice")
        golfer_4 = _make_golfer(db, "Fourth Choice")

        tournament = _make_tournament(db, league, status="in_progress")
        # Add golfers to tournament field
        for g in (golfer_1, golfer_2, golfer_3, golfer_4):
            _make_entry(db, tournament, g, earnings_usd=None)

        # picks_per_round=2: snake order for 2 players = [1,2,2,1]
        # Slot 1 → draft_position 1 (player_a), Slot 2 → draft_position 2 (player_b),
        # Slot 3 → draft_position 2 (player_b), Slot 4 → draft_position 1 (player_a)
        config = _make_config(db, league, season, draft_style="snake", picks_per_round=[2])
        round_obj = _make_round(db, config, tournament, status="drafting")
        pod = _make_pod(db, round_obj, status="drafting")
        ma = _make_pod_member(db, pod, player_a, seed=1, draft_position=1)
        mb = _make_pod_member(db, pod, player_b, seed=2, draft_position=2)

        # Both rank all 4 golfers (2 players × 2 picks = 4 preferences required)
        for rank, g in enumerate([golfer_1, golfer_2, golfer_3, golfer_4], start=1):
            _make_preference(db, pod, ma, g, rank)
        # player_b prefers golfer_1 first, but it will be claimed by player_a
        for rank, g in enumerate([golfer_1, golfer_2, golfer_3, golfer_4], start=1):
            _make_preference(db, pod, mb, g, rank)

        resolve_draft(db, _reload_round(db, round_obj.id))

        picks = db.query(PlayoffPick).filter_by(pod_id=pod.id).all()
        assert len(picks) == 4

        # player_a (slot 1) claims golfer_1 first
        # player_b (slot 2) gets golfer_2 (golfer_1 claimed)
        # player_b (slot 3) gets golfer_3
        # player_a (slot 4) gets golfer_4
        a_picks = [p.golfer_id for p in picks if p.pod_member_id == ma.id]
        b_picks = [p.golfer_id for p in picks if p.pod_member_id == mb.id]
        assert golfer_1.id in a_picks  # player_a gets top choice
        assert golfer_1.id not in b_picks  # player_b cannot have it
        assert golfer_2.id in b_picks  # player_b's first available choice

    def test_member_with_no_preferences_gets_no_picks(self, db):
        """A player who did not submit preferences receives zero picks."""
        manager = _make_user(db, "mgr_nop@test.com")
        league, season = _make_league(db, manager)
        player_a = _make_user(db, "pa_nop@test.com")
        player_b = _make_user(db, "pb_nop@test.com")
        for u in (player_a, player_b):
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
        db.commit()

        golfer_1 = _make_golfer(db, "Only Choice")
        golfer_2 = _make_golfer(db, "Backup Choice")

        tournament = _make_tournament(db, league, status="in_progress")
        _make_entry(db, tournament, golfer_1)
        _make_entry(db, tournament, golfer_2)

        config = _make_config(db, league, season, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="drafting")
        pod = _make_pod(db, round_obj, status="drafting")
        ma = _make_pod_member(db, pod, player_a, seed=1, draft_position=1)
        mb = _make_pod_member(db, pod, player_b, seed=2, draft_position=2)

        # Only player_a submits preferences
        _make_preference(db, pod, ma, golfer_1, rank=1)
        _make_preference(db, pod, ma, golfer_2, rank=2)
        # player_b submits nothing

        resolve_draft(db, _reload_round(db, round_obj.id))

        a_picks = db.query(PlayoffPick).filter_by(pod_id=pod.id, pod_member_id=ma.id).all()
        b_picks = db.query(PlayoffPick).filter_by(pod_id=pod.id, pod_member_id=mb.id).all()
        assert len(a_picks) == 1
        assert len(b_picks) == 0  # no preferences → no picks

    def test_skips_golfers_not_in_tournament_field(self, db):
        """Non-field golfers in a preference list are silently skipped."""
        manager = _make_user(db, "mgr_skip@test.com")
        league, season = _make_league(db, manager)
        player = _make_user(db, "p_skip@test.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=player.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        field_golfer = _make_golfer(db, "In the Field")
        non_field_golfer = _make_golfer(db, "Not Playing")

        tournament = _make_tournament(db, league, status="in_progress")
        _make_entry(db, tournament, field_golfer)  # only this golfer is in the field

        config = _make_config(db, league, season, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="drafting")
        pod = _make_pod(db, round_obj, status="drafting")
        member = _make_pod_member(db, pod, player, seed=1, draft_position=1)

        # Player ranks the non-field golfer first, field golfer second
        _make_preference(db, pod, member, non_field_golfer, rank=1)
        _make_preference(db, pod, member, field_golfer, rank=2)

        resolve_draft(db, _reload_round(db, round_obj.id))

        picks = db.query(PlayoffPick).filter_by(pod_id=pod.id).all()
        assert len(picks) == 1
        assert picks[0].golfer_id == field_golfer.id  # skipped non-field; fell through to #2

    def test_idempotent_if_round_already_locked(self, db):
        """resolve_draft silently returns if the round is already locked (idempotent)."""
        manager = _make_user(db, "mgr_rnrd@test.com")
        league, season = _make_league(db, manager)
        tournament = _make_tournament(db, league, status="in_progress")
        config = _make_config(db, league, season)
        round_obj = _make_round(db, config, tournament, status="locked")

        # Should return without raising — safe for SQS at-least-once delivery
        resolve_draft(db, _reload_round(db, round_obj.id))

    def test_raises_if_round_in_pending_status(self, db):
        """resolve_draft raises 422 if the round is in 'pending' status."""
        from fastapi import HTTPException

        manager = _make_user(db, "mgr_pend@test.com")
        league, season = _make_league(db, manager)
        tournament = _make_tournament(db, league, status="in_progress")
        config = _make_config(db, league, season)
        round_obj = _make_round(db, config, tournament, status="pending")

        with pytest.raises(HTTPException) as exc:
            resolve_draft(db, _reload_round(db, round_obj.id))
        assert exc.value.status_code == 422

    def test_raises_if_window_not_yet_closed(self, db):
        """resolve_draft raises 422 if the tournament is still scheduled (window open)."""
        from fastapi import HTTPException

        manager = _make_user(db, "mgr_rwnyc@test.com")
        league, season = _make_league(db, manager)
        # Tournament is still scheduled — preference window is open
        tournament = _make_tournament(db, league, status="scheduled", days_ago=-7)
        config = _make_config(db, league, season)
        round_obj = _make_round(db, config, tournament, status="drafting")

        with pytest.raises(HTTPException) as exc:
            resolve_draft(db, _reload_round(db, round_obj.id))
        assert exc.value.status_code == 422
        assert "window" in exc.value.detail.lower() or "open" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# DB tests — override_result
# ---------------------------------------------------------------------------


class TestOverrideResult:
    def _setup_locked_pod(self, db, suffix=""):
        """Build a locked pod with 2 scored members."""
        manager = _make_user(db, f"mgr_ovr{suffix}@test.com")
        league, season = _make_league(db, manager)
        player_a = _make_user(db, f"pa_ovr{suffix}@test.com")
        player_b = _make_user(db, f"pb_ovr{suffix}@test.com")
        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="locked")
        pod = _make_pod(db, round_obj, status="locked")
        ma = _make_pod_member(db, pod, player_a, seed=1, draft_position=1, total_points=100_000)
        mb = _make_pod_member(db, pod, player_b, seed=2, draft_position=2, total_points=200_000)
        return pod, player_a, player_b, ma, mb

    def test_sets_winner_and_marks_others_eliminated(self, db):
        """Manager can override winner; non-winners are marked is_eliminated=True."""
        pod, player_a, player_b, ma, mb = self._setup_locked_pod(db, suffix="sw")
        # Override to player_a even though player_b scored higher
        override_result(db, _reload_pod(db, pod.id), player_a.id)

        db.refresh(pod)
        db.refresh(ma)
        db.refresh(mb)
        assert pod.winner_user_id == player_a.id
        assert ma.is_eliminated is False
        assert mb.is_eliminated is True

    def test_raises_if_tournament_not_completed(self, db):
        """override_result raises 422 when the tournament is still in_progress."""
        from fastapi import HTTPException

        manager = _make_user(db, "mgr_otnc@test.com")
        league, season = _make_league(db, manager)
        player = _make_user(db, "p_otnc@test.com")
        tournament = _make_tournament(db, league, status="in_progress")
        config = _make_config(db, league, season, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="locked")
        pod = _make_pod(db, round_obj)
        _make_pod_member(db, pod, player, seed=1, draft_position=1, total_points=0)

        with pytest.raises(HTTPException) as exc:
            override_result(db, _reload_pod(db, pod.id), player.id)
        assert exc.value.status_code == 422

    def test_raises_if_round_already_advanced(self, db):
        """override_result raises 422 once the bracket is advanced (round completed)."""
        from fastapi import HTTPException

        manager = _make_user(db, "mgr_oraa@test.com")
        league, season = _make_league(db, manager)
        player = _make_user(db, "p_oraa@test.com")
        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="completed")  # already advanced
        pod = _make_pod(db, round_obj)
        _make_pod_member(db, pod, player, seed=1, draft_position=1, total_points=0)

        with pytest.raises(HTTPException) as exc:
            override_result(db, _reload_pod(db, pod.id), player.id)
        assert exc.value.status_code == 422

    def test_raises_if_winner_not_in_pod(self, db):
        """override_result raises 422 if the specified winner is not a pod member."""
        from fastapi import HTTPException

        pod, player_a, player_b, _, _ = self._setup_locked_pod(db, suffix="wnp")
        outsider = _make_user(db, "outsider_wnp@test.com")

        with pytest.raises(HTTPException) as exc:
            override_result(db, _reload_pod(db, pod.id), outsider.id)
        assert exc.value.status_code == 422
        assert "not a member" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# Edge case tests: seed_playoff, tied scoring, departed members
# ---------------------------------------------------------------------------


class TestSeedPlayoffEdgeCases:
    """Tests for seed_playoff with exact member counts and boundary conditions."""

    def test_seed_with_exactly_playoff_size_members(self, db):
        """seed_playoff succeeds when member count == playoff_size (no extras)."""
        from app.services.playoff import seed_playoff

        manager = _make_user(db, "seed_mgr@test.com")
        league, season = _make_league(db, manager)

        # Add exactly 3 more members (4 total including manager)
        members = [manager]
        for i in range(3):
            u = _make_user(db, f"seed_p{i}@test.com")
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
            members.append(u)
        db.commit()

        # Create a completed tournament so standings have data
        completed_t = _make_tournament(db, league, status="completed", days_ago=14)
        for i, m in enumerate(members):
            g = _make_golfer(db, f"SeedGolfer{i}")
            _make_entry(db, completed_t, g, earnings_usd=(i + 1) * 100_000)
            from app.models import Pick

            db.add(
                Pick(
                    league_id=league.id,
                    season_id=season.id,
                    user_id=m.id,
                    tournament_id=completed_t.id,
                    golfer_id=g.id,
                    points_earned=(i + 1) * 100_000,
                )
            )
        db.commit()

        # 4-player bracket = log2(4) = 2 rounds, needs 2 scheduled tournaments
        _make_tournament(db, league, status="scheduled", days_ago=-7)
        _make_tournament(db, league, status="scheduled", days_ago=-14)

        config = _make_config(db, league, season, playoff_size=4, picks_per_round=[1, 1])

        seed_playoff(db, config)

        db.refresh(config)
        assert config.status == "active"
        assert config.seeded_at is not None

        rounds = db.query(PlayoffRound).filter_by(playoff_config_id=config.id).all()
        assert len(rounds) == 2
        assert rounds[0].status == "drafting"  # round 1 opens immediately

        # All 4 members should be assigned to pods
        r1_pods = db.query(PlayoffPod).filter_by(playoff_round_id=rounds[0].id).all()
        total_members = sum(
            db.query(PlayoffPodMember).filter_by(pod_id=p.id).count() for p in r1_pods
        )
        assert total_members == 4

    def test_seed_fails_with_fewer_members_than_playoff_size(self, db):
        """seed_playoff raises 422 when not enough members for the bracket."""
        from fastapi import HTTPException

        from app.services.playoff import seed_playoff

        manager = _make_user(db, "seedfail_mgr@test.com")
        league, season = _make_league(db, manager)
        # Only 1 member (the manager) — need 4

        _make_tournament(db, league, status="scheduled", days_ago=-7)
        _make_tournament(db, league, status="scheduled", days_ago=-14)
        config = _make_config(db, league, season, playoff_size=4, picks_per_round=[1, 1])

        with pytest.raises(HTTPException) as exc:
            seed_playoff(db, config)
        assert exc.value.status_code == 422
        assert "not enough members" in exc.value.detail.lower()

    def test_seed_fails_with_insufficient_scheduled_tournaments(self, db):
        """seed_playoff raises 422 when not enough future tournaments for rounds."""
        from fastapi import HTTPException

        from app.services.playoff import seed_playoff

        manager = _make_user(db, "seedt_mgr@test.com")
        league, season = _make_league(db, manager)
        for i in range(3):
            u = _make_user(db, f"seedt_p{i}@test.com")
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
        db.commit()

        # Only 1 scheduled tournament but need 2 for a 4-player bracket
        _make_tournament(db, league, status="scheduled", days_ago=-7)
        config = _make_config(db, league, season, playoff_size=4, picks_per_round=[1, 1])

        with pytest.raises(HTTPException) as exc:
            seed_playoff(db, config)
        assert exc.value.status_code == 422
        assert "future tournament" in exc.value.detail.lower()


class TestTiedScoresInAdvanceBracket:
    """Tests that tied scores in advance_bracket use seed as tiebreaker."""

    def test_tied_points_broken_by_lower_seed(self, db):
        """When two members have identical total_points, lower seed wins."""
        manager = _make_user(db, "tie_mgr@test.com")
        league, season = _make_league(db, manager)
        player_a = _make_user(db, "tie_pa@test.com")
        player_b = _make_user(db, "tie_pb@test.com")
        for u in [player_a, player_b]:
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
        db.commit()

        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season, playoff_size=2, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="locked")
        pod = _make_pod(db, round_obj, bracket_position=1, status="locked")

        # Both have identical points — seed 1 should win
        _make_pod_member(db, pod, player_a, seed=1, draft_position=1, total_points=500_000)
        _make_pod_member(db, pod, player_b, seed=2, draft_position=2, total_points=500_000)

        advance_bracket(db, _reload_round(db, round_obj.id))

        refreshed_pod = _reload_pod(db, pod.id)
        assert refreshed_pod.winner_user_id == player_a.id
        assert refreshed_pod.status == "completed"

        # Verify loser is eliminated
        loser = next(m for m in refreshed_pod.members if m.user_id == player_b.id)
        assert loser.is_eliminated is True

    def test_higher_seed_loses_when_outscored(self, db):
        """Higher seed loses despite seed advantage when opponent scores more."""
        manager = _make_user(db, "hsl_mgr@test.com")
        league, season = _make_league(db, manager)
        player_a = _make_user(db, "hsl_pa@test.com")
        player_b = _make_user(db, "hsl_pb@test.com")
        for u in [player_a, player_b]:
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
        db.commit()

        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season, playoff_size=2, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="locked")
        pod = _make_pod(db, round_obj, bracket_position=1, status="locked")

        # Seed 1 has FEWER points — seed 2 should win
        _make_pod_member(db, pod, player_a, seed=1, draft_position=1, total_points=200_000)
        _make_pod_member(db, pod, player_b, seed=2, draft_position=2, total_points=800_000)

        advance_bracket(db, _reload_round(db, round_obj.id))

        refreshed_pod = _reload_pod(db, pod.id)
        assert refreshed_pod.winner_user_id == player_b.id


class TestDepartedMemberInPlayoff:
    """Tests for advance_bracket when a member has departed (is_eliminated=True pre-scoring)."""

    def test_departed_member_loses_automatically(self, db):
        """A departed (pre-eliminated) member can never win, even with higher points."""
        manager = _make_user(db, "dep_mgr@test.com")
        league, season = _make_league(db, manager)
        player_a = _make_user(db, "dep_pa@test.com")
        player_b = _make_user(db, "dep_pb@test.com")
        for u in [player_a, player_b]:
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
        db.commit()

        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season, playoff_size=2, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="locked")
        pod = _make_pod(db, round_obj, bracket_position=1, status="locked")

        # Player A departed (is_eliminated=True) but has higher points
        _make_pod_member(
            db,
            pod,
            player_a,
            seed=1,
            draft_position=1,
            total_points=1_000_000,
            is_eliminated=True,
        )
        _make_pod_member(db, pod, player_b, seed=2, draft_position=2, total_points=100_000)

        advance_bracket(db, _reload_round(db, round_obj.id))

        refreshed_pod = _reload_pod(db, pod.id)
        assert refreshed_pod.winner_user_id == player_b.id

    def test_advance_with_bye_slot(self, db):
        """In a 4-player bracket, if one member departs from a pod, the remaining
        member wins their pod automatically and advances to the next round."""
        manager = _make_user(db, "bye_mgr@test.com")
        league, season = _make_league(db, manager)
        players = []
        for i in range(4):
            u = _make_user(db, f"bye_p{i}@test.com")
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
            players.append(u)
        db.commit()

        t1 = _make_tournament(db, league, status="completed", days_ago=7)
        t2 = _make_tournament(db, league, status="scheduled", days_ago=-7)
        config = _make_config(db, league, season, playoff_size=4, picks_per_round=[1, 1])

        # Round 1 with 2 pods
        round1 = _make_round(db, config, t1, round_number=1, status="locked")
        _make_round(db, config, t2, round_number=2, status="pending")

        # Pod 1: normal matchup
        pod1 = _make_pod(db, round1, bracket_position=1, status="locked")
        _make_pod_member(db, pod1, players[0], seed=1, draft_position=1, total_points=300_000)
        _make_pod_member(db, pod1, players[3], seed=4, draft_position=2, total_points=100_000)

        # Pod 2: one member departed (bye)
        pod2 = _make_pod(db, round1, bracket_position=2, status="locked")
        _make_pod_member(
            db,
            pod2,
            players[1],
            seed=2,
            draft_position=1,
            total_points=0,
            is_eliminated=True,  # departed
        )
        _make_pod_member(db, pod2, players[2], seed=3, draft_position=2, total_points=200_000)

        advance_bracket(db, _reload_round(db, round1.id))

        # Pod 1 winner = seed 1 (more points)
        refreshed_pod1 = _reload_pod(db, pod1.id)
        assert refreshed_pod1.winner_user_id == players[0].id

        # Pod 2 winner = seed 3 (only eligible member)
        refreshed_pod2 = _reload_pod(db, pod2.id)
        assert refreshed_pod2.winner_user_id == players[2].id

        # Both winners should be in the next round's pod
        round2 = (
            db.query(PlayoffRound).filter_by(playoff_config_id=config.id, round_number=2).first()
        )
        next_pod = db.query(PlayoffPod).filter_by(playoff_round_id=round2.id).first()
        next_members = db.query(PlayoffPodMember).filter_by(pod_id=next_pod.id).all()
        next_user_ids = {m.user_id for m in next_members}
        assert players[0].id in next_user_ids
        assert players[2].id in next_user_ids
        assert len(next_members) == 2


# ---------------------------------------------------------------------------
# Additional edge case coverage
# ---------------------------------------------------------------------------


class TestAssignPod32Player:
    """Tests for assign_pod() — pods-of-4 bracket seeding for 32-player brackets."""

    def test_32_player_bracket_8_pods(self):
        """32 seeds assigned to 8 pods of 4 using tier-based seeding."""
        num_pods = 8  # 32 players / 4 per pod
        assignments: dict[int, list[int]] = {}
        for seed in range(1, 33):
            bp = assign_pod(seed, num_pods)
            assignments.setdefault(bp, []).append(seed)

        # Every pod should have exactly 4 members
        for bp in range(1, 9):
            assert len(assignments[bp]) == 4, f"Pod {bp} has {len(assignments[bp])} members"

        # Top seed (1) and bottom seed (32) should be in the same pod (bracket fairness)
        pod_of_seed_1 = assign_pod(1, num_pods)
        pod_of_seed_32 = assign_pod(32, num_pods)
        assert pod_of_seed_1 == pod_of_seed_32

        # Seeds 1 and 2 should NOT be in the same pod (top seeds spread out)
        assert assign_pod(1, num_pods) != assign_pod(2, num_pods)

    def test_all_seeds_assigned_to_valid_pods(self):
        """Every seed maps to a pod between 1 and num_pods inclusive."""
        num_pods = 8
        for seed in range(1, 33):
            bp = assign_pod(seed, num_pods)
            assert 1 <= bp <= num_pods, f"Seed {seed} assigned to invalid pod {bp}"


class TestThreeAndFourWayTies:
    """Tests for _determine_pod_winner with multi-way ties in pods of 4."""

    def test_four_way_tie_broken_by_lowest_seed(self, db):
        """In a 4-person pod where all members tie, lowest seed wins."""
        manager = _make_user(db, "4tie_mgr@test.com")
        league, season = _make_league(db, manager)
        players = []
        for i in range(4):
            u = _make_user(db, f"4tie_p{i}@test.com")
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
            players.append(u)
        db.commit()

        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season, playoff_size=4, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="locked")
        pod = _make_pod(db, round_obj, bracket_position=1, status="locked")

        # All 4 members have identical points
        for i, p in enumerate(players):
            _make_pod_member(db, pod, p, seed=i + 1, draft_position=i + 1, total_points=250_000)

        advance_bracket(db, _reload_round(db, round_obj.id))

        refreshed_pod = _reload_pod(db, pod.id)
        # Seed 1 wins the 4-way tie
        assert refreshed_pod.winner_user_id == players[0].id
        # All others eliminated
        for m in refreshed_pod.members:
            if m.user_id != players[0].id:
                assert m.is_eliminated is True

    def test_three_way_tie_in_four_person_pod(self, db):
        """In a 4-person pod, 3 members tie but one has more points — the one
        with more points wins regardless of seed."""
        manager = _make_user(db, "3tie_mgr@test.com")
        league, season = _make_league(db, manager)
        players = []
        for i in range(4):
            u = _make_user(db, f"3tie_p{i}@test.com")
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
            players.append(u)
        db.commit()

        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season, playoff_size=4, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="locked")
        pod = _make_pod(db, round_obj, bracket_position=1, status="locked")

        # Seeds 1, 2, 3 tie at 200k; seed 4 has 500k
        _make_pod_member(db, pod, players[0], seed=1, draft_position=1, total_points=200_000)
        _make_pod_member(db, pod, players[1], seed=2, draft_position=2, total_points=200_000)
        _make_pod_member(db, pod, players[2], seed=3, draft_position=3, total_points=200_000)
        _make_pod_member(db, pod, players[3], seed=4, draft_position=4, total_points=500_000)

        advance_bracket(db, _reload_round(db, round_obj.id))

        refreshed_pod = _reload_pod(db, pod.id)
        # Seed 4 wins despite worst seed — they have the most points
        assert refreshed_pod.winner_user_id == players[3].id


class TestFinalChampionshipRound:
    """Tests for advance_bracket on the final round (no next round)."""

    def test_final_round_completes_without_promotion(self, db):
        """The championship round (last round) completes, sets winner,
        but does not create any next-round pods."""
        manager = _make_user(db, "fin_mgr@test.com")
        league, season = _make_league(db, manager)
        player_a = _make_user(db, "fin_pa@test.com")
        player_b = _make_user(db, "fin_pb@test.com")
        for u in [player_a, player_b]:
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
        db.commit()

        tournament = _make_tournament(db, league, status="completed")
        config = _make_config(db, league, season, playoff_size=2, picks_per_round=[1])
        # Only one round — this IS the final
        round_obj = _make_round(db, config, tournament, round_number=1, status="locked")
        pod = _make_pod(db, round_obj, bracket_position=1, status="locked")
        _make_pod_member(db, pod, player_a, seed=1, draft_position=1, total_points=600_000)
        _make_pod_member(db, pod, player_b, seed=2, draft_position=2, total_points=300_000)

        advance_bracket(db, _reload_round(db, round_obj.id))

        refreshed_round = _reload_round(db, round_obj.id)
        assert refreshed_round.status == "completed"

        refreshed_pod = _reload_pod(db, pod.id)
        assert refreshed_pod.winner_user_id == player_a.id
        assert refreshed_pod.status == "completed"

        # No round 2 should exist
        next_round = (
            db.query(PlayoffRound).filter_by(playoff_config_id=config.id, round_number=2).first()
        )
        assert next_round is None

        # No pods created for a non-existent next round
        all_pods = db.query(PlayoffPod).filter_by(playoff_round_id=round_obj.id).all()
        assert len(all_pods) == 1  # only the original pod


class TestResolveDraftIdempotency:
    """Tests that resolve_draft is safe to call multiple times."""

    def test_second_call_is_noop(self, db):
        """Calling resolve_draft twice on the same round does not duplicate picks."""
        from app.models import TournamentEntry as TE

        manager = _make_user(db, "idem_mgr@test.com")
        league, season = _make_league(db, manager)
        player_a = _make_user(db, "idem_pa@test.com")
        player_b = _make_user(db, "idem_pb@test.com")
        for u in [player_a, player_b]:
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
        db.commit()

        tournament = _make_tournament(db, league, status="in_progress")
        golfer_a = _make_golfer(db, "IdemGolferA")
        golfer_b = _make_golfer(db, "IdemGolferB")
        # Create field entries so golfers are in the tournament
        db.add(TE(tournament_id=tournament.id, golfer_id=golfer_a.id))
        db.add(TE(tournament_id=tournament.id, golfer_id=golfer_b.id))
        # Add a tee time in the past so the window is closed
        from datetime import datetime

        db.add(
            TournamentEntry(
                tournament_id=tournament.id,
                golfer_id=_make_golfer(db, "TeeTimeGolfer").id,
                tee_time=datetime(2020, 1, 1, tzinfo=UTC),
            )
        )
        db.commit()

        config = _make_config(db, league, season, playoff_size=2, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="drafting")
        pod = _make_pod(db, round_obj, bracket_position=1, status="drafting")
        mem_a = _make_pod_member(db, pod, player_a, seed=1, draft_position=1)
        mem_b = _make_pod_member(db, pod, player_b, seed=2, draft_position=2)

        # Submit preferences
        _make_preference(db, pod, mem_a, golfer_a, rank=1)
        _make_preference(db, pod, mem_b, golfer_b, rank=1)

        # First call — creates picks and locks the round
        resolve_draft(db, _reload_round(db, round_obj.id))

        pick_count_after_first = db.query(PlayoffPick).filter_by(pod_id=pod.id).count()
        assert pick_count_after_first == 2

        refreshed = _reload_round(db, round_obj.id)
        assert refreshed.status == "locked"

        # Second call — should be a silent no-op
        resolve_draft(db, _reload_round(db, round_obj.id))

        pick_count_after_second = db.query(PlayoffPick).filter_by(pod_id=pod.id).count()
        assert pick_count_after_second == 2  # no duplicates


class TestPickedGolferMissingFromField:
    """Tests for score_round when a picked golfer has no TournamentEntry."""

    def test_missing_entry_scores_as_zero(self, db):
        """A playoff pick for a golfer with no TournamentEntry scores as 0 points."""
        manager = _make_user(db, "mf_mgr@test.com")
        league, season = _make_league(db, manager)
        player_a = _make_user(db, "mf_pa@test.com")
        player_b = _make_user(db, "mf_pb@test.com")
        for u in [player_a, player_b]:
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
        db.commit()

        tournament = _make_tournament(db, league, status="completed")
        golfer_a = _make_golfer(db, "FieldGolfer")
        golfer_b = _make_golfer(db, "MissingGolfer")  # no TournamentEntry created

        # Only golfer_a has an entry
        _make_entry(db, tournament, golfer_a, earnings_usd=500_000)

        config = _make_config(db, league, season, playoff_size=2, picks_per_round=[1])
        round_obj = _make_round(db, config, tournament, status="locked")
        pod = _make_pod(db, round_obj, bracket_position=1, status="locked")
        mem_a = _make_pod_member(db, pod, player_a, seed=1, draft_position=1)
        mem_b = _make_pod_member(db, pod, player_b, seed=2, draft_position=2)

        # Player A picked a golfer in the field; Player B picked one NOT in the field
        _make_playoff_pick(db, pod, mem_a, golfer_a, tournament, draft_slot=1)
        _make_playoff_pick(db, pod, mem_b, golfer_b, tournament, draft_slot=1)

        score_round(db, _reload_round(db, round_obj.id))

        db.refresh(mem_a)
        db.refresh(mem_b)
        # Player A: 500k earnings * 1.0 multiplier = 500k
        assert mem_a.total_points == 500_000.0
        # Player B: golfer not in field → 0 earnings, scores as 0
        assert mem_b.total_points == 0.0


# ---------------------------------------------------------------------------
# Team event handling in playoffs
# ---------------------------------------------------------------------------


class TestTeamEventDraft:
    """resolve_draft correctly handles team events — claiming both partners."""

    def test_team_event_claims_both_partners(self, db):
        """When Member A picks Golfer X from Team X/Y, Member B cannot pick
        Golfer Y — the entire team is claimed as a unit."""
        manager = _make_user(db, "mgr_team@test.com", "Manager")
        league, season = _make_league(db, manager)
        t = _make_tournament(db, league, status="in_progress", days_ago=0, is_team_event=True)

        # Two teams: Team1 = (gA, gB), Team2 = (gC, gD)
        gA = _make_golfer(db, "Golfer A")
        gB = _make_golfer(db, "Golfer B")
        gC = _make_golfer(db, "Golfer C")
        gD = _make_golfer(db, "Golfer D")
        _make_entry(db, t, gA, team_competitor_id="team1")
        _make_entry(db, t, gB, team_competitor_id="team1")
        _make_entry(db, t, gC, team_competitor_id="team2")
        _make_entry(db, t, gD, team_competitor_id="team2")

        config = _make_config(db, league, season, playoff_size=2, picks_per_round=[1])
        round_obj = _make_round(db, config, t, status="drafting")
        pod = _make_pod(db, round_obj, status="drafting")

        u1 = _make_user(db, "u1_team@test.com", "U1")
        u2 = _make_user(db, "u2_team@test.com", "U2")
        m1 = _make_pod_member(db, pod, u1, seed=1, draft_position=1)
        m2 = _make_pod_member(db, pod, u2, seed=2, draft_position=2)

        # U1 prefers gA (Team1), U2 prefers gB (Team1 partner) then gC
        _make_preference(db, pod, m1, gA, rank=1)
        _make_preference(db, pod, m2, gB, rank=1)  # partner of gA
        _make_preference(db, pod, m2, gC, rank=2)  # fallback

        round_obj = _reload_round(db, round_obj.id)
        resolve_draft(db, round_obj)

        picks = db.query(PlayoffPick).filter_by(pod_id=pod.id).all()
        pick_golfer_ids = {p.golfer_id for p in picks}

        # U1 should get gA, U2 should get gC (not gB — partner claimed)
        assert gA.id in pick_golfer_ids
        assert gC.id in pick_golfer_ids
        assert gB.id not in pick_golfer_ids

    def test_team_event_preference_skips_claimed_partner(self, db):
        """Member B's top preference is claimed (as partner). Verify
        fallthrough to their next ranked golfer."""
        manager = _make_user(db, "mgr_skip@test.com", "Manager")
        league, season = _make_league(db, manager)
        t = _make_tournament(db, league, status="in_progress", days_ago=0, is_team_event=True)

        gA = _make_golfer(db, "Golfer A")
        gB = _make_golfer(db, "Golfer B")
        gC = _make_golfer(db, "Golfer C")
        gD = _make_golfer(db, "Golfer D")
        _make_entry(db, t, gA, team_competitor_id="team1")
        _make_entry(db, t, gB, team_competitor_id="team1")
        _make_entry(db, t, gC, team_competitor_id="team2")
        _make_entry(db, t, gD, team_competitor_id="team2")

        config = _make_config(db, league, season, playoff_size=2, picks_per_round=[1])
        round_obj = _make_round(db, config, t, status="drafting")
        pod = _make_pod(db, round_obj, status="drafting")

        u1 = _make_user(db, "u1_skip@test.com", "U1")
        u2 = _make_user(db, "u2_skip@test.com", "U2")
        m1 = _make_pod_member(db, pod, u1, seed=1, draft_position=1)
        m2 = _make_pod_member(db, pod, u2, seed=2, draft_position=2)

        # U1 picks gA, U2 wants gB (partner) then gD
        _make_preference(db, pod, m1, gA, rank=1)
        _make_preference(db, pod, m2, gB, rank=1)
        _make_preference(db, pod, m2, gD, rank=2)

        round_obj = _reload_round(db, round_obj.id)
        resolve_draft(db, round_obj)

        u2_pick = db.query(PlayoffPick).filter_by(pod_id=pod.id, pod_member_id=m2.id).first()
        assert u2_pick is not None
        assert u2_pick.golfer_id == gD.id  # fell through to gD

    def test_non_team_event_allows_both_partners(self, db):
        """Non-team event: two golfers with same team_competitor_id are
        treated independently (no partner claiming)."""
        manager = _make_user(db, "mgr_nteam@test.com", "Manager")
        league, season = _make_league(db, manager)
        t = _make_tournament(db, league, status="in_progress", days_ago=0, is_team_event=False)

        gA = _make_golfer(db, "Golfer A")
        gB = _make_golfer(db, "Golfer B")
        _make_entry(db, t, gA)
        _make_entry(db, t, gB)

        config = _make_config(db, league, season, playoff_size=2, picks_per_round=[1])
        round_obj = _make_round(db, config, t, status="drafting")
        pod = _make_pod(db, round_obj, status="drafting")

        u1 = _make_user(db, "u1_nt@test.com", "U1")
        u2 = _make_user(db, "u2_nt@test.com", "U2")
        m1 = _make_pod_member(db, pod, u1, seed=1, draft_position=1)
        m2 = _make_pod_member(db, pod, u2, seed=2, draft_position=2)

        _make_preference(db, pod, m1, gA, rank=1)
        _make_preference(db, pod, m2, gB, rank=1)

        round_obj = _reload_round(db, round_obj.id)
        resolve_draft(db, round_obj)

        picks = db.query(PlayoffPick).filter_by(pod_id=pod.id).all()
        pick_golfer_ids = {p.golfer_id for p in picks}
        assert gA.id in pick_golfer_ids
        assert gB.id in pick_golfer_ids  # both allowed


class TestTeamEventPreferences:
    """submit_preferences validation for team events."""

    def test_rejects_both_partners_in_team_event(self, db):
        """Submitting both halves of a team in a team event → 422."""
        manager = _make_user(db, "mgr_pref@test.com", "Manager")
        league, season = _make_league(db, manager)
        t = _make_tournament(db, league, status="scheduled", days_ago=-7, is_team_event=True)

        gA = _make_golfer(db, "Golfer A")
        gB = _make_golfer(db, "Golfer B")
        gC = _make_golfer(db, "Golfer C")
        gD = _make_golfer(db, "Golfer D")
        _make_entry(db, t, gA, team_competitor_id="team1")
        _make_entry(db, t, gB, team_competitor_id="team1")
        _make_entry(db, t, gC, team_competitor_id="team2")
        _make_entry(db, t, gD, team_competitor_id="team2")

        config = _make_config(db, league, season, playoff_size=2, picks_per_round=[1])
        round_obj = _make_round(db, config, t, status="drafting")
        pod = _make_pod(db, round_obj, status="drafting")

        u1 = _make_user(db, "u1_pref@test.com", "U1")
        u2 = _make_user(db, "u2_pref@test.com", "U2")
        m1 = _make_pod_member(db, pod, u1, seed=1, draft_position=1)
        _make_pod_member(db, pod, u2, seed=2, draft_position=2)

        # 2-player pod × 1 pick = 2 required. Include both partners of team1.
        with pytest.raises(Exception) as exc_info:
            submit_preferences(db, m1, [gA.id, gB.id], t.id)
        assert exc_info.value.status_code == 422
        assert "team event" in exc_info.value.detail.lower()

    def test_allows_both_golfers_non_team_event(self, db):
        """Non-team event: ranking any two golfers is fine."""
        manager = _make_user(db, "mgr_pref2@test.com", "Manager")
        league, season = _make_league(db, manager)
        t = _make_tournament(db, league, status="scheduled", days_ago=-7, is_team_event=False)

        gA = _make_golfer(db, "Golfer A")
        gB = _make_golfer(db, "Golfer B")
        _make_entry(db, t, gA)
        _make_entry(db, t, gB)

        config = _make_config(db, league, season, playoff_size=2, picks_per_round=[1])
        round_obj = _make_round(db, config, t, status="drafting")
        pod = _make_pod(db, round_obj, status="drafting")

        u1 = _make_user(db, "u1_pref2@test.com", "U1")
        u2 = _make_user(db, "u2_pref2@test.com", "U2")
        m1 = _make_pod_member(db, pod, u1, seed=1, draft_position=1)
        _make_pod_member(db, pod, u2, seed=2, draft_position=2)

        # Should not raise
        prefs = submit_preferences(db, m1, [gA.id, gB.id], t.id)
        assert len(prefs) == 2


class TestTeamEventScoring:
    """score_round uses team earnings correctly for team events."""

    def test_score_round_team_event_uses_team_earnings(self, db):
        """Both partners share the same team earnings. Pick stores one
        golfer_id, scoring uses that entry's earnings_usd."""
        manager = _make_user(db, "mgr_score_te@test.com", "Manager")
        league, season = _make_league(db, manager)
        t = _make_tournament(db, league, status="completed", days_ago=7, is_team_event=True)

        gA = _make_golfer(db, "Golfer A")
        gB = _make_golfer(db, "Golfer B")
        # Both entries share same team earnings (as ESPN reports)
        _make_entry(db, t, gA, earnings_usd=1_000_000, team_competitor_id="team1")
        _make_entry(db, t, gB, earnings_usd=1_000_000, team_competitor_id="team1")

        config = _make_config(db, league, season, playoff_size=2, picks_per_round=[1])
        round_obj = _make_round(db, config, t, status="locked")
        pod = _make_pod(db, round_obj, status="scoring")

        u1 = _make_user(db, "u1_score_te@test.com", "U1")
        m1 = _make_pod_member(db, pod, u1, seed=1, draft_position=1)
        _make_playoff_pick(db, pod, m1, gA, t, draft_slot=1)

        round_obj = _reload_round(db, round_obj.id)
        score_round(db, round_obj)

        pick = db.query(PlayoffPick).filter_by(pod_member_id=m1.id).first()
        assert pick.points_earned == 1_000_000.0

        db.refresh(m1)
        assert m1.total_points == 1_000_000.0


class TestBuildPartnerMap:
    """_build_partner_map utility returns correct mappings."""

    def test_returns_empty_for_non_team_event(self, db):
        manager = _make_user(db, "mgr_pm1@test.com", "Manager")
        league, _ = _make_league(db, manager)
        t = _make_tournament(db, league, is_team_event=False)
        assert _build_partner_map(db, t.id) == {}

    def test_maps_partners_correctly(self, db):
        manager = _make_user(db, "mgr_pm2@test.com", "Manager")
        league, _ = _make_league(db, manager)
        t = _make_tournament(db, league, is_team_event=True)

        gA = _make_golfer(db, "A")
        gB = _make_golfer(db, "B")
        _make_entry(db, t, gA, team_competitor_id="t1")
        _make_entry(db, t, gB, team_competitor_id="t1")

        pmap = _build_partner_map(db, t.id)
        assert pmap[gA.id].golfer_id == gB.id
        assert pmap[gB.id].golfer_id == gA.id
