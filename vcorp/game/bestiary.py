"""The bestiary: every world boss is a different fight, not a reskin.

Each entry owns its portrait, its stat profile and one mechanic that changes
how the group has to attack it. A mechanic is a pure function of the current
fight state, so it is fully testable and never touches Telegram.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

# ── mechanic result ───────────────────────────────────────────────────────


@dataclass
class Blow:
    """The outcome of one player's strike after the boss mechanic runs."""
    damage: int
    recoil: int                     # extra damage back to the attacker
    note: str = ""                  # one line shown in the group


MechanicFn = Callable[["BossKind", dict, int, int, random.Random], Blow]


# ── mechanics ─────────────────────────────────────────────────────────────
def m_armor(kind: "BossKind", state: dict, dmg: int, pins: int,
            rng: random.Random) -> Blow:
    """AVAR — concrete plating. Weak hits glance off; heavy hits crack it.

    Counter-play: stop chipping. Land a big roll or bring more attack.
    """
    thr = state.get("armor_threshold", 45)
    if dmg < thr:
        return Blow(max(1, dmg // 4), 0, "🪨 زره بتنی — ضربه سُر خورد.")
    cracked = state.get("cracks", 0) + 1
    state["cracks"] = cracked
    bonus = int(dmg * (0.15 * min(cracked, 4)))
    return Blow(dmg + bonus, 0,
                f"🪨 ترک برداشت! (شکاف {min(cracked, 4)}/4) +{bonus}")


def m_swarm(kind: "BossKind", state: dict, dmg: int, pins: int,
            rng: random.Random) -> Blow:
    """HIVE — splits into drones. Every hit spawns retaliation.

    Counter-play: burst it down fast; a long fight bleeds the whole group.
    """
    drones = state.get("drones", 0) + 1
    state["drones"] = drones
    sting = min(30, drones * 3)
    return Blow(dmg, sting, f"🐝 {drones} پهپاد زنده — نیش {sting}")


def m_regen(kind: "BossKind", state: dict, dmg: int, pins: int,
            rng: random.Random) -> Blow:
    """AMALGAM — knits itself back together between blows.

    Counter-play: sustained group pressure; gaps let it heal.
    """
    heal = state.get("regen", 26)
    return Blow(dmg, 0, f"🩸 بافت ترمیم می‌شود — +{heal} به باس")


def m_frenzy(kind: "BossKind", state: dict, dmg: int, pins: int,
             rng: random.Random) -> Blow:
    """SECTOR 9 — a horde that gets angrier as it thins.

    Counter-play: it hits hardest at the end, so finish it with a full HP bar.
    """
    lost = 1.0 - state.get("hp_ratio", 1.0)
    rage = int(10 + 45 * lost)
    return Blow(int(dmg * (1.0 + 0.25 * lost)), rage,
                f"🧟 هرچه کمتر، خشمگین‌تر — ضدحمله {rage}")


def m_shield(kind: "BossKind", state: dict, dmg: int, pins: int,
             rng: random.Random) -> Blow:
    """TITAN — cycles a containment shield every few hits.

    Counter-play: read the cycle and time your cooldown, or waste the hit.
    """
    tick = state.get("tick", 0) + 1
    state["tick"] = tick
    if tick % 3 == 0:
        return Blow(max(1, dmg // 6), 12,
                    "🛡️ سپر مهار فعال بود — ضربه دفع شد.")
    if pins >= 6:
        return Blow(int(dmg * 1.6), 0, "🎯 شکاف زره — ضربه کامل!")
    return Blow(dmg, 0, "")


@dataclass(frozen=True)
class BossKind:
    key: str
    icon: str
    name: str
    tagline: str
    art: str                        # workspace path to its portrait
    hp_mult: float
    attack_mult: float
    reward_mult: float
    mechanic: MechanicFn
    mechanic_hint: str
    init: dict


BESTIARY: list[BossKind] = [
    BossKind(
        "avar", "🗿", "سوژه ۰۴ — «آوار»",
        "چیزی که از زیر آوار سکتور ۳ بیرون آمد.",
        "brand/boss_avar.jpg",
        hp_mult=1.35, attack_mult=0.85, reward_mult=1.15,
        mechanic=m_armor,
        mechanic_hint="🪨 <b>زره بتنی</b> — ضربه‌های ضعیف سُر می‌خورند. "
                      "محکم بزن وگرنه وقتت تلف است.",
        init={"armor_threshold": 45, "cracks": 0},
    ),
    BossKind(
        "hive", "🐝", "کندوی متحرک",
        "یک میزبان، هزار ساکن.",
        "brand/boss_hive.jpg",
        hp_mult=1.05, attack_mult=0.70, reward_mult=1.00,
        mechanic=m_swarm,
        mechanic_hint="🐝 <b>ازدحام</b> — هر ضربه یک پهپاد آزاد می‌کند و "
                      "نیش‌ها جمع می‌شوند. سریع تمامش کنید.",
        init={"drones": 0},
    ),
    BossKind(
        "amalgam", "🩸", "توده هم‌جوش",
        "دیگر معلوم نیست چند نفر بوده.",
        "brand/boss_amalgam.jpg",
        hp_mult=1.10, attack_mult=0.95, reward_mult=1.10,
        mechanic=m_regen,
        mechanic_hint="🩸 <b>ترمیم</b> — بین ضربه‌ها خودش را می‌دوزد. "
                      "فشار گروهی پیوسته لازم است.",
        init={"regen": 26},
    ),
    BossKind(
        "sector9", "🧟", "دسته سکتور ۹",
        "یک تن نیست. یک جمعیت است.",
        "brand/boss_sector9.jpg",
        hp_mult=1.00, attack_mult=1.00, reward_mult=1.05,
        mechanic=m_frenzy,
        mechanic_hint="🧟 <b>جنون</b> — هرچه جانش کمتر شود خشمگین‌تر می‌زند. "
                      "با جان پر واردش شوید.",
        init={},
    ),
    BossKind(
        "titan", "🦾", "نمونه تیتان",
        "پروژه‌ای که V-CORP هرگز تأییدش نکرد.",
        "brand/boss_titan.jpg",
        hp_mult=1.45, attack_mult=1.20, reward_mult=1.35,
        mechanic=m_shield,
        mechanic_hint="🛡️ <b>سپر دوره‌ای</b> — هر ضربه سوم دفع می‌شود. "
                      "ضربه ۶ 🎳 زره را می‌شکافد.",
        init={"tick": 0},
    ),
]

BY_KEY = {b.key: b for b in BESTIARY}


def pick(rng: random.Random | None = None) -> BossKind:
    return (rng or random).choice(BESTIARY)


def scale(kind: BossKind, players: int) -> tuple[int, int, int]:
    """Return (hp, attack, reward) for this boss against a group of N."""
    players = max(1, players)
    hp = int((1100 + players * 260) * kind.hp_mult)
    attack = int((25 + players * 2) * kind.attack_mult)
    reward = int((4000 + players * 900) * kind.reward_mult)
    return hp, attack, reward


def strike(kind: BossKind, state: dict, raw_damage: int, pins: int,
           hp: int, max_hp: int, rng: random.Random | None = None) -> Blow:
    """Run this boss's mechanic over a raw hit.

    `state` is the boss's mutable fight state and is updated in place.
    """
    rng = rng or random.Random()
    state["hp_ratio"] = hp / max(1, max_hp)
    blow = kind.mechanic(kind, state, max(1, raw_damage), pins, rng)
    return Blow(max(1, blow.damage), max(0, blow.recoil), blow.note)


def post_hit(kind: BossKind, state: dict, hp: int, max_hp: int) -> int:
    """Boss-side effects applied after damage lands. Returns the new HP."""
    if kind.mechanic is m_regen and 0 < hp < max_hp:
        return min(max_hp, hp + state.get("regen", 26))
    return hp
