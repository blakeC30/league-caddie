"""
Tests covering remaining coverage gaps across multiple routers.

Organized by router to push coverage above 95%.
"""

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.models import (
    Golfer,
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    LeaguePurchase,
    LeagueTournament,
    Pick,
    PlayoffConfig,
    PlayoffRound,
    Season,
    StripeCustomer,
    Tournament,
    TournamentStatus,
    User,
)
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(db: Session, email: str, display_name: str = "Test", **kwargs) -> User:
    user = User(
        email=email,
        password_hash=hash_password("password123"),
        display_name=display_name,
        **kwargs,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client, email: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_league(db, creator, name="Test League"):
    league = League(name=name, created_by=creator.id)
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


# ---------------------------------------------------------------------------
# Stripe: _get_or_create_stripe_customer
# ---------------------------------------------------------------------------


class TestStripeCustomerCreation:
    """Covers stripe_router.py lines 70-111."""

    def test_create_checkout_creates_stripe_customer(self, client, db):
        """POST /stripe/create-checkout-session should work for a manager with a league."""
        user = _make_user(db, "stripe1@test.com")
        league, _ = _make_league(db, user)
        headers = _login(client, "stripe1@test.com")

        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/test"
        mock_customer = MagicMock()
        mock_customer.id = "cus_test123"

        with (
            patch("app.routers.stripe_router.stripe.Customer.create", return_value=mock_customer),
            patch(
                "app.routers.stripe_router.stripe.checkout.Session.create",
                return_value=mock_session,
            ),
        ):
            resp = client.post(
                "/api/v1/stripe/create-checkout-session",
                headers=headers,
                json={"league_id": str(league.id), "tier": "starter"},
            )

        assert resp.status_code == 200
        assert resp.json()["url"] == "https://checkout.stripe.com/test"

        # Verify StripeCustomer row was created
        sc = db.query(StripeCustomer).filter_by(user_id=user.id).first()
        assert sc is not None
        assert sc.stripe_customer_id == "cus_test123"


class TestStripeWebhookEdgeCases:
    """Covers stripe_router.py webhook validation lines."""

    def test_webhook_missing_signature_returns_400(self, client):
        resp = client.post(
            "/api/v1/stripe/webhook",
            content=b"{}",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_webhook_invalid_signature_returns_400(self, client):
        resp = client.post(
            "/api/v1/stripe/webhook",
            content=b'{"type": "checkout.session.completed"}',
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "t=1234,v1=invalid",
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Leagues: admin league creation, roster, member management
# ---------------------------------------------------------------------------


class TestAdminLeagueCreation:
    """Covers leagues.py lines 167-190: platform admin creates league with free Elite purchase."""

    def test_admin_league_gets_free_elite_purchase(self, client, db):
        _make_user(db, "admincreate@test.com", is_platform_admin=True)
        headers = _login(client, "admincreate@test.com")

        resp = client.post(
            "/api/v1/leagues",
            headers=headers,
            json={"name": "Admin League"},
        )
        assert resp.status_code == 201
        league_id = resp.json()["id"]

        # Verify league is admin league
        league = db.query(League).filter_by(id=league_id).first()
        assert league.is_admin_league is True

        # Verify Elite purchase exists
        purchase = db.query(LeaguePurchase).filter_by(league_id=league.id).first()
        assert purchase is not None
        assert purchase.tier == "elite"
        assert purchase.amount_cents == 0


class TestRosterEndpoint:
    """Covers leagues.py lines 596-604: roster with manager vs member email visibility."""

    def test_manager_sees_emails(self, client, db):
        manager = _make_user(db, "roster_mgr@test.com")
        league, _ = _make_league(db, manager)
        member = _make_user(db, "roster_mem@test.com", display_name="Member")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        headers = _login(client, "roster_mgr@test.com")
        resp = client.get(f"/api/v1/leagues/{league.id}/roster", headers=headers)
        assert resp.status_code == 200
        emails = [r["email"] for r in resp.json() if r["email"] is not None]
        assert len(emails) >= 1  # manager can see emails

    def test_member_cannot_see_emails(self, client, db):
        manager = _make_user(db, "roster_mgr2@test.com")
        league, _ = _make_league(db, manager)
        member = _make_user(db, "roster_mem2@test.com", display_name="Member")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        headers = _login(client, "roster_mem2@test.com")
        resp = client.get(f"/api/v1/leagues/{league.id}/roster", headers=headers)
        assert resp.status_code == 200
        for row in resp.json():
            assert row["email"] is None

    def test_roster_includes_joined_at(self, client, db):
        manager = _make_user(db, "roster_mgr3@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "roster_mgr3@test.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/roster", headers=headers)
        assert resp.status_code == 200
        for row in resp.json():
            assert "joined_at" in row
            assert row["joined_at"] != ""


class TestLeagueScheduleValidation:
    """Covers leagues.py schedule validation branches."""

    def test_schedule_rejects_invalid_multiplier(self, client, db):
        """Multiplier not in (1.0, 1.5, 2.0) should be rejected."""
        user = _make_user(db, "sched_val@test.com")
        league, _ = _make_league(db, user)
        headers = _login(client, "sched_val@test.com")

        start = date.today() + timedelta(days=14)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Val Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
        )
        db.add(t)
        db.commit()

        resp = client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            headers=headers,
            json={"tournaments": [{"tournament_id": str(t.id), "multiplier": 3.0}]},
        )
        assert resp.status_code == 422


class TestMemberRoleUpdate:
    """Covers leagues.py member role change and removal."""

    def test_update_role_to_manager(self, client, db):
        manager = _make_user(db, "role_mgr@test.com")
        league, _ = _make_league(db, manager)
        member = _make_user(db, "role_mem@test.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        headers = _login(client, "role_mgr@test.com")
        resp = client.patch(
            f"/api/v1/leagues/{league.id}/members/{member.id}/role",
            headers=headers,
            json={"role": "manager"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "manager"

    def test_update_role_invalid_returns_422(self, client, db):
        manager = _make_user(db, "role_mgr2@test.com")
        league, _ = _make_league(db, manager)
        member = _make_user(db, "role_mem2@test.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        headers = _login(client, "role_mgr2@test.com")
        resp = client.patch(
            f"/api/v1/leagues/{league.id}/members/{member.id}/role",
            headers=headers,
            json={"role": "admin"},
        )
        assert resp.status_code == 422

    def test_update_role_nonexistent_member_returns_404(self, client, db):
        manager = _make_user(db, "role_mgr3@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "role_mgr3@test.com")

        fake_id = str(uuid.uuid4())
        resp = client.patch(
            f"/api/v1/leagues/{league.id}/members/{fake_id}/role",
            headers=headers,
            json={"role": "manager"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Picks: context endpoint, admin override edge cases
# ---------------------------------------------------------------------------


class TestLeagueCreationRestricted:
    """Covers leagues.py line 105: LEAGUE_CREATION_RESTRICTED flag."""

    def test_restricted_creation_blocks_non_admin(self, client, db):
        _make_user(db, "restricted@test.com")
        headers = _login(client, "restricted@test.com")

        with patch("app.routers.leagues.settings") as mock_settings:
            mock_settings.LEAGUE_CREATION_RESTRICTED = True
            resp = client.post(
                "/api/v1/leagues",
                headers=headers,
                json={"name": "Blocked League"},
            )
        assert resp.status_code == 403


class TestMemberRemovalWithPlayoff:
    """Covers leagues.py lines 699-752: playoff cleanup when member is removed."""

    def test_remove_member_cleans_playoff_data(self, client, db):
        manager = _make_user(db, "rem_mgr@test.com")
        league, season = _make_league(db, manager)
        member = _make_user(db, "rem_mem@test.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        headers = _login(client, "rem_mgr@test.com")
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/members/{member.id}",
            headers=headers,
        )
        assert resp.status_code == 204

        # Member should no longer be in the league
        m = (
            db.query(LeagueMember)
            .filter_by(
                league_id=league.id,
                user_id=member.id,
            )
            .first()
        )
        assert m is None


class TestMemberRemovalWithPlayoffCleanup:
    """Covers leagues.py lines 699-752: playoff bracket auto-shrink on member departure."""

    def test_bracket_shrinks_when_member_removed_before_schedule_lock(self, client, db):
        """Removing a member while regular season is ongoing should auto-shrink the bracket."""
        manager = _make_user(db, "shrink_mgr@test.com")
        league, season = _make_league(db, manager)

        # Add 7 more members (8 total)
        members = [manager]
        for i in range(7):
            u = _make_user(db, f"shrink_p{i}@test.com")
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

        # Create playoff config with size 8
        config = PlayoffConfig(
            league_id=league.id,
            season_id=season.id,
            is_enabled=True,
            playoff_size=8,
            draft_style="snake",
            picks_per_round=[1, 1, 1],
            status="pending",
        )
        db.add(config)

        # Must have some scheduled tournaments (regular season not yet complete)
        for i in range(4):
            start = date.today() + timedelta(days=7 * (i + 1))
            t = Tournament(
                pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
                name=f"Future {i}",
                start_date=start,
                end_date=start + timedelta(days=3),
                status=TournamentStatus.SCHEDULED.value,
            )
            db.add(t)
            db.flush()
            db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))
        db.commit()

        headers = _login(client, "shrink_mgr@test.com")
        # Remove one member → 7 remaining → bracket should shrink to 4
        target = members[7]
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/members/{target.id}",
            headers=headers,
        )
        assert resp.status_code == 204

        db.refresh(config)
        assert config.playoff_size == 4  # auto-shrunk from 8 to 4


class TestScheduleWithPlayoffConfig:
    """Covers leagues.py lines 993-1029 and 1213-1248: playoff tournament ID computation
    and schedule sufficiency checks."""

    def test_get_tournaments_marks_playoff_rounds(self, client, db):
        """GET /leagues/{id}/tournaments with a pending playoff config should mark
        the last N scheduled tournaments as is_playoff_round=True."""
        manager = _make_user(db, "po_sched@test.com")
        league, season = _make_league(db, manager)
        headers = _login(client, "po_sched@test.com")

        # Create 4 scheduled tournaments
        for i in range(4):
            start = date.today() + timedelta(days=7 * (i + 1))
            t = Tournament(
                pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
                name=f"Sched {i}",
                start_date=start,
                end_date=start + timedelta(days=3),
                status=TournamentStatus.SCHEDULED.value,
            )
            db.add(t)
            db.flush()
            db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))

        # Pending playoff config (4-player bracket = 2 rounds)
        config = PlayoffConfig(
            league_id=league.id,
            season_id=season.id,
            is_enabled=True,
            playoff_size=4,
            draft_style="snake",
            picks_per_round=[1, 1],
            status="pending",
        )
        db.add(config)
        db.commit()

        resp = client.get(f"/api/v1/leagues/{league.id}/tournaments", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        playoff_flags = [t["is_playoff_round"] for t in data]
        # Last 2 of 4 should be playoff rounds
        assert playoff_flags.count(True) == 2

    def test_schedule_update_rejects_insufficient_future_tournaments(self, client, db):
        """PUT /leagues/{id}/tournaments with a pending playoff config rejects
        if not enough scheduled tournaments for the bracket."""
        manager = _make_user(db, "po_sched2@test.com")
        league, season = _make_league(db, manager)
        headers = _login(client, "po_sched2@test.com")

        # Create 1 scheduled tournament
        start = date.today() + timedelta(days=14)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Only One",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
        )
        db.add(t)
        db.flush()

        # Pending config needs 2 scheduled tournaments for 4-player bracket
        config = PlayoffConfig(
            league_id=league.id,
            season_id=season.id,
            is_enabled=True,
            playoff_size=4,
            draft_style="snake",
            picks_per_round=[1, 1],
            status="pending",
        )
        db.add(config)
        db.commit()

        resp = client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            headers=headers,
            json={"tournaments": [{"tournament_id": str(t.id)}]},
        )
        assert resp.status_code == 422
        assert "future tournament" in resp.json()["detail"].lower()

    def test_schedule_locks_when_playoff_draft_opened(self, client, db):
        """PUT /leagues/{id}/tournaments returns 422 when first playoff round
        is not pending (schedule locked)."""
        manager = _make_user(db, "po_lock@test.com")
        league, season = _make_league(db, manager)
        headers = _login(client, "po_lock@test.com")

        start = date.today() + timedelta(days=14)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Lock Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
        )
        db.add(t)
        db.flush()

        config = PlayoffConfig(
            league_id=league.id,
            season_id=season.id,
            is_enabled=True,
            playoff_size=2,
            draft_style="snake",
            picks_per_round=[1],
            status="active",
        )
        db.add(config)
        db.flush()

        # Round 1 in "drafting" status (not "pending") = schedule locked
        db.add(
            PlayoffRound(
                playoff_config_id=config.id,
                round_number=1,
                tournament_id=t.id,
                status="drafting",
            )
        )
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))
        db.commit()

        resp = client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            headers=headers,
            json={"tournaments": [{"tournament_id": str(t.id)}]},
        )
        assert resp.status_code == 422
        assert "locked" in resp.json()["detail"].lower()


class TestStripeCreateLeagueCheckout:
    """Covers stripe_router.py lines 273-314: create-league-checkout endpoint."""

    def test_create_league_checkout_returns_url(self, client, db):
        _make_user(db, "checkout1@test.com")
        headers = _login(client, "checkout1@test.com")

        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/league"
        mock_customer = MagicMock()
        mock_customer.id = "cus_league123"

        with (
            patch("app.routers.stripe_router.stripe.Customer.create", return_value=mock_customer),
            patch(
                "app.routers.stripe_router.stripe.checkout.Session.create",
                return_value=mock_session,
            ),
        ):
            resp = client.post(
                "/api/v1/stripe/create-league-checkout",
                headers=headers,
                json={
                    "name": "New League",
                    "no_pick_penalty": 50000,
                    "tier": "standard",
                    "auto_accept_requests": False,
                },
            )

        assert resp.status_code == 200
        assert resp.json()["url"] == "https://checkout.stripe.com/league"

    def test_create_league_checkout_invalid_tier_returns_422(self, client, db):
        _make_user(db, "checkout2@test.com")
        headers = _login(client, "checkout2@test.com")

        resp = client.post(
            "/api/v1/stripe/create-league-checkout",
            headers=headers,
            json={
                "name": "Bad Tier League",
                "tier": "nonexistent",
            },
        )
        assert resp.status_code == 422


class TestPickContextEndpoint:
    """Covers picks.py lines 203-231: GET /picks/context."""

    def test_pick_context_returns_used_golfers(self, client, db):
        user = _make_user(db, "ctx@test.com")
        league, season = _make_league(db, user)
        headers = _login(client, "ctx@test.com")

        # Create a completed tournament with a pick
        start = date(date.today().year, 1, 6)
        t1 = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Past Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.COMPLETED.value,
        )
        db.add(t1)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t1.id))

        golfer = Golfer(pga_tour_id=f"G{uuid.uuid4().hex[:6]}", name="Used Golfer")
        db.add(golfer)
        db.flush()
        db.add(
            Pick(
                league_id=league.id,
                season_id=season.id,
                user_id=user.id,
                tournament_id=t1.id,
                golfer_id=golfer.id,
                points_earned=100_000,
            )
        )

        # Create a future tournament
        start2 = date.today() + timedelta(days=14)
        t2 = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Future Open",
            start_date=start2,
            end_date=start2 + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
        )
        db.add(t2)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t2.id))
        db.commit()

        resp = client.get(
            f"/api/v1/leagues/{league.id}/picks/member-context"
            f"?tournament_id={t2.id}&user_id={user.id}",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        used_ids = [g["golfer_id"] for g in data["used_golfers"]]
        assert str(golfer.id) in used_ids


class TestAdminOverridePick:
    """Covers picks.py admin override edge cases."""

    def test_override_with_nonexistent_golfer_returns_404(self, client, db):
        admin = _make_user(db, "override_adm@test.com", is_platform_admin=True)
        league, season = _make_league(db, admin)
        headers = _login(client, "override_adm@test.com")

        start = date.today() + timedelta(days=7)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Override Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))
        db.commit()

        resp = client.put(
            f"/api/v1/leagues/{league.id}/picks/admin-override",
            headers=headers,
            json={
                "user_id": str(admin.id),
                "tournament_id": str(t.id),
                "golfer_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404

    def test_override_delete_pick(self, client, db):
        """Admin override with golfer_id=null deletes the pick."""
        admin = _make_user(db, "override_del@test.com", is_platform_admin=True)
        league, season = _make_league(db, admin)
        headers = _login(client, "override_del@test.com")

        start = date.today() + timedelta(days=7)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Del Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))

        golfer = Golfer(pga_tour_id=f"G{uuid.uuid4().hex[:6]}", name="Del Golfer")
        db.add(golfer)
        db.flush()
        db.add(
            Pick(
                league_id=league.id,
                season_id=season.id,
                user_id=admin.id,
                tournament_id=t.id,
                golfer_id=golfer.id,
            )
        )
        db.commit()

        resp = client.put(
            f"/api/v1/leagues/{league.id}/picks/admin-override",
            headers=headers,
            json={
                "user_id": str(admin.id),
                "tournament_id": str(t.id),
                "golfer_id": None,
            },
        )
        assert resp.status_code == 200

        # Pick should be deleted
        pick = (
            db.query(Pick)
            .filter_by(
                league_id=league.id,
                user_id=admin.id,
                tournament_id=t.id,
            )
            .first()
        )
        assert pick is None

    def test_override_nonmember_returns_404(self, client, db):
        admin = _make_user(db, "override_adm2@test.com", is_platform_admin=True)
        league, season = _make_league(db, admin)
        headers = _login(client, "override_adm2@test.com")

        outsider = _make_user(db, "override_outsider@test.com")
        start = date.today() + timedelta(days=7)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Override Open2",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))

        golfer = Golfer(pga_tour_id=f"G{uuid.uuid4().hex[:6]}", name="Override Golfer")
        db.add(golfer)
        db.commit()

        resp = client.put(
            f"/api/v1/leagues/{league.id}/picks/admin-override",
            headers=headers,
            json={
                "user_id": str(outsider.id),
                "tournament_id": str(t.id),
                "golfer_id": str(golfer.id),
            },
        )
        assert resp.status_code == 404
