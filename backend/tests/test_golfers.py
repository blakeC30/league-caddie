"""
Tests for the global golfer search endpoint.

Golfers are populated by the scraper; tests insert rows directly to verify
the listing, search, ranking, and 404 behavior.
"""

import uuid

from sqlalchemy.orm import Session

from app.models import Golfer

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_golfer(
    db: Session,
    name: str,
    ranking: int | None = None,
    country: str | None = None,
) -> Golfer:
    g = Golfer(
        pga_tour_id=f"T{uuid.uuid4().hex[:8]}",
        name=name,
        world_ranking=ranking,
        country=country,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


# ---------------------------------------------------------------------------
# GET /golfers
# ---------------------------------------------------------------------------


class TestListGolfers:
    def test_empty_list_when_no_golfers_exist(self, client, auth_headers):
        resp = client.get("/api/v1/golfers", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all_golfers(self, client, auth_headers, db):
        make_golfer(db, "Tiger Woods", ranking=10)
        make_golfer(db, "Rory McIlroy", ranking=1)

        resp = client.get("/api/v1/golfers", headers=auth_headers)
        assert resp.status_code == 200
        names = [g["name"] for g in resp.json()]
        assert "Tiger Woods" in names
        assert "Rory McIlroy" in names

    def test_results_sorted_by_world_ranking_ascending(self, client, auth_headers, db):
        make_golfer(db, "Ranked 5", ranking=5)
        make_golfer(db, "Ranked 1", ranking=1)
        make_golfer(db, "Ranked 3", ranking=3)

        resp = client.get("/api/v1/golfers", headers=auth_headers)
        names = [g["name"] for g in resp.json()]
        assert names == ["Ranked 1", "Ranked 3", "Ranked 5"]

    def test_unranked_golfers_sorted_last(self, client, auth_headers, db):
        make_golfer(db, "Ranked 2", ranking=2)
        make_golfer(db, "Unranked")  # world_ranking=None

        resp = client.get("/api/v1/golfers", headers=auth_headers)
        names = [g["name"] for g in resp.json()]
        assert names[0] == "Ranked 2"
        assert names[-1] == "Unranked"

    def test_search_filters_by_name_substring(self, client, auth_headers, db):
        make_golfer(db, "Tiger Woods")
        make_golfer(db, "Rory McIlroy")

        resp = client.get("/api/v1/golfers?search=tiger", headers=auth_headers)
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["name"] == "Tiger Woods"

    def test_search_is_case_insensitive(self, client, auth_headers, db):
        make_golfer(db, "Jon Rahm")

        resp = client.get("/api/v1/golfers?search=JON", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "Jon Rahm"

    def test_search_matches_partial_last_name(self, client, auth_headers, db):
        make_golfer(db, "Scottie Scheffler")
        make_golfer(db, "Xander Schauffele")

        resp = client.get("/api/v1/golfers?search=scheff", headers=auth_headers)
        names = [g["name"] for g in resp.json()]
        assert "Scottie Scheffler" in names
        assert "Xander Schauffele" not in names

    def test_search_returns_empty_when_no_match(self, client, auth_headers, db):
        make_golfer(db, "Dustin Johnson")

        resp = client.get("/api/v1/golfers?search=nobody", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_response_includes_expected_fields(self, client, auth_headers, db):
        make_golfer(db, "Brooks Koepka", ranking=7, country="United States")

        resp = client.get("/api/v1/golfers?search=Brooks", headers=auth_headers)
        golfer = resp.json()[0]
        assert "id" in golfer
        assert "pga_tour_id" in golfer
        assert "name" in golfer
        assert "world_ranking" in golfer
        assert "country" in golfer
        assert golfer["country"] == "United States"
        assert golfer["world_ranking"] == 7

    def test_unauthenticated_request_returns_401(self, client):
        resp = client.get("/api/v1/golfers")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /golfers/{golfer_id}
# ---------------------------------------------------------------------------


class TestGetGolfer:
    def test_get_golfer_by_id_returns_details(self, client, auth_headers, db):
        golfer = make_golfer(db, "Dustin Johnson", ranking=15, country="United States")

        resp = client.get(f"/api/v1/golfers/{golfer.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Dustin Johnson"
        assert data["world_ranking"] == 15
        assert data["country"] == "United States"

    def test_nonexistent_golfer_returns_404(self, client, auth_headers):
        resp = client.get(f"/api/v1/golfers/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    def test_unauthenticated_request_returns_401(self, client, db):
        golfer = make_golfer(db, "Phil Mickelson")
        resp = client.get(f"/api/v1/golfers/{golfer.id}")
        assert resp.status_code == 401
