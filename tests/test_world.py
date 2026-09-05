"""World-tick simulation: the background loop must stay stable unattended."""
from __future__ import annotations

import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vcorp import scheduler  # noqa: E402
from vcorp.db import db  # noqa: E402
from vcorp.game import engine as E  # noqa: E402


class FakeBot:
    def __init__(self):
        self.sent = 0

    async def send_message(self, chat_id, text, **kw):
        self.sent += 1
        return types.SimpleNamespace(message_id=self.sent)

    async def send_dice(self, chat_id, emoji=None):
        return types.SimpleNamespace(dice=types.SimpleNamespace(value=4))


async def main() -> None:
    db.path = ":memory:"
    await db.connect()
    await E.seed()
    bot = FakeBot()

    await db.execute("INSERT INTO chats(chat_id,title,active,added_at) VALUES(-100,'T',1,0)")
    for i in range(1, 6):
        await E.ensure_player(i, f"P{i}")
    await E.update(1, energy=10, hp=40, heat=9, infection=30, stage="mutant")
    await E.update(2, infection=0)

    # 200 ticks ≈ 16 hours of wall-clock play at the default 300s interval
    for _ in range(200):
        await scheduler.tick_once(bot)

    p1 = await E.get_player(1)
    assert p1["energy"] == 100, "energy must regenerate to the cap"
    assert p1["heat"] == 0, "heat must cool off over time"
    assert p1["hp"] <= p1["max_hp"], "regen must never exceed max HP"
    assert p1["infection"] <= 100, "infection must stay bounded"

    # a clean human must not spontaneously get infected by the tick alone
    assert (await E.get_player(2))["infection"] == 0

    # stage must stay consistent with the infection value at all times
    for r in await db.fetchall("SELECT user_id,infection,stage FROM players"):
        from vcorp.game.content import stage_for
        assert r["stage"] == stage_for(r["infection"])[0], dict(r)

    # world state stays inside sane bounds
    threat = int(await db.world_get("threat"))
    assert 0 <= threat <= 100, threat

    # events were actually generated and broadcast at some point
    total_events = await db.scalar("SELECT COUNT(*) FROM events")
    assert total_events > 0, "the living world produced no events in 200 ticks"

    # cure completion must trigger the global relief path.
    # pin threat low so the tick's own infection-creep cannot interfere.
    await db.world_set("threat", 5)
    await db.world_set("cure_progress", 100)
    await db.execute("UPDATE players SET infection=60, stage='advanced'")
    before_cure = await db.scalar("SELECT MAX(infection) FROM players")
    await scheduler.tick_once(bot)
    assert int(await db.world_get("cure_progress")) == 0, "cure must be consumed"
    after_cure = await db.scalar("SELECT MAX(infection) FROM players")
    assert after_cure < before_cure, (before_cure, after_cure)
    # and the bulk change must have resynced everyone's stage
    from vcorp.game.content import stage_for as _sf
    for r in await db.fetchall("SELECT infection,stage FROM players"):
        assert r["stage"] == _sf(r["infection"])[0], dict(r)

    # a failing chat must be deactivated, never crash the loop
    class BrokenBot(FakeBot):
        async def send_message(self, *a, **kw):
            raise RuntimeError("chat not found")

    await scheduler.broadcast(BrokenBot(), "test")
    assert await db.scalar("SELECT active FROM chats WHERE chat_id=-100") == 0

    await db.close()
    print(f"✅ world tick stable over 200 ticks ({total_events} events, "
          f"{bot.sent} broadcasts)", flush=True)


if __name__ == "__main__":
    import traceback
    code = 0
    try:
        asyncio.run(main())
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    os._exit(code)
