"""SQLite storage layer for user favorites and personal campsite notes."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings

FALLBACK_LOCAL_DB = Path(__file__).resolve().parent.parent / "data" / "app.db"


class UserStorage:
    """Manages SQLite persistence for authenticated user favorites and campsite notes."""

    def __init__(self, db_path: str | None = None) -> None:
        candidate = db_path or settings.database_path
        try:
            Path(candidate).parent.mkdir(parents=True, exist_ok=True)
            self.db_path = candidate
        except PermissionError:
            FALLBACK_LOCAL_DB.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(FALLBACK_LOCAL_DB)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_favorites (
                    user_sub TEXT NOT NULL,
                    campsite_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_sub, campsite_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_notes (
                    user_sub TEXT NOT NULL,
                    campsite_id TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    rating INTEGER,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_sub, campsite_id)
                )
                """
            )
            conn.commit()

    def get_favorites(self, user_sub: str) -> List[str]:
        """Return list of favorite campsite IDs for a given user."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT campsite_id FROM user_favorites WHERE user_sub = ? ORDER BY created_at DESC",
                (user_sub,),
            ).fetchall()
            return [row["campsite_id"] for row in rows]

    def toggle_favorite(self, user_sub: str, campsite_id: str) -> bool:
        """Toggle a campsite favorite for a user. Returns True if now favorited, False if removed."""
        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT 1 FROM user_favorites WHERE user_sub = ? AND campsite_id = ?",
                (user_sub, campsite_id),
            ).fetchone()
            if existing:
                conn.execute(
                    "DELETE FROM user_favorites WHERE user_sub = ? AND campsite_id = ?",
                    (user_sub, campsite_id),
                )
                conn.commit()
                return False
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO user_favorites (user_sub, campsite_id, created_at) VALUES (?, ?, ?)",
                (user_sub, campsite_id, now_iso),
            )
            conn.commit()
            return True

    def get_notes(self, user_sub: str) -> Dict[str, Dict[str, Any]]:
        """Return dictionary of campsite_id -> {note, rating, updated_at} for a user."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT campsite_id, note, rating, updated_at FROM user_notes WHERE user_sub = ?",
                (user_sub,),
            ).fetchall()
            return {
                row["campsite_id"]: {
                    "note": row["note"],
                    "rating": row["rating"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            }

    def save_note(
        self,
        user_sub: str,
        campsite_id: str,
        note: str,
        rating: int | None = None,
    ) -> Dict[str, Any]:
        """Upsert or delete a note/rating for a campsite."""
        clean_note = note.strip()
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            if not clean_note and rating is None:
                conn.execute(
                    "DELETE FROM user_notes WHERE user_sub = ? AND campsite_id = ?",
                    (user_sub, campsite_id),
                )
                conn.commit()
                return {"campsite_id": campsite_id, "note": "", "rating": None, "updated_at": now_iso}

            conn.execute(
                """
                INSERT INTO user_notes (user_sub, campsite_id, note, rating, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_sub, campsite_id) DO UPDATE SET
                    note = excluded.note,
                    rating = excluded.rating,
                    updated_at = excluded.updated_at
                """,
                (user_sub, campsite_id, clean_note, rating, now_iso),
            )
            conn.commit()
            return {
                "campsite_id": campsite_id,
                "note": clean_note,
                "rating": rating,
                "updated_at": now_iso,
            }


user_storage = UserStorage()
