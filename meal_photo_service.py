"""Meal photo log: a locally-stored photo per /upload_photo, tagged with when it was
taken and (optionally) where, keyed by the Telegram user who sent it."""

import sqlite3


def add_photo(conn: sqlite3.Connection, telegram_user_id: int, file_path: str, taken_at: str) -> int:
    cursor = conn.execute(
        "INSERT INTO meal_photos (telegram_user_id, file_path, taken_at) VALUES (?, ?, ?)",
        (telegram_user_id, file_path, taken_at),
    )
    conn.commit()
    return int(cursor.lastrowid)


def set_location(conn: sqlite3.Connection, photo_id: int, latitude: float, longitude: float) -> None:
    conn.execute(
        "UPDATE meal_photos SET latitude = ?, longitude = ? WHERE id = ?",
        (latitude, longitude, photo_id),
    )
    conn.commit()


def get_photo(conn: sqlite3.Connection, photo_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM meal_photos WHERE id = ?", (photo_id,)).fetchone()
