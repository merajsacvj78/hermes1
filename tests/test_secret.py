"""Secret delivery must prefer ephemeral, fall back to DM, and never raise."""
from __future__ import annotations

import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vcorp import secret  # noqa: E402

CHAT = -500


class Bot:
    """Fake bot recording how each message was routed."""

    def __init__(self, ephemeral_ok=True, dm_ok=True):
        self.ephemeral_ok = ephemeral_ok
        self.dm_ok = dm_ok
        self.ephemeral: list[tuple[int, str]] = []
        self.dms: list[tuple[int, str]] = []
        self.group: list[str] = []

    async def send_message(self, chat_id, text, reply_markup=None,
                           ephemeral_message_parameters=None, **kw):
        if ephemeral_message_parameters is not None:
            if not self.ephemeral_ok:
                raise RuntimeError("ephemeral not supported here")
            self.ephemeral.append(
                (ephemeral_message_parameters.receiver_user_id, text))
            return types.SimpleNamespace(message_id=1)
        if chat_id == CHAT:
            self.group.append(text)
            return types.SimpleNamespace(message_id=2)
        if not self.dm_ok:
            raise RuntimeError("bot was blocked")
        self.dms.append((chat_id, text))
        return types.SimpleNamespace(message_id=3)


async def main() -> None:
    assert secret._HAS_EPHEMERAL, \
        "aiogram build must support ephemeral messages"

    # ── happy path: nothing leaks into the group ─────────────────────────
    secret.reset_cache()
    bot = Bot()
    r = await secret.deliver(bot, CHAT, 77, "your role is carrier")
    assert r is secret.Route.EPHEMERAL
    assert bot.ephemeral == [(77, "your role is carrier")]
    assert not bot.group, "a secret must never be posted openly"
    assert not bot.dms

    # ── ephemeral unavailable -> DM, and it stops retrying ───────────────
    secret.reset_cache()
    bot = Bot(ephemeral_ok=False)
    r = await secret.deliver(bot, CHAT, 77, "secret")
    assert r is secret.Route.DM and bot.dms == [(77, "secret")]
    assert CHAT in secret._no_ephemeral, "the failure must be remembered"
    await secret.deliver(bot, CHAT, 78, "secret2")
    assert len(bot.ephemeral) == 0
    assert len(bot.dms) == 2, "should go straight to DM after the first failure"

    # a different chat is still tried
    other = -600
    await secret.deliver(bot, other, 79, "x")
    assert other in secret._no_ephemeral

    # ── both routes down -> reported, not raised ─────────────────────────
    secret.reset_cache()
    bot = Bot(ephemeral_ok=False, dm_ok=False)
    r = await secret.deliver(bot, CHAT, 77, "secret")
    assert r is secret.Route.FAILED, "an unreachable user must be reported"
    assert not bot.group, "a failed secret must not spill into the group"

    # ── deliver_many keeps per-user routing and ordering ─────────────────
    secret.reset_cache()
    bot = Bot()
    items = [(i, f"role {i}", None) for i in range(1, 6)]
    routes = await secret.deliver_many(bot, CHAT, items)
    assert set(routes) == {1, 2, 3, 4, 5}
    assert all(v is secret.Route.EPHEMERAL for v in routes.values())
    assert len(bot.ephemeral) == 5
    # every player got their own text, not someone else's
    assert dict(bot.ephemeral) == {i: f"role {i}" for i in range(1, 6)}
    assert secret.unreachable(routes) == []

    # ── partial failure is isolated to the affected user ─────────────────
    secret.reset_cache()

    class Picky(Bot):
        async def send_message(self, chat_id, text, reply_markup=None,
                               ephemeral_message_parameters=None, **kw):
            if ephemeral_message_parameters is not None:
                raise RuntimeError("no ephemeral")
            if chat_id == 3:                     # this one blocked the bot
                raise RuntimeError("blocked")
            return await Bot.send_message(self, chat_id, text, reply_markup,
                                          None, **kw)

    bot = Picky(ephemeral_ok=False)
    routes = await secret.deliver_many(
        bot, CHAT, [(i, f"r{i}", None) for i in (1, 2, 3, 4)])
    assert secret.unreachable(routes) == [3], f"got {routes}"
    assert routes[1] is secret.Route.DM and routes[4] is secret.Route.DM

    # ── empty input is a no-op ───────────────────────────────────────────
    assert await secret.deliver_many(Bot(), CHAT, []) == {}

    print("✅ secret delivery passed — ephemeral first, DM fallback, "
          "failures reported", flush=True)


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
