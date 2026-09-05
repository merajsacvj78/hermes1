"""THE CONVOY — cooperative escape run for a whole group.

Where THE HOLLOW is one-on-one and LOCKDOWN turns the group against itself,
THE CONVOY points everyone the same direction: three trucks, one cracked
highway, and a quarantine zone closing behind you.

The convoy is a single shared body with three vital signs — fuel, hull and
morale. Each leg of the road throws one hazard at it. Every player privately
commits a station (repair / siphon / defend / scout / ration), then the group
publicly votes a speed. The hazard is resolved against what the group actually
staffed, not against dice.

This module is a pure state machine: no aiogram, no IO, no timers. Randomness
is always injected so every outcome is reproducible in tests.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

MIN_PLAYERS = 3
MAX_PLAYERS = 25

LOBBY_SECONDS = 90
STATION_SECONDS = 75
SPEED_SECONDS = 45

DISTANCE_GOAL = 105          # kilometres to the cordon
MAX_LEGS = 12                # the zone seals after this many legs

START_FUEL = 60
START_HULL = 100
START_MORALE = 70
CAP = 130              # headroom so a short crew's bonus is not clipped away
ATTRITION = 5          # morale the road takes every leg, no matter what
WEAR = 9               # hull the road takes every leg, even when unscathed


class Phase(str, Enum):
    LOBBY = "lobby"
    STATION = "station"      # private: pick your post
    SPEED = "speed"          # public: how hard do we push
    ENDED = "ended"


class Station(str, Enum):
    REPAIR = "repair"
    SIPHON = "siphon"
    DEFEND = "defend"
    SCOUT = "scout"
    RATION = "ration"


STATION_META: dict[Station, tuple[str, str, str]] = {
    Station.REPAIR: ("🔧", "تعمیرکار", "بدنه را می‌دوزد. بدون او هر خراش می‌ماند."),
    Station.SIPHON: ("⛽", "سوخت‌گیر", "از لاشه‌ها بنزین می‌کشد. کند ولی حیاتی."),
    Station.DEFEND: ("🔫", "تیرانداز", "چیزی که به کاروان می‌رسد را عقب می‌راند."),
    Station.SCOUT: ("🔭", "دیده‌بان", "خطر بعدی را زودتر می‌بیند."),
    Station.RATION: ("🍖", "سرآشپز", "روحیه را بالا نگه می‌دارد. روحیه صفر یعنی شورش."),
}


class Speed(str, Enum):
    CAREFUL = "careful"
    STEADY = "steady"
    RECKLESS = "reckless"


# distance, fuel burn, hazard severity multiplier, morale drift
SPEED_META: dict[Speed, tuple[str, str, int, int, float, int]] = {
    Speed.CAREFUL: ("🐌", "محتاط", 6, 4, 0.65, +2),
    Speed.STEADY: ("🚚", "یکنواخت", 9, 7, 1.00, 0),
    Speed.RECKLESS: ("🔥", "بی‌پروا", 14, 11, 1.55, -3),
}


@dataclass(frozen=True)
class Hazard:
    key: str
    icon: str
    title: str
    body: str
    # station -> how many staffers are needed to fully answer this hazard
    demand: dict[Station, int]
    # what an unanswered hazard costs, per missing staffer
    hull_per_miss: int = 0
    fuel_per_miss: int = 0
    morale_per_miss: int = 0
    # what it costs even when fully answered
    hull_floor: int = 0


HAZARDS: list[Hazard] = [
    Hazard("swarm", "🧟", "دسته روی جاده",
           "ده‌ها آلوده از مه بیرون زدند و به کاروان چسبیدند.",
           {Station.DEFEND: 2}, hull_per_miss=9, morale_per_miss=5),
    Hazard("blockade", "🚧", "مسیر مسدود",
           "یک تصادف زنجیره‌ای جاده را بسته. باید راه باز کنید.",
           {Station.SCOUT: 1, Station.REPAIR: 1}, hull_per_miss=7, fuel_per_miss=5),
    Hazard("leak", "🩹", "نشتی سوخت",
           "یک ترکش باک کامیون دوم را سوراخ کرده.",
           {Station.REPAIR: 2}, fuel_per_miss=8, hull_per_miss=3),
    Hazard("dry", "🏜️", "باک خالی",
           "عقربه روی صفر است. باید از لاشه‌های کنار جاده بکشید.",
           {Station.SIPHON: 2}, fuel_per_miss=9, morale_per_miss=4),
    Hazard("ambush", "🎯", "کمین غارتگرها",
           "کسانی که جاده را می‌شناسند منتظرتان بودند.",
           {Station.DEFEND: 2, Station.SCOUT: 1}, hull_per_miss=8, morale_per_miss=6),
    Hazard("storm", "🌧️", "باران اسیدی",
           "باران رنگ را از بدنه می‌کند و دید را می‌بندد.",
           {Station.REPAIR: 1, Station.SCOUT: 1}, hull_per_miss=6, morale_per_miss=5,
           hull_floor=3),
    Hazard("despair", "🕯️", "شب طولانی",
           "کسی حرف نمی‌زند. بعضی می‌گویند برگردیم.",
           {Station.RATION: 2}, morale_per_miss=11),
    Hazard("checkpoint", "🚨", "ایست بازرسی متروک",
           "پست بازرسی خالی است — یا اینطور به نظر می‌رسد.",
           {Station.SCOUT: 2, Station.DEFEND: 1}, hull_per_miss=7, morale_per_miss=4),
]

HAZARD_BY_KEY = {h.key: h for h in HAZARDS}


@dataclass
class CPlayer:
    user_id: int
    name: str
    station: Station | None = None
    speed_vote: Speed | None = None
    contributed: int = 0          # legs where their post actually mattered


@dataclass
class Convoy:
    chat_id: int
    host_id: int
    stake: int = 0
    pot: int = 0
    phase: Phase = Phase.LOBBY
    players: dict[int, CPlayer] = field(default_factory=dict)
    leg: int = 0
    distance: int = 0
    fuel: int = START_FUEL
    hull: int = START_HULL
    morale: int = START_MORALE
    hazard: Hazard | None = None
    next_hazard: Hazard | None = None      # revealed to scouts
    scouted: bool = False
    log: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    winner: str = ""                       # "escaped" | "lost"
    cause: str = ""
    message_id: int | None = None
    deadline: float = 0.0

    # ── lobby ────────────────────────────────────────────────────────────
    def add(self, user_id: int, name: str) -> bool:
        if self.phase is not Phase.LOBBY or user_id in self.players:
            return False
        if len(self.players) >= MAX_PLAYERS:
            return False
        self.players[user_id] = CPlayer(user_id, name)
        return True

    def remove(self, user_id: int) -> bool:
        if self.phase is not Phase.LOBBY or user_id not in self.players:
            return False
        if user_id == self.host_id:
            return False
        del self.players[user_id]
        return True

    def crew(self) -> list[CPlayer]:
        return list(self.players.values())

    def alive(self) -> bool:
        return self.fuel > 0 and self.hull > 0 and self.morale > 0


def start(g: Convoy, rng: random.Random | None = None) -> None:
    rng = rng or random.Random()
    # A small crew cannot cover every station, so it rides a tougher truck.
    # This keeps a 3-player run tense instead of hopeless, without making a
    # 15-player run trivial.
    short = max(0, 9 - len(g.players))
    g.hull = _clamp(START_HULL + short * 2)
    g.fuel = _clamp(START_FUEL + short * 2)
    g.morale = _clamp(START_MORALE + short * 2)
    assert g.hull <= CAP and g.fuel <= CAP and g.morale <= CAP
    g.phase = Phase.STATION
    g.leg = 1
    g.hazard = rng.choice(HAZARDS)
    g.next_hazard = rng.choice(HAZARDS)
    g.scouted = False
    for p in g.players.values():
        p.station = None
        p.speed_vote = None


def set_station(g: Convoy, user_id: int, station: Station) -> tuple[bool, str]:
    if g.phase is not Phase.STATION:
        return False, "الان زمان انتخاب پست نیست."
    p = g.players.get(user_id)
    if p is None:
        return False, "تو سوار این کاروان نیستی."
    p.station = station
    return True, ""


def everyone_stationed(g: Convoy) -> bool:
    return all(p.station is not None for p in g.players.values())


def staffing(g: Convoy) -> dict[Station, int]:
    out: dict[Station, int] = {s: 0 for s in Station}
    for p in g.players.values():
        if p.station is not None:
            out[p.station] += 1
    return out


def close_stations(g: Convoy) -> None:
    """Lock in posts and move to the public speed vote."""
    if g.phase is not Phase.STATION:
        return
    g.phase = Phase.SPEED
    for p in g.players.values():
        p.speed_vote = None
    # scouts see what is coming, and that is what makes the vote meaningful
    g.scouted = staffing(g)[Station.SCOUT] > 0


def set_speed(g: Convoy, user_id: int, speed: Speed) -> tuple[bool, str]:
    if g.phase is not Phase.SPEED:
        return False, "الان زمان رأی سرعت نیست."
    p = g.players.get(user_id)
    if p is None:
        return False, "تو سوار این کاروان نیستی."
    p.speed_vote = speed
    return True, ""


def speed_tally(g: Convoy) -> dict[Speed, int]:
    out: dict[Speed, int] = {s: 0 for s in Speed}
    for p in g.players.values():
        if p.speed_vote is not None:
            out[p.speed_vote] += 1
    return out


def everyone_voted_speed(g: Convoy) -> bool:
    return all(p.speed_vote is not None for p in g.players.values())


def chosen_speed(g: Convoy, rng: random.Random | None = None) -> Speed:
    rng = rng or random.Random()
    tally = speed_tally(g)
    best = max(tally.values())
    if best == 0:
        return Speed.STEADY
    top = [s for s, n in tally.items() if n == best]
    return rng.choice(top)


def _clamp(v: int) -> int:
    return max(0, min(CAP, v))


def pressure(leg: int) -> float:
    """Hazard severity multiplier as the cordon closes behind the convoy."""
    return 1.0 + 0.16 * max(0, leg - 1)


def demand_for(need: int, crew: int) -> int:
    """How many bodies a hazard wants from a crew of this size.

    Demand grows with the crew, otherwise a large group trivially covers
    every station at once and there is no decision left to make.
    """
    # Sub-linear in crew size: a bigger group is genuinely stronger, but
    # never so much that every station can be covered at once.
    return need + round(max(0, crew - 3) * need * 0.34)


def upkeep(staff: int, first: int) -> int:
    """Diminishing return on passive station output.

    1 worker -> `first`, and each extra worker adds progressively less
    (roughly first * sqrt-ish growth), so stacking one station is never a
    substitute for covering the hazard.
    """
    total = 0.0
    for i in range(staff):
        total += first / (1 + i * 0.9)
    return int(total)


def resolve_leg(g: Convoy, rng: random.Random | None = None) -> list[str]:
    """Apply the hazard against the group's staffing, then travel."""
    rng = rng or random.Random()
    if g.phase is not Phase.SPEED:
        return []
    speed = chosen_speed(g, rng)
    icon, label, dist, burn, severity, drift = SPEED_META[speed]
    hz = g.hazard
    have = staffing(g)
    n = max(1, len(g.players))

    out = [f"{hz.icon} <b>{hz.title}</b>", f"<i>{hz.body}</i>", ""]
    out.append(f"{icon} سرعت گروه: <b>{label}</b>")

    # ── how well was the hazard answered ─────────────────────────────────
    misses = 0
    covered: list[str] = []
    for station, need in hz.demand.items():
        scaled = demand_for(need, n)
        got = have[station]
        s_icon, s_label, _ = STATION_META[station]
        if got >= scaled:
            covered.append(f"✅ {s_icon} {s_label} {got}/{scaled}")
            for p in g.players.values():
                if p.station is station:
                    p.contributed += 1
        else:
            covered.append(f"❌ {s_icon} {s_label} {got}/{scaled}")
            misses += scaled - got
    out += covered

    # The quarantine zone tightens: every leg hits harder than the last, so
    # a crew cannot simply idle in CAREFUL and grind the road down safely.
    # The road is not deterministic. A leg rolls between a lull and a bad
    # night, so even a perfectly staffed convoy can be hurt — this is what
    # keeps a competent crew from being a guaranteed win. Scouts narrow the
    # roll, which is the real reward for staffing the lookout.
    swing = 0.30 if have[Station.SCOUT] else 0.55
    luck = rng.uniform(1.0 - swing, 1.0 + swing)
    press = pressure(g.leg) * luck
    # A longer convoy is more metal to keep on the road and more mouths to
    # feed, which is what stops a huge crew from being a free win.
    bulk = max(0, n - 5) * 0.18
    hull_loss = int((hz.hull_per_miss * misses + hz.hull_floor + WEAR + bulk)
                    * severity * press)
    fuel_loss = int(hz.fuel_per_miss * misses * severity * press) + burn
    morale_loss = int(hz.morale_per_miss * misses * severity * press
                      + ATTRITION + bulk)

    # ── stations that always pay off, hazard or not ──────────────────────
    # Diminishing returns: the second mechanic helps much less than the
    # first, and a tenth adds almost nothing. Without this, a large crew
    # simply out-heals the road and the mode stops being a game.
    repair_gain = upkeep(have[Station.REPAIR], 4)
    siphon_gain = upkeep(have[Station.SIPHON], 5)
    ration_gain = upkeep(have[Station.RATION], 4)
    # a lone gunner still thins whatever is chasing you
    guard_relief = min(hull_loss, upkeep(have[Station.DEFEND], 4))

    g.hull = _clamp(g.hull - hull_loss + guard_relief + repair_gain)
    g.fuel = _clamp(g.fuel - fuel_loss + siphon_gain)
    g.morale = _clamp(g.morale - morale_loss + ration_gain + drift)
    g.distance += dist

    if misses == 0:
        out += ["", "🛡️ خطر کامل مهار شد."]
    else:
        out += ["", f"💥 {misses} پست خالی ماند — کاروان تاوان داد."]
    out += [
        "",
        f"🛞 مسافت +{dist} → <b>{min(g.distance, DISTANCE_GOAL)}/{DISTANCE_GOAL}</b>",
        f"🔩 بدنه {g.hull} · ⛽ سوخت {g.fuel} · 🫀 روحیه {g.morale}",
    ]

    g.history.append(
        f"{hz.icon} {hz.title} — {label}"
        + ("، مهار شد" if misses == 0 else f"، {misses} پست خالی"))

    # ── set up the next leg ──────────────────────────────────────────────
    g.leg += 1
    g.hazard = g.next_hazard or rng.choice(HAZARDS)
    g.next_hazard = rng.choice(HAZARDS)
    g.phase = Phase.STATION
    for p in g.players.values():
        p.station = None
        p.speed_vote = None
    g.log = out
    return out


def check_end(g: Convoy) -> str | None:
    """Return the outcome once the run is decided, else None."""
    if g.winner:
        return g.winner
    if g.distance >= DISTANCE_GOAL:
        g.winner, g.cause = "escaped", "کاروان به حصار رسید."
        g.phase = Phase.ENDED
        return g.winner
    if g.hull <= 0:
        g.winner, g.cause = "lost", "بدنه از هم پاشید. کاروان روی جاده ماند."
    elif g.fuel <= 0:
        g.winner, g.cause = "lost", "سوخت تمام شد. موتورها خاموش شدند."
    elif g.morale <= 0:
        g.winner, g.cause = "lost", "روحیه شکست. خدمه کاروان را رها کردند."
    elif g.leg > MAX_LEGS:
        g.winner, g.cause = "lost", "منطقه قرنطینه بسته شد. دیر رسیدید."
    if g.winner:
        g.phase = Phase.ENDED
        return g.winner
    return None


def payouts(g: Convoy) -> dict[int, int]:
    """Split the pot among the crew — everyone survives or nobody does.

    Shares are weighted by how many legs a player's post actually answered
    the hazard, so showing up matters, but every survivor is paid.
    """
    if g.winner != "escaped" or not g.players or not g.pot:
        return {}
    weights = {p.user_id: 1 + p.contributed for p in g.players.values()}
    total = sum(weights.values())
    pay = {uid: g.pot * w // total for uid, w in weights.items()}
    # hand any rounding remainder to the biggest contributor
    spent = sum(pay.values())
    if spent < g.pot:
        top = max(weights, key=lambda u: weights[u])
        pay[top] += g.pot - spent
    return pay


def summary(g: Convoy) -> list[str]:
    lines = [
        f"🛞 مسافت طی‌شده: <b>{min(g.distance, DISTANCE_GOAL)}/{DISTANCE_GOAL}</b>"
        f" در {g.leg - 1} مرحله",
        f"🔩 بدنه {g.hull} · ⛽ سوخت {g.fuel} · 🫀 روحیه {g.morale}",
        "",
        "<b>خدمه</b>",
    ]
    for p in sorted(g.crew(), key=lambda x: -x.contributed):
        lines.append(f"• {p.name} — {p.contributed} مرحله مؤثر")
    if g.history:
        lines += ["", "<b>جاده</b>"] + [f"{i}. {h}" for i, h in
                                        enumerate(g.history, 1)]
    return lines
