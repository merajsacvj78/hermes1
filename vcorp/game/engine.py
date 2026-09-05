"""Core game rules engine: players, infection, combat, economy, reputation."""
from __future__ import annotations

import random
import time
from typing import Any, Optional

from ..db import db
from . import content
from .content import ITEMS, MUTATIONS, POWERS, STAGE_BONUS, stage_for

NOW = lambda: int(time.time())  # noqa: E731

XP_PER_LEVEL = 250


# ── players ───────────────────────────────────────────────────────────────
async def get_player(user_id: int) -> Optional[dict]:
    row = await db.fetchone("SELECT * FROM players WHERE user_id=?", (user_id,))
    return dict(row) if row else None


async def ensure_player(user_id: int, name: str) -> dict:
    p = await get_player(user_id)
    if p:
        if name and p["name"] != name:
            await db.execute("UPDATE players SET name=? WHERE user_id=?", (name, user_id))
            p["name"] = name
        return p
    await db.execute(
        "INSERT INTO players(user_id,name,created_at,last_action) VALUES(?,?,?,?)",
        (user_id, name or "Unknown", NOW(), 0),
    )
    for org in ("vcorp", "ubc", "umbra"):
        await db.execute(
            "INSERT OR IGNORE INTO reputation(user_id,org,value) VALUES(?,?,0)",
            (user_id, org),
        )
    await db.log("player", f"{name} وارد جهان شد", user_id)
    return await get_player(user_id)  # type: ignore[return-value]


async def update(user_id: int, **fields: Any) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    await db.execute(f"UPDATE players SET {sets} WHERE user_id=?",
                     (*fields.values(), user_id))


async def add(user_id: int, **deltas: Any) -> None:
    if not deltas:
        return
    sets = ", ".join(f"{k}={k}+?" for k in deltas)
    await db.execute(f"UPDATE players SET {sets} WHERE user_id=?",
                     (*deltas.values(), user_id))


async def find_player(query: str) -> Optional[dict]:
    q = query.strip().lstrip("@")
    if q.isdigit():
        p = await get_player(int(q))
        if p:
            return p
    row = await db.fetchone(
        "SELECT * FROM players WHERE lower(name)=lower(?) LIMIT 1", (q,))
    if row:
        return dict(row)
    row = await db.fetchone(
        "SELECT * FROM players WHERE name LIKE ? LIMIT 1", (f"%{q}%",))
    return dict(row) if row else None


# ── cooldowns ─────────────────────────────────────────────────────────────
async def cooldown_left(user_id: int, key: str) -> int:
    ready = await db.scalar(
        "SELECT ready_at FROM cooldowns WHERE user_id=? AND key=?", (user_id, key), 0)
    return max(0, int(ready) - NOW())


async def set_cooldown(user_id: int, key: str, seconds: int) -> None:
    await db.execute(
        "INSERT INTO cooldowns(user_id,key,ready_at) VALUES(?,?,?) "
        "ON CONFLICT(user_id,key) DO UPDATE SET ready_at=excluded.ready_at",
        (user_id, key, NOW() + seconds),
    )


def fmt_time(seconds: int) -> str:
    if seconds <= 0:
        return "آماده"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}س {m}د"
    if m:
        return f"{m}د {s}ث"
    return f"{s}ث"


# ── stats ─────────────────────────────────────────────────────────────────
async def mutation_bonus(user_id: int) -> dict[str, int]:
    rows = await db.fetchall("SELECT node FROM mutations WHERE user_id=?", (user_id,))
    bonus: dict[str, int] = {}
    for r in rows:
        for k, v in MUTATIONS.get(r["node"], {}).get("effect", {}).items():
            bonus[k] = bonus.get(k, 0) + v
    return bonus


async def effective(p: dict) -> dict[str, int]:
    sb = STAGE_BONUS.get(p["stage"], STAGE_BONUS["human"])
    mb = await mutation_bonus(p["user_id"])
    lvl = p["level"] - 1
    return {
        "attack": p["attack"] + sb["attack"] + mb.get("attack", 0) + lvl * 2,
        "defense": p["defense"] + sb["defense"] + mb.get("defense", 0) + lvl * 2,
        "stealth": max(0, p["stealth"] + sb["stealth"] + mb.get("stealth", 0)),
        "intellect": p["intellect"] + mb.get("intellect", 0) + lvl,
        "max_hp": p["max_hp"] + mb.get("max_hp", 0),
    }


async def grant_xp(user_id: int, amount: int) -> int:
    p = await get_player(user_id)
    if not p:
        return 0
    xp = p["xp"] + amount
    level = p["level"]
    gained = 0
    while xp >= level * XP_PER_LEVEL:
        xp -= level * XP_PER_LEVEL
        level += 1
        gained += 1
    await update(user_id, xp=xp, level=level)
    if gained:
        await add(user_id, max_hp=10 * gained, attack=2 * gained, defense=2 * gained)
    return gained


# ── infection ─────────────────────────────────────────────────────────────
async def apply_infection(user_id: int, delta: int) -> tuple[int, str, bool]:
    """Returns (new_infection, stage_code, stage_changed)."""
    p = await get_player(user_id)
    if not p:
        return 0, "human", False
    new = max(0, min(100, p["infection"] + delta))
    stage, _, _ = stage_for(new)
    changed = stage != p["stage"]
    fields: dict[str, Any] = {"infection": new, "stage": stage}
    if changed:
        if stage in ("infected",) and p["path"] in ("survivor",):
            fields["path"] = "infected"
        elif stage == "mutant" and p["path"] in ("survivor", "infected"):
            fields["path"] = "mutant"
        elif stage == "bioweapon":
            fields["path"] = "bioweapon"
        await db.log("infection", f"{p['name']} → {stage}", user_id)
    await update(user_id, **fields)
    return new, stage, changed


async def auto_mutations(user_id: int) -> list[str]:
    """Unlock available mutation nodes automatically is NOT done; returns options."""
    p = await get_player(user_id)
    if not p:
        return []
    owned = {r["node"] for r in
             await db.fetchall("SELECT node FROM mutations WHERE user_id=?", (user_id,))}
    out = []
    for code, m in MUTATIONS.items():
        if code in owned:
            continue
        if p["infection"] < m["inf"]:
            continue
        if m["req"] and m["req"] not in owned:
            continue
        out.append(code)
    return out


async def unlock_mutation(user_id: int, node: str) -> bool:
    if node not in await auto_mutations(user_id):
        return False
    await db.execute("INSERT OR IGNORE INTO mutations(user_id,node) VALUES(?,?)",
                     (user_id, node))
    await db.log("mutation", f"جهش {node}", user_id)
    return True


# ── items ─────────────────────────────────────────────────────────────────
async def item_qty(user_id: int, code: str) -> int:
    return int(await db.scalar(
        "SELECT qty FROM items WHERE user_id=? AND code=?", (user_id, code), 0))


async def give_item(user_id: int, code: str, qty: int = 1) -> None:
    await db.execute(
        "INSERT INTO items(user_id,code,qty) VALUES(?,?,?) "
        "ON CONFLICT(user_id,code) DO UPDATE SET qty=qty+excluded.qty",
        (user_id, code, qty),
    )


async def take_item(user_id: int, code: str, qty: int = 1) -> bool:
    have = await item_qty(user_id, code)
    if have < qty:
        return False
    await db.execute("UPDATE items SET qty=qty-? WHERE user_id=? AND code=?",
                     (qty, user_id, code))
    await db.execute("DELETE FROM items WHERE user_id=? AND code=? AND qty<=0",
                     (user_id, code))
    return True


async def inventory(user_id: int) -> list[tuple[str, int]]:
    rows = await db.fetchall(
        "SELECT code,qty FROM items WHERE user_id=? AND qty>0 ORDER BY code", (user_id,))
    return [(r["code"], r["qty"]) for r in rows]


# ── economy (dynamic pricing) ─────────────────────────────────────────────
async def price_of(code: str) -> int:
    base = ITEMS[code]["price"]
    row = await db.fetchone("SELECT price FROM economy WHERE code=?", (code,))
    if row:
        return int(row["price"])
    await db.execute("INSERT OR IGNORE INTO economy(code,price,demand) VALUES(?,?,0)",
                     (code, base))
    return base


async def register_trade(code: str, direction: int) -> None:
    """direction +1 buy (price up), -1 sell (price down)."""
    base = ITEMS[code]["price"]
    cur = await price_of(code)
    step = max(1, base // 40)
    new = max(int(base * 0.5), min(int(base * 2.5), cur + direction * step))
    await db.execute(
        "INSERT INTO economy(code,price,demand) VALUES(?,?,?) "
        "ON CONFLICT(code) DO UPDATE SET price=excluded.price, demand=demand+?",
        (code, new, direction, direction),
    )


# ── reputation ────────────────────────────────────────────────────────────
async def rep_add(user_id: int, org: str, delta: int) -> None:
    await db.execute(
        "INSERT INTO reputation(user_id,org,value) VALUES(?,?,?) "
        "ON CONFLICT(user_id,org) DO UPDATE SET value=value+?",
        (user_id, org, delta, delta),
    )


async def rep_all(user_id: int) -> dict[str, int]:
    rows = await db.fetchall("SELECT org,value FROM reputation WHERE user_id=?", (user_id,))
    return {r["org"]: r["value"] for r in rows}


# ── powers ────────────────────────────────────────────────────────────────
async def power_row(code: str) -> Optional[dict]:
    row = await db.fetchone("SELECT * FROM powers WHERE code=?", (code,))
    return dict(row) if row else None


async def player_powers(user_id: int) -> list[dict]:
    rows = await db.fetchall(
        "SELECT p.* FROM player_powers pp JOIN powers p ON p.code=pp.code "
        "WHERE pp.user_id=?", (user_id,))
    return [dict(r) for r in rows]


async def grant_power(user_id: int, code: str) -> bool:
    if not await power_row(code):
        return False
    cur = await db.scalar(
        "SELECT COUNT(*) FROM player_powers WHERE user_id=? AND code=?", (user_id, code))
    if cur:
        return False
    await db.execute("INSERT INTO player_powers(user_id,code) VALUES(?,?)", (user_id, code))
    await db.log("power", f"قدرت {code} داده شد", user_id)
    return True


async def random_power_for(user_id: int) -> Optional[dict]:
    owned = {p["code"] for p in await player_powers(user_id)}
    rows = await db.fetchall("SELECT * FROM powers")
    pool = [dict(r) for r in rows if r["code"] not in owned]
    if not pool:
        return None
    return random.choice(pool)


# ── combat ────────────────────────────────────────────────────────────────
async def resolve_attack(att: dict, dfn: dict, power: Optional[dict] = None) -> dict:
    a = await effective(att)
    d = await effective(dfn)
    roll = random.randint(1, 20)
    dodge = min(35, d["stealth"] * 2)
    if roll == 1 or random.randint(1, 100) <= dodge:
        return {"hit": False, "damage": 0, "crit": False, "roll": roll}
    base = a["attack"] + random.randint(0, a["attack"] // 2 + 4)
    if power:
        base += power["magnitude"]
    dmg = max(3, int(base - d["defense"] * 0.6))
    crit = roll >= 19
    if crit:
        dmg = int(dmg * 1.7)
    return {"hit": True, "damage": dmg, "crit": crit, "roll": roll}


async def damage_player(user_id: int, dmg: int) -> tuple[int, bool]:
    p = await get_player(user_id)
    if not p:
        return 0, False
    hp = p["hp"] - dmg
    if hp <= 0:
        await kill_player(user_id)
        return 0, True
    await update(user_id, hp=hp)
    return hp, False


async def kill_player(user_id: int, killer_id: int | None = None) -> None:
    """Legacy system: part of progress carries into the next generation."""
    p = await get_player(user_id)
    if not p:
        return
    legacy = p["legacy"] + p["level"] * 2 + p["money"] // 5000
    keep_money = p["money"] // 4
    await update(
        user_id,
        hp=100, max_hp=100 + legacy, energy=100,
        attack=10 + legacy // 2, defense=8 + legacy // 2,
        stealth=5, intellect=5,
        infection=0, stage="human", path="survivor",
        money=keep_money + legacy * 100,
        xp=0, level=1, heat=0,
        legacy=legacy, generation=p["generation"] + 1,
        alive=1, deaths=p["deaths"] + 1, org_id=None, org_rank="recruit",
    )
    await db.execute("DELETE FROM mutations WHERE user_id=?", (user_id,))
    await db.execute("DELETE FROM player_powers WHERE user_id=?", (user_id,))
    if killer_id:
        await add(killer_id, kills=1, heat=8)
        await grant_xp(killer_id, 120)
    await db.log("death", f"{p['name']} کشته شد (نسل {p['generation']} → "
                          f"{p['generation'] + 1}, Legacy {legacy})", user_id)


# ── seeding ───────────────────────────────────────────────────────────────
async def seed() -> None:
    for pw in POWERS:
        await db.execute(
            "INSERT OR IGNORE INTO powers"
            "(code,name,icon,description,cooldown,risk,counter,power_type,magnitude,custom)"
            " VALUES(?,?,?,?,?,?,?,?,?,0)",
            (pw["code"], pw["name"], pw["icon"], pw["description"], pw["cooldown"],
             pw["risk"], pw["counter"], pw["power_type"], pw["magnitude"]),
        )
    for org in content.SYSTEM_ORGS:
        await db.execute(
            "INSERT OR IGNORE INTO orgs(code,name,icon,funds,research,power,founded_at,system)"
            " VALUES(?,?,?,?,?,?,?,1)",
            (org["code"], org["name"], org["icon"], 1_000_000, 50, 100, NOW()),
        )
    for m in content.BASE_MISSIONS:
        await db.execute(
            "INSERT OR IGNORE INTO missions"
            "(code,title,org,difficulty,reward,infection,rep,description,active)"
            " VALUES(?,?,?,?,?,?,?,?,1)",
            (m["code"], m["title"], m["org"], m["difficulty"], m["reward"],
             m["infection"], m["rep"], m["description"]),
        )
    for code, it in ITEMS.items():
        await db.execute("INSERT OR IGNORE INTO economy(code,price,demand) VALUES(?,?,0)",
                         (code, it["price"]))
    if await db.world_get("threat") is None:
        await db.world_set("threat", 10)
        await db.world_set("cure_progress", 0)
        await db.world_set("vcorp_stability", 100)
