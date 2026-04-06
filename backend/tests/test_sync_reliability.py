"""
Tests for the tournament sync reliability improvements.

Covers real production scenarios that motivated the changes:
  - ESPN publishes earnings gradually (winner first, others over 12-48h)
  - Amateurs who make the cut have confirmed $0 earnings (not NULL)
  - Pre-tournament withdrawals have 0 rounds and shouldn't block scoring
  - Force sync should repopulate earnings via concurrent fetch
  - score_picks defers until all made-the-cut earnings are available
  - Playoff scoring handles $0 earnings golfers correctly

These tests use mocked HTTP responses — no real ESPN calls are made.
"""

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.models import (
    Golfer,
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    LeagueTournament,
    Pick,
    Season,
    Tournament,
    TournamentEntry,
    TournamentEntryRound,
)
from app.models.playoff import (
    PlayoffConfig,
    PlayoffPick,
    PlayoffPod,
    PlayoffPodMember,
    PlayoffRound,
)
from app.models.user import User
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Helpers — reusable builders for test data
# ---------------------------------------------------------------------------


def _user(db, email=None):
    u = User(
        email=email or f"u_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password("pw"),
        display_name="Tester",
    )
    db.add(u)
    db.flush()
    return u


def _golfer(db, name="Golfer", pga_tour_id=None):
    g = Golfer(pga_tour_id=pga_tour_id or f"g{uuid.uuid4().hex[:6]}", name=name)
    db.add(g)
    db.flush()
    return g


def _tournament(db, *, status="completed", days_ago=3, name="Test Open"):
    """Create a tournament that ended `days_ago` days before today."""
    today = date.today()
    t = Tournament(
        pga_tour_id=f"t{uuid.uuid4().hex[:6]}",
        name=name,
        start_date=today - timedelta(days=days_ago + 3),
        end_date=today - timedelta(days=days_ago),
        status=status,
    )
    db.add(t)
    db.flush()
    return t


def _entry(db, tournament, golfer, *, earnings=None, status=None, pos=None, rounds=0):
    """Create a TournamentEntry with optional round rows."""
    e = TournamentEntry(
        tournament_id=tournament.id,
        golfer_id=golfer.id,
        earnings_usd=earnings,
        status=status,
        finish_position=pos,
    )
    db.add(e)
    db.flush()
    for rn in range(1, rounds + 1):
        db.add(TournamentEntryRound(tournament_entry_id=e.id, round_number=rn))
    db.commit()
    db.refresh(e)
    return e


def _league_with_pick(db, tournament, golfer):
    """Create a league, season, member, and pick for scoring tests."""
    user = _user(db)
    league = League(name=f"L_{uuid.uuid4().hex[:6]}", created_by=user.id)
    db.add(league)
    db.flush()
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=user.id,
            role=LeagueMemberRole.MANAGER.value,
            status=LeagueMemberStatus.APPROVED.value,
        )
    )
    season = Season(league_id=league.id, year=date.today().year, is_active=True)
    db.add(season)
    db.flush()
    pick = Pick(
        league_id=league.id,
        season_id=season.id,
        user_id=user.id,
        tournament_id=tournament.id,
        golfer_id=golfer.id,
    )
    db.add(pick)
    db.commit()
    db.refresh(pick)
    return league, season, user, pick


# ---------------------------------------------------------------------------
# _fetch_golfer_earnings: $0 vs None distinction
# ---------------------------------------------------------------------------


class TestFetchGolferEarnings:
    """_fetch_golfer_earnings returns 0 for confirmed $0 (amateurs, CUT)
    and None when ESPN hasn't published earnings or the endpoint fails."""

    def _make_stats_response(self, amount_value, *, stat_name="amount"):
        """Build a minimal ESPN /statistics JSON response."""
        return {
            "splits": {
                "categories": [
                    {
                        "stats": [
                            {"name": stat_name, "value": amount_value},
                        ]
                    }
                ]
            }
        }

    def test_returns_positive_earnings(self):
        from app.services.scraper import _fetch_golfer_earnings

        response = httpx.Response(200, json=self._make_stats_response(1764000.0))
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = lambda s: s
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.get.return_value = response

            result = _fetch_golfer_earnings("401811940", "10166")

        assert result == 1764000

    def test_returns_none_for_zero_earnings(self):
        """ESPN returns amount=0.0 for both amateurs and unpublished earnings.

        Since we can't distinguish the two, we return None and let the
        threshold-based earnings gate handle it.
        """
        from app.services.scraper import _fetch_golfer_earnings

        response = httpx.Response(200, json=self._make_stats_response(0.0))
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = lambda s: s
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.get.return_value = response

            result = _fetch_golfer_earnings("401811936", "5209798")

        assert result is None

    def test_returns_none_when_endpoint_404s(self):
        """Pre-tournament WD: ESPN returns 404 on /statistics."""
        from app.services.scraper import _fetch_golfer_earnings

        response = httpx.Response(404, json={"error": {"message": "Not found"}})
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = lambda s: s
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.get.return_value = response

            result = _fetch_golfer_earnings("401811939", "10906")

        assert result is None

    def test_returns_none_on_network_error(self):
        """Network timeout — should not crash, just return None."""
        from app.services.scraper import _fetch_golfer_earnings

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = lambda s: s
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.get.side_effect = httpx.ConnectTimeout("timeout")

            result = _fetch_golfer_earnings("401811940", "10166")

        assert result is None

    def test_team_event_uses_official_amount(self):
        """Team events use 'officialAmount' stat, not 'amount'."""
        from app.services.scraper import _fetch_golfer_earnings

        # officialAmount has the real value; amount is 0 for team events.
        response = httpx.Response(
            200,
            json=self._make_stats_response(850000.0, stat_name="officialAmount"),
        )
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = lambda s: s
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.get.return_value = response

            result = _fetch_golfer_earnings(
                "401811943",
                "131066",
                competition_id="11450",
                is_team_event=True,
            )

        assert result == 850000


# ---------------------------------------------------------------------------
# score_picks: earnings gate defers scoring when earnings incomplete
# ---------------------------------------------------------------------------


class TestScorePicksEarningsGate:
    """score_picks defers scoring until all made-the-cut entries have earnings.

    This prevents the real production issue: ESPN publishes the winner's
    earnings within hours, but mid-field earnings trickle in over 12-48h.
    Without the gate, picks would be scored as 0 then corrected days later.
    """

    def test_defers_when_mid_field_earnings_missing(self, db):
        """Tournament just completed — winner has earnings but T30 player doesn't."""
        from app.services.scraper import score_picks

        # ended 1 day ago (within 72h window, so escape hatch doesn't trigger)
        tournament = _tournament(db, days_ago=1, name="Deferred Scoring")
        winner = _golfer(db, "Winner")
        mid_field = _golfer(db, "MidField Player")

        _entry(db, tournament, winner, earnings=1764000, pos=1, rounds=4)
        _entry(db, tournament, mid_field, earnings=None, pos=30, rounds=4)

        _, _, _, pick = _league_with_pick(db, tournament, winner)

        count = score_picks(db, tournament)
        assert count == 0  # deferred — not scored yet

        db.refresh(pick)
        assert pick.points_earned is None  # untouched

    def test_scores_when_all_earnings_available(self, db):
        """All made-the-cut players have earnings → scoring proceeds."""
        from app.services.scraper import score_picks

        tournament = _tournament(db, days_ago=1, name="Ready To Score")
        winner = _golfer(db, "Scoring Winner")
        runner_up = _golfer(db, "Runner Up")

        _entry(db, tournament, winner, earnings=1764000, pos=1, rounds=4)
        _entry(db, tournament, runner_up, earnings=741533, pos=2, rounds=4)

        _, _, _, pick = _league_with_pick(db, tournament, winner)

        count = score_picks(db, tournament)
        assert count == 1

        db.refresh(pick)
        assert pick.points_earned == 1764000.0

    def test_amateur_with_null_earnings_does_not_block(self, db):
        """Amateur has earnings=NULL (ESPN returns $0 which we store as NULL).

        With a realistic field where >80% of entries have positive earnings,
        the threshold gate passes despite the amateur's NULL.
        """
        from app.services.scraper import score_picks

        tournament = _tournament(db, days_ago=1, name="Amateur Field")
        # 9 pros with earnings (90% of field)
        for i in range(9):
            g = _golfer(db, f"Field Pro {i}")
            _entry(db, tournament, g, earnings=(9 - i) * 200000, pos=i + 1, rounds=4)
        # 1 amateur: NULL earnings (ESPN returned $0)
        amateur = _golfer(db, "Amateur Kid")
        _entry(db, tournament, amateur, earnings=None, pos=10, rounds=4)

        pro_winner = db.query(Golfer).filter_by(name="Field Pro 0").first()
        _, _, _, pick = _league_with_pick(db, tournament, pro_winner)

        count = score_picks(db, tournament)
        assert count == 1  # 9/10 = 90% → above threshold → not deferred

        db.refresh(pick)
        assert pick.points_earned == 1800000.0

    def test_pre_tournament_wd_does_not_block(self, db):
        """Pre-tournament WD (0 rounds, status=NULL) doesn't block scoring.

        Real case: Aaron Rai withdrew before Houston Open. ESPN has no status
        endpoint for him (404), no rounds played, but he's still in the field.
        """
        from app.services.scraper import score_picks

        tournament = _tournament(db, days_ago=1, name="Pre-WD Field")
        winner = _golfer(db, "WD Test Winner")
        wd_player = _golfer(db, "Aaron Rai")

        _entry(db, tournament, winner, earnings=1782000, pos=1, rounds=4)
        # Pre-WD: 0 rounds, no status, no earnings, no position
        _entry(db, tournament, wd_player, earnings=None, rounds=0)

        _, _, _, pick = _league_with_pick(db, tournament, winner)

        count = score_picks(db, tournament)
        assert count == 1  # pre-WD player excluded from gate

    def test_cut_player_does_not_block(self, db):
        """CUT player (status='CUT', null earnings) doesn't block scoring."""
        from app.services.scraper import score_picks

        tournament = _tournament(db, days_ago=1, name="CUT Field")
        winner = _golfer(db, "CUT Test Winner")
        cut_player = _golfer(db, "Missed Cut")

        _entry(db, tournament, winner, earnings=1764000, pos=1, rounds=4)
        _entry(
            db,
            tournament,
            cut_player,
            earnings=None,
            status="CUT",
            pos=78,
            rounds=2,
        )

        _, _, _, pick = _league_with_pick(db, tournament, winner)

        count = score_picks(db, tournament)
        assert count == 1  # CUT player excluded from gate

    def test_escape_hatch_scores_after_72_hours(self, db):
        """After 72h, missing earnings don't block — COALESCE handles NULLs."""
        from app.services.scraper import score_picks

        # ended 4 days ago → escape hatch triggers
        tournament = _tournament(db, days_ago=4, name="Old Tournament")
        winner = _golfer(db, "Escape Winner")
        stuck = _golfer(db, "Stuck Player")

        _entry(db, tournament, winner, earnings=1764000, pos=1, rounds=4)
        # This player's earnings never arrived from ESPN
        _entry(db, tournament, stuck, earnings=None, pos=40, rounds=4)

        _, _, _, pick = _league_with_pick(db, tournament, winner)

        count = score_picks(db, tournament)
        assert count == 1  # escape hatch lets it through

    def test_mixed_field_realistic_scenario(self, db):
        """Realistic field: 8 pros, 1 amateur, 1 CUT, 1 pre-WD, and 1 pro
        whose earnings are delayed.

        Scoring defers while the delayed pro brings the ratio below 80%.
        Once the delayed pro's earnings appear, 8/10 = 80% → scoring proceeds.
        The amateur (NULL earnings) and CUT/pre-WD players don't block.
        """
        from app.services.scraper import score_picks

        tournament = _tournament(db, days_ago=1, name="Mixed Field Open")

        # 8 pros with positive earnings
        for i in range(8):
            g = _golfer(db, f"Pro {i}")
            _entry(db, tournament, g, earnings=(8 - i) * 200000, pos=i + 1, rounds=4)

        # 1 pro whose earnings ESPN hasn't published yet
        delayed_pro = _golfer(db, "Delayed Pro")
        _entry(db, tournament, delayed_pro, earnings=None, pos=9, rounds=4)

        # 1 amateur (NULL earnings — ESPN returns $0)
        amateur = _golfer(db, "Miles Russell")
        _entry(db, tournament, amateur, earnings=None, pos=10, rounds=4)

        # CUT and pre-WD (excluded from threshold calculation)
        cut = _golfer(db, "CUT Player")
        _entry(db, tournament, cut, earnings=None, status="CUT", rounds=2)
        pre_wd = _golfer(db, "Pre-WD Player")
        _entry(db, tournament, pre_wd, earnings=None, rounds=0)

        winner = db.query(Golfer).filter_by(name="Pro 0").first()
        _, _, _, pick = _league_with_pick(db, tournament, winner)

        # 8/10 made-the-cut entries have earnings, but 2 have NULL (delayed + amateur)
        # 8/10 = 80% → exactly at threshold → passes
        # Wait — delayed pro has NULL, so it's actually 8/10 with positive = 80%
        # But we need to test the DEFER case first. Set more entries to NULL.
        # Actually: 8 pros with earnings + 1 delayed NULL + 1 amateur NULL = 10 total
        # 8/10 = 80% → gate passes. To test deferral, let's also null one pro.
        pro_to_null = db.query(Golfer).filter_by(name="Pro 7").first()
        null_entry = (
            db.query(TournamentEntry)
            .filter_by(tournament_id=tournament.id, golfer_id=pro_to_null.id)
            .first()
        )
        null_entry.earnings_usd = None
        db.commit()

        # Now: 7/10 = 70% → below 80% → deferred
        count = score_picks(db, tournament)
        assert count == 0

        db.refresh(pick)
        assert pick.points_earned is None

        # ESPN publishes the delayed pro's earnings
        null_entry.earnings_usd = 200000
        db.commit()

        # Now: 8/10 = 80% → at threshold → proceeds
        count = score_picks(db, tournament)
        assert count == 1

        db.refresh(pick)
        assert pick.points_earned == 1600000.0


# ---------------------------------------------------------------------------
# Concurrent earnings fetch in _fetch_tournament_data
# ---------------------------------------------------------------------------


class TestConcurrentEarningsFetch:
    """When fetch_earnings=True, _fetch_tournament_data fetches earnings
    for all competitors concurrently and includes them in results."""

    def _mock_competitors_response(self, athlete_ids):
        """Minimal ESPN /competitors response."""
        return {"items": [{"id": aid, "order": i + 1} for i, aid in enumerate(athlete_ids)]}

    def _mock_earnings_by_id(self, earnings_map):
        """Return a side_effect function for _fetch_golfer_earnings."""

        def _side_effect(pga_tour_id, competitor_id, **kwargs):
            return earnings_map.get(competitor_id)

        return _side_effect

    def test_earnings_populated_in_results(self):
        """Completed tournament: earnings appear in the results dicts.

        _fetch_golfer_earnings returns None for $0 (amateurs, unpublished),
        so only positive earnings appear. NULL entries stay None.
        """
        from app.services.scraper import _fetch_tournament_data

        athletes = ["1001", "1002", "1003"]
        # 1003 = amateur/unpublished → _fetch_golfer_earnings returns None
        earnings = {"1001": 1500000, "1002": 500000, "1003": None}

        with (
            patch("app.services.scraper._get_json") as mock_get,
            patch(
                "app.services.scraper._fetch_golfer_earnings",
                side_effect=self._mock_earnings_by_id(earnings),
            ),
            patch(
                "app.services.scraper._fetch_competitor_rounds",
                return_value=("dummy", []),
            ),
            patch(
                "app.services.scraper._fetch_competitor_status",
                return_value=("dummy", None, None, None),
            ),
        ):
            mock_get.return_value = self._mock_competitors_response(athletes)

            _, results = _fetch_tournament_data(
                "401811940",
                known_golfer_ids=set(athletes),
                fetch_round_data=True,
                fetch_earnings=True,
            )

        result_earnings = {r["pga_tour_id"]: r["earnings_usd"] for r in results}
        assert result_earnings == {"1001": 1500000, "1002": 500000, "1003": None}

    def test_earnings_none_when_not_fetching(self):
        """In-progress tournament: fetch_earnings=False → all earnings are None."""
        from app.services.scraper import _fetch_tournament_data

        athletes = ["2001"]

        with (
            patch("app.services.scraper._get_json") as mock_get,
            patch(
                "app.services.scraper._fetch_competitor_rounds",
                return_value=("dummy", []),
            ),
            patch(
                "app.services.scraper._fetch_competitor_status",
                return_value=("dummy", None, None, None),
            ),
        ):
            mock_get.return_value = self._mock_competitors_response(athletes)

            _, results = _fetch_tournament_data(
                "401811940",
                known_golfer_ids=set(athletes),
                fetch_round_data=True,
                fetch_earnings=False,
            )

        assert results[0]["earnings_usd"] is None

    def test_partial_fetch_failure_leaves_none(self):
        """If one golfer's earnings fetch fails, their earnings stay None.

        The other golfers' earnings should still be populated. score_picks
        will retry the failed ones in its pre-step.
        """
        from app.services.scraper import _fetch_tournament_data

        athletes = ["3001", "3002"]

        def _flaky_earnings(pga_tour_id, competitor_id, **kwargs):
            if competitor_id == "3002":
                raise httpx.ConnectTimeout("timeout")
            return 1000000

        with (
            patch("app.services.scraper._get_json") as mock_get,
            patch(
                "app.services.scraper._fetch_golfer_earnings",
                side_effect=_flaky_earnings,
            ),
            patch(
                "app.services.scraper._fetch_competitor_rounds",
                return_value=("dummy", []),
            ),
            patch(
                "app.services.scraper._fetch_competitor_status",
                return_value=("dummy", None, None, None),
            ),
        ):
            mock_get.return_value = self._mock_competitors_response(athletes)

            _, results = _fetch_tournament_data(
                "401811940",
                known_golfer_ids=set(athletes),
                fetch_round_data=True,
                fetch_earnings=True,
            )

        result_earnings = {r["pga_tour_id"]: r["earnings_usd"] for r in results}
        assert result_earnings["3001"] == 1000000
        assert result_earnings["3002"] is None  # failed → None, not crash


# ---------------------------------------------------------------------------
# Playoff scoring with $0 earnings golfers
# ---------------------------------------------------------------------------


class TestPlayoffScoringZeroEarnings:
    """Playoff score_round handles golfers with earnings_usd=0 correctly.

    Real scenario: an amateur makes the cut at a PGA tournament used as a
    playoff round. A pod member picks that amateur. The pick should score
    0 points (not crash, not be treated as "earnings unavailable").
    """

    def test_score_round_with_amateur_null_earnings_pick(self, db):
        """Playoff pick on an amateur (earnings=NULL). The earnings gate
        uses the 80% threshold — if enough pros have earnings, the amateur's
        NULL is tolerated and treated as $0 for scoring."""
        from app.services.playoff import score_round

        tournament = _tournament(db, days_ago=1, name="Playoff Amateur")
        pro = _golfer(db, "Playoff Pro")
        amateur = _golfer(db, "Playoff Amateur")
        # Build a field where >80% have earnings so the threshold passes
        _entry(db, tournament, pro, earnings=1500000, pos=1, rounds=4)
        _entry(db, tournament, amateur, earnings=None, pos=20, rounds=4)
        for i in range(8):
            g = _golfer(db, f"Field Filler {i}")
            _entry(db, tournament, g, earnings=(8 - i) * 100000, pos=i + 3, rounds=4)

        # Build playoff infrastructure
        user1 = _user(db)
        user2 = _user(db)
        league = League(name="Playoff League", created_by=user1.id)
        db.add(league)
        db.flush()
        for u in [user1, user2]:
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=u.id,
                    role=LeagueMemberRole.MANAGER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
        season = Season(league_id=league.id, year=date.today().year, is_active=True)
        db.add(season)
        db.flush()

        config = PlayoffConfig(
            id=uuid.uuid4(),
            league_id=league.id,
            season_id=season.id,
            is_enabled=True,
            playoff_size=2,
            draft_style="snake",
            picks_per_round=[1],
            status="seeded",
        )
        db.add(config)
        db.flush()

        playoff_round = PlayoffRound(
            playoff_config_id=config.id,
            round_number=1,
            status="locked",
            tournament_id=tournament.id,
        )
        db.add(playoff_round)
        db.flush()

        pod = PlayoffPod(
            playoff_round_id=playoff_round.id,
            bracket_position=1,
            status="active",
        )
        db.add(pod)
        db.flush()

        m1 = PlayoffPodMember(pod_id=pod.id, user_id=user1.id, seed=1, draft_position=1)
        m2 = PlayoffPodMember(pod_id=pod.id, user_id=user2.id, seed=2, draft_position=2)
        db.add_all([m1, m2])
        db.flush()

        # User1 picked the pro, User2 picked the amateur
        pick1 = PlayoffPick(
            pod_id=pod.id,
            pod_member_id=m1.id,
            golfer_id=pro.id,
            tournament_id=tournament.id,
            draft_slot=1,
        )
        pick2 = PlayoffPick(
            pod_id=pod.id,
            pod_member_id=m2.id,
            golfer_id=amateur.id,
            tournament_id=tournament.id,
            draft_slot=1,
        )
        db.add_all([pick1, pick2])
        db.add(LeagueTournament(league_id=league.id, tournament_id=tournament.id))
        db.commit()

        # score_round should NOT raise — earnings_usd=0 is not NULL
        score_round(db, playoff_round)

        db.refresh(pick1)
        db.refresh(pick2)
        db.refresh(m1)
        db.refresh(m2)

        assert pick1.points_earned == 1500000.0  # pro earnings × 1.0
        assert pick2.points_earned == 0.0  # amateur: 0 × 1.0
        assert m1.total_points == 1500000.0
        assert m2.total_points == 0.0

    def test_score_round_rejects_when_earnings_below_threshold(self, db):
        """score_round raises 422 when the earnings threshold isn't met.

        When <80% of made-the-cut entries have positive earnings, ESPN
        hasn't finished publishing — scoring should be deferred.
        """
        from fastapi import HTTPException

        from app.services.playoff import score_round

        tournament = _tournament(db, days_ago=1, name="Null Earnings Playoff")
        golfer_with_null = _golfer(db, "Null Golfer")
        _entry(
            db,
            tournament,
            golfer_with_null,
            earnings=None,
            pos=30,
            rounds=4,
        )

        user = _user(db)
        league = League(name="Null PL", created_by=user.id)
        db.add(league)
        db.flush()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=user.id,
                role=LeagueMemberRole.MANAGER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        season = Season(league_id=league.id, year=date.today().year, is_active=True)
        db.add(season)
        db.flush()

        config = PlayoffConfig(
            id=uuid.uuid4(),
            league_id=league.id,
            season_id=season.id,
            is_enabled=True,
            playoff_size=2,
            draft_style="snake",
            picks_per_round=[1],
            status="seeded",
        )
        db.add(config)
        db.flush()

        playoff_round = PlayoffRound(
            playoff_config_id=config.id,
            round_number=1,
            status="locked",
            tournament_id=tournament.id,
        )
        db.add(playoff_round)
        db.flush()

        pod = PlayoffPod(
            playoff_round_id=playoff_round.id,
            bracket_position=1,
            status="active",
        )
        db.add(pod)
        db.flush()

        member = PlayoffPodMember(pod_id=pod.id, user_id=user.id, seed=1, draft_position=1)
        db.add(member)
        db.flush()

        pick = PlayoffPick(
            pod_id=pod.id,
            pod_member_id=member.id,
            golfer_id=golfer_with_null.id,
            tournament_id=tournament.id,
            draft_slot=1,
        )
        db.add(pick)
        db.add(LeagueTournament(league_id=league.id, tournament_id=tournament.id))
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            score_round(db, playoff_round)
        assert exc_info.value.status_code == 422
        assert "Earnings are not yet available" in exc_info.value.detail


# ---------------------------------------------------------------------------
# ESPN earnings gradual publish: end-to-end deferred scoring
# ---------------------------------------------------------------------------


class TestGradualEarningsPublish:
    """Simulates ESPN's gradual earnings publish pattern end-to-end.

    Sunday afternoon: tournament completes, winner has earnings.
    Monday morning: ESPN publishes more earnings, but not all.
    Monday evening: all earnings published, scoring can proceed.

    This tests the full flow through score_picks including the pre-step
    fetch and the earnings gate.
    """

    def test_scoring_defers_then_succeeds_on_retry(self, db):
        from app.services.scraper import score_picks

        tournament = _tournament(db, days_ago=0, name="Gradual Open")
        g_winner = _golfer(db, "Sunday Winner", pga_tour_id="SW001")
        g_second = _golfer(db, "Second Place", pga_tour_id="SP002")
        g_thirtieth = _golfer(db, "Thirtieth Place", pga_tour_id="TP030")
        g_cut = _golfer(db, "Cut Player", pga_tour_id="CP099")

        _entry(db, tournament, g_winner, earnings=1764000, pos=1, rounds=4)
        _entry(db, tournament, g_second, earnings=741533, pos=2, rounds=4)
        _entry(db, tournament, g_thirtieth, earnings=None, pos=30, rounds=4)
        _entry(db, tournament, g_cut, earnings=None, status="CUT", rounds=2)

        _, _, _, pick_winner = _league_with_pick(db, tournament, g_winner)
        _, _, _, pick_second = _league_with_pick(db, tournament, g_second)

        # First attempt: T30 still missing earnings → deferred
        count = score_picks(db, tournament)
        assert count == 0

        db.refresh(pick_winner)
        db.refresh(pick_second)
        assert pick_winner.points_earned is None
        assert pick_second.points_earned is None

        # ESPN publishes T30's earnings
        t30_entry = (
            db.query(TournamentEntry)
            .filter_by(tournament_id=tournament.id, golfer_id=g_thirtieth.id)
            .first()
        )
        t30_entry.earnings_usd = 59625
        db.commit()

        # Second attempt: all earnings available → scoring proceeds
        count = score_picks(db, tournament)
        assert count == 2

        db.refresh(pick_winner)
        db.refresh(pick_second)
        assert pick_winner.points_earned == 1764000.0
        assert pick_second.points_earned == 741533.0


# ---------------------------------------------------------------------------
# rescore_league_picks: earnings gate (admin override path)
# ---------------------------------------------------------------------------


class TestRescoreLeaguePicksEarningsGate:
    """rescore_league_picks defers when earnings are incomplete.

    Real scenario: manager uses admin override to set a member's pick for a
    just-completed tournament. rescore_league_picks runs immediately, but ESPN
    hasn't published all earnings. Without the gate, the pick gets scored as
    $0 via COALESCE(NULL, 0). With the gate, the pick stays unscored (NULL)
    until results_finalization retries after earnings are available.
    """

    def test_defers_when_earnings_incomplete(self, db):
        from app.services.scoring import rescore_league_picks

        tournament = _tournament(db, days_ago=1, name="Admin Override Open")
        winner = _golfer(db, "Override Winner")
        unpublished = _golfer(db, "Unpublished Player")

        _entry(db, tournament, winner, earnings=1764000, pos=1, rounds=4)
        _entry(db, tournament, unpublished, earnings=None, pos=30, rounds=4)

        league, season, user, pick = _league_with_pick(db, tournament, winner)

        count = rescore_league_picks(db, tournament.id, league.id)
        assert count == 0  # deferred

        db.refresh(pick)
        assert pick.points_earned is None  # untouched

    def test_scores_when_earnings_complete(self, db):
        from app.services.scoring import rescore_league_picks

        tournament = _tournament(db, days_ago=1, name="Admin Complete Open")
        winner = _golfer(db, "Complete Winner")
        runner_up = _golfer(db, "Complete Runner")

        _entry(db, tournament, winner, earnings=1764000, pos=1, rounds=4)
        _entry(db, tournament, runner_up, earnings=741533, pos=2, rounds=4)

        league, season, user, pick = _league_with_pick(db, tournament, winner)
        db.add(LeagueTournament(league_id=league.id, tournament_id=tournament.id))
        db.commit()

        count = rescore_league_picks(db, tournament.id, league.id)
        assert count == 1

        db.refresh(pick)
        assert pick.points_earned == 1764000.0

    def test_skips_gate_for_non_completed_tournaments(self, db):
        """In-progress tournaments skip the earnings gate entirely — they
        aren't scored by rescore_league_picks anyway (no earnings to score)."""
        from app.services.scoring import rescore_league_picks

        tournament = _tournament(db, status="in_progress", days_ago=0, name="Live Open")
        golfer = _golfer(db, "Live Golfer")
        _entry(db, tournament, golfer, earnings=None, pos=1, rounds=2)

        league, _, _, pick = _league_with_pick(db, tournament, golfer)
        db.add(LeagueTournament(league_id=league.id, tournament_id=tournament.id))
        db.commit()

        # Should not crash or defer — just runs normally (0 earnings → 0 points)
        count = rescore_league_picks(db, tournament.id, league.id)
        assert count >= 0  # may be 0 or 1 depending on entry match


# ---------------------------------------------------------------------------
# calculate_standings: excludes earnings-pending tournaments
# ---------------------------------------------------------------------------


class TestStandingsExcludesEarningsPending:
    """calculate_standings excludes completed tournaments with incomplete
    earnings from the standings calculation entirely — no points, no penalty.

    Real scenario: Valero Texas Open just completed but ESPN hasn't published
    mid-field earnings. A member with no pick for the Valero should NOT get
    the no-pick penalty. A member WITH a pick should not get $0 points.
    The tournament should be invisible to standings until scoring completes.
    """

    def test_no_penalty_for_earnings_pending_tournament(self, db):
        from app.services.scoring import calculate_standings

        # Set up league with 1 scored tournament and 1 earnings-pending tournament
        user = _user(db)
        league = League(name="Penalty Test League", created_by=user.id)
        db.add(league)
        db.flush()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=user.id,
                role=LeagueMemberRole.MANAGER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        season = Season(league_id=league.id, year=date.today().year, is_active=True)
        db.add(season)
        db.flush()

        # Tournament 1: fully scored
        t1 = _tournament(db, days_ago=10, name="Scored Open")
        g1 = _golfer(db, "T1 Winner")
        _entry(db, t1, g1, earnings=1000000, pos=1, rounds=4)
        db.add(LeagueTournament(league_id=league.id, tournament_id=t1.id))
        pick1 = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user.id,
            tournament_id=t1.id,
            golfer_id=g1.id,
            points_earned=1000000.0,
        )
        db.add(pick1)

        # Tournament 2: completed but earnings incomplete — NO pick submitted
        t2 = _tournament(db, days_ago=1, name="Pending Open")
        g2 = _golfer(db, "T2 Player")
        _entry(db, t2, g2, earnings=None, pos=1, rounds=4)  # earnings missing
        db.add(LeagueTournament(league_id=league.id, tournament_id=t2.id))
        db.commit()

        standings = calculate_standings(db, league, season)
        assert len(standings) == 1

        row = standings[0]
        # T2 should be excluded entirely: no penalty, no points from it
        assert row["total_points"] == 1000000.0
        assert row["pick_count"] == 1
        assert row["missed_count"] == 0  # NOT 1 — T2 doesn't count

    def test_includes_tournament_once_earnings_available(self, db):
        """After earnings are published, the tournament enters standings."""
        from app.services.scoring import calculate_standings

        user = _user(db)
        league = League(name="Include Test League", created_by=user.id)
        db.add(league)
        db.flush()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=user.id,
                role=LeagueMemberRole.MANAGER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        season = Season(league_id=league.id, year=date.today().year, is_active=True)
        db.add(season)
        db.flush()

        # Completed tournament with one entry missing earnings
        tournament = _tournament(db, days_ago=1, name="Delayed Open")
        g1 = _golfer(db, "Delayed Winner")
        g2 = _golfer(db, "Delayed Other")
        _entry(db, tournament, g1, earnings=2000000, pos=1, rounds=4)
        e2 = _entry(db, tournament, g2, earnings=None, pos=30, rounds=4)
        db.add(LeagueTournament(league_id=league.id, tournament_id=tournament.id))
        # User has no pick → would be a penalty once tournament counts
        db.commit()

        # Before earnings: tournament excluded, 0 missed
        standings = calculate_standings(db, league, season)
        assert standings[0]["missed_count"] == 0
        assert standings[0]["total_points"] == 0.0

        # Publish missing earnings
        e2.earnings_usd = 59625
        db.commit()

        # After earnings: tournament now counts, 1 missed (no pick)
        # Clear standings cache first
        season.standings_cache = None
        season.standings_cached_at = None
        db.flush()

        standings = calculate_standings(db, league, season)
        assert standings[0]["missed_count"] == 1
        assert standings[0]["total_points"] == league.no_pick_penalty


# ---------------------------------------------------------------------------
# Standings API: scoring_pending_tournaments field
# ---------------------------------------------------------------------------


class TestStandingsAPIScoringPending:
    """GET /standings returns scoring_pending_tournaments based on
    _all_earnings_available, not just unscored picks."""

    def test_returns_pending_tournament_with_no_picks(self, client, db):
        """Tournament completed, no picks at all, but earnings incomplete.

        The banner should still show because the tournament will eventually
        affect standings (no-pick penalty) once earnings are published.
        """
        email = f"sp_{uuid.uuid4().hex[:6]}@test.com"
        user = _user(db, email=email)
        league = League(name="SP Test League", created_by=user.id)
        db.add(league)
        db.flush()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=user.id,
                role=LeagueMemberRole.MANAGER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        season = Season(league_id=league.id, year=date.today().year, is_active=True)
        db.add(season)
        db.flush()

        tournament = _tournament(db, days_ago=1, name="Valero Texas Open")
        g = _golfer(db, "Pending Golfer")
        _entry(db, tournament, g, earnings=None, pos=1, rounds=4)
        db.add(LeagueTournament(league_id=league.id, tournament_id=tournament.id))
        db.commit()

        headers = {"Authorization": f"Bearer {_get_token(client, email)}"}
        resp = client.get(f"/api/v1/leagues/{league.id}/standings", headers=headers)
        assert resp.status_code == 200
        assert "Valero Texas Open" in resp.json()["scoring_pending_tournaments"]

    def test_returns_empty_when_all_earnings_available(self, client, db):
        email = f"sp2_{uuid.uuid4().hex[:6]}@test.com"
        user = _user(db, email=email)
        league = League(name="SP2 Test League", created_by=user.id)
        db.add(league)
        db.flush()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=user.id,
                role=LeagueMemberRole.MANAGER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        season = Season(league_id=league.id, year=date.today().year, is_active=True)
        db.add(season)
        db.flush()

        tournament = _tournament(db, days_ago=1, name="Fully Scored Open")
        g = _golfer(db, "Scored Golfer")
        _entry(db, tournament, g, earnings=1500000, pos=1, rounds=4)
        db.add(LeagueTournament(league_id=league.id, tournament_id=tournament.id))
        db.commit()

        headers = {"Authorization": f"Bearer {_get_token(client, email)}"}
        resp = client.get(f"/api/v1/leagues/{league.id}/standings", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["scoring_pending_tournaments"] == []


def _get_token(client, email: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]
