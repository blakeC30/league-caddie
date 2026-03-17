"""
Extended pick tests: my picks, all picks reveal rules, change pick, tournament
picks summary, and admin override.

Covers the GET and PATCH/PUT endpoints that test_picks.py does not reach.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

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
    TournamentStatus,
    User,
)
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Helpers (mirror test_picks.py helpers to keep tests self-contained)
# ---------------------------------------------------------------------------


def make_user(db: Session, email: str, display_name: str = "Test") -> User:
    user = User(email=email, password_hash=hash_password("password123"), display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_league(db: Session, creator: User) -> tuple[League, Season]:
    league = League(name="Test League", created_by=creator.id)
    db.add(league)
    db.flush()
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=creator.id,
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


def make_golfer(db: Session, name: str = "Test Golfer") -> Golfer:
    g = Golfer(pga_tour_id=f"T{uuid.uuid4().hex[:6]}", name=name)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def make_tournament(
    db: Session,
    days_from_now: int = 7,
    league: League | None = None,
    status: str = TournamentStatus.SCHEDULED.value,
) -> Tournament:
    start = date.today() + timedelta(days=days_from_now)
    t = Tournament(
        pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
        name="Test Open",
        start_date=start,
        end_date=start + timedelta(days=3),
        status=status,
        multiplier=1.0,
    )
    db.add(t)
    db.flush()
    if league is not None:
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))
    db.commit()
    db.refresh(t)
    return t


def add_golfer_to_tournament(
    db: Session, tournament: Tournament, golfer: Golfer
) -> TournamentEntry:
    entry = TournamentEntry(tournament_id=tournament.id, golfer_id=golfer.id)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _direct_pick(
    db: Session,
    league: League,
    season: Season,
    user: User,
    tournament: Tournament,
    golfer: Golfer,
    points_earned: float | None = None,
) -> Pick:
    """Insert a Pick directly, bypassing API validation (used for completed-tournament rows)."""
    pick = Pick(
        league_id=league.id,
        season_id=season.id,
        user_id=user.id,
        tournament_id=tournament.id,
        golfer_id=golfer.id,
        points_earned=points_earned,
    )
    db.add(pick)
    db.commit()
    db.refresh(pick)
    return pick


# ---------------------------------------------------------------------------
# GET /leagues/{id}/picks/mine
# ---------------------------------------------------------------------------


class TestGetMyPicks:
    def test_returns_empty_list_when_no_picks(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.get(f"/api/v1/leagues/{league.id}/picks/mine", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_submitted_pick(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        golfer = make_golfer(db)
        tournament = make_tournament(db, days_from_now=7, league=league)
        add_golfer_to_tournament(db, tournament, golfer)

        client.post(
            f"/api/v1/leagues/{league.id}/picks",
            headers=auth_headers,
            json={"tournament_id": str(tournament.id), "golfer_id": str(golfer.id)},
        )

        resp = client.get(f"/api/v1/leagues/{league.id}/picks/mine", headers=auth_headers)
        assert resp.status_code == 200
        picks = resp.json()
        assert len(picks) == 1
        assert picks[0]["golfer_id"] == str(golfer.id)
        assert picks[0]["points_earned"] is None  # Not scored until tournament completes.

    def test_only_returns_picks_within_league_schedule(self, client, auth_headers, db):
        """Picks for tournaments NOT in the league schedule are excluded."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        golfer = make_golfer(db)

        # Tournament added to the league schedule.
        t_in = make_tournament(db, days_from_now=7, league=league)
        # Tournament NOT added to the league schedule.
        t_out = make_tournament(db, days_from_now=14)
        add_golfer_to_tournament(db, t_in, golfer)
        add_golfer_to_tournament(db, t_out, golfer)

        # Submit pick for the in-schedule tournament.
        client.post(
            f"/api/v1/leagues/{league.id}/picks",
            headers=auth_headers,
            json={"tournament_id": str(t_in.id), "golfer_id": str(golfer.id)},
        )
        # Force-insert a pick for the out-of-schedule tournament.
        g2 = make_golfer(db, "Extra Golfer")
        _direct_pick(db, league, season, user, t_out, g2)

        resp = client.get(f"/api/v1/leagues/{league.id}/picks/mine", headers=auth_headers)
        assert resp.status_code == 200
        tournament_ids = [p["tournament_id"] for p in resp.json()]
        assert str(t_in.id) in tournament_ids
        assert str(t_out.id) not in tournament_ids


# ---------------------------------------------------------------------------
# GET /leagues/{id}/picks (all picks, reveal rules)
# ---------------------------------------------------------------------------


class TestGetAllPicks:
    def test_scheduled_tournament_picks_are_hidden(self, client, auth_headers, db):
        """Picks for upcoming SCHEDULED tournaments must not be visible."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        golfer = make_golfer(db)
        tournament = make_tournament(db, days_from_now=7, league=league)
        add_golfer_to_tournament(db, tournament, golfer)

        client.post(
            f"/api/v1/leagues/{league.id}/picks",
            headers=auth_headers,
            json={"tournament_id": str(tournament.id), "golfer_id": str(golfer.id)},
        )

        resp = client.get(f"/api/v1/leagues/{league.id}/picks", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_completed_tournament_picks_are_visible(self, client, auth_headers, db):
        """Once a tournament completes, all picks become visible to league members."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        golfer = make_golfer(db)

        tournament = make_tournament(
            db, days_from_now=-7, league=league, status=TournamentStatus.COMPLETED.value
        )
        add_golfer_to_tournament(db, tournament, golfer)
        _direct_pick(db, league, season, user, tournament, golfer, points_earned=200_000.0)

        resp = client.get(f"/api/v1/leagues/{league.id}/picks", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["golfer_id"] == str(golfer.id)


# ---------------------------------------------------------------------------
# PATCH /leagues/{id}/picks/{pick_id} — change pick
# ---------------------------------------------------------------------------


class TestChangePick:
    def test_change_golfer_before_tournament_starts(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        g1 = make_golfer(db, "Original Golfer")
        g2 = make_golfer(db, "New Golfer")
        tournament = make_tournament(db, days_from_now=7, league=league)
        add_golfer_to_tournament(db, tournament, g1)
        add_golfer_to_tournament(db, tournament, g2)

        submit = client.post(
            f"/api/v1/leagues/{league.id}/picks",
            headers=auth_headers,
            json={"tournament_id": str(tournament.id), "golfer_id": str(g1.id)},
        )
        pick_id = submit.json()["id"]

        resp = client.patch(
            f"/api/v1/leagues/{league.id}/picks/{pick_id}",
            headers=auth_headers,
            json={"golfer_id": str(g2.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["golfer_id"] == str(g2.id)

    def test_cannot_change_pick_for_completed_tournament(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        g1 = make_golfer(db, "Done Golfer")
        g2 = make_golfer(db, "Swap Target")

        tournament = make_tournament(
            db, days_from_now=-7, league=league, status=TournamentStatus.COMPLETED.value
        )
        entry = TournamentEntry(tournament_id=tournament.id, golfer_id=g1.id, earnings_usd=50_000)
        db.add(entry)
        add_golfer_to_tournament(db, tournament, g2)
        pick = _direct_pick(db, league, season, user, tournament, g1, points_earned=50_000.0)

        resp = client.patch(
            f"/api/v1/leagues/{league.id}/picks/{pick.id}",
            headers=auth_headers,
            json={"golfer_id": str(g2.id)},
        )
        assert resp.status_code == 400

    def test_cannot_change_nonexistent_pick(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.patch(
            f"/api/v1/leagues/{league.id}/picks/{uuid.uuid4()}",
            headers=auth_headers,
            json={"golfer_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_cannot_change_pick_to_already_used_golfer(self, client, auth_headers, db):
        """No-repeat rule is enforced on pick changes too."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        g1 = make_golfer(db, "Used Golfer")
        g2 = make_golfer(db, "Second Golfer")
        g3 = make_golfer(db, "Third Golfer")

        t1 = make_tournament(db, days_from_now=7, league=league)
        t2 = make_tournament(db, days_from_now=21, league=league)
        add_golfer_to_tournament(db, t1, g1)
        add_golfer_to_tournament(db, t1, g2)
        add_golfer_to_tournament(db, t2, g1)
        add_golfer_to_tournament(db, t2, g3)

        # Pick g1 for t1.
        client.post(
            f"/api/v1/leagues/{league.id}/picks",
            headers=auth_headers,
            json={"tournament_id": str(t1.id), "golfer_id": str(g1.id)},
        )

        # Mark t1 complete so t2 becomes available.
        t1.status = TournamentStatus.COMPLETED.value
        e = db.query(TournamentEntry).filter_by(tournament_id=t1.id, golfer_id=g1.id).first()
        e.earnings_usd = 200_000
        db.commit()

        # Pick g3 for t2.
        r2 = client.post(
            f"/api/v1/leagues/{league.id}/picks",
            headers=auth_headers,
            json={"tournament_id": str(t2.id), "golfer_id": str(g3.id)},
        )
        assert r2.status_code == 201
        t2_pick_id = r2.json()["id"]

        # Attempt to change t2 pick to g1 (already used in t1). Should fail.
        resp = client.patch(
            f"/api/v1/leagues/{league.id}/picks/{t2_pick_id}",
            headers=auth_headers,
            json={"golfer_id": str(g1.id)},
        )
        assert resp.status_code == 400

    def test_can_change_pick_to_same_golfer_for_same_tournament(self, client, auth_headers, db):
        """Changing a pick to the same golfer is a no-op and must be allowed."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        golfer = make_golfer(db, "Same Golfer")
        tournament = make_tournament(db, days_from_now=7, league=league)
        add_golfer_to_tournament(db, tournament, golfer)

        submit = client.post(
            f"/api/v1/leagues/{league.id}/picks",
            headers=auth_headers,
            json={"tournament_id": str(tournament.id), "golfer_id": str(golfer.id)},
        )
        pick_id = submit.json()["id"]

        resp = client.patch(
            f"/api/v1/leagues/{league.id}/picks/{pick_id}",
            headers=auth_headers,
            json={"golfer_id": str(golfer.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["golfer_id"] == str(golfer.id)


# ---------------------------------------------------------------------------
# GET /leagues/{id}/picks/tournament/{tournament_id} — summary
# ---------------------------------------------------------------------------


class TestTournamentPicksSummary:
    def test_scheduled_tournament_returns_403(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)
        tournament = make_tournament(db, days_from_now=7, league=league)

        resp = client.get(
            f"/api/v1/leagues/{league.id}/picks/tournament/{tournament.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 403

    def test_tournament_not_in_schedule_returns_404(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)
        # Tournament exists globally but not in this league's schedule.
        unscheduled = make_tournament(db, days_from_now=-7, status=TournamentStatus.COMPLETED.value)

        resp = client.get(
            f"/api/v1/leagues/{league.id}/picks/tournament/{unscheduled.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_completed_tournament_returns_full_summary(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        golfer = make_golfer(db, "Winner Golfer")

        tournament = make_tournament(
            db, days_from_now=-7, league=league, status=TournamentStatus.COMPLETED.value
        )
        entry = TournamentEntry(
            tournament_id=tournament.id,
            golfer_id=golfer.id,
            earnings_usd=1_000_000,
            finish_position=1,
        )
        db.add(entry)
        _direct_pick(db, league, season, user, tournament, golfer, points_earned=1_000_000.0)

        resp = client.get(
            f"/api/v1/leagues/{league.id}/picks/tournament/{tournament.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tournament_status"] == "completed"
        assert data["member_count"] == 1
        assert len(data["picks_by_golfer"]) == 1
        assert data["picks_by_golfer"][0]["golfer_name"] == "Winner Golfer"
        assert data["picks_by_golfer"][0]["pick_count"] == 1
        assert data["winner"]["golfer_name"] == "Winner Golfer"
        assert data["winner"]["pick_count"] == 1

    def test_member_without_pick_appears_in_no_pick_list(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)

        tournament = make_tournament(
            db, days_from_now=-7, league=league, status=TournamentStatus.COMPLETED.value
        )

        resp = client.get(
            f"/api/v1/leagues/{league.id}/picks/tournament/{tournament.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        no_pickers = [m["user_id"] for m in data["no_pick_members"]]
        assert str(user.id) in no_pickers
        assert data["winner"] is None

    def test_summary_groups_picks_by_golfer(self, client, db):
        """When two members pick the same golfer, pick_count should be 2."""
        creator = make_user(db, "sum_creator@example.com", "Creator")
        member2 = make_user(db, "sum_member2@example.com", "Member2")

        league, season = make_league(db, creator)
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member2.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        golfer = make_golfer(db, "Popular Golfer")
        tournament = make_tournament(
            db, days_from_now=-7, league=league, status=TournamentStatus.COMPLETED.value
        )
        entry = TournamentEntry(
            tournament_id=tournament.id, golfer_id=golfer.id, earnings_usd=500_000
        )
        db.add(entry)

        _direct_pick(db, league, season, creator, tournament, golfer, points_earned=500_000.0)
        _direct_pick(db, league, season, member2, tournament, golfer, points_earned=500_000.0)

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "sum_creator@example.com", "password": "password123"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = client.get(
            f"/api/v1/leagues/{league.id}/picks/tournament/{tournament.id}",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["picks_by_golfer"][0]["pick_count"] == 2
        assert data["picks_by_golfer"][0]["golfer_name"] == "Popular Golfer"


# ---------------------------------------------------------------------------
# PUT /leagues/{id}/picks/admin-override
# ---------------------------------------------------------------------------


class TestAdminOverridePick:
    def test_manager_creates_pick_without_field_entry(self, client, auth_headers, db):
        """Admin override bypasses the field-released check."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        golfer = make_golfer(db, "Unregistered Golfer")
        tournament = make_tournament(db, days_from_now=7, league=league)
        # No TournamentEntry — field not released yet.

        resp = client.put(
            f"/api/v1/leagues/{league.id}/picks/admin-override",
            headers=auth_headers,
            json={
                "user_id": str(user.id),
                "tournament_id": str(tournament.id),
                "golfer_id": str(golfer.id),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["golfer_id"] == str(golfer.id)

    def test_manager_replaces_existing_pick(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        g1 = make_golfer(db, "First Choice")
        g2 = make_golfer(db, "Second Choice")
        tournament = make_tournament(db, days_from_now=7, league=league)
        add_golfer_to_tournament(db, tournament, g1)

        # Create initial pick via normal flow.
        client.post(
            f"/api/v1/leagues/{league.id}/picks",
            headers=auth_headers,
            json={"tournament_id": str(tournament.id), "golfer_id": str(g1.id)},
        )

        # Override to g2.
        resp = client.put(
            f"/api/v1/leagues/{league.id}/picks/admin-override",
            headers=auth_headers,
            json={
                "user_id": str(user.id),
                "tournament_id": str(tournament.id),
                "golfer_id": str(g2.id),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["golfer_id"] == str(g2.id)

    def test_manager_deletes_pick_with_null_golfer_id(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        golfer = make_golfer(db)
        tournament = make_tournament(db, days_from_now=7, league=league)
        add_golfer_to_tournament(db, tournament, golfer)

        client.post(
            f"/api/v1/leagues/{league.id}/picks",
            headers=auth_headers,
            json={"tournament_id": str(tournament.id), "golfer_id": str(golfer.id)},
        )

        resp = client.put(
            f"/api/v1/leagues/{league.id}/picks/admin-override",
            headers=auth_headers,
            json={
                "user_id": str(user.id),
                "tournament_id": str(tournament.id),
                "golfer_id": None,
            },
        )
        assert resp.status_code == 200
        assert resp.json() is None  # Deleted — null body.

    def test_admin_override_deleting_nonexistent_pick_is_a_noop(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        tournament = make_tournament(db, days_from_now=7, league=league)

        resp = client.put(
            f"/api/v1/leagues/{league.id}/picks/admin-override",
            headers=auth_headers,
            json={
                "user_id": str(user.id),
                "tournament_id": str(tournament.id),
                "golfer_id": None,
            },
        )
        # No pick exists — deletion is idempotent (still succeeds with null).
        assert resp.status_code == 200
        assert resp.json() is None

    def test_admin_override_enforces_no_repeat_rule(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        golfer = make_golfer(db, "Repeat Golfer")
        t1 = make_tournament(db, days_from_now=7, league=league)
        t2 = make_tournament(db, days_from_now=14, league=league)
        add_golfer_to_tournament(db, t1, golfer)

        client.post(
            f"/api/v1/leagues/{league.id}/picks",
            headers=auth_headers,
            json={"tournament_id": str(t1.id), "golfer_id": str(golfer.id)},
        )

        resp = client.put(
            f"/api/v1/leagues/{league.id}/picks/admin-override",
            headers=auth_headers,
            json={
                "user_id": str(user.id),
                "tournament_id": str(t2.id),
                "golfer_id": str(golfer.id),
            },
        )
        assert resp.status_code == 422
        assert "already been used" in resp.json()["detail"].lower()

    def test_admin_override_for_tournament_not_in_schedule_returns_422(
        self, client, auth_headers, db
    ):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        golfer = make_golfer(db)
        # Tournament is NOT added to the league's schedule.
        unscheduled = make_tournament(db, days_from_now=7)

        resp = client.put(
            f"/api/v1/leagues/{league.id}/picks/admin-override",
            headers=auth_headers,
            json={
                "user_id": str(user.id),
                "tournament_id": str(unscheduled.id),
                "golfer_id": str(golfer.id),
            },
        )
        assert resp.status_code == 422

    def test_non_manager_cannot_use_admin_override(self, client, db):
        creator = make_user(db, "ao_creator@example.com")
        league, season = make_league(db, creator)
        golfer = make_golfer(db)
        tournament = make_tournament(db, days_from_now=7, league=league)

        # Register a regular member.
        member_email = "ao_member@example.com"
        client.post(
            "/api/v1/auth/register",
            json={"email": member_email, "password": "password123", "display_name": "Mbr"},
        )
        member = db.query(User).filter_by(email=member_email).first()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        login = client.post(
            "/api/v1/auth/login", json={"email": member_email, "password": "password123"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = client.put(
            f"/api/v1/leagues/{league.id}/picks/admin-override",
            headers=headers,
            json={
                "user_id": str(member.id),
                "tournament_id": str(tournament.id),
                "golfer_id": str(golfer.id),
            },
        )
        assert resp.status_code == 403
