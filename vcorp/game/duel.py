"""THE HOLLOW — simultaneous-reveal PvP duels.

Design goals (this is the part that has to be *fun*, not just functional):

  • No dice deciding the winner. Both fighters commit a move in secret at the
    same time; the outcome is a read of the opponent, not a coin flip.
  • Every move costs or generates ADRENALINE, so you cannot spam the best one.
  • A clean rock-paper-scissors core, then depth on top of it:

        STRIKE  ⚔️  beats GUARD      (chips through a turtle)
        GUARD   🛡️  beats FERAL      (punishes the all-in)
        FERAL   🩸  beats STRIKE      (trades hard, wins the trade)
        READ    👁️  loses damage-wise but refunds adrenaline and, if it
                    correctly predicts a FERAL, fully counters it

  • FERAL costs infection: it hits like a truck and pushes VX-13 up. The
    infected player is genuinely stronger in the ring and genuinely closer
    to losing their character forever. That tension is the whole game.

State lives in memory only: a duel is a short, live event. If the process
restarts mid-duel, stakes are refunded by `abort_all`.
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Optional

from ..db import db
from . import engine as E

TURN_SECONDS = 45
MAX_ROUNDS = 12
START_ADRENALINE = 3

MOVES = {
    "strike": ("⚔️", "ضربه", "آسیب پایدار. سپر را می‌شکند."),
    "guard": ("🛡️", "گارد", "جذب آسیب + شارژ آدرنالین. حریص را تنبیه می‌کند."),
    "feral": ("🩸", "توحش", "آسیب سنگین، ولی آلودگی و ریسک می‌آورد."),
    "read": ("👁️", "خوانش", "آدرنالین برمی‌گرداند و توحش را کامل خنثی می‌کند."),
}

# Adrenaline economy. Negative = the move refunds. Tuned by simulation so
# that no pure strategy beats a random opponent by more than ~60%:
# STRIKE is the reliable bread-and-butter but cannot be spammed forever,
# GUARD is the engine that pays for everything else,
# FERAL is a burst you must save up for, READ is the cheap hard counter.
COST = {"strike": 2, "guard": -2, "feral": 3, "read": 1}
GUARD_REGEN = 2          # extra adrenaline for a guard that ate an attack
READ_PUNISH = 0.55       # a read that guesses wrong leaves you wide open


def _beats(a: str, b: str) -> int:
    """1 if a wins the read, -1 if b wins, 0 if neutral.

    The loop is deliberately closed so every move has a real answer:
        strike → guard → feral → strike        (the core triangle)
        read   → strike, feral                 (reading aggression)
        guard  → read                          (patience beats guessing)
    """
    wins = {("strike", "guard"), ("guard", "feral"), ("feral", "strike"),
            ("read", "feral"), ("read", "strike"), ("guard", "read")}
    if (a, b) in wins:
        return 1
    if (b, a) in wins:
        return -1
    return 0


@dataclass
class Fighter:
    user_id: int
    name: str
    hp: int
    max_hp: int
    attack: int
    defense: int
    infection: int
    adrenaline: int = START_ADRENALINE
    move: Optional[str] = None
    guard_broken: bool = False
    feral_used: int = 0
    last_move: Optional[str] = None
    repeat: int = 0          # how many times the current move was repeated
    poise: int = 0           # points from winning reads — decides a long fight

    def alive(self) -> bool:
        return self.hp > 0


@dataclass
class Duel:
    chat_id: int
    a: Fighter
    b: Fighter
    stake: int = 0
    round: int = 1
    log: list[str] = field(default_factory=list)
    message_id: Optional[int] = None
    finished: bool = False
    winner: Optional[int] = None
    reason: str = ""
    deadline: float = 0.0
    _task: Optional[asyncio.Task] = None

    def side(self, user_id: int) -> Optional[Fighter]:
        if self.a.user_id == user_id:
            return self.a
        if self.b.user_id == user_id:
            return self.b
        return None

    def foe(self, user_id: int) -> Fighter:
        return self.b if self.a.user_id == user_id else self.a

    def both_ready(self) -> bool:
        return self.a.move is not None and self.b.move is not None


# chat_id -> Duel  (only one live duel per group keeps the ring readable)
ACTIVE: dict[int, Duel] = {}
# user_id -> chat_id, so a player cannot fight two duels at once
BUSY: dict[int, int] = {}


def duel_of(chat_id: int) -> Optional[Duel]:
    return ACTIVE.get(chat_id)


def duel_for_user(user_id: int) -> Optional[Duel]:
    cid = BUSY.get(user_id)
    return ACTIVE.get(cid) if cid is not None else None


async def make_fighter(p: dict) -> Fighter:
    eff = await E.effective(p)
    return Fighter(
        user_id=p["user_id"], name=p["name"],
        hp=max(1, p["hp"]), max_hp=eff["max_hp"],
        attack=eff["attack"], defense=eff["defense"],
        infection=p["infection"],
    )


def register(d: Duel) -> None:
    ACTIVE[d.chat_id] = d
    BUSY[d.a.user_id] = d.chat_id
    BUSY[d.b.user_id] = d.chat_id
    d.deadline = time.time() + TURN_SECONDS


def unregister(d: Duel) -> None:
    ACTIVE.pop(d.chat_id, None)
    BUSY.pop(d.a.user_id, None)
    BUSY.pop(d.b.user_id, None)


def _damage(att: Fighter, dfn: Fighter, mult: float, pierce: float = 0.0) -> int:
    soak = dfn.defense * (1.0 - pierce)
    raw = att.attack * mult + random.randint(0, max(1, att.attack // 3))
    return max(2, int(raw - soak * 0.5))


def resolve_round(d: Duel) -> list[str]:
    """Apply both committed moves simultaneously. Returns narration lines."""
    a, b = d.a, d.b
    ma, mb = a.move or "guard", b.move or "guard"
    out: list[str] = []
    ia, ib = MOVES[ma][0], MOVES[mb][0]
    out.append(f"{ia} <b>{a.name}</b>  ×  <b>{b.name}</b> {ib}")

    # adrenaline settles first; a move you cannot afford degrades to GUARD
    for f, m in ((a, ma), (b, mb)):
        if COST[m] > f.adrenaline:
            if f is a:
                ma = "guard"
            else:
                mb = "guard"
            out.append(f"⚡ <b>{f.name}</b> آدرنالین کم آورد — به گارد افتاد.")
    a.adrenaline = max(0, min(9, a.adrenaline - COST[ma]))
    b.adrenaline = max(0, min(9, b.adrenaline - COST[mb]))

    # Telegraphing: repeating the same move makes it readable and weaker.
    # This is what stops a duel from collapsing into one dominant button.
    for f, m in ((a, ma), (b, mb)):
        f.repeat = f.repeat + 1 if f.last_move == m else 0
        f.last_move = m
    fatigue_a = max(0.15, 1.0 - 0.40 * a.repeat)
    fatigue_b = max(0.15, 1.0 - 0.40 * b.repeat)

    edge = _beats(ma, mb)

    def hit(att: Fighter, dfn: Fighter, mv: str, foe_mv: str, won: bool) -> int:
        """Damage dealt by `att` playing `mv` against `dfn` playing `foe_mv`."""
        if mv in ("guard", "read"):
            return 0
        if mv == "feral":
            att.feral_used += 1
            if foe_mv == "read":          # a correct read fully stops FERAL
                return 0
        mult = {"strike": 1.0, "feral": 1.9}[mv]
        # STRIKE punches through the GUARD it out-reads
        pierce = 0.5 if (mv == "strike" and won) else 0.0
        dmg = _damage(att, dfn, mult, pierce)
        if foe_mv == "guard":
            # even a guard that loses the read still soaks; a predictable
            # attacker gets soaked much harder
            soak = 0.55 if won else 0.30
            dmg = int(dmg * max(0.10, soak - 0.15 * att.repeat))
        if foe_mv == "read":
            # reading a STRIKE blunts it; being read while feral is fatal
            dmg = int(dmg * (0.55 if mv == "strike" else 1.0 + READ_PUNISH))
        return dmg

    dmg_a = int(hit(a, b, ma, mb, edge > 0) * fatigue_a)
    dmg_b = int(hit(b, a, mb, ma, edge < 0) * fatigue_b)

    # A defensive move that wins the read does not just survive — it punishes.
    # Without this, GUARD/READ can never close a game and STRIKE dominates.
    def riposte(dfn: Fighter, att: Fighter, mv: str, foe_mv: str) -> int:
        # A defender always answers an incoming attack. Standing there taking
        # free hits is what made pure defence unplayable.
        if mv == "guard" and foe_mv == "feral":
            return _damage(dfn, att, 1.05)      # turn the wild swing around
        if mv == "guard" and foe_mv == "strike":
            return _damage(dfn, att, 0.78)      # shield bash
        if mv == "read" and foe_mv == "feral":
            return _damage(dfn, att, 1.15)      # perfect counter
        if mv == "read" and foe_mv == "strike":
            return _damage(dfn, att, 0.18)      # glancing counter-jab
        return 0

    rip_a = int(riposte(a, b, ma, mb) * fatigue_a)
    rip_b = int(riposte(b, a, mb, ma) * fatigue_b)

    # POISE: winning the mind-game scores, even with a defensive move.
    # Without this a pure defender can never win and the meta collapses.
    if edge > 0:
        a.poise += 2 if ma in ("guard", "read") else 1
    elif edge < 0:
        b.poise += 2 if mb in ("guard", "read") else 1
    dmg_a += rip_a
    dmg_b += rip_b

    # a guard that actually absorbed a blow converts it into adrenaline
    if ma == "guard" and dmg_b > 0:
        a.adrenaline = min(9, a.adrenaline + GUARD_REGEN)
    if mb == "guard" and dmg_a > 0:
        b.adrenaline = min(9, b.adrenaline + GUARD_REGEN)

    b.hp = max(0, b.hp - dmg_a)
    a.hp = max(0, a.hp - dmg_b)

    if dmg_a:
        tag = " · 🔓 سپر شکست" if ma == "strike" and edge > 0 else ""
        tag += " · ↩️ ضدحمله" if rip_a else ""
        out.append(f"➡️ <b>{a.name}</b> {dmg_a} آسیب زد{tag}")
    if dmg_b:
        tag = " · 🔓 سپر شکست" if mb == "strike" and edge < 0 else ""
        tag += " · ↩️ ضدحمله" if rip_b else ""
        out.append(f"⬅️ <b>{b.name}</b> {dmg_b} آسیب زد{tag}")
    if ma == "read" and mb == "feral":
        out.append(f"👁️ <b>{a.name}</b> توحش را خواند و کامل خنثی کرد!")
    if mb == "read" and ma == "feral":
        out.append(f"👁️ <b>{b.name}</b> توحش را خواند و کامل خنثی کرد!")
    # patience beats guessing: a guard punishes a whiffed read hard
    if ma == "guard" and mb == "read":
        b.adrenaline = max(0, b.adrenaline - 2)
        out.append(f"🛡️ <b>{a.name}</b> صبر کرد — خوانش <b>{b.name}</b> هدر رفت.")
    if mb == "guard" and ma == "read":
        a.adrenaline = max(0, a.adrenaline - 2)
        out.append(f"🛡️ <b>{b.name}</b> صبر کرد — خوانش <b>{a.name}</b> هدر رفت.")
    if a.repeat >= 2:
        out.append(f"📉 <b>{a.name}</b> الگویش لو رفته — ضربه‌اش کم‌اثر شد.")
    if b.repeat >= 2:
        out.append(f"📉 <b>{b.name}</b> الگویش لو رفته — ضربه‌اش کم‌اثر شد.")
    if not dmg_a and not dmg_b:
        out.append("🌫️ هیچ‌کدام باز نشدند. تنش بالا رفت.")

    a.move = b.move = None
    return out


def check_end(d: Duel) -> bool:
    if not d.a.alive() or not d.b.alive():
        if not d.a.alive() and not d.b.alive():
            d.winner, d.reason = None, "هر دو سقوط کردند"
        elif not d.b.alive():
            d.winner, d.reason = d.a.user_id, "ناک‌اوت"
        else:
            d.winner, d.reason = d.b.user_id, "ناک‌اوت"
        d.finished = True
        return True
    if d.round > MAX_ROUNDS:
        # judged decision: HP share first, poise breaks anything close
        pa = d.a.hp / max(1, d.a.max_hp)
        pb = d.b.hp / max(1, d.b.max_hp)
        if abs(pa - pb) < 0.12:
            if d.a.poise == d.b.poise:
                d.winner, d.reason = None, "مساوی — زنگ پایان"
            else:
                d.winner = d.a.user_id if d.a.poise > d.b.poise else d.b.user_id
                d.reason = f"برتری تکنیکی ({max(d.a.poise, d.b.poise)} امتیاز خوانش)"
        else:
            d.winner = d.a.user_id if pa > pb else d.b.user_id
            d.reason = "برتری امتیازی"
        d.finished = True
        return True
    return False


def elo_delta(winner_elo: int, loser_elo: int, k: int = 32) -> int:
    exp = 1.0 / (1.0 + 10 ** ((loser_elo - winner_elo) / 400.0))
    return max(5, int(k * (1.0 - exp)))


async def settle(d: Duel) -> dict:
    """Persist the result: money, elo, streaks, infection, history."""
    a = await E.get_player(d.a.user_id)
    b = await E.get_player(d.b.user_id)
    if not a or not b:
        return {}
    res: dict = {"stake": d.stake, "winner": d.winner, "reason": d.reason}

    # carry ring damage back into the world, but never kill outright here:
    # THE HOLLOW is a fight pit, not an execution. Survivors leave at 1 HP.
    await E.update(d.a.user_id, hp=max(1, d.a.hp))
    await E.update(d.b.user_id, hp=max(1, d.b.hp))

    # feral use costs VX-13 progression
    for f in (d.a, d.b):
        if f.feral_used:
            new, stage, changed = await E.apply_infection(
                f.user_id, min(12, 2 * f.feral_used))
            if f.user_id == d.a.user_id:
                res["a_inf"], res["a_stage_changed"], res["a_stage"] = new, changed, stage
            else:
                res["b_inf"], res["b_stage_changed"], res["b_stage"] = new, changed, stage

    if d.winner is None:
        # draw: stakes returned, small elo drift toward each other
        if d.stake:
            await E.add(d.a.user_id, money=d.stake)
            await E.add(d.b.user_id, money=d.stake)
        await E.update(d.a.user_id, streak=0)
        await E.update(d.b.user_id, streak=0)
        res["delta"] = 0
    else:
        win_id = d.winner
        lose_id = d.b.user_id if win_id == d.a.user_id else d.a.user_id
        w = a if win_id == a["user_id"] else b
        l = b if win_id == a["user_id"] else a
        delta = elo_delta(w["elo"], l["elo"])
        pot = d.stake * 2
        await E.add(win_id, money=pot, elo=delta, duel_wins=1, streak=1)
        await E.add(lose_id, elo=-delta, duel_losses=1)
        await E.update(lose_id, streak=0)
        await E.grant_xp(win_id, 120)
        await E.grant_xp(lose_id, 45)
        res["delta"] = delta
        res["pot"] = pot
        res["winner_name"] = w["name"]
        res["loser_name"] = l["name"]
        res["streak"] = (await E.get_player(win_id))["streak"]

    await db.execute(
        "INSERT INTO duels(chat_id,a_id,b_id,stake,winner_id,rounds,reason,elo_delta,at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (d.chat_id, d.a.user_id, d.b.user_id, d.stake, d.winner,
         d.round, d.reason, res.get("delta", 0), int(time.time())))
    await db.log("duel", f"{d.a.name} vs {d.b.name} — {d.reason}", d.winner, d.chat_id)
    unregister(d)
    return res


async def abort(d: Duel, reason: str) -> None:
    """Cancel a duel and refund both stakes."""
    if d.stake:
        await E.add(d.a.user_id, money=d.stake)
        await E.add(d.b.user_id, money=d.stake)
    d.finished = True
    d.reason = reason
    if d._task:
        d._task.cancel()
    unregister(d)


async def abort_all(reason: str = "ری‌استارت سرور") -> int:
    n = 0
    for d in list(ACTIVE.values()):
        await abort(d, reason)
        n += 1
    return n
