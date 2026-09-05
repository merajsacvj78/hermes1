"""Async SQLite storage layer for V-CORP: OUTBREAK."""
from __future__ import annotations

import json
import time
from typing import Any, Iterable, Optional

import aiosqlite

from .config import config

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS players (
    user_id      INTEGER PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT 'Unknown',
    path         TEXT NOT NULL DEFAULT 'survivor',
    faction      TEXT,
    org_id       INTEGER,
    org_rank     TEXT DEFAULT 'recruit',
    hp           INTEGER NOT NULL DEFAULT 100,
    max_hp       INTEGER NOT NULL DEFAULT 100,
    energy       INTEGER NOT NULL DEFAULT 100,
    money        INTEGER NOT NULL DEFAULT 500,
    infection    INTEGER NOT NULL DEFAULT 0,
    stage        TEXT NOT NULL DEFAULT 'human',
    hidden       INTEGER NOT NULL DEFAULT 0,
    attack       INTEGER NOT NULL DEFAULT 10,
    defense      INTEGER NOT NULL DEFAULT 8,
    stealth      INTEGER NOT NULL DEFAULT 5,
    intellect    INTEGER NOT NULL DEFAULT 5,
    xp           INTEGER NOT NULL DEFAULT 0,
    level        INTEGER NOT NULL DEFAULT 1,
    heat         INTEGER NOT NULL DEFAULT 0,
    kills        INTEGER NOT NULL DEFAULT 0,
    deaths       INTEGER NOT NULL DEFAULT 0,
    elo          INTEGER NOT NULL DEFAULT 1000,
    duel_wins    INTEGER NOT NULL DEFAULT 0,
    duel_losses  INTEGER NOT NULL DEFAULT 0,
    streak       INTEGER NOT NULL DEFAULT 0,
    legacy       INTEGER NOT NULL DEFAULT 0,
    generation   INTEGER NOT NULL DEFAULT 1,
    alive        INTEGER NOT NULL DEFAULT 1,
    banned       INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL DEFAULT 0,
    last_action  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cooldowns (
    user_id INTEGER NOT NULL,
    key     TEXT NOT NULL,
    ready_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS powers (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    icon        TEXT NOT NULL DEFAULT '🦸',
    description TEXT NOT NULL DEFAULT '',
    cooldown    INTEGER NOT NULL DEFAULT 900,
    risk        INTEGER NOT NULL DEFAULT 10,
    counter     TEXT NOT NULL DEFAULT '',
    power_type  TEXT NOT NULL DEFAULT 'offense',
    magnitude   INTEGER NOT NULL DEFAULT 20,
    custom      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS player_powers (
    user_id INTEGER NOT NULL,
    code    TEXT NOT NULL,
    charges INTEGER NOT NULL DEFAULT -1,
    PRIMARY KEY (user_id, code)
);

CREATE TABLE IF NOT EXISTS mutations (
    user_id INTEGER NOT NULL,
    node    TEXT NOT NULL,
    PRIMARY KEY (user_id, node)
);

CREATE TABLE IF NOT EXISTS items (
    user_id INTEGER NOT NULL,
    code    TEXT NOT NULL,
    qty     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, code)
);

CREATE TABLE IF NOT EXISTS orgs (
    org_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT UNIQUE NOT NULL,
    name       TEXT NOT NULL,
    icon       TEXT NOT NULL DEFAULT '🏢',
    leader_id  INTEGER,
    funds      INTEGER NOT NULL DEFAULT 0,
    research   INTEGER NOT NULL DEFAULT 0,
    power      INTEGER NOT NULL DEFAULT 10,
    founded_at INTEGER NOT NULL DEFAULT 0,
    system     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reputation (
    user_id INTEGER NOT NULL,
    org     TEXT NOT NULL,
    value   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, org)
);

CREATE TABLE IF NOT EXISTS contracts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    issuer_id  INTEGER NOT NULL,
    target_id  INTEGER NOT NULL,
    reward     INTEGER NOT NULL,
    secret     INTEGER NOT NULL DEFAULT 1,
    status     TEXT NOT NULL DEFAULT 'open',
    taker_id   INTEGER,
    chat_id    INTEGER,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS missions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,
    title       TEXT NOT NULL,
    org         TEXT NOT NULL DEFAULT 'any',
    difficulty  INTEGER NOT NULL DEFAULT 3,
    reward      INTEGER NOT NULL DEFAULT 1000,
    infection   INTEGER NOT NULL DEFAULT 0,
    rep         INTEGER NOT NULL DEFAULT 5,
    description TEXT NOT NULL DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mission_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    mission_id INTEGER NOT NULL,
    result     TEXT NOT NULL,
    at         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id  INTEGER NOT NULL,
    about_id  INTEGER,
    kind      TEXT NOT NULL,
    body      TEXT NOT NULL,
    value     INTEGER NOT NULL DEFAULT 500,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS market (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER NOT NULL,
    kind      TEXT NOT NULL,           -- item | evidence | sample
    ref       TEXT NOT NULL,
    qty       INTEGER NOT NULL DEFAULT 1,
    price     INTEGER NOT NULL,
    status    TEXT NOT NULL DEFAULT 'open',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS economy (
    code   TEXT PRIMARY KEY,
    price  INTEGER NOT NULL,
    demand INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS world (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    chat_id    INTEGER,
    status     TEXT NOT NULL DEFAULT 'active',
    data       TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bosses (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id  INTEGER NOT NULL,
    name     TEXT NOT NULL,
    hp       INTEGER NOT NULL,
    max_hp   INTEGER NOT NULL,
    attack   INTEGER NOT NULL DEFAULT 25,
    reward   INTEGER NOT NULL DEFAULT 5000,
    status   TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS boss_damage (
    boss_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    damage  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (boss_id, user_id)
);

CREATE TABLE IF NOT EXISTS chats (
    chat_id   INTEGER PRIMARY KEY,
    title     TEXT NOT NULL DEFAULT '',
    active    INTEGER NOT NULL DEFAULT 1,
    added_at  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS logs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    at      INTEGER NOT NULL,
    kind    TEXT NOT NULL,
    user_id INTEGER,
    chat_id INTEGER,
    text    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS duels (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    a_id       INTEGER NOT NULL,
    b_id       INTEGER NOT NULL,
    stake      INTEGER NOT NULL DEFAULT 0,
    winner_id  INTEGER,
    rounds     INTEGER NOT NULL DEFAULT 0,
    reason     TEXT NOT NULL DEFAULT '',
    elo_delta  INTEGER NOT NULL DEFAULT 0,
    at         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS mutes (
    user_id  INTEGER PRIMARY KEY,
    until    INTEGER NOT NULL,
    reason   TEXT NOT NULL DEFAULT ''
);
"""


class Database:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or config.db_path
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()
        await self.migrate()

    async def migrate(self) -> None:
        """Add columns introduced after a database was first created.

        CREATE TABLE IF NOT EXISTS never alters an existing table, so every
        new player column must be listed here or old deployments break.
        """
        wanted = {
            "players": {
                "elo": "INTEGER NOT NULL DEFAULT 1000",
                "duel_wins": "INTEGER NOT NULL DEFAULT 0",
                "duel_losses": "INTEGER NOT NULL DEFAULT 0",
                "streak": "INTEGER NOT NULL DEFAULT 0",
                "legacy": "INTEGER NOT NULL DEFAULT 0",
                "generation": "INTEGER NOT NULL DEFAULT 1",
            },
        }
        for table, cols in wanted.items():
            rows = await self.fetchall(f"PRAGMA table_info({table})")
            have = {r["name"] for r in rows}
            if not have:
                continue
            for name, ddl in cols.items():
                if name not in have:
                    await self.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            self.conn = None

    # -- low level helpers -------------------------------------------------
    async def execute(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Cursor:
        assert self.conn
        cur = await self.conn.execute(sql, tuple(params))
        await self.conn.commit()
        return cur

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> Optional[aiosqlite.Row]:
        assert self.conn
        async with self.conn.execute(sql, tuple(params)) as cur:
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        assert self.conn
        async with self.conn.execute(sql, tuple(params)) as cur:
            return list(await cur.fetchall())

    async def scalar(self, sql: str, params: Iterable[Any] = (), default: Any = 0) -> Any:
        row = await self.fetchone(sql, params)
        if row is None or row[0] is None:
            return default
        return row[0]

    # -- world state -------------------------------------------------------
    async def world_get(self, key: str, default: Any = None) -> Any:
        row = await self.fetchone("SELECT value FROM world WHERE key=?", (key,))
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    async def world_set(self, key: str, value: Any) -> None:
        await self.execute(
            "INSERT INTO world(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )

    async def log(self, kind: str, text: str, user_id: int | None = None,
                  chat_id: int | None = None) -> None:
        await self.execute(
            "INSERT INTO logs(at,kind,user_id,chat_id,text) VALUES(?,?,?,?,?)",
            (int(time.time()), kind, user_id, chat_id, text),
        )


db = Database()
