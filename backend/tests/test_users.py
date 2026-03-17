"""
Tests for the users router: profile retrieval, updates, and league listing.
"""

from datetime import date

from app.models import League, LeagueMember, LeagueMemberRole, LeagueMemberStatus, Season, User

# ---------------------------------------------------------------------------
# GET /users/me
# ---------------------------------------------------------------------------


class TestGetMe:
    def test_returns_current_user_profile(self, client, auth_headers):
        resp = client.get("/api/v1/users/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "test@example.com"
        assert data["display_name"] == "Test User"

    def test_sensitive_fields_not_exposed(self, client, auth_headers):
        resp = client.get("/api/v1/users/me", headers=auth_headers)
        data = resp.json()
        assert "password_hash" not in data
        assert "google_id" not in data

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/v1/users/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /users/me
# ---------------------------------------------------------------------------


class TestUpdateMe:
    def test_update_display_name(self, client, auth_headers):
        resp = client.patch(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"display_name": "Updated Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated Name"

        # Verify the change persists on subsequent GET.
        get_resp = client.get("/api/v1/users/me", headers=auth_headers)
        assert get_resp.json()["display_name"] == "Updated Name"

    def test_update_pick_reminders_disabled(self, client, auth_headers):
        resp = client.patch(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"pick_reminders_enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["pick_reminders_enabled"] is False

    def test_update_pick_reminders_re_enabled(self, client, auth_headers):
        client.patch(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"pick_reminders_enabled": False},
        )
        resp = client.patch(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"pick_reminders_enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json()["pick_reminders_enabled"] is True

    def test_empty_display_name_rejected(self, client, auth_headers):
        resp = client.patch(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"display_name": ""},
        )
        assert resp.status_code == 422

    def test_partial_update_only_changes_specified_fields(self, client, auth_headers):
        """Passing only one field must not reset the other."""
        # Establish a known state.
        client.patch(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"pick_reminders_enabled": False, "display_name": "Known Name"},
        )

        # Update only the name.
        resp = client.patch(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"display_name": "New Name Only"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "New Name Only"
        assert data["pick_reminders_enabled"] is False  # Unchanged.

    def test_unauthenticated_cannot_update_profile(self, client):
        resp = client.patch("/api/v1/users/me", json={"display_name": "Hacker"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /users/me/leagues
# ---------------------------------------------------------------------------


class TestMyLeagues:
    def test_returns_empty_list_when_not_in_any_league(self, client, auth_headers):
        resp = client.get("/api/v1/users/me/leagues", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_approved_leagues(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league = League(name="My League", created_by=user.id)
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
        db.add(Season(league_id=league.id, year=date.today().year, is_active=True))
        db.commit()

        resp = client.get("/api/v1/users/me/leagues", headers=auth_headers)
        assert resp.status_code == 200
        names = [lg["name"] for lg in resp.json()]
        assert "My League" in names

    def test_pending_leagues_not_returned(self, client, auth_headers, db):
        """Leagues where the user is still pending approval are excluded."""
        from app.services.auth import hash_password

        user = db.query(User).filter_by(email="test@example.com").first()

        # Create a league owned by someone else.
        other = User(
            email="other_lg@example.com",
            password_hash=hash_password("password123"),
            display_name="Other",
        )
        db.add(other)
        db.flush()
        league = League(name="Pending League", created_by=other.id)
        db.add(league)
        db.flush()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=other.id,
                role=LeagueMemberRole.MANAGER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        # Add user with PENDING status.
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=user.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.PENDING.value,
            )
        )
        db.commit()

        resp = client.get("/api/v1/users/me/leagues", headers=auth_headers)
        names = [lg["name"] for lg in resp.json()]
        assert "Pending League" not in names
