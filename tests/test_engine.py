"""Offline smoke test of the V-CORP game engine (no Telegram needed)."""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vcorp.db import db  # noqa: E402
from vcorp.game import engine as E  # noqa: E402
from vcorp.game.content import ITEMS  # noqa: E402


async def main() -> None:
    db.path = ":memory:"
    await db.connect()
    await E.seed()

    a = await E.ensure_player(1, "Kade")
    b = await E.ensure_player(2, "Vera")
    assert (await E.effective(a))["attack"] == 10

    # infection ladder
    for step, expect in ((20, "infected"), (25, "mutant"), (25, "advanced"), (25, "bioweapon")):
        inf, stage, _ = await E.apply_infection(1, step)
        assert stage == expect, (inf, stage, expect)

    # mutation tree gating
    opts = await E.auto_mutations(1)
    assert "claw" in opts and "ripper" not in opts
    assert await E.unlock_mutation(1, "claw")
    assert "ripper" in await E.auto_mutations(1)
    assert (await E.mutation_bonus(1))["attack"] == 6

    # powers
    a = await E.get_player(1)
    pw = await E.random_power_for(1)
    assert await E.grant_power(1, pw["code"])
    assert len(await E.player_powers(1)) == 1

    # combat + legacy death
    for _ in range(60):
        res = await E.resolve_attack(await E.get_player(1), await E.get_player(2))
        if res["hit"]:
            _, died = await E.damage_player(2, res["damage"])
            if died:
                break
    vb = await E.get_player(2)
    assert vb["generation"] >= 1

    gen_before = (await E.get_player(2))["generation"]
    await E.kill_player(2, 1)
    v2 = await E.get_player(2)
    assert v2["generation"] == gen_before + 1
    assert v2["legacy"] > 0 and v2["infection"] == 0
    assert (await E.get_player(1))["kills"] >= 1

    # economy
    base = ITEMS["medkit"]["price"]
    for _ in range(10):
        await E.register_trade("medkit", +1)
    assert await E.price_of("medkit") > base

    # items / reputation / xp
    await E.give_item(1, "vserum", 2)
    assert await E.take_item(1, "vserum")
    assert await E.item_qty(1, "vserum") == 1
    await E.rep_add(1, "ubc", 12)
    assert (await E.rep_all(1))["ubc"] == 12
    await E.grant_xp(1, 5000)
    assert (await E.get_player(1))["level"] > 1

    # cooldowns
    await E.set_cooldown(1, "scavenge", 60)
    assert 0 < await E.cooldown_left(1, "scavenge") <= 60

    await db.close()
    print("✅ all engine checks passed", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        os._exit(0 if not sys.exc_info()[0] else 1)
