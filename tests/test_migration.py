"""Upgrading an existing deployment must never lose player data."""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PATH = "/tmp/vcorp_migration_test.sqlite3"

# the players table exactly as it shipped before PvP existed
V1 = """
CREATE TABLE players(
 user_id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT 'Unknown',
 path TEXT DEFAULT 'survivor', faction TEXT, org_id INTEGER,
 org_rank TEXT DEFAULT 'recruit', hp INTEGER DEFAULT 100,
 max_hp INTEGER DEFAULT 100, energy INTEGER DEFAULT 100,
 money INTEGER DEFAULT 500, infection INTEGER DEFAULT 0,
 stage TEXT DEFAULT 'human', hidden INTEGER DEFAULT 0,
 attack INTEGER DEFAULT 10, defense INTEGER DEFAULT 8,
 stealth INTEGER DEFAULT 5, intellect INTEGER DEFAULT 5,
 xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, heat INTEGER DEFAULT 0,
 kills INTEGER DEFAULT 0, deaths INTEGER DEFAULT 0, alive INTEGER DEFAULT 1,
 banned INTEGER DEFAULT 0, created_at INTEGER DEFAULT 0,
 last_action INTEGER DEFAULT 0);
CREATE TABLE items(user_id INTEGER, code TEXT, qty INTEGER DEFAULT 0,
 PRIMARY KEY(user_id,code));
"""


async def main() -> None:
    if os.path.exists(PATH):
        os.remove(PATH)
    c = sqlite3.connect(PATH)
    c.executescript(V1)
    c.execute("INSERT INTO players(user_id,name,money,level,kills,infection,stage)"
              " VALUES(42,'Veteran',77777,9,13,55,'mutant')")
    c.execute("INSERT INTO items(user_id,code,qty) VALUES(42,'medkit',4)")
    c.commit()
    c.close()

    import vcorp.db as dbmod
    import vcorp.game.engine as eng
    from vcorp.db import Database

    fresh = Database(PATH)
    await fresh.connect()
    dbmod.db = fresh
    eng.db = fresh
    await eng.seed()

    row = dict(await fresh.fetchone("SELECT * FROM players WHERE user_id=42"))
    assert row["money"] == 77777, "money lost during upgrade"
    assert row["level"] == 9 and row["kills"] == 13, "progress lost"
    assert row["infection"] == 55 and row["stage"] == "mutant", "infection lost"
    assert await fresh.scalar(
        "SELECT qty FROM items WHERE user_id=42 AND code='medkit'") == 4

    # every column added after v1 must exist with a sane default
    for col, default in (("elo", 1000), ("duel_wins", 0), ("duel_losses", 0),
                         ("streak", 0), ("legacy", 0), ("generation", 1)):
        assert col in row, f"missing column {col}"
        assert row[col] == default, f"{col} = {row[col]}, expected {default}"

    # tables introduced later must be present
    for t in ("duels", "contracts", "bosses", "evidence", "market"):
        await fresh.scalar(f"SELECT COUNT(*) FROM {t}")

    # running the migration repeatedly must be harmless
    await fresh.migrate()
    await fresh.migrate()
    assert dict(await fresh.fetchone(
        "SELECT * FROM players WHERE user_id=42"))["money"] == 77777

    # and the upgraded row still works with the live engine
    await eng.apply_infection(42, 5)
    p = await eng.get_player(42)
    assert p["infection"] == 60
    await eng.add(42, elo=25)
    assert (await eng.get_player(42))["elo"] == 1025

    await fresh.close()
    os.remove(PATH)
    print("✅ migration from a pre-PvP database preserves everything", flush=True)


if __name__ == "__main__":
    import traceback
    code = 0
    try:
        asyncio.run(main())
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    os._exit(code)
