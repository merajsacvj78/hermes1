"""Balance harness for THE CONVOY.

Compares three crews:
  random   — everyone picks a post at random, votes speed at random
  greedy   — everyone piles onto whatever the current hazard demands
  smart    — staffs the hazard, keeps fuel/morale topped up, and picks a
             speed that matches how healthy the convoy is

A good co-op mode should punish random play, reward coordination, and still
leave smart crews short of a guaranteed win.
"""
from __future__ import annotations

import random
import sys
from collections import Counter

sys.path.insert(0, "/home/user/hermes1")

from vcorp.game import convoy as C  # noqa: E402


def build(n: int, seed: int) -> C.Convoy:
    g = C.Convoy(chat_id=-1, host_id=1)
    for i in range(1, n + 1):
        g.add(i, f"P{i}")
    C.start(g, random.Random(seed))
    return g


def play(n: int, seed: int, mode: str) -> tuple[str, int]:
    rng = random.Random(seed)
    g = build(n, seed)
    guard = 0
    while C.check_end(g) is None and guard < 200:
        guard += 1
        hz = g.hazard
        need: list[C.Station] = []
        for st, cnt in hz.demand.items():
            scaled = C.demand_for(cnt, n)
            need += [st] * scaled

        for i, p in enumerate(g.players.values()):
            if mode == "random":
                st = rng.choice(list(C.Station))
            elif mode == "greedy":
                st = need[i % len(need)] if need else C.Station.REPAIR
            else:
                if i < len(need):
                    st = need[i]
                else:
                    # spare hands go where the convoy is weakest
                    low = min([(g.fuel, C.Station.SIPHON),
                               (g.hull, C.Station.REPAIR),
                               (g.morale, C.Station.RATION)])
                    st = low[1]
            C.set_station(g, p.user_id, st)
        C.close_stations(g)

        for p in g.players.values():
            if mode == "random":
                sp = rng.choice(list(C.Speed))
            else:
                worst = min(g.hull, g.fuel, g.morale)
                if worst < 30:
                    sp = C.Speed.CAREFUL
                elif g.fuel > 55 and g.hull > 60:
                    sp = C.Speed.RECKLESS
                else:
                    sp = C.Speed.STEADY
            C.set_speed(g, p.user_id, sp)
        C.resolve_leg(g, rng)
    C.check_end(g)
    return g.winner or "lost", g.leg - 1


def run(mode: str, games: int = 1500) -> float:
    wins = Counter()
    legs = 0
    for s in range(games):
        w, l = play(random.Random(s).randint(2, 14), s, mode)
        wins[w] += 1
        legs += l
    rate = wins["escaped"] / games
    print(f"{mode:8s} escape {rate*100:5.1f}%   avg legs {legs/games:4.1f}")
    return rate


if __name__ == "__main__":
    print("=== overall ===")
    r = run("random")
    gr = run("greedy")
    sm = run("smart")

    print("\n=== smart crew, by size ===")
    for n in range(3, 16):
        wins = Counter()
        for s in range(400):
            w, _ = play(n, s * 31 + n, "smart")
            wins[w] += 1
        print(f"{n:3d} players: escape {wins['escaped']/400*100:5.1f}%")

    print("\n=== causes of failure (smart, 800 runs) ===")
    causes = Counter()
    for s in range(800):
        rng = random.Random(s)
        n = rng.randint(3, 14)
        g = build(n, s)
        guard = 0
        while C.check_end(g) is None and guard < 200:
            guard += 1
            hz = g.hazard
            need = []
            for st, cnt in hz.demand.items():
                scaled = C.demand_for(cnt, n)
                need += [st] * scaled
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
            for p in g.players.values():
                C.set_speed(g, p.user_id, sp)
            C.resolve_leg(g, rng)
        C.check_end(g)
        causes[g.cause] += 1
    for c, k in causes.most_common():
        print(f"  {k:4d}  {c}")
