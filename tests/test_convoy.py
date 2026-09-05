"""THE CONVOY engine: rules, termination, payouts and balance guard rails."""
from __future__ import annotations

import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vcorp.game import convoy as C  # noqa: E402


def game(n: int, seed: int = 0, stake: int = 0) -> C.Convoy:
    g = C.Convoy(chat_id=-1, host_id=1, stake=stake, pot=stake * n)
    for i in range(1, n + 1):
        g.add(i, f"P{i}")
    C.start(g, random.Random(seed))
    return g


def staff(g: C.Convoy, plan: list[C.Station]) -> None:
    for p, st in zip(g.players.values(), plan):
        C.set_station(g, p.user_id, st)


def vote_all(g: C.Convoy, speed: C.Speed) -> None:
    for p in g.players.values():
        C.set_speed(g, p.user_id, speed)


def main() -> None:
    # ── lobby rules ──────────────────────────────────────────────────────
    g = C.Convoy(chat_id=-1, host_id=1)
    assert g.add(1, "host")
    assert not g.add(1, "host"), "no double join"
    assert g.add(2, "b")
    assert not g.remove(1), "host may not abandon the convoy"
    assert g.remove(2)
    for i in range(100, 100 + C.MAX_PLAYERS + 5):
        g.add(i, f"x{i}")
    assert len(g.players) == C.MAX_PLAYERS, "capacity must hold"

    # ── starting condition scales to crew size ───────────────────────────
    small, big = game(3, 1), game(15, 1)
    assert small.hull > big.hull and small.fuel > big.fuel, \
        "a short crew must ride a tougher truck"
    assert big.hull == C.START_HULL and big.fuel == C.START_FUEL

    # ── phase gating ─────────────────────────────────────────────────────
    g = game(5, 2)
    assert g.phase is C.Phase.STATION
    assert not C.set_speed(g, 1, C.Speed.STEADY)[0], "speed is locked in STATION"
    assert not C.set_station(g, 999, C.Station.REPAIR)[0], "outsiders cannot act"
    assert C.set_station(g, 1, C.Station.REPAIR)[0]
    assert not C.everyone_stationed(g)
    staff(g, [C.Station.REPAIR] * 5)
    assert C.everyone_stationed(g)
    C.close_stations(g)
    assert g.phase is C.Phase.SPEED
    assert not C.set_station(g, 1, C.Station.SCOUT)[0], "posts are locked"

    # ── scouting is what reveals the road ────────────────────────────────
    g = game(5, 3)
    staff(g, [C.Station.REPAIR] * 5)
    C.close_stations(g)
    assert not g.scouted, "no lookout, no warning"
    g = game(5, 3)
    staff(g, [C.Station.SCOUT] + [C.Station.REPAIR] * 4)
    C.close_stations(g)
    assert g.scouted and g.next_hazard is not None

    # ── speed vote: majority wins, ties are broken, silence is STEADY ────
    g = game(5, 4)
    staff(g, [C.Station.REPAIR] * 5)
    C.close_stations(g)
    assert C.chosen_speed(g) is C.Speed.STEADY, "an unvoted convoy rolls steady"
    for uid, sp in zip([1, 2, 3, 4, 5], [C.Speed.RECKLESS, C.Speed.RECKLESS,
                                         C.Speed.RECKLESS, C.Speed.CAREFUL,
                                         C.Speed.CAREFUL]):
        C.set_speed(g, uid, sp)
    assert C.everyone_voted_speed(g)
    assert C.chosen_speed(g) is C.Speed.RECKLESS
    assert C.speed_tally(g)[C.Speed.RECKLESS] == 3

    # ── covering the hazard is strictly better than ignoring it ──────────
    def run_leg(plan_all: C.Station, seed: int) -> tuple[int, int, int]:
        g = C.Convoy(chat_id=-1, host_id=1)
        for i in range(1, 7):
            g.add(i, f"P{i}")
        C.start(g, random.Random(seed))
        g.hazard = C.HAZARD_BY_KEY["swarm"]      # wants DEFEND
        need = C.demand_for(2, 6)
        plan = ([C.Station.DEFEND] * need if plan_all is C.Station.DEFEND
                else [C.Station.RATION] * 6)
        plan += [C.Station.RATION] * (6 - len(plan))
        staff(g, plan)
        C.close_stations(g)
        vote_all(g, C.Speed.STEADY)
        C.resolve_leg(g, random.Random(seed))
        return g.hull, g.fuel, g.morale

    covered = [run_leg(C.Station.DEFEND, s)[0] for s in range(40)]
    ignored = [run_leg(C.Station.RATION, s)[0] for s in range(40)]
    assert sum(covered) / 40 > sum(ignored) / 40 + 8, \
        "staffing the hazard must clearly beat ignoring it"

    # ── reckless travels further but costs more ──────────────────────────
    def run_speed(sp: C.Speed, seed: int) -> tuple[int, int]:
        g = game(6, seed)
        staff(g, [C.Station.REPAIR] * 6)
        C.close_stations(g)
        vote_all(g, sp)
        C.resolve_leg(g, random.Random(seed))
        return g.distance, g.fuel

    slow = [run_speed(C.Speed.CAREFUL, s) for s in range(30)]
    fast = [run_speed(C.Speed.RECKLESS, s) for s in range(30)]
    assert sum(d for d, _ in fast) > sum(d for d, _ in slow), "reckless is faster"
    assert sum(f for _, f in fast) < sum(f for _, f in slow), "reckless burns more"

    # ── pressure escalates ───────────────────────────────────────────────
    assert C.pressure(1) < C.pressure(5) < C.pressure(10), \
        "the cordon must tighten"

    # ── upkeep has diminishing returns ───────────────────────────────────
    one, two, ten = C.upkeep(1, 5), C.upkeep(2, 5), C.upkeep(10, 5)
    assert one == 5 and two < one * 2 and ten < one * 4, \
        f"stacking one station must not scale linearly: {one},{two},{ten}"

    # ── stats never leave their bounds ───────────────────────────────────
    for seed in range(150):
        rng = random.Random(seed)
        g = game(rng.randint(3, C.MAX_PLAYERS), seed)
        guard = 0
        while C.check_end(g) is None and guard < 100:
            guard += 1
            for p in g.players.values():
                C.set_station(g, p.user_id, rng.choice(list(C.Station)))
            C.close_stations(g)
            for p in g.players.values():
                C.set_speed(g, p.user_id, rng.choice(list(C.Speed)))
            C.resolve_leg(g, rng)
            for v in (g.hull, g.fuel, g.morale):
                assert 0 <= v <= C.CAP, f"stat out of bounds: {v}"
        assert guard < 100, "every run must terminate"
        assert g.phase is C.Phase.ENDED and g.winner and g.cause

    # ── payouts: only on escape, never exceed the pot ────────────────────
    g = game(6, 7, stake=1000)
    g.winner = "lost"
    assert C.payouts(g) == {}, "a lost convoy pays nobody"
    g.winner = "escaped"
    pay = C.payouts(g)
    assert set(pay) == set(g.players), "every survivor is paid"
    assert sum(pay.values()) == g.pot, f"pot must be exact: {sum(pay.values())}"

    # contribution weighting: a worker outearns a passenger
    g = game(4, 8, stake=500)
    g.winner = "escaped"
    ids = list(g.players)
    g.players[ids[0]].contributed = 10
    pay = C.payouts(g)
    assert pay[ids[0]] > pay[ids[1]], "effort must pay more"
    assert sum(pay.values()) == g.pot

    # a free run pays nothing at all
    g = game(4, 9)
    g.winner = "escaped"
    assert C.payouts(g) == {}

    # ── both outcomes are reachable, and skill decides which ─────────────
    def informed(seed: int) -> str:
        rng = random.Random(seed)
        n = rng.randint(3, 14)
        g = game(n, seed)
        guard = 0
        while C.check_end(g) is None and guard < 100:
            guard += 1
            need: list[C.Station] = []
            for st, cnt in g.hazard.demand.items():
                need += [st] * C.demand_for(cnt, n)
            for i, p in enumerate(g.players.values()):
                if i < len(need):
                    st = need[i]
                else:
                    st = min([(g.fuel, C.Station.SIPHON),
                              (g.hull, C.Station.REPAIR),
                              (g.morale, C.Station.RATION)])[1]
                C.set_station(g, p.user_id, st)
            C.close_stations(g)
            worst = min(g.hull, g.fuel, g.morale)
            sp = (C.Speed.CAREFUL if worst < 30 else
                  C.Speed.RECKLESS if g.fuel > 55 and g.hull > 60 else
                  C.Speed.STEADY)
            vote_all(g, sp)
            C.resolve_leg(g, rng)
        C.check_end(g)
        return g.winner

    def clueless(seed: int) -> str:
        rng = random.Random(seed)
        g = game(rng.randint(3, 14), seed)
        guard = 0
        while C.check_end(g) is None and guard < 100:
            guard += 1
            for p in g.players.values():
                C.set_station(g, p.user_id, rng.choice(list(C.Station)))
            C.close_stations(g)
            for p in g.players.values():
                C.set_speed(g, p.user_id, rng.choice(list(C.Speed)))
            C.resolve_leg(g, rng)
        C.check_end(g)
        return g.winner

    smart = Counter(informed(s) for s in range(500))
    blind = Counter(clueless(s) for s in range(500))
    s_rate = smart["escaped"] / 500
    b_rate = blind["escaped"] / 500
    assert smart["escaped"] > 30 and smart["lost"] > 30, \
        f"both outcomes must be live: {smart}"
    assert s_rate > b_rate + 0.25, \
        f"coordination must pay off: smart {s_rate:.2f} vs blind {b_rate:.2f}"
    assert 0.25 < s_rate < 0.75, f"a good crew must not be a sure thing: {s_rate:.2f}"

    print(f"✅ CONVOY engine passed — blind crew {b_rate*100:.0f}%, "
          f"coordinated crew {s_rate*100:.0f}% escape", flush=True)


if __name__ == "__main__":
    import traceback
    code = 0
    try:
        main()
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    os._exit(code)
