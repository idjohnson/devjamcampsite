"""Federated Google IdP Authentication (OAuth 2.0 / OIDC + Google Identity Services ID Token)."""

import logging
import secrets
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings
from app.models import GoogleTokenPayload, UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"


def get_current_user(request: Request) -> Optional[UserProfile]:
    """Retrieve the authenticated user profile from the signed session cookie."""
    user_data = request.session.get("user")
    if not user_data:
        return None
    try:
        return UserProfile(**user_data)
    except Exception:
        return None


def require_user(request: Request) -> UserProfile:
    """Dependency that requires an authenticated Google IdP user."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in with Google.",
        )
    return user


@router.get("/login")
async def google_oauth_login(request: Request):
    """Initiate federated Google IdP OAuth 2.0 / OIDC authorization code flow."""
    if not settings.google_oauth_configured:
        if settings.enable_demo_auth:
            return RedirectResponse(url="/auth/demo-login", status_code=302)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Google OAuth 2.0 is not configured yet. Set GOOGLE_CLIENT_ID and "
                "GOOGLE_CLIENT_SECRET in your .env file (see SETUP.md)."
            ),
        )

    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state

    params = {
        "client_id": settings.google_client_id.strip(),
        "redirect_uri": settings.google_redirect_uri.strip(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    auth_url = f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback")
async def google_oauth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Handle Google OAuth 2.0 redirect callback and exchange authorization code for tokens."""
    if error:
        logger.warning("Google OAuth error callback: %s", error)
        return RedirectResponse(url=f"/?auth_error={error}", status_code=302)

    expected_state = request.session.pop("oauth_state", None)
    if not code or not state or (expected_state and state != expected_state):
        return RedirectResponse(url="/?auth_error=invalid_oauth_state", status_code=302)

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": settings.google_client_id.strip(),
                "client_secret": settings.google_client_secret.strip(),
                "redirect_uri": settings.google_redirect_uri.strip(),
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            logger.error("Failed exchanging code for Google token: %s", token_resp.text)
            return RedirectResponse(url="/?auth_error=token_exchange_failed", status_code=302)

        tokens = token_resp.json()
        access_token = tokens.get("access_token")

        userinfo_resp = await client.get(
            GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            return RedirectResponse(url="/?auth_error=userinfo_failed", status_code=302)

        info = userinfo_resp.json()

    profile = UserProfile(
        sub=str(info.get("sub") or info.get("email")),
        email=info.get("email", ""),
        name=info.get("name") or info.get("email", "Google User"),
        picture=info.get("picture", ""),
        provider="google",
    )
    request.session["user"] = profile.model_dump()
    return RedirectResponse(url="/", status_code=302)


@router.post("/google/token")
async def google_id_token_login(request: Request, payload: GoogleTokenPayload):
    """Verify a federated Google Identity Services (Sign In With Google) JWT ID token."""
    if not settings.google_client_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GOOGLE_CLIENT_ID is not configured on the server.",
        )
    try:
        idinfo = google_id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            settings.google_client_id.strip(),
        )
    except Exception as exc:
        logger.warning("Google ID token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google ID token.",
        ) from exc

    profile = UserProfile(
        sub=str(idinfo.get("sub")),
        email=idinfo.get("email", ""),
        name=idinfo.get("name") or idinfo.get("email", "Google User"),
        picture=idinfo.get("picture", ""),
        provider="google_gsi",
    )
    request.session["user"] = profile.model_dump()
    return JSONResponse({"status": "authenticated", "user": profile.model_dump()})


@router.get("/demo-login")
@router.post("/demo-login")
async def demo_login(request: Request):
    """Sign in with a local demo Google profile when ENABLE_DEMO_AUTH=true."""
    if not settings.enable_demo_auth:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo login is disabled. Please configure Google OAuth credentials.",
        )
    profile = UserProfile(
        sub="demo-mn-camper-001",
        email="camper@northwoods.mn.example",
        name="Northwoods Explorer (Demo)",
        picture="",
        provider="demo_google_idp",
    )
    request.session["user"] = profile.model_dump()
    if request.method == "POST":
        return JSONResponse({"status": "authenticated", "user": profile.model_dump()})
    return RedirectResponse(url="/", status_code=302)


@router.get("/logout")
@router.post("/logout")
async def logout(request: Request):
    """Clear the authenticated session."""
    request.session.clear()
    if request.method == "POST":
        return JSONResponse({"status": "logged_out"})
    return RedirectResponse(url="/", status_code=302)
