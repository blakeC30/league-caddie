"""
Tests for league management, membership, join flow, and tournament scheduling.

Covers all major HTTP paths through the leagues router. The goal is meaningful
behavior verification — not exhaustive permutation testing.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import (
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    Season,
    Tournament,
    TournamentStatus,
    User,
)
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_user(db: Session, email: str, display_name: str = "Test") -> User:
    user = User(email=email, password_hash=hash_password("password123"), display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_league(db: Session, creator: User, name: str = "Test League") -> tuple[League, Season]:
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


def make_tournament(db: Session, days_from_now: int = 7) -> Tournament:
    start = date.today() + timedelta(days=days_from_now)
    t = Tournament(
        pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
        name=f"Open {uuid.uuid4().hex[:4]}",
        start_date=start,
        end_date=start + timedelta(days=3),
        status=TournamentStatus.SCHEDULED.value,
        multiplier=1.0,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _login_headers(client, email: str, password: str = "password123") -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _register_and_login(client, email: str, display_name: str = "User") -> dict:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": display_name},
    )
    return _login_headers(client, email)


# ---------------------------------------------------------------------------
# League creation
# ---------------------------------------------------------------------------


class TestCreateLeague:
    def test_create_league_success(self, client, auth_headers):
        resp = client.post(
            "/api/v1/leagues",
            headers=auth_headers,
            json={"name": "My League"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My League"
        assert "invite_code" in data
        assert data["no_pick_penalty"] == -50_000

    def test_create_league_with_custom_penalty(self, client, auth_headers):
        resp = client.post(
            "/api/v1/leagues",
            headers=auth_headers,
            json={"name": "Low Penalty League", "no_pick_penalty": -25_000},
        )
        assert resp.status_code == 201
        assert resp.json()["no_pick_penalty"] == -25_000

    def test_create_league_requires_authentication(self, client):
        resp = client.post("/api/v1/leagues", json={"name": "No Auth"})
        assert resp.status_code == 401

    def test_creator_is_automatically_made_manager(self, client, auth_headers, db):
        resp = client.post(
            "/api/v1/leagues",
            headers=auth_headers,
            json={"name": "Auto Manager"},
        )
        assert resp.status_code == 201
        league_id = uuid.UUID(resp.json()["id"])

        # The creator should be an approved manager — they can immediately GET the league.
        get_resp = client.get(f"/api/v1/leagues/{league_id}", headers=auth_headers)
        assert get_resp.status_code == 200


# ---------------------------------------------------------------------------
# League detail
# ---------------------------------------------------------------------------


class TestLeagueDetail:
    def test_member_can_get_league_details(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.get(f"/api/v1/leagues/{league.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test League"
        assert "invite_code" in data

    def test_non_member_receives_403(self, client, auth_headers, db):
        creator = make_user(db, "other_creator@example.com")
        league, _ = make_league(db, creator)

        # auth_headers is for test@example.com who is NOT a member of creator's league.
        resp = client.get(f"/api/v1/leagues/{league.id}", headers=auth_headers)
        assert resp.status_code == 403

    def test_nonexistent_league_returns_404(self, client, auth_headers):
        resp = client.get(f"/api/v1/leagues/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    def test_pending_member_receives_403_with_helpful_message(self, client, db):
        creator = make_user(db, "pending_host@example.com")
        league, _ = make_league(db, creator)

        headers = _register_and_login(client, "pending_joiner@example.com")
        client.post(f"/api/v1/leagues/join/{league.invite_code}", headers=headers)

        resp = client.get(f"/api/v1/leagues/{league.id}", headers=headers)
        assert resp.status_code == 403
        assert "pending" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# League update
# ---------------------------------------------------------------------------


class TestUpdateLeague:
    def test_manager_can_rename_league(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=auth_headers,
            json={"name": "Renamed League"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed League"

    def test_manager_can_update_no_pick_penalty(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=auth_headers,
            json={"no_pick_penalty": -10_000},
        )
        assert resp.status_code == 200
        assert resp.json()["no_pick_penalty"] == -10_000

    def test_regular_member_cannot_update_league(self, client, db):
        creator = make_user(db, "update_host@example.com")
        league, _ = make_league(db, creator)

        headers = _register_and_login(client, "update_member@example.com", "Member")
        member = db.query(User).filter_by(email="update_member@example.com").first()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        resp = client.patch(
            f"/api/v1/leagues/{league.id}", headers=headers, json={"name": "Hacked Name"}
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# League deletion
# ---------------------------------------------------------------------------


class TestDeleteLeague:
    def test_manager_can_delete_league(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)
        league_id = league.id

        resp = client.delete(f"/api/v1/leagues/{league_id}", headers=auth_headers)
        assert resp.status_code == 204

        # Confirm it is gone.
        assert client.get(f"/api/v1/leagues/{league_id}", headers=auth_headers).status_code == 404

    def test_regular_member_cannot_delete_league(self, client, db):
        creator = make_user(db, "del_host@example.com")
        league, _ = make_league(db, creator)

        headers = _register_and_login(client, "del_member@example.com", "Member")
        member = db.query(User).filter_by(email="del_member@example.com").first()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        resp = client.delete(f"/api/v1/leagues/{league.id}", headers=headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Invite / join flow
# ---------------------------------------------------------------------------


class TestJoinFlow:
    def test_preview_invite_shows_league_info(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.get(f"/api/v1/leagues/join/{league.invite_code}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test League"
        assert data["member_count"] == 1
        # Creator previewing their own league sees themselves as "approved".
        assert data["user_status"] == "approved"

    def test_preview_invalid_invite_code_returns_404(self, client, auth_headers):
        resp = client.get("/api/v1/leagues/join/not-a-real-code", headers=auth_headers)
        assert resp.status_code == 404

    def test_join_request_creates_pending_membership(self, client, db):
        creator = make_user(db, "jf_host@example.com")
        league, _ = make_league(db, creator)

        headers = _register_and_login(client, "jf_joiner@example.com", "Joiner")
        resp = client.post(f"/api/v1/leagues/join/{league.invite_code}", headers=headers)
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"

    def test_duplicate_join_request_returns_409(self, client, db):
        creator = make_user(db, "dup_host@example.com")
        league, _ = make_league(db, creator)

        headers = _register_and_login(client, "dup_joiner@example.com", "Dup")
        client.post(f"/api/v1/leagues/join/{league.invite_code}", headers=headers)

        resp = client.post(f"/api/v1/leagues/join/{league.invite_code}", headers=headers)
        assert resp.status_code == 409

    def test_already_member_join_request_returns_409(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        # Creator (already an approved member) attempts to join their own league.
        resp = client.post(f"/api/v1/leagues/join/{league.invite_code}", headers=auth_headers)
        assert resp.status_code == 409

    def test_invalid_invite_code_join_returns_404(self, client, auth_headers):
        resp = client.post("/api/v1/leagues/join/definitely-not-real", headers=auth_headers)
        assert resp.status_code == 404

    def test_manager_can_approve_join_request(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        pending = make_user(db, "approve_me@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=pending.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.PENDING.value,
            )
        )
        db.commit()

        resp = client.post(
            f"/api/v1/leagues/{league.id}/requests/{pending.id}/approve",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_manager_can_deny_join_request(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        pending = make_user(db, "deny_me@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=pending.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.PENDING.value,
            )
        )
        db.commit()

        resp = client.delete(
            f"/api/v1/leagues/{league.id}/requests/{pending.id}", headers=auth_headers
        )
        assert resp.status_code == 204

        # The membership record should be completely removed, not just status-changed.
        assert (
            db.query(LeagueMember).filter_by(league_id=league.id, user_id=pending.id).first()
            is None
        )

    def test_user_can_cancel_own_join_request(self, client, db):
        creator = make_user(db, "cancel_host@example.com")
        league, _ = make_league(db, creator)

        headers = _register_and_login(client, "canceller@example.com", "Canceller")
        client.post(f"/api/v1/leagues/join/{league.invite_code}", headers=headers)

        resp = client.delete(f"/api/v1/leagues/{league.id}/requests/me", headers=headers)
        assert resp.status_code == 204

    def test_list_pending_requests_returns_only_pending(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        pending = make_user(db, "pending_list@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=pending.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.PENDING.value,
            )
        )
        db.commit()

        resp = client.get(f"/api/v1/leagues/{league.id}/requests", headers=auth_headers)
        assert resp.status_code == 200
        ids = [r["user_id"] for r in resp.json()]
        assert str(pending.id) in ids
        # The manager (approved) should not appear in pending requests.
        assert str(user.id) not in ids

    def test_my_join_requests_endpoint(self, client, db):
        creator = make_user(db, "my_req_host@example.com")
        league, _ = make_league(db, creator)

        headers = _register_and_login(client, "my_req_joiner@example.com", "Joiner")
        client.post(f"/api/v1/leagues/join/{league.invite_code}", headers=headers)

        resp = client.get("/api/v1/leagues/my-requests", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["league_name"] == league.name


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


class TestMemberManagement:
    def test_list_approved_members(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.get(f"/api/v1/leagues/{league.id}/members", headers=auth_headers)
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) == 1
        assert members[0]["role"] == "manager"

    def test_pending_members_not_included_in_member_list(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        pending = make_user(db, "pending_list2@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=pending.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.PENDING.value,
            )
        )
        db.commit()

        resp = client.get(f"/api/v1/leagues/{league.id}/members", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1  # Only the approved manager.

    def test_manager_can_promote_member_to_manager(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        other = make_user(db, "promotee@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=other.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        resp = client.patch(
            f"/api/v1/leagues/{league.id}/members/{other.id}/role",
            headers=auth_headers,
            json={"role": "manager"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "manager"

    def test_manager_can_demote_manager_to_member(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        co_manager = make_user(db, "demotee@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=co_manager.id,
                role=LeagueMemberRole.MANAGER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        resp = client.patch(
            f"/api/v1/leagues/{league.id}/members/{co_manager.id}/role",
            headers=auth_headers,
            json={"role": "member"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "member"

    def test_member_can_leave_league(self, client, db):
        creator = make_user(db, "leave_host@example.com")
        league, _ = make_league(db, creator)

        headers = _register_and_login(client, "leaver@example.com", "Leaver")
        leaver = db.query(User).filter_by(email="leaver@example.com").first()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=leaver.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        resp = client.delete(f"/api/v1/leagues/{league.id}/members/me", headers=headers)
        assert resp.status_code == 204

    def test_manager_can_remove_member(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        target = make_user(db, "remove_target@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=target.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        resp = client.delete(
            f"/api/v1/leagues/{league.id}/members/{target.id}", headers=auth_headers
        )
        assert resp.status_code == 204

    def test_manager_cannot_remove_themselves(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.delete(f"/api/v1/leagues/{league.id}/members/{user.id}", headers=auth_headers)
        assert resp.status_code == 400

    def test_removing_nonexistent_member_returns_404(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.delete(
            f"/api/v1/leagues/{league.id}/members/{uuid.uuid4()}", headers=auth_headers
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tournament schedule management
# ---------------------------------------------------------------------------


class TestTournamentSchedule:
    def test_empty_schedule_returns_empty_list(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.get(f"/api/v1/leagues/{league.id}/tournaments", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_put_schedule_adds_tournament(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)
        t = make_tournament(db, days_from_now=7)

        resp = client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            headers=auth_headers,
            json={"tournaments": [{"tournament_id": str(t.id)}]},
        )
        assert resp.status_code == 200
        schedule = resp.json()
        assert len(schedule) == 1
        assert schedule[0]["id"] == str(t.id)

    def test_put_schedule_atomically_replaces_existing(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)
        t1 = make_tournament(db, days_from_now=7)
        t2 = make_tournament(db, days_from_now=14)

        client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            headers=auth_headers,
            json={"tournaments": [{"tournament_id": str(t1.id)}]},
        )
        resp = client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            headers=auth_headers,
            json={"tournaments": [{"tournament_id": str(t2.id)}]},
        )
        assert resp.status_code == 200
        ids = [row["id"] for row in resp.json()]
        assert str(t1.id) not in ids
        assert str(t2.id) in ids

    def test_put_schedule_with_multiplier_override(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)
        t = make_tournament(db, days_from_now=7)

        resp = client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            headers=auth_headers,
            json={"tournaments": [{"tournament_id": str(t.id), "multiplier": 2.0}]},
        )
        assert resp.status_code == 200
        assert resp.json()[0]["effective_multiplier"] == 2.0

    def test_put_schedule_clears_all_when_empty_list(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)
        t = make_tournament(db, days_from_now=7)

        client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            headers=auth_headers,
            json={"tournaments": [{"tournament_id": str(t.id)}]},
        )
        resp = client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            headers=auth_headers,
            json={"tournaments": []},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_put_schedule_invalid_tournament_id_returns_422(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            headers=auth_headers,
            json={"tournaments": [{"tournament_id": str(uuid.uuid4())}]},
        )
        assert resp.status_code == 422

    def test_put_schedule_two_tournaments_same_week_rejected(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        # Ensure both dates fall within the same ISO calendar week.
        anchor = date.today() + timedelta(days=14)
        monday = anchor - timedelta(days=anchor.weekday())  # Monday of that week
        thursday = monday + timedelta(days=3)  # Thursday of same week

        t1 = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Monday Open",
            start_date=monday,
            end_date=monday + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
            multiplier=1.0,
        )
        t2 = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Thursday Open",
            start_date=thursday,
            end_date=thursday + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
            multiplier=1.0,
        )
        db.add_all([t1, t2])
        db.commit()

        resp = client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            headers=auth_headers,
            json={
                "tournaments": [
                    {"tournament_id": str(t1.id)},
                    {"tournament_id": str(t2.id)},
                ]
            },
        )
        assert resp.status_code == 422
        assert "same week" in resp.json()["detail"].lower()

    def test_only_manager_can_update_schedule(self, client, db):
        creator = make_user(db, "sched_host@example.com")
        league, _ = make_league(db, creator)
        t = make_tournament(db, days_from_now=7)

        headers = _register_and_login(client, "sched_member@example.com", "Member")
        member = db.query(User).filter_by(email="sched_member@example.com").first()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        resp = client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            headers=headers,
            json={"tournaments": [{"tournament_id": str(t.id)}]},
        )
        assert resp.status_code == 403
