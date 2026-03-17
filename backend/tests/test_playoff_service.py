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
from datetime import date, timedelta

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
    advance_bracket,
    assign_pod_2,
    generate_draft_order,
    override_result,
    resolve_draft,
    score_round,
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
) -> Tournament:
    start = date.today() - timedelta(days=days_ago)
    t = Tournament(
        pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
        name="Test Open",
        start_date=start,
        end_date=start + timedelta(days=3),
        status=status,
        multiplier=multiplier,
    )
    db.add(t)
    db.flush()
    db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))
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
) -> TournamentEntry:
    entry = TournamentEntry(
        tournament_id=tournament.id, golfer_id=golfer.id, earnings_usd=earnings_usd
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
            multiplier=2.0,  # global says 2x
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

    def test_raises_if_round_not_drafting(self, db):
        """resolve_draft raises 422 if the round is not in 'drafting' status."""
        from fastapi import HTTPException

        manager = _make_user(db, "mgr_rnrd@test.com")
        league, season = _make_league(db, manager)
        tournament = _make_tournament(db, league, status="in_progress")
        config = _make_config(db, league, season)
        round_obj = _make_round(db, config, tournament, status="locked")

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
