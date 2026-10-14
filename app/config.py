"""Configuration settings for the Minnesota Park & Campsite Explorer application."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    app_name: str = "Minnesota Park & Campsite Explorer"
    app_env: str = "production"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    session_secret_key: str = "mn-campsite-dev-secret-key-change-in-prod"

    # Google Sheets settings
    google_sheet_id: str = "1CW-0euFLFz24nzcXNrTY24IoqTX9BCHLX5fdLjxAHgk"
    google_sheet_gid: str = "459530859"
    google_sheets_api_key: str = ""
    sheet_cache_ttl_seconds: int = 1800

    # Google Maps settings
    google_maps_api_key: str = ""
    google_maps_map_id: str = "DEMO_MAP_ID"

    # Federated Google IdP (OAuth 2.0 / OIDC) settings
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/callback"
    enable_demo_auth: bool = True

    # SQLite storage path for user favorites & notes
    database_path: str = str(
        Path(__file__).resolve().parent.parent / "data" / "app.db"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sheet_csv_export_url(self) -> str:
        """Direct CSV export URL for the configured Google Sheet & GID."""
        return (
            f"https://docs.google.com/spreadsheets/d/{self.google_sheet_id}"
            f"/export?format=csv&gid={self.google_sheet_gid}"
        )

    @property
    def sheet_edit_url(self) -> str:
        """Human-readable Google Sheet URL."""
        return (
            f"https://docs.google.com/spreadsheets/d/{self.google_sheet_id}"
            f"/edit?gid={self.google_sheet_gid}#gid={self.google_sheet_gid}"
        )

    @property
    def google_oauth_configured(self) -> bool:
        """Return True if Google OAuth Client ID is configured."""
        return bool(self.google_client_id.strip())


settings = Settings()
