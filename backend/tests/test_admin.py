"""
Tests for admin endpoints.

Covers:
  GET  /admin/stats                                  — aggregated platform statistics
  POST /admin/sync                                   — trigger full PGA Tour sync
  POST /admin/sync/{pga_tour_id}                     — trigger single tournament sync
  GET  /admin/stripe/webhook-failures                — list unresolved failures
  POST /admin/stripe/webhook-failures/{id}/retry     — retry a failed webhook event
  POST /admin/import-members                         — bulk import members from CSV
  POST /admin/import-picks                           — bulk import picks from CSV

All endpoints require platform_admin privilege. Non-admins receive 403; missing
credentials receive 401.
"""

import io
import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from app.models import (
    Golfer,
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    LeagueTournament,
    Pick,
    Season,
    StripeWebhookFailure,
    Tournament,
    TournamentEntry,
    TournamentStatus,
    User,
)
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(db, email: str, *, is_platform_admin: bool = False) -> User:
    user = User(
        email=email,
        password_hash=hash_password("password123"),
        display_name="Test",
        is_platform_admin=is_platform_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(client, email: str) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert resp.status_code == 200, resp.json()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_tournament(db, pga_tour_id: str = "401580315") -> Tournament:
    t = Tournament(
        pga_tour_id=pga_tour_id,
        name="The Masters",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 13),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_webhook_failure(
    db,
    *,
    session_id: str = "cs_test_fail",
    error: str = "Something went wrong",
    resolved: bool = False,
) -> StripeWebhookFailure:
    failure = StripeWebhookFailure(
        id=uuid.uuid4(),
        stripe_checkout_session_id=session_id,
        raw_payload={"id": session_id, "metadata": {}},
        error_message=error,
        resolved_at=datetime.now(UTC) if resolved else None,
    )
    db.add(failure)
    db.commit()
    db.refresh(failure)
    return failure


# ---------------------------------------------------------------------------
# Authorization (all admin endpoints require platform_admin)
# ---------------------------------------------------------------------------


class TestAdminAuth:
    def test_sync_unauthenticated_returns_401(self, client):
        resp = client.post("/api/v1/admin/sync")
        assert resp.status_code == 401

    def test_sync_non_admin_returns_403(self, client, db):
        _make_user(db, "user@example.com")
        headers = _auth_headers(client, "user@example.com")
        resp = client.post("/api/v1/admin/sync", headers=headers)
        assert resp.status_code == 403
        assert "admin" in resp.json()["detail"].lower()

    def test_tournament_sync_unauthenticated_returns_401(self, client):
        resp = client.post("/api/v1/admin/sync/401580315")
        assert resp.status_code == 401

    def test_tournament_sync_non_admin_returns_403(self, client, db):
        _make_user(db, "user2@example.com")
        headers = _auth_headers(client, "user2@example.com")
        resp = client.post("/api/v1/admin/sync/401580315", headers=headers)
        assert resp.status_code == 403

    def test_webhook_failures_unauthenticated_returns_401(self, client):
        resp = client.get("/api/v1/admin/stripe/webhook-failures")
        assert resp.status_code == 401

    def test_webhook_failures_non_admin_returns_403(self, client, db):
        _make_user(db, "user3@example.com")
        headers = _auth_headers(client, "user3@example.com")
        resp = client.get("/api/v1/admin/stripe/webhook-failures", headers=headers)
        assert resp.status_code == 403

    def test_retry_unauthenticated_returns_401(self, client):
        resp = client.post(f"/api/v1/admin/stripe/webhook-failures/{uuid.uuid4()}/retry")
        assert resp.status_code == 401

    def test_retry_non_admin_returns_403(self, client, db):
        _make_user(db, "user4@example.com")
        headers = _auth_headers(client, "user4@example.com")
        resp = client.post(
            f"/api/v1/admin/stripe/webhook-failures/{uuid.uuid4()}/retry",
            headers=headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /admin/sync
# ---------------------------------------------------------------------------


class TestAdminSync:
    def test_success_returns_sync_result(self, client, db):
        _make_user(db, "admin@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin@example.com")
        mock_result = {"synced": 10, "skipped": 2}

        with patch("app.routers.admin.full_sync", return_value=mock_result) as mock_sync:
            resp = client.post("/api/v1/admin/sync", headers=headers)

        assert resp.status_code == 200
        assert resp.json() == mock_result
        mock_sync.assert_called_once()

    def test_passes_year_param_to_full_sync(self, client, db):
        _make_user(db, "admin2@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin2@example.com")

        with patch("app.routers.admin.full_sync", return_value={}) as mock_sync:
            client.post("/api/v1/admin/sync?year=2025", headers=headers)

        args, _ = mock_sync.call_args
        assert args[1] == 2025  # second positional arg is target_year

    def test_defaults_to_current_year(self, client, db):
        _make_user(db, "admin3@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin3@example.com")
        current_year = date.today().year

        with patch("app.routers.admin.full_sync", return_value={}) as mock_sync:
            client.post("/api/v1/admin/sync", headers=headers)

        args, _ = mock_sync.call_args
        assert args[1] == current_year

    def test_passes_force_true_flag(self, client, db):
        _make_user(db, "admin4@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin4@example.com")

        with patch("app.routers.admin.full_sync", return_value={}) as mock_sync:
            client.post("/api/v1/admin/sync?force=true", headers=headers)

        _, kwargs = mock_sync.call_args
        assert kwargs["force"] is True

    def test_force_defaults_to_false(self, client, db):
        _make_user(db, "admin5@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin5@example.com")

        with patch("app.routers.admin.full_sync", return_value={}) as mock_sync:
            client.post("/api/v1/admin/sync", headers=headers)

        _, kwargs = mock_sync.call_args
        assert kwargs["force"] is False

    def test_sync_exception_returns_502_with_detail(self, client, db):
        _make_user(db, "admin6@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin6@example.com")

        with patch("app.routers.admin.full_sync", side_effect=RuntimeError("ESPN API timeout")):
            resp = client.post("/api/v1/admin/sync", headers=headers)

        assert resp.status_code == 502
        assert "Sync failed" in resp.json()["detail"]
        assert "ESPN API timeout" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /admin/sync/{pga_tour_id}
# ---------------------------------------------------------------------------


class TestAdminTournamentSync:
    def test_unknown_pga_tour_id_returns_404(self, client, db):
        _make_user(db, "admin7@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin7@example.com")

        resp = client.post("/api/v1/admin/sync/nonexistent_id", headers=headers)

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_success_returns_sync_result(self, client, db):
        _make_user(db, "admin8@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin8@example.com")
        _make_tournament(db, pga_tour_id="401580315")
        mock_result = {"tournament": "The Masters", "rounds": 4}

        with patch("app.routers.admin.sync_tournament", return_value=mock_result):
            resp = client.post("/api/v1/admin/sync/401580315", headers=headers)

        assert resp.status_code == 200
        assert resp.json() == mock_result

    def test_exception_returns_502_with_detail(self, client, db):
        _make_user(db, "admin9@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin9@example.com")
        _make_tournament(db, pga_tour_id="401580315")

        with patch("app.routers.admin.sync_tournament", side_effect=ValueError("Bad ESPN data")):
            resp = client.post("/api/v1/admin/sync/401580315", headers=headers)

        assert resp.status_code == 502
        assert "Bad ESPN data" in resp.json()["detail"]

    def test_force_flag_passed_to_sync_tournament(self, client, db):
        _make_user(db, "admin10@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin10@example.com")
        _make_tournament(db, pga_tour_id="401580315")

        with patch("app.routers.admin.sync_tournament", return_value={}) as mock_sync:
            client.post("/api/v1/admin/sync/401580315?force=true", headers=headers)

        _, kwargs = mock_sync.call_args
        assert kwargs["force"] is True


# ---------------------------------------------------------------------------
# GET /admin/stripe/webhook-failures
# ---------------------------------------------------------------------------


class TestListWebhookFailures:
    def test_empty_list_when_no_failures(self, client, db):
        _make_user(db, "admin11@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin11@example.com")

        resp = client.get("/api/v1/admin/stripe/webhook-failures", headers=headers)

        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_unresolved_failures(self, client, db):
        _make_user(db, "admin12@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin12@example.com")
        _make_webhook_failure(db, session_id="cs_fail_1", error="DB constraint violation")

        resp = client.get("/api/v1/admin/stripe/webhook-failures", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["stripe_checkout_session_id"] == "cs_fail_1"
        assert data[0]["error_message"] == "DB constraint violation"
        assert data[0]["resolved_at"] is None

    def test_excludes_resolved_failures(self, client, db):
        _make_user(db, "admin13@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin13@example.com")
        _make_webhook_failure(db, session_id="cs_unresolved", resolved=False)
        _make_webhook_failure(db, session_id="cs_resolved", resolved=True)

        resp = client.get("/api/v1/admin/stripe/webhook-failures", headers=headers)

        data = resp.json()
        assert len(data) == 1
        assert data[0]["stripe_checkout_session_id"] == "cs_unresolved"

    def test_returns_failures_newest_first(self, client, db):
        _make_user(db, "admin14@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin14@example.com")
        _make_webhook_failure(db, session_id="cs_older")
        _make_webhook_failure(db, session_id="cs_newer")

        resp = client.get("/api/v1/admin/stripe/webhook-failures", headers=headers)

        session_ids = [d["stripe_checkout_session_id"] for d in resp.json()]
        assert session_ids.index("cs_newer") < session_ids.index("cs_older")

    def test_response_includes_required_fields(self, client, db):
        _make_user(db, "admin15@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin15@example.com")
        _make_webhook_failure(db, session_id="cs_check")

        resp = client.get("/api/v1/admin/stripe/webhook-failures", headers=headers)

        failure = resp.json()[0]
        assert "id" in failure
        assert "stripe_checkout_session_id" in failure
        assert "error_message" in failure
        assert "created_at" in failure
        assert "resolved_at" in failure


# ---------------------------------------------------------------------------
# POST /admin/stripe/webhook-failures/{failure_id}/retry
# ---------------------------------------------------------------------------


class TestRetryWebhookFailure:
    def test_unknown_failure_id_returns_404(self, client, db):
        _make_user(db, "admin16@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin16@example.com")

        resp = client.post(
            f"/api/v1/admin/stripe/webhook-failures/{uuid.uuid4()}/retry",
            headers=headers,
        )

        assert resp.status_code == 404

    def test_already_resolved_returns_409(self, client, db):
        _make_user(db, "admin17@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin17@example.com")
        failure = _make_webhook_failure(db, resolved=True)

        resp = client.post(
            f"/api/v1/admin/stripe/webhook-failures/{failure.id}/retry",
            headers=headers,
        )

        assert resp.status_code == 409
        assert "resolved" in resp.json()["detail"].lower()

    def test_handler_exception_returns_502_and_leaves_unresolved(self, client, db):
        """A failed retry must return 502 and leave resolved_at as None so the admin can retry
        again."""
        _make_user(db, "admin18@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin18@example.com")
        failure = _make_webhook_failure(db)

        with patch(
            "app.routers.stripe_router._handle_checkout_complete",
            side_effect=RuntimeError("Duplicate key violation"),
        ):
            resp = client.post(
                f"/api/v1/admin/stripe/webhook-failures/{failure.id}/retry",
                headers=headers,
            )

        assert resp.status_code == 502
        assert "Retry failed" in resp.json()["detail"]
        db.refresh(failure)
        assert failure.resolved_at is None

    def test_successful_retry_marks_resolved_at_and_returns_200(self, client, db):
        _make_user(db, "admin19@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "admin19@example.com")
        failure = _make_webhook_failure(db)

        with patch("app.routers.stripe_router._handle_checkout_complete", return_value=None):
            resp = client.post(
                f"/api/v1/admin/stripe/webhook-failures/{failure.id}/retry",
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"resolved": True}
        db.refresh(failure)
        assert failure.resolved_at is not None


# ---------------------------------------------------------------------------
# GET /admin/stats
# ---------------------------------------------------------------------------


class TestAdminStats:
    def test_returns_stats_for_empty_platform(self, client, db):
        _make_user(db, "stats1@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "stats1@example.com")

        resp = client.get("/api/v1/admin/stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_users"] >= 1  # at least the admin
        assert data["total_leagues"] >= 0
        assert data["total_picks"] >= 0
        assert data["tournaments_scheduled"] >= 0
        assert data["tournaments_in_progress"] >= 0
        assert data["tournaments_completed"] >= 0
        assert data["open_webhook_failures"] >= 0
        assert isinstance(data["leagues_by_tier"], list)
        assert isinstance(data["avg_members_per_league"], float)

    def test_stats_reflect_created_data(self, client, db):
        admin = _make_user(db, "stats2@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "stats2@example.com")

        # Create a league with a season, member, tournament, and pick
        league = League(name="Stats League", created_by=admin.id)
        db.add(league)
        db.flush()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=admin.id,
                role=LeagueMemberRole.MANAGER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        season = Season(league_id=league.id, year=date.today().year, is_active=True)
        db.add(season)
        db.flush()

        start = date(date.today().year, 1, 6)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Stats Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.COMPLETED.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))
        golfer = Golfer(pga_tour_id=f"G{uuid.uuid4().hex[:6]}", name="StatsGolfer")
        db.add(golfer)
        db.flush()
        db.add(TournamentEntry(tournament_id=t.id, golfer_id=golfer.id, earnings_usd=100_000))
        db.add(
            Pick(
                league_id=league.id,
                season_id=season.id,
                user_id=admin.id,
                tournament_id=t.id,
                golfer_id=golfer.id,
                points_earned=100_000,
            )
        )
        db.commit()

        resp = client.get("/api/v1/admin/stats", headers=headers)
        data = resp.json()
        assert data["total_leagues"] >= 1
        assert data["total_picks"] >= 1
        assert data["tournaments_completed"] >= 1
        assert data["total_approved_memberships"] >= 1

    def test_non_admin_gets_403(self, client, db):
        _make_user(db, "stats3@example.com", is_platform_admin=False)
        headers = _auth_headers(client, "stats3@example.com")
        resp = client.get("/api/v1/admin/stats", headers=headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /admin/import-members
# ---------------------------------------------------------------------------


def _make_league_for_import(db, admin: User) -> League:
    league = League(name="Import League", created_by=admin.id)
    db.add(league)
    db.flush()
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=admin.id,
            role=LeagueMemberRole.MANAGER.value,
            status=LeagueMemberStatus.APPROVED.value,
        )
    )
    db.add(Season(league_id=league.id, year=date.today().year, is_active=True))
    db.commit()
    db.refresh(league)
    return league


class TestImportMembers:
    def test_import_creates_users_and_members(self, client, db):
        admin = _make_user(db, "imp1@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "imp1@example.com")
        league = _make_league_for_import(db, admin)

        csv_content = "name,email\nAlice,alice@test.com\nBob,bob@test.com"
        resp = client.post(
            "/api/v1/admin/import-members",
            headers=headers,
            data={"league_id": str(league.id)},
            files={"file": ("members.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accounts_created"] == 2
        assert data["members_added"] == 2
        assert data["errors"] == []

    def test_import_skips_existing_members(self, client, db):
        admin = _make_user(db, "imp2@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "imp2@example.com")
        league = _make_league_for_import(db, admin)

        # Admin is already a member — importing their email should skip
        csv_content = "name,email\nAdmin,imp2@example.com"
        resp = client.post(
            "/api/v1/admin/import-members",
            headers=headers,
            data={"league_id": str(league.id)},
            files={"file": ("members.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped_already_in_league"] == 1
        assert data["members_added"] == 0

    def test_import_empty_csv_returns_422(self, client, db):
        admin = _make_user(db, "imp3@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "imp3@example.com")
        league = _make_league_for_import(db, admin)

        csv_content = "name,email\n"
        resp = client.post(
            "/api/v1/admin/import-members",
            headers=headers,
            data={"league_id": str(league.id)},
            files={"file": ("members.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 422

    def test_import_missing_columns_returns_422(self, client, db):
        admin = _make_user(db, "imp4@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "imp4@example.com")
        league = _make_league_for_import(db, admin)

        csv_content = "foo,bar\nAlice,alice@test.com"
        resp = client.post(
            "/api/v1/admin/import-members",
            headers=headers,
            data={"league_id": str(league.id)},
            files={"file": ("members.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 422
        assert "name" in resp.json()["detail"].lower()

    def test_import_invalid_league_returns_404(self, client, db):
        _make_user(db, "imp5@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "imp5@example.com")

        csv_content = "name,email\nAlice,alice@test.com"
        fake_id = str(uuid.uuid4())
        resp = client.post(
            "/api/v1/admin/import-members",
            headers=headers,
            data={"league_id": fake_id},
            files={"file": ("members.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 404

    def test_import_row_with_missing_email_reports_error(self, client, db):
        admin = _make_user(db, "imp6@example.com", is_platform_admin=True)
        headers = _auth_headers(client, "imp6@example.com")
        league = _make_league_for_import(db, admin)

        csv_content = "name,email\nAlice,\nBob,bob@test.com"
        resp = client.post(
            "/api/v1/admin/import-members",
            headers=headers,
            data={"league_id": str(league.id)},
            files={"file": ("members.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["errors"]) == 1
        assert "Row 2" in data["errors"][0]
        assert data["members_added"] == 1


# ---------------------------------------------------------------------------
# POST /admin/import-picks
# ---------------------------------------------------------------------------


class TestImportPicks:
    def _setup(self, db, admin_email: str):
        admin = _make_user(db, admin_email, is_platform_admin=True)
        league = _make_league_for_import(db, admin)
        season = db.query(Season).filter_by(league_id=league.id).first()

        # Create a member
        member = _make_user(db, f"mem_{admin_email}")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )

        # Create tournament in league schedule
        start = date(date.today().year, 2, 1)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Import Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.COMPLETED.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))

        golfer = Golfer(pga_tour_id=f"G{uuid.uuid4().hex[:6]}", name="Import Golfer")
        db.add(golfer)
        db.flush()
        db.add(TournamentEntry(tournament_id=t.id, golfer_id=golfer.id, earnings_usd=200_000))
        db.commit()
        return admin, league, season, member, t, golfer

    def test_import_picks_creates_picks(self, client, db):
        admin, league, season, member, t, golfer = self._setup(db, "pickimp1@example.com")
        headers = _auth_headers(client, "pickimp1@example.com")

        csv_content = "email,golfer_name\nmem_pickimp1@example.com,Import Golfer"
        resp = client.post(
            "/api/v1/admin/import-picks",
            headers=headers,
            data={"league_id": str(league.id), "tournament_id": str(t.id)},
            files={"file": ("picks.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["picks_created"] >= 1
        assert data["errors"] == []

    def test_import_picks_missing_columns_returns_422(self, client, db):
        admin, league, season, member, t, golfer = self._setup(db, "pickimp2@example.com")
        headers = _auth_headers(client, "pickimp2@example.com")

        csv_content = "foo,bar\nval1,val2"
        resp = client.post(
            "/api/v1/admin/import-picks",
            headers=headers,
            data={"league_id": str(league.id), "tournament_id": str(t.id)},
            files={"file": ("picks.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 422

    def test_import_picks_unknown_email_returns_422(self, client, db):
        """Unknown email in CSV triggers validation failure (no data written)."""
        admin, league, season, member, t, golfer = self._setup(db, "pickimp3@example.com")
        headers = _auth_headers(client, "pickimp3@example.com")

        csv_content = "email,golfer_name\nnoone@test.com,Import Golfer"
        resp = client.post(
            "/api/v1/admin/import-picks",
            headers=headers,
            data={"league_id": str(league.id), "tournament_id": str(t.id)},
            files={"file": ("picks.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 422
        assert "user not found" in str(resp.json()["detail"]).lower()

    def test_import_picks_no_pick_row_skipped(self, client, db):
        admin, league, season, member, t, golfer = self._setup(db, "pickimp4@example.com")
        headers = _auth_headers(client, "pickimp4@example.com")

        csv_content = "email,golfer_name\nmem_pickimp4@example.com,No Pick"
        resp = client.post(
            "/api/v1/admin/import-picks",
            headers=headers,
            data={"league_id": str(league.id), "tournament_id": str(t.id)},
            files={"file": ("picks.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["skipped_no_pick"] >= 1
