"""Automated test suite for the Minnesota Park & Campsite Explorer FastAPI application."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_and_dataset_loaded():
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["total_campsites"] >= 5500
        assert data["total_parks"] >= 100


def test_index_page_renders():
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Minnesota Park &amp; Campsite Explorer" in resp.text
        assert "Sign in with Google" in resp.text


def test_metadata_and_parks_endpoints():
    with TestClient(app) as client:
        meta_resp = client.get("/api/metadata")
        assert meta_resp.status_code == 200
        meta = meta_resp.json()
        assert meta["sheet_id"] == "1CW-0euFLFz24nzcXNrTY24IoqTX9BCHLX5fdLjxAHgk"
        assert meta["sheet_gid"] == "459530859"
        assert "Afton State Park" in meta["facets"]["parks"]
        assert "Northeast" in meta["facets"]["tourism_regions"]

        parks_resp = client.get("/api/parks")
        assert parks_resp.status_code == 200
        parks_data = parks_resp.json()
        assert parks_data["total"] == 109


def test_campsite_filtering():
    with TestClient(app) as client:
        # Filter by specific park
        resp = client.get("/api/campsites", params={"park": "Afton State Park"})
        assert resp.status_code == 200
        afton = resp.json()
        assert afton["total"] > 20
        assert all(s["park"] == "Afton State Park" for s in afton["campsites"])

        # Filter by waterfront & electric
        wf_resp = client.get(
            "/api/campsites",
            params={"waterfront": "true", "electric": "true", "tourism_region": "Northeast"},
        )
        assert wf_resp.status_code == 200
        wf_data = wf_resp.json()
        assert wf_data["total"] > 0
        for site in wf_data["campsites"]:
            assert site["waterfront"] is True
            assert site["electric_30amp"] is True or site["electric_50amp"] is True
            assert site["tourism_region"] == "Northeast"

        # Single campsite lookup
        first_id = wf_data["campsites"][0]["id"]
        detail_resp = client.get(f"/api/campsites/{first_id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id"] == first_id


def test_auth_favorites_and_notes_workflow():
    with TestClient(app) as client:
        # Initially unauthenticated
        me_resp = client.get("/api/auth/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["authenticated"] is False

        # Grab a campsite ID
        sites_resp = client.get("/api/campsites", params={"park": "Afton State Park"})
        site_id = sites_resp.json()["campsites"][0]["id"]

        # Unauthenticated favorite attempt returns 401
        unauth_fav = client.post(f"/api/favorites/{site_id}")
        assert unauth_fav.status_code == 401

        # Authenticate via demo IdP session
        login_resp = client.post("/auth/demo-login")
        assert login_resp.status_code == 200
        assert login_resp.json()["status"] == "authenticated"

        # Toggle favorite ON
        fav_on = client.post(f"/api/favorites/{site_id}")
        assert fav_on.status_code == 200
        assert fav_on.json()["favorited"] is True
        assert site_id in fav_on.json()["favorites"]

        # Save a personal campsite note & rating
        note_resp = client.put(
            f"/api/notes/{site_id}",
            json={"note": "Great evening shade near the St. Croix River!", "rating": 5},
        )
        assert note_resp.status_code == 200
        assert note_resp.json()["item"]["rating"] == 5

        # Filter by favorites_only=true
        fav_filter = client.get("/api/campsites", params={"favorites_only": "true"})
        assert fav_filter.status_code == 200
        assert any(s["id"] == site_id for s in fav_filter.json()["campsites"])

        # Logout
        logout_resp = client.post("/auth/logout")
        assert logout_resp.status_code == 200
