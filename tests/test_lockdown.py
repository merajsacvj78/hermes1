"""LOCKDOWN engine: role assignment, night/day resolution, win conditions."""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vcorp.game import lockdown as L  # noqa: E402


def game(n: int, seed: int = 1) -> L.Lockdown:
    g = L.Lockdown(chat_id=-1, host_id=1)
    for i in range(1, n + 1):
        g.add(i, f"P{i}")
    L.start(g, random.Random(seed))
    return g


def carrier_ids(g):
    return [p.user_id for p in g.carriers()]


def first_human(g):
    return next(p.user_id for p in g.alive_players() if p.role is not L.Role.CARRIER)


def main() -> None:
    # ── lobby rules ───────────────────────────────────────────────────────
    g = L.Lockdown(chat_id=-1, host_id=1)
    assert g.add(1, "A") and not g.add(1, "A"), "no duplicate joins"
    assert g.remove(1) and not g.remove(1)
    for i in range(1, L.MAX_PLAYERS + 1):
        g.add(i, f"P{i}")
    assert not g.add(999, "X"), "lobby cap must hold"
    L.start(g, random.Random(0))
    assert not g.add(500, "late"), "cannot join after start"

    # ── role distribution scales and is never degenerate ──────────────────
    for n in range(L.MIN_PLAYERS, L.MAX_PLAYERS + 1):
        gg = game(n)
        c = len(gg.carriers())
        assert c == L.carrier_count(n) >= 1
        assert c < len(gg.humans()), f"carriers must start outnumbered at n={n}"
        assert len(gg.players) == n
        roles = [p.role for p in gg.players.values()]
        assert roles.count(L.Role.SCREENER) <= 1
        assert roles.count(L.Role.ENFORCER) <= 1
        if n >= 6:
            assert gg.role_holder(L.Role.SCREENER) is not None
            assert gg.role_holder(L.Role.ENFORCER) is not None

    # ── night 1 is incubation: nobody is lost ─────────────────────────────
    g = game(8, seed=3)
    c = carrier_ids(g)[0]
    victim = first_human(g)
    assert L.set_convert(g, c, victim)[0]
    out = L.resolve_night(g, random.Random(0))
    assert g.players[victim].alive, "night 1 must not convert anyone"
    assert any("نهفتگی" in x for x in out)
    assert g.phase is L.Phase.DAY

    # ── night 2+: conversion works ────────────────────────────────────────
    g = game(8, seed=3)
    L.resolve_night(g, random.Random(0))          # incubation night
    L.resolve_day(g)                              # nobody voted -> night 2
    assert g.round == 2 and g.phase is L.Phase.NIGHT
    c = carrier_ids(g)[0]
    victim = first_human(g)
    ok, err = L.set_convert(g, c, victim)
    assert ok, err
    L.resolve_night(g, random.Random(0))
    assert not g.players[victim].alive, "unshielded target must be converted"
    assert g.phase is L.Phase.DAY

    g = game(8, seed=3)
    L.resolve_night(g, random.Random(0))
    L.resolve_day(g)
    c = carrier_ids(g)[0]
    enf = g.role_holder(L.Role.ENFORCER)
    victim = first_human(g)
    L.set_convert(g, c, victim)
    assert L.set_shield(g, enf.user_id, victim)[0]
    out = L.resolve_night(g, random.Random(0))
    assert g.players[victim].alive, "the shield must stop the conversion"
    assert any("مهار موفق" in x for x in out)

    # the enforcer cannot shield the same person twice in a row
    g.phase = L.Phase.NIGHT
    assert not L.set_shield(g, enf.user_id, victim)[0]
    other = next(p.user_id for p in g.alive_players() if p.user_id != victim)
    assert L.set_shield(g, enf.user_id, other)[0]

    # ── a carrier can never convert another carrier ───────────────────────
    g = game(12, seed=5)
    cs = carrier_ids(g)
    assert len(cs) >= 2
    ok, err = L.set_convert(g, cs[0], cs[1])
    assert not ok and err

    # non-carriers cannot use the carrier action at all
    human = first_human(g)
    assert not L.set_convert(g, human, cs[0])[0]

    # ── screening reports the truth, and only to the screener ─────────────
    g = game(8, seed=7)
    scr = g.role_holder(L.Role.SCREENER)
    c = carrier_ids(g)[0]
    assert L.set_screen(g, scr.user_id, c)[0]
    sid, name, is_carrier = L.screening_result(g)
    assert sid == scr.user_id and is_carrier is True
    clean = first_human(g)
    L.set_screen(g, scr.user_id, clean)
    _, _, is_carrier2 = L.screening_result(g)
    assert is_carrier2 is False
    assert not L.set_screen(g, scr.user_id, scr.user_id)[0], "no self-test"

    # ── day voting ────────────────────────────────────────────────────────
    g = game(6, seed=11)
    L.resolve_night(g, random.Random(1))   # incubation
    alive = [p.user_id for p in g.alive_players()]
    target = alive[0]
    for v in alive:
        L.set_vote(g, v, target)
    assert L.everyone_voted(g)
    out = L.resolve_day(g)
    assert not g.players[target].alive
    assert any("پاکسازی" in x for x in out)
    assert g.phase is L.Phase.NIGHT and g.round == 2

    # a tie kills nobody
    g = game(6, seed=13)
    L.resolve_night(g, random.Random(2))
    alive = [p.user_id for p in g.alive_players()]
    L.set_vote(g, alive[0], alive[1])
    L.set_vote(g, alive[1], alive[0])
    before = len(g.alive_players())
    out = L.resolve_day(g)
    assert len(g.alive_players()) == before
    assert any("گره" in x for x in out)

    # dead players and outsiders cannot vote
    g.phase = L.Phase.DAY
    corpse = g.players[alive[0]]
    corpse.alive = False
    corpse.out_reason = "تست"
    assert not L.set_vote(g, corpse.user_id, alive[1])[0]
    assert not L.set_vote(g, 99999, alive[1])[0]
    corpse.alive = True
    corpse.out_reason = ""

    # ── win conditions ────────────────────────────────────────────────────
    g = game(6, seed=17)
    for p in g.carriers():
        p.alive = False
    assert L.check_win(g) == "facility"
    assert g.phase is L.Phase.ENDED

    g = game(6, seed=19)
    humans = [p for p in g.alive_players() if p.role is not L.Role.CARRIER]
    for p in humans[:-1]:
        p.alive = False
    # one carrier vs one human = parity = carriers win
    assert len(g.carriers()) >= len(g.humans())
    assert L.check_win(g) == "carriers"

    # a fresh game is not already over
    assert L.check_win(game(8, seed=23)) is None

    # ── payouts go only to the winning side and never exceed the pot ──────
    g = game(8, seed=29)
    g.pot = 8000
    for p in g.carriers():
        p.alive = False
    L.check_win(g)
    pay = L.payouts(g)
    assert set(pay) == {p.user_id for p in g.players.values()
                        if p.role is not L.Role.CARRIER}
    assert sum(pay.values()) <= g.pot, "payout must not mint money"

    g = game(8, seed=31)
    g.pot = 8000
    for p in list(g.humans()):
        p.alive = False
    L.check_win(g)
    pay = L.payouts(g)
    assert set(pay) == {p.user_id for p in g.carriers(alive_only=False)}
    assert sum(pay.values()) <= g.pot
    # dead carriers still get paid: they earned it
    assert all(v > 0 for v in pay.values())

    # ── full random playthroughs always terminate with a winner ───────────
    for seed in range(120):
        rng = random.Random(seed)
        n = rng.randint(L.MIN_PLAYERS, 14)
        g = game(n, seed=seed)
        guard = 0
        while L.check_win(g) is None and guard < 200:
            guard += 1
            if g.phase is L.Phase.NIGHT:
                cs = g.carriers()
                targets = [p.user_id for p in g.alive_players()
                           if p.role is not L.Role.CARRIER]
                if cs and targets:
                    L.set_convert(g, cs[0].user_id, rng.choice(targets))
                enf = g.role_holder(L.Role.ENFORCER)
                if enf:
                    pick = rng.choice([p.user_id for p in g.alive_players()])
                    L.set_shield(g, enf.user_id, pick)
                scr = g.role_holder(L.Role.SCREENER)
                if scr:
                    opts = [p.user_id for p in g.alive_players()
                            if p.user_id != scr.user_id]
                    if opts:
                        L.set_screen(g, scr.user_id, rng.choice(opts))
                L.resolve_night(g, rng)
            elif g.phase is L.Phase.DAY:
                alive = [p.user_id for p in g.alive_players()]
                for v in alive:
                    L.set_vote(g, v, rng.choice(alive + [0]))
                L.resolve_day(g)
            # invariants that must hold at every single step
            assert all(p.alive or p.out_reason for p in g.players.values())
            assert len(g.alive_players()) <= n
        assert g.winner in ("carriers", "facility"), f"seed {seed} never ended"
        assert guard < 200, f"seed {seed} looped forever"

    # ── both sides are actually winnable with random play ─────────────────
    wins = {"carriers": 0, "facility": 0}
    for seed in range(400, 700):
        rng = random.Random(seed)
        g = game(rng.randint(5, 12), seed=seed)
        guard = 0
        while L.check_win(g) is None and guard < 200:
            guard += 1
            if g.phase is L.Phase.NIGHT:
                cs = g.carriers()
                targets = [p.user_id for p in g.alive_players()
                           if p.role is not L.Role.CARRIER]
                if cs and targets:
                    L.set_convert(g, cs[0].user_id, rng.choice(targets))
                L.resolve_night(g, rng)
            else:
                alive = [p.user_id for p in g.alive_players()]
                for v in alive:
                    L.set_vote(g, v, rng.choice(alive + [0]))
                L.resolve_day(g)
        wins[g.winner] += 1
    assert wins["carriers"] > 20 and wins["facility"] > 20, \
        f"one side is unwinnable: {wins}"

    # ── skill must matter: informed play has to beat clueless play ────────
    # Uninformed voting loses badly; a group that uses screening results and
    # coordinates its vote should flip the round. If this ever inverts, the
    # social-deduction layer has stopped mattering.
    def informed_round(seed: int) -> str:
        rng = random.Random(seed)
        g = game(rng.randint(6, 12), seed=seed)
        known_carriers: set[int] = set()
        known_clean: set[int] = set()
        guard = 0
        while L.check_win(g) is None and guard < 200:
            guard += 1
            if g.phase is L.Phase.NIGHT:
                cs = g.carriers()
                targets = [p.user_id for p in g.alive_players()
                           if p.role is not L.Role.CARRIER]
                if cs and targets:
                    L.set_convert(g, cs[0].user_id, rng.choice(targets))
                scr = g.role_holder(L.Role.SCREENER)
                if scr:
                    opts = [p.user_id for p in g.alive_players()
                            if p.user_id != scr.user_id
                            and p.user_id not in known_carriers | known_clean]
                    if opts:
                        L.set_screen(g, scr.user_id, rng.choice(opts))
                res = L.screening_result(g)
                L.resolve_night(g, rng)
                if res:
                    _, nm, is_c = res
                    tid = next(p.user_id for p in g.players.values()
                               if p.name == nm)
                    (known_carriers if is_c else known_clean).add(tid)
            else:
                alive = [p.user_id for p in g.alive_players()]
                exposed = [u for u in alive if u in known_carriers]
                for v in alive:
                    if exposed:
                        L.set_vote(g, v, exposed[0])
                    else:
                        pool = [u for u in alive
                                if u not in known_clean and u != v] or alive
                        L.set_vote(g, v, rng.choice(pool))
                L.resolve_day(g)
        return g.winner

    smart = {"carriers": 0, "facility": 0}
    for seed in range(1000, 1600):
        smart[informed_round(seed)] += 1
    smart_rate = smart["facility"] / sum(smart.values())
    blind_rate = wins["facility"] / sum(wins.values())
    assert smart_rate > blind_rate + 0.20, (
        f"information does not pay off: informed {smart_rate:.2f} "
        f"vs blind {blind_rate:.2f}")
    assert 0.35 < smart_rate < 0.80, f"informed play is unbalanced: {smart_rate:.2f}"

    print(f"✅ LOCKDOWN engine passed — blind play facility "
          f"{blind_rate*100:.0f}%, informed play facility {smart_rate*100:.0f}%",
          flush=True)


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
