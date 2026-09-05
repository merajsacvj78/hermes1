"""Every boss must be a distinct, beatable fight."""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vcorp.game import bestiary as B  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fight(kind: B.BossKind, party: int, power: int, seed: int) -> tuple[bool, int, int]:
    """Simulate a group grinding a boss. Returns (killed, rounds, party damage)."""
    rng = random.Random(seed)
    hp, atk, _ = B.scale(kind, party)
    max_hp = hp
    state = dict(kind.init)
    taken = 0
    rounds = 0
    while hp > 0 and rounds < 400:
        rounds += 1
        for _ in range(party):
            if hp <= 0:
                break
            pins = rng.randint(1, 6)
            raw = int((power * 2 + rng.randint(0, 40)) * (0.5 + pins * 0.18))
            blow = B.strike(kind, state, raw, pins, hp, max_hp, rng)
            hp = max(0, hp - blow.damage)
            if hp > 0:
                hp = B.post_hit(kind, state, hp, max_hp)
            taken += max(5, atk - 10 + rng.randint(0, 15)) + blow.recoil
    return hp <= 0, rounds, taken


def main() -> None:
    # ── the bestiary is well formed ──────────────────────────────────────
    assert len(B.BESTIARY) >= 5, "a bestiary needs variety"
    keys = [k.key for k in B.BESTIARY]
    assert len(keys) == len(set(keys)), "boss keys must be unique"
    names = [k.name for k in B.BESTIARY]
    assert len(names) == len(set(names)), "boss names must be unique"

    for k in B.BESTIARY:
        assert k.icon and k.name and k.tagline and k.mechanic_hint
        # every boss must ship its own portrait, or the group sees nothing
        path = os.path.join(ROOT, k.art)
        assert os.path.exists(path), f"missing art for {k.key}: {k.art}"
        assert os.path.getsize(path) > 10_000, f"art too small for {k.key}"
        assert k.art != B.BESTIARY[0].art or k is B.BESTIARY[0], \
            "each boss needs its own portrait"
    arts = [k.art for k in B.BESTIARY]
    assert len(arts) == len(set(arts)), "portraits must not be shared"

    # ── mechanics are genuinely different ────────────────────────────────
    mechs = [k.mechanic for k in B.BESTIARY]
    assert len(set(mechs)) == len(mechs), "every boss needs its own mechanic"

    # ── scaling responds to group size ───────────────────────────────────
    for k in B.BESTIARY:
        small = B.scale(k, 2)
        large = B.scale(k, 20)
        assert large[0] > small[0] and large[2] > small[2], \
            f"{k.key} must scale with the group"

    # ── AVAR: weak hits glance, heavy hits bite ──────────────────────────
    avar = B.BY_KEY["avar"]
    st = dict(avar.init)
    weak = B.strike(avar, st, 20, 3, 1000, 1000)
    assert weak.damage < 20, "armour must blunt a weak hit"
    assert "زره" in weak.note
    st = dict(avar.init)
    heavy = B.strike(avar, st, 120, 5, 1000, 1000)
    assert heavy.damage >= 120, "a heavy hit must break through"
    assert st["cracks"] == 1
    # cracks compound
    second = B.strike(avar, st, 120, 5, 1000, 1000)
    assert second.damage > heavy.damage, "cracks must compound"

    # ── HIVE: recoil grows with every hit ────────────────────────────────
    hive = B.BY_KEY["hive"]
    st = dict(hive.init)
    first = B.strike(hive, st, 60, 4, 500, 500)
    for _ in range(6):
        last = B.strike(hive, st, 60, 4, 500, 500)
    assert last.recoil > first.recoil, "the swarm must escalate"
    assert last.recoil <= 30, "swarm recoil must stay bounded"

    # ── AMALGAM: heals between blows, but not past full or when dead ─────
    amal = B.BY_KEY["amalgam"]
    st = dict(amal.init)
    assert B.post_hit(amal, st, 500, 1000) > 500, "it must regenerate"
    assert B.post_hit(amal, st, 0, 1000) == 0, "a corpse must not heal"
    assert B.post_hit(amal, st, 1000, 1000) == 1000, "no overheal"
    assert B.post_hit(B.BY_KEY["avar"], {}, 500, 1000) == 500, \
        "only the amalgam regenerates"

    # ── SECTOR 9: angrier as it dies ─────────────────────────────────────
    s9 = B.BY_KEY["sector9"]
    fresh = B.strike(s9, {}, 60, 4, 1000, 1000)
    dying = B.strike(s9, {}, 60, 4, 50, 1000)
    assert dying.recoil > fresh.recoil, "the horde must frenzy"
    assert dying.damage >= fresh.damage

    # ── TITAN: every third hit is blocked, a 6 pierces ───────────────────
    titan = B.BY_KEY["titan"]
    st = dict(titan.init)
    r = [B.strike(titan, st, 100, 4, 1000, 1000) for _ in range(3)]
    assert r[2].damage < r[0].damage, "the shield must cycle"
    assert "سپر" in r[2].note
    st = dict(titan.init)
    pierce = B.strike(titan, st, 100, 6, 1000, 1000)
    assert pierce.damage > 100, "a perfect roll must pierce"

    # ── nothing ever produces a nonsense number ──────────────────────────
    rng = random.Random(0)
    for k in B.BESTIARY:
        st = dict(k.init)
        for _ in range(400):
            blow = B.strike(k, st, rng.randint(1, 300), rng.randint(1, 6),
                            rng.randint(1, 2000), 2000, rng)
            assert blow.damage >= 1, f"{k.key} produced {blow.damage}"
            assert blow.recoil >= 0, f"{k.key} negative recoil"
            assert blow.damage < 100_000

    # ── every boss is killable, and none is trivial ──────────────────────
    for k in B.BESTIARY:
        killed, rounds, _ = fight(k, party=6, power=60, seed=5)
        assert killed, f"{k.key} is unkillable by a competent group"
        assert rounds > 1, f"{k.key} dies too fast to be a world boss"

    # a lone weak player should not solo a world boss quickly
    for k in B.BESTIARY:
        killed, rounds, _ = fight(k, party=1, power=12, seed=9)
        assert not killed or rounds > 15, f"{k.key} solos too easily"

    # ── the fights differ measurably from one another ────────────────────
    profile = {}
    for k in B.BESTIARY:
        _, rounds, taken = fight(k, party=6, power=60, seed=11)
        profile[k.key] = (rounds, taken)
    assert len(set(profile.values())) == len(profile), \
        f"bosses feel identical: {profile}"

    print("✅ bestiary passed — "
          + ", ".join(f"{k}:{v[0]}r" for k, v in profile.items()), flush=True)


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
