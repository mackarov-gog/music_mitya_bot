"""SQLite persistence layer for server playlists and per-guild settings.

Uses aiosqlite (async wrapper around sqlite3) to keep the event loop free.
All queries are parameterized; no user input is ever interpolated into SQL.
"""
import aiosqlite
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'bot.db')

_db: aiosqlite.Connection | None = None


async def init_db(db_path: str = DB_PATH) -> None:
    """Create tables and open the shared connection (WAL mode)."""
    global _db
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL;")
    await _db.execute("PRAGMA foreign_keys=ON;")

    await _db.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id    INTEGER NOT NULL,
            name        TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            created_by  TEXT NOT NULL,
            UNIQUE(guild_id, name)
        )
    """)

    await _db.execute("""
        CREATE TABLE IF NOT EXISTS playlist_tracks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id  INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
            title        TEXT NOT NULL,
            url          TEXT,
            file_name    TEXT,
            source_type  TEXT NOT NULL CHECK(source_type IN ('YouTube','Radio','Local')),
            duration_sec INTEGER NOT NULL DEFAULT 0,
            added_by     TEXT NOT NULL,
            position     INTEGER NOT NULL,
            added_at     TEXT NOT NULL
        )
    """)

    await _db.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id    INTEGER PRIMARY KEY,
            chain_play  INTEGER NOT NULL DEFAULT 0,
            volume      INTEGER NOT NULL DEFAULT 100,
            repeat_mode TEXT NOT NULL DEFAULT 'off' CHECK(repeat_mode IN ('off','one','all')),
            language    TEXT NOT NULL DEFAULT 'ru' CHECK(language IN ('ru','en'))
        )
    """)

    # --- Schema migration ----------------------------------------------- #
    # CREATE TABLE IF NOT EXISTS does NOT add columns to an existing table.
    # Ensure any newly introduced columns exist on pre-created databases.
    cur = await _db.execute("PRAGMA table_info(guild_settings)")
    existing_columns = {row[1] for row in await cur.fetchall()}
    await cur.close()

    _migrations = {
        'language': "ALTER TABLE guild_settings ADD COLUMN language TEXT NOT NULL DEFAULT 'ru' CHECK(language IN ('ru','en'))",
    }
    for column, ddl in _migrations.items():
        if column not in existing_columns:
            await _db.execute(ddl)

    await _db.commit()


def get_connection() -> aiosqlite.Connection:
    """Return the shared connection. init_db() must have been called."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


# --------------------------------------------------------------------------- #
# Playlists
# --------------------------------------------------------------------------- #

async def create_playlist(guild_id: int, name: str, created_by: str) -> bool:
    """Create an empty playlist. Returns False if a playlist with the same name exists."""
    db = get_connection()
    try:
        await db.execute(
            "INSERT INTO playlists (guild_id, name, created_at, created_by) VALUES (?, ?, ?, ?)",
            (guild_id, name, _now(), created_by)
        )
        await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def list_playlists(guild_id: int) -> list[dict]:
    db = get_connection()
    cur = await db.execute(
        "SELECT id, name, created_by FROM playlists WHERE guild_id = ? ORDER BY name",
        (guild_id,)
    )
    rows = await cur.fetchall()
    await cur.close()
    return [dict(row) for row in rows]


async def get_playlist(guild_id: int, name: str) -> dict | None:
    db = get_connection()
    cur = await db.execute(
        "SELECT id, name, created_by FROM playlists WHERE guild_id = ? AND name = ?",
        (guild_id, name)
    )
    row = await cur.fetchone()
    await cur.close()
    return dict(row) if row else None


async def delete_playlist(guild_id: int, name: str) -> bool:
    db = get_connection()
    cur = await db.execute(
        "DELETE FROM playlists WHERE guild_id = ? AND name = ?",
        (guild_id, name)
    )
    await db.commit()
    deleted = cur.rowcount > 0
    await cur.close()
    return deleted


async def add_track(
    guild_id: int,
    playlist_name: str,
    *,
    title: str,
    source_type: str,
    duration_sec: int = 0,
    url: str | None = None,
    file_name: str | None = None,
    added_by: str = "",
) -> bool:
    """Append a track to a playlist. Returns False if the playlist does not exist."""
    playlist = await get_playlist(guild_id, playlist_name)
    if not playlist:
        return False

    db = get_connection()
    cur = await db.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_tracks WHERE playlist_id = ?",
        (playlist['id'],)
    )
    row = await cur.fetchone()
    position = row[0]
    await cur.close()

    await db.execute(
        """INSERT INTO playlist_tracks
           (playlist_id, title, url, file_name, source_type, duration_sec, added_by, position, added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (playlist['id'], title, url, file_name, source_type, duration_sec, added_by, position, _now())
    )
    await db.commit()
    return True


async def get_playlist_tracks(guild_id: int, name: str) -> list[dict]:
    playlist = await get_playlist(guild_id, name)
    if not playlist:
        return []

    db = get_connection()
    cur = await db.execute(
        """SELECT id, title, url, file_name, source_type, duration_sec, position
           FROM playlist_tracks
           WHERE playlist_id = ?
           ORDER BY position""",
        (playlist['id'],)
    )
    rows = await cur.fetchall()
    await cur.close()
    return [dict(row) for row in rows]


async def remove_track(guild_id: int, name: str, position: int) -> bool:
    """Delete track at 1-based position and renumber the rest. Returns False if not found."""
    playlist = await get_playlist(guild_id, name)
    if not playlist:
        return False

    db = get_connection()
    cur = await db.execute(
        "DELETE FROM playlist_tracks WHERE playlist_id = ? AND position = ?",
        (playlist['id'], position)
    )
    await db.commit()
    deleted = cur.rowcount > 0
    await cur.close()

    # Renumber remaining tracks
    await db.execute(
        """UPDATE playlist_tracks SET position = position - 1
           WHERE playlist_id = ? AND position > ?""",
        (playlist['id'], position)
    )
    await db.commit()
    return deleted


async def move_track(guild_id: int, name: str, from_pos: int, to_pos: int) -> bool:
    """Reorder tracks. Both positions are 1-based. Returns False on invalid input."""
    tracks = await get_playlist_tracks(guild_id, name)
    if not tracks:
        return False
    if from_pos < 1 or to_pos < 1 or from_pos > len(tracks) or to_pos > len(tracks):
        return False

    playlist = await get_playlist(guild_id, name)
    track = tracks.pop(from_pos - 1)
    tracks.insert(to_pos - 1, track)

    db = get_connection()
    for index, item in enumerate(tracks, start=1):
        await db.execute(
            "UPDATE playlist_tracks SET position = ? WHERE id = ?",
            (index, item['id'])
        )
    await db.commit()
    return True


# --------------------------------------------------------------------------- #
# Guild settings
# --------------------------------------------------------------------------- #

async def get_setting(guild_id: int, key: str, default):
    """Read a per-guild setting (chain_play, volume, repeat_mode, language)."""
    db = get_connection()
    cur = await db.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,))
    row = await cur.fetchone()
    await cur.close()
    if row is None:
        return default
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


async def set_setting(guild_id: int, key: str, value) -> None:
    """Upsert a per-guild setting (chain_play, volume, repeat_mode, language).

    Only the targeted key is updated; all other fields keep their current
    value (or their default when the row is created).

    The statement is built dynamically from the columns that actually exist
    in the table, so this works even on a database created by an older
    schema (before the `language` column existed).
    """
    db = get_connection()

    # Discover actual columns in the table (robust against old schemas).
    cur = await db.execute("PRAGMA table_info(guild_settings)")
    columns = {row[1] for row in await cur.fetchall()}
    await cur.close()

    VALUES_DEFAULTS = {
        'chain_play': (0, lambda v: 1 if v else 0),
        'volume': (100, lambda v: int(v)),
        'repeat_mode': ('off', str),
        'language': ('ru', str),
    }
    if key not in VALUES_DEFAULTS:
        raise ValueError(f"Unknown setting key: {key}")

    # Read current row if it exists.
    cur = await db.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,))
    row = await cur.fetchone()
    await cur.close()

    col_map = {}
    for col, (default, _coerce) in VALUES_DEFAULTS.items():
        if col not in columns:
            continue
        if row is not None:
            try:
                val = row[col]
            except (KeyError, IndexError):
                val = default
        else:
            val = default
        col_map[col] = val

    # Apply the targeted change.
    _, coerce = VALUES_DEFAULTS[key]
    col_map[key] = coerce(value)

    # Build INSERT ... ON CONFLICT dynamically over existing columns.
    cols = ['guild_id'] + list(col_map.keys())
    placeholders = ', '.join('?' for _ in cols)
    assignments = ', '.join(f"{c}=excluded.{c}" for c in col_map.keys())
    sql = (
        f"INSERT INTO guild_settings ({', '.join(cols)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT(guild_id) DO UPDATE SET {assignments}"
    )
    values = [guild_id] + [col_map[c] for c in col_map.keys()]

    await db.execute(sql, values)
    await db.commit()