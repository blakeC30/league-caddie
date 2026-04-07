"""
Tests for the manager league email feature.

Covers:
  - Sending email to all opted-in members
  - Sending email to selected members
  - Opted-out members excluded from recipient count
  - Regular members cannot send (403)
  - DB-enforced 1-per-day limit
  - Validation: empty subject, empty body, no eligible recipients
  - Email history endpoint (manager only)
  - Audit record created with correct data
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import (
    League,
    LeagueEmail,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    Season,
    User,
)
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(db: Session, email: str, **kwargs) -> User:
    u = User(
        email=email,
        password_hash=hash_password("password123"),
        display_name=kwargs.get("display_name", "Player"),
        **{k: v for k, v in kwargs.items() if k != "display_name"},
    )
    db.add(u)
    db.flush()
    return u


def _login(client, email: str) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _setup_league(db, *, suffix="", member_count=2, opted_out_count=0):
    """Create a league with a manager and N-1 members.

    opted_out_count members (from the end) will have manager_emails_enabled=False.
    Returns (manager_email, league, all_user_ids).
    """
    sfx = suffix or uuid.uuid4().hex[:4]
    manager = _make_user(db, f"mgr_{sfx}@test.com", display_name="Manager")
    league = League(name=f"Email League {sfx}", created_by=manager.id)
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

    all_user_ids = [manager.id]
    for i in range(member_count - 1):
        opted_out = i >= (member_count - 1 - opted_out_count)
        m = _make_user(
            db,
            f"m{i}_{sfx}@test.com",
            display_name=f"Member {i}",
            manager_emails_enabled=not opted_out,
        )
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=m.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        all_user_ids.append(m.id)

    db.commit()
    db.refresh(league)
    return f"mgr_{sfx}@test.com", league, all_user_ids


# ---------------------------------------------------------------------------
# POST /leagues/{id}/send-email
# ---------------------------------------------------------------------------


class TestSendLeagueEmail:
    """Manager sends email to league members."""

    def test_send_to_all_members(self, client, db):
        """Empty recipient_user_ids → sends to all opted-in members."""
        email, league, _ = _setup_league(db, suffix="all", member_count=4)
        headers = _login(client, email)

        resp = client.post(
            f"/api/v1/leagues/{league.id}/send-email",
            headers=headers,
            json={
                "recipient_user_ids": [],
                "subject": "Season update",
                "body": "Hello everyone!",
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["subject"] == "Season update"
        assert data["recipient_count"] == 4  # manager + 3 members

    def test_send_to_selected_members(self, client, db):
        """Specific user IDs → only those members receive the email."""
        email, league, user_ids = _setup_league(db, suffix="sel", member_count=4)
        headers = _login(client, email)

        # Send to only 2 of the 4 members.
        selected = [str(user_ids[0]), str(user_ids[1])]
        resp = client.post(
            f"/api/v1/leagues/{league.id}/send-email",
            headers=headers,
            json={
                "recipient_user_ids": selected,
                "subject": "Private note",
                "body": "Just for you two.",
            },
        )
        assert resp.status_code == 202
        assert resp.json()["recipient_count"] == 2

    def test_opted_out_members_excluded(self, client, db):
        """Members with manager_emails_enabled=False are not counted."""
        email, league, _ = _setup_league(db, suffix="opt", member_count=5, opted_out_count=2)
        headers = _login(client, email)

        resp = client.post(
            f"/api/v1/leagues/{league.id}/send-email",
            headers=headers,
            json={
                "recipient_user_ids": [],
                "subject": "Update",
                "body": "Some news.",
            },
        )
        assert resp.status_code == 202
        # 5 total members, 2 opted out → 3 recipients
        assert resp.json()["recipient_count"] == 3

    def test_all_opted_out_returns_422(self, client, db):
        """If every member opted out, returns 422."""
        email, league, _ = _setup_league(db, suffix="norecip", member_count=3, opted_out_count=2)
        # Opt out the manager too.
        mgr = db.query(User).filter_by(email=email).first()
        mgr.manager_emails_enabled = False
        db.commit()

        headers = _login(client, email)
        resp = client.post(
            f"/api/v1/leagues/{league.id}/send-email",
            headers=headers,
            json={
                "recipient_user_ids": [],
                "subject": "Hello?",
                "body": "Anyone there?",
            },
        )
        assert resp.status_code == 422
        assert "opted out" in resp.json()["detail"].lower()

    def test_regular_member_cannot_send(self, client, db):
        """Non-managers get 403."""
        _, league, user_ids = _setup_league(db, suffix="perm", member_count=3)
        # Log in as a regular member, not the manager.
        member = db.query(User).filter_by(id=user_ids[1]).first()
        headers = _login(client, member.email)

        resp = client.post(
            f"/api/v1/leagues/{league.id}/send-email",
            headers=headers,
            json={
                "recipient_user_ids": [],
                "subject": "Unauthorized",
                "body": "Should fail.",
            },
        )
        assert resp.status_code == 403

    def test_one_per_day_db_enforced(self, client, db):
        """Second email within 24 hours is rejected (DB check, not rate limit)."""
        email, league, _ = _setup_league(db, suffix="daily", member_count=2)
        headers = _login(client, email)

        # First email succeeds.
        resp1 = client.post(
            f"/api/v1/leagues/{league.id}/send-email",
            headers=headers,
            json={
                "recipient_user_ids": [],
                "subject": "First",
                "body": "First email.",
            },
        )
        assert resp1.status_code == 202

        # Second email within 24h fails.
        resp2 = client.post(
            f"/api/v1/leagues/{league.id}/send-email",
            headers=headers,
            json={
                "recipient_user_ids": [],
                "subject": "Second",
                "body": "Should be blocked.",
            },
        )
        assert resp2.status_code == 422
        assert "one email per day" in resp2.json()["detail"].lower()

    def test_daily_limit_resets_after_24h(self, client, db):
        """An email sent >24h ago does not block a new one."""
        email, league, _ = _setup_league(db, suffix="reset", member_count=2)
        headers = _login(client, email)

        # Insert a stale audit record from 25 hours ago.
        old_email = LeagueEmail(
            league_id=league.id,
            sender_id=db.query(User).filter_by(email=email).first().id,
            subject="Old",
            body="Old email.",
            recipient_count=2,
            created_at=datetime.now(UTC) - timedelta(hours=25),
        )
        db.add(old_email)
        db.commit()

        # New email should succeed.
        resp = client.post(
            f"/api/v1/leagues/{league.id}/send-email",
            headers=headers,
            json={
                "recipient_user_ids": [],
                "subject": "New",
                "body": "Should work.",
            },
        )
        assert resp.status_code == 202

    def test_subject_too_long_rejected(self, client, db):
        email, league, _ = _setup_league(db, suffix="subj", member_count=2)
        headers = _login(client, email)

        resp = client.post(
            f"/api/v1/leagues/{league.id}/send-email",
            headers=headers,
            json={
                "recipient_user_ids": [],
                "subject": "A" * 101,
                "body": "Body text.",
            },
        )
        assert resp.status_code == 422

    def test_empty_body_rejected(self, client, db):
        email, league, _ = _setup_league(db, suffix="body", member_count=2)
        headers = _login(client, email)

        resp = client.post(
            f"/api/v1/leagues/{league.id}/send-email",
            headers=headers,
            json={
                "recipient_user_ids": [],
                "subject": "Valid subject",
                "body": "",
            },
        )
        assert resp.status_code == 422

    def test_audit_record_created(self, client, db):
        """The LeagueEmail audit row has correct sender and league."""
        email, league, _ = _setup_league(db, suffix="audit", member_count=3)
        headers = _login(client, email)
        mgr = db.query(User).filter_by(email=email).first()

        resp = client.post(
            f"/api/v1/leagues/{league.id}/send-email",
            headers=headers,
            json={
                "recipient_user_ids": [],
                "subject": "Audit test",
                "body": "Check the DB.",
            },
        )
        assert resp.status_code == 202

        record = db.query(LeagueEmail).filter_by(league_id=league.id).first()
        assert record is not None
        assert record.sender_id == mgr.id
        assert record.subject == "Audit test"
        assert record.body == "Check the DB."
        assert record.recipient_count == 3


# ---------------------------------------------------------------------------
# GET /leagues/{id}/emails
# ---------------------------------------------------------------------------


class TestGetLeagueEmails:
    """Email history is manager-only and returns recent emails."""

    def test_returns_recent_emails(self, client, db):
        email, league, _ = _setup_league(db, suffix="hist", member_count=2)
        headers = _login(client, email)
        mgr = db.query(User).filter_by(email=email).first()

        # Insert some audit records directly.
        for i in range(3):
            db.add(
                LeagueEmail(
                    league_id=league.id,
                    sender_id=mgr.id,
                    subject=f"Email {i}",
                    body=f"Body {i}",
                    recipient_count=2,
                    created_at=datetime.now(UTC) - timedelta(days=i + 2),
                )
            )
        db.commit()

        resp = client.get(f"/api/v1/leagues/{league.id}/emails", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        # Ordered by created_at desc — most recent first.
        assert data[0]["subject"] == "Email 0"

    def test_regular_member_cannot_view(self, client, db):
        _, league, user_ids = _setup_league(db, suffix="histperm", member_count=2)
        member = db.query(User).filter_by(id=user_ids[1]).first()
        headers = _login(client, member.email)

        resp = client.get(f"/api/v1/leagues/{league.id}/emails", headers=headers)
        assert resp.status_code == 403

    def test_empty_history(self, client, db):
        email, league, _ = _setup_league(db, suffix="empty", member_count=2)
        headers = _login(client, email)

        resp = client.get(f"/api/v1/leagues/{league.id}/emails", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []
