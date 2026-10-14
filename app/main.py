"""Main FastAPI application for the Minnesota Park & Campsite Explorer."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import get_current_user, require_user, router as auth_router
from app.config import settings
from app.models import UserNotePayload, UserProfile
from app.sheets import sheets_service
from app.storage import user_storage

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load and index the Minnesota Park Google Sheet dataset on startup."""
    await sheets_service.ensure_loaded()
    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "Interactive Minnesota State Park & Forest Campsite Explorer powered by "
        "Google Sheets, Google Maps, and Federated Google IdP Authentication."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie="mn_campsite_session",
    max_age=60 * 60 * 24 * 7,  # 7 days
    same_site="lax",
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(auth_router)


@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """Render the interactive map explorer application."""
    await sheets_service.ensure_loaded()
    user = get_current_user(request)
    metadata = sheets_service.get_metadata()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": settings.app_name,
            "user": user.model_dump() if user else None,
            "google_maps_api_key": settings.google_maps_api_key.strip(),
            "google_maps_map_id": settings.google_maps_map_id.strip(),
            "google_client_id": settings.google_client_id.strip(),
            "google_oauth_configured": settings.google_oauth_configured,
            "enable_demo_auth": settings.enable_demo_auth,
            "metadata": metadata.model_dump(),
        },
    )


@app.get("/api/health")
async def health_check():
    """Container health check and dataset readiness endpoint."""
    await sheets_service.ensure_loaded()
    meta = sheets_service.get_metadata()
    return {
        "status": "healthy",
        "app": settings.app_name,
        "sheet_source": meta.source,
        "last_synced_at": meta.last_synced_at,
        "total_campsites": meta.total_campsites,
        "total_parks": meta.total_parks,
    }


@app.get("/api/config")
async def get_public_config(request: Request):
    """Return client-side configuration and current auth state."""
    await sheets_service.ensure_loaded()
    user = get_current_user(request)
    favorites = user_storage.get_favorites(user.sub) if user else []
    notes = user_storage.get_notes(user.sub) if user else {}
    return {
        "app_name": settings.app_name,
        "google_maps_api_key": settings.google_maps_api_key.strip(),
        "google_maps_map_id": settings.google_maps_map_id.strip(),
        "google_client_id": settings.google_client_id.strip(),
        "google_oauth_configured": settings.google_oauth_configured,
        "enable_demo_auth": settings.enable_demo_auth,
        "user": user.model_dump() if user else None,
        "favorites": favorites,
        "notes": notes,
    }


@app.get("/api/metadata")
async def get_dataset_metadata():
    """Return Google Sheet metadata, statistics, and filter facet options."""
    await sheets_service.ensure_loaded()
    return sheets_service.get_metadata()


@app.get("/api/parks")
async def list_parks():
    """Return aggregated summaries for all Minnesota parks in the sheet."""
    await sheets_service.ensure_loaded()
    parks = sheets_service.get_parks()
    return {"total": len(parks), "parks": parks}


@app.get("/api/campsites")
async def list_campsites(
    request: Request,
    q: Optional[str] = Query(default=None, description="Search park, campground, site, or county"),
    park: Optional[str] = Query(default=None),
    park_type: Optional[str] = Query(default=None),
    tourism_region: Optional[str] = Query(default=None),
    county: Optional[str] = Query(default=None),
    unit_type: Optional[str] = Query(default=None),
    site_type: Optional[str] = Query(default=None),
    shade: Optional[str] = Query(default=None),
    electric: Optional[bool] = Query(default=None),
    electric_50amp: Optional[bool] = Query(default=None),
    waterfront: Optional[bool] = Query(default=None),
    ada_accessible: Optional[bool] = Query(default=None),
    pets_allowed: Optional[bool] = Query(default=None),
    food_locker: Optional[bool] = Query(default=None),
    min_pad_length: Optional[int] = Query(default=None, ge=0),
    min_people: Optional[int] = Query(default=None, ge=0),
    favorites_only: bool = Query(default=False),
):
    """Query and filter Minnesota campsites from the Google Sheet dataset."""
    await sheets_service.ensure_loaded()

    fav_set: Optional[set[str]] = None
    if favorites_only:
        user = get_current_user(request)
        if not user:
            return {"total": 0, "campsites": []}
        fav_set = set(user_storage.get_favorites(user.sub))

    sites = sheets_service.filter_campsites(
        q=q,
        park=park,
        park_type=park_type,
        tourism_region=tourism_region,
        county=county,
        unit_type=unit_type,
        site_type=site_type,
        shade=shade,
        electric=electric,
        electric_50amp=electric_50amp,
        waterfront=waterfront,
        ada_accessible=ada_accessible,
        pets_allowed=pets_allowed,
        food_locker=food_locker,
        min_pad_length=min_pad_length,
        min_people=min_people,
        favorite_ids=fav_set,
    )
    return {"total": len(sites), "campsites": sites}


@app.get("/api/campsites/{campsite_id}")
async def get_campsite(campsite_id: str):
    """Return full details for a single campsite by ID."""
    await sheets_service.ensure_loaded()
    site = sheets_service.get_campsite_by_id(campsite_id)
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campsite '{campsite_id}' not found.",
        )
    return site


@app.post("/api/sync")
async def trigger_sheet_sync(user: UserProfile = Depends(require_user)):
    """Force an immediate re-fetch of the Minnesota Park Google Sheet (requires sign-in)."""
    meta = await sheets_service.refresh_data()
    return {
        "status": "synced",
        "triggered_by": user.email,
        "metadata": meta,
    }


@app.get("/api/auth/me")
async def get_authenticated_user(request: Request):
    """Return the current authenticated Google user and their saved favorites & notes."""
    user = get_current_user(request)
    if not user:
        return {"authenticated": False, "user": None, "favorites": [], "notes": {}}
    return {
        "authenticated": True,
        "user": user.model_dump(),
        "favorites": user_storage.get_favorites(user.sub),
        "notes": user_storage.get_notes(user.sub),
    }


@app.post("/api/favorites/{campsite_id}")
async def toggle_favorite_campsite(
    campsite_id: str,
    user: UserProfile = Depends(require_user),
):
    """Toggle a campsite as favorite for the authenticated Google user."""
    await sheets_service.ensure_loaded()
    site = sheets_service.get_campsite_by_id(campsite_id)
    if not site:
        raise HTTPException(status_code=404, detail="Campsite not found")
    is_favorited = user_storage.toggle_favorite(user.sub, campsite_id)
    return {
        "campsite_id": campsite_id,
        "favorited": is_favorited,
        "favorites": user_storage.get_favorites(user.sub),
    }


@app.put("/api/notes/{campsite_id}")
async def save_campsite_note(
    campsite_id: str,
    payload: UserNotePayload,
    user: UserProfile = Depends(require_user),
):
    """Save or update a personal trip note and star rating for a campsite."""
    await sheets_service.ensure_loaded()
    site = sheets_service.get_campsite_by_id(campsite_id)
    if not site:
        raise HTTPException(status_code=404, detail="Campsite not found")
    saved = user_storage.save_note(
        user_sub=user.sub,
        campsite_id=campsite_id,
        note=payload.note,
        rating=payload.rating,
    )
    return {
        "status": "saved",
        "item": saved,
        "notes": user_storage.get_notes(user.sub),
    }
