"""LOCKDOWN — پروتکل قرنطینه: hidden-role social deduction for the whole group.

A round of LOCKDOWN is the one mode that cannot exist outside a group: it needs
a crowd that can lie to each other.

    🦠 حامل (carrier)   knows the other carriers, converts one person per night
    🔬 غربالگر (screener) tests one person per night, learns if they are a carrier
    🪖 مأمور مهار (enforcer) shields one person per night, blocking the conversion
    🧑 بازمانده (survivor) has only a voice and a vote

Night actions arrive by private message so the group never sees them. During the
day the whole group votes in the open. Carriers win by reaching parity; the
facility wins by purging every carrier.

This module is deliberately pure: no aiogram, no I/O, no timers. It is a state
machine plus resolution rules, so the whole thing is testable offline and the
handler layer only has to move time forward.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

MIN_PLAYERS = 4
MAX_PLAYERS = 20

LOBBY_SECONDS = 90
NIGHT_SECONDS = 75
DAY_SECONDS = 120


class Phase(str, Enum):
    LOBBY = "lobby"
    NIGHT = "night"
    DAY = "day"
    ENDED = "ended"


class Role(str, Enum):
    CARRIER = "carrier"
    SCREENER = "screener"
    ENFORCER = "enforcer"
    SURVIVOR = "survivor"


ROLE_META = {
    Role.CARRIER: ("🦠", "حامل", "هر شب یک نفر را تبدیل کن. لو نرو."),
    Role.SCREENER: ("🔬", "غربالگر", "هر شب خون یک نفر را تست کن."),
    Role.ENFORCER: ("🪖", "مأمور مهار", "هر شب از یک نفر محافظت کن."),
    Role.SURVIVOR: ("🧑", "بازمانده", "فقط صدا و رأی داری. کافی است."),
}


@dataclass
class LPlayer:
    user_id: int
    name: str
    role: Role = Role.SURVIVOR
    alive: bool = True
    out_reason: str = ""
    # night bookkeeping
    tested_by: bool = False
    shielded: bool = False


@dataclass
class Lockdown:
    chat_id: int
    host_id: int
    players: dict[int, LPlayer] = field(default_factory=dict)
    phase: Phase = Phase.LOBBY
    round: int = 0
    # night intents: actor_id -> target_id
    convert_votes: dict[int, int] = field(default_factory=dict)
    screen_pick: dict[int, int] = field(default_factory=dict)
    shield_pick: dict[int, int] = field(default_factory=dict)
    last_shield: Optional[int] = None
    # day votes: voter_id -> target_id (or 0 for skip)
    day_votes: dict[int, int] = field(default_factory=dict)
    winner: Optional[str] = None
    log: list[str] = field(default_factory=list)
    message_id: Optional[int] = None
    deadline: float = 0.0
    stake: int = 0
    pot: int = 0
    _task: object = None

    # ── membership ────────────────────────────────────────────────────────
    def alive_players(self) -> list[LPlayer]:
        return [p for p in self.players.values() if p.alive]

    def carriers(self, alive_only: bool = True) -> list[LPlayer]:
        return [p for p in self.players.values()
                if p.role is Role.CARRIER and (p.alive or not alive_only)]

    def humans(self) -> list[LPlayer]:
        return [p for p in self.alive_players() if p.role is not Role.CARRIER]

    def role_holder(self, role: Role) -> Optional[LPlayer]:
        for p in self.alive_players():
            if p.role is role:
                return p
        return None

    def add(self, user_id: int, name: str) -> bool:
        if self.phase is not Phase.LOBBY:
            return False
        if user_id in self.players or len(self.players) >= MAX_PLAYERS:
            return False
        self.players[user_id] = LPlayer(user_id=user_id, name=name)
        return True

    def remove(self, user_id: int) -> bool:
        if self.phase is not Phase.LOBBY:
            return False
        return self.players.pop(user_id, None) is not None


def carrier_count(n: int) -> int:
    """Tuned by simulation against informed play (see tests/test_lockdown.py).

    Carriers snowball on their own, so the count stays low; but in very small
    rounds a lone carrier is found too fast, and at 11+ a pair gets drowned
    out by the crowd.
    """
    if n >= 11:
        return 3
    if n >= 6:
        return 2
    return 1


def assign_roles(g: Lockdown, rng: random.Random | None = None) -> None:
    rng = rng or random
    ids = list(g.players)
    rng.shuffle(ids)
    n = len(ids)
    roles: list[Role] = [Role.CARRIER] * carrier_count(n)
    if n >= 5:
        roles.append(Role.SCREENER)
    if n >= 6:
        roles.append(Role.ENFORCER)
    roles += [Role.SURVIVOR] * (n - len(roles))
    for uid, role in zip(ids, roles):
        g.players[uid].role = role


def start(g: Lockdown, rng: random.Random | None = None) -> None:
    assign_roles(g, rng)
    g.phase = Phase.NIGHT
    g.round = 1
    g.log = ["🌑 شب اول. چراغ‌ها خاموش شد."]


# ── night ─────────────────────────────────────────────────────────────────
def can_convert(g: Lockdown, actor_id: int, target_id: int) -> tuple[bool, str]:
    a = g.players.get(actor_id)
    t = g.players.get(target_id)
    if g.phase is not Phase.NIGHT:
        return False, "الان شب نیست."
    if not a or not a.alive or a.role is not Role.CARRIER:
        return False, "تو حامل نیستی."
    if not t or not t.alive:
        return False, "هدف در بازی نیست."
    if t.role is Role.CARRIER:
        return False, "او هم حامل است."
    return True, ""


def set_convert(g: Lockdown, actor_id: int, target_id: int) -> tuple[bool, str]:
    ok, err = can_convert(g, actor_id, target_id)
    if not ok:
        return False, err
    g.convert_votes[actor_id] = target_id
    return True, ""


def set_screen(g: Lockdown, actor_id: int, target_id: int) -> tuple[bool, str]:
    a = g.players.get(actor_id)
    t = g.players.get(target_id)
    if g.phase is not Phase.NIGHT:
        return False, "الان شب نیست."
    if not a or not a.alive or a.role is not Role.SCREENER:
        return False, "تو غربالگر نیستی."
    if not t or not t.alive:
        return False, "هدف در بازی نیست."
    if target_id == actor_id:
        return False, "خودت را تست نکن."
    g.screen_pick = {actor_id: target_id}
    return True, ""


def set_shield(g: Lockdown, actor_id: int, target_id: int) -> tuple[bool, str]:
    a = g.players.get(actor_id)
    t = g.players.get(target_id)
    if g.phase is not Phase.NIGHT:
        return False, "الان شب نیست."
    if not a or not a.alive or a.role is not Role.ENFORCER:
        return False, "تو مأمور مهار نیستی."
    if not t or not t.alive:
        return False, "هدف در بازی نیست."
    if target_id == g.last_shield:
        return False, "دو شب پشت‌سرهم از یک نفر محافظت نمی‌شود."
    g.shield_pick = {actor_id: target_id}
    return True, ""


def _majority_target(votes: dict[int, int], rng: random.Random) -> Optional[int]:
    if not votes:
        return None
    tally: dict[int, int] = {}
    for t in votes.values():
        tally[t] = tally.get(t, 0) + 1
    best = max(tally.values())
    tied = [t for t, c in tally.items() if c == best]
    return rng.choice(tied)


def resolve_night(g: Lockdown, rng: random.Random | None = None) -> list[str]:
    """Apply every night intent at once and move the game to day."""
    rng = rng or random
    out: list[str] = []
    if g.phase is not Phase.NIGHT:
        return out

    shielded_id = next(iter(g.shield_pick.values()), None)
    if shielded_id is not None:
        g.last_shield = shielded_id
    else:
        g.last_shield = None

    # carriers act as one; if they never picked, the virus stays quiet.
    # Night 1 is incubation: no conversion. Without this the facility starts
    # a man down before it has learned anything and the round is a coin flip.
    target_id = None
    if g.round > 1:
        target_id = _majority_target(g.convert_votes, rng)
        if target_id is None:
            alive_targets = [p.user_id for p in g.alive_players()
                             if p.role is not Role.CARRIER]
            if alive_targets and g.carriers():
                target_id = rng.choice(alive_targets)

    if g.round == 1:
        out.append("🌑 شب اول — ویروس در حال نهفتگی است. کسی از دست نرفت.")
    elif target_id is not None:
        victim = g.players[target_id]
        if target_id == shielded_id:
            out.append(f"🪖 مهار موفق — تلاش برای تبدیل <b>{victim.name}</b> خنثی شد.")
        elif not victim.alive:
            out.append("🌑 شب بدون اتفاق گذشت.")
        else:
            victim.alive = False
            victim.out_reason = "تبدیل شد"
            out.append(f"🦠 <b>{victim.name}</b> شب تبدیل شد و به قرنطینه رفت.")
    else:
        out.append("🌑 شب بدون اتفاق گذشت.")

    g.convert_votes.clear()
    g.shield_pick.clear()
    g.phase = Phase.DAY
    g.day_votes.clear()
    g.log = out
    return out


def screening_result(g: Lockdown) -> Optional[tuple[int, str, bool]]:
    """(screener_id, target_name, is_carrier) — resolved before night is cleared."""
    if not g.screen_pick:
        return None
    sid, tid = next(iter(g.screen_pick.items()))
    t = g.players.get(tid)
    if not t:
        return None
    return sid, t.name, t.role is Role.CARRIER


# ── day ───────────────────────────────────────────────────────────────────
def set_vote(g: Lockdown, voter_id: int, target_id: int) -> tuple[bool, str]:
    v = g.players.get(voter_id)
    if g.phase is not Phase.DAY:
        return False, "الان روز نیست."
    if not v or not v.alive:
        return False, "فقط زنده‌ها رأی می‌دهند."
    if target_id != 0:
        t = g.players.get(target_id)
        if not t or not t.alive:
            return False, "هدف در بازی نیست."
    g.day_votes[voter_id] = target_id
    return True, ""


def vote_tally(g: Lockdown) -> dict[int, int]:
    tally: dict[int, int] = {}
    for t in g.day_votes.values():
        tally[t] = tally.get(t, 0) + 1
    return tally


def everyone_voted(g: Lockdown) -> bool:
    return len(g.day_votes) >= len(g.alive_players())


def resolve_day(g: Lockdown) -> list[str]:
    """Purge whoever the group agreed on. A tie protects everyone."""
    out: list[str] = []
    if g.phase is not Phase.DAY:
        return out
    tally = {t: c for t, c in vote_tally(g).items() if t != 0}
    if not tally:
        out.append("🕊️ کسی رأی نداد. قرنطینه ادامه دارد.")
    else:
        best = max(tally.values())
        tied = [t for t, c in tally.items() if c == best]
        if len(tied) > 1:
            out.append("⚖️ رأی‌ها گره خورد — هیچ‌کس پاکسازی نشد.")
        else:
            victim = g.players[tied[0]]
            victim.alive = False
            victim.out_reason = "پاکسازی شد"
            icon, label, _ = ROLE_META[victim.role]
            out.append(f"🗳️ گروه <b>{victim.name}</b> را پاکسازی کرد.")
            out.append(f"پرونده باز شد: او {icon} <b>{label}</b> بود.")
    g.day_votes.clear()
    g.screen_pick.clear()
    g.phase = Phase.NIGHT
    g.round += 1
    g.log = out
    return out


# ── win conditions ────────────────────────────────────────────────────────
def check_win(g: Lockdown) -> Optional[str]:
    if g.phase is Phase.ENDED:
        return g.winner
    carriers = len(g.carriers())
    humans = len(g.humans())
    if carriers == 0:
        g.winner, g.phase = "facility", Phase.ENDED
    elif carriers >= humans:
        g.winner, g.phase = "carriers", Phase.ENDED
    return g.winner


def summary(g: Lockdown) -> list[str]:
    lines = []
    for p in g.players.values():
        icon, label, _ = ROLE_META[p.role]
        state = "✅" if p.alive else "☠️"
        lines.append(f"{state} {icon} <b>{p.name}</b> — {label}"
                     + (f" ({p.out_reason})" if not p.alive else ""))
    return lines


def payouts(g: Lockdown) -> dict[int, int]:
    """Split the pot among the winning side; survivors of the losing side get 0."""
    if not g.winner:
        return {}
    if g.winner == "carriers":
        winners = [p.user_id for p in g.carriers(alive_only=False)]
    else:
        winners = [p.user_id for p in g.players.values()
                   if p.role is not Role.CARRIER]
    if not winners or not g.pot:
        return {uid: 0 for uid in winners}
    share = g.pot // len(winners)
    return {uid: share for uid in winners}
