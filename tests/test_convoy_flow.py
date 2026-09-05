"""THE CONVOY handler flow: escrow safety, private posts, a full run."""
from __future__ import annotations

import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vcorp.db import db  # noqa: E402
from vcorp.game import convoy as C  # noqa: E402
from vcorp.game import engine as E  # noqa: E402
from vcorp.handlers import convoy as H  # noqa: E402

CHAT = -700


class FakeBot:
    def __init__(self):
        self.group: list[str] = []
        self.dms: dict[int, list[str]] = {}
        # whatever reached exactly one player, by whichever route
        self.secrets: dict[int, list[str]] = {}
        self.blocked: set[int] = set()

    async def send_message(self, chat_id, text,
                           ephemeral_message_parameters=None, **kw):
        # An ephemeral message is posted to the group but is visible only to
        # one user, so it counts as private delivery, not a group post.
        if ephemeral_message_parameters is not None:
            uid = ephemeral_message_parameters.receiver_user_id
            if uid in self.blocked:
                raise RuntimeError("ephemeral undeliverable")
            self.secrets.setdefault(uid, []).append(text)
            return types.SimpleNamespace(message_id=99)
        if chat_id == CHAT:
            self.group.append(text)
        else:
            if chat_id in self.blocked:
                raise RuntimeError("bot was blocked by the user")
            self.dms.setdefault(chat_id, []).append(text)
            self.secrets.setdefault(chat_id, []).append(text)
        return types.SimpleNamespace(message_id=len(self.group) + 1)

    async def edit_message_text(self, **kw):
        return True

    async def edit_message_reply_markup(self, **kw):
        return True

    async def send_dice(self, chat_id, emoji=None):
        return types.SimpleNamespace(dice=types.SimpleNamespace(value=4))


class U:
    def __init__(self, uid, name):
        self.id, self.full_name, self.is_bot = uid, name, False


class Msg:
    def __init__(self, user, text, bot, chat_id=CHAT):
        self.from_user, self.text, self.bot = user, text, bot
        self.chat = types.SimpleNamespace(id=chat_id, type="supergroup", title="G")
        self.message_id = 3
        self.out = []

    async def reply(self, t, **kw):
        self.out.append(t)
        return types.SimpleNamespace(message_id=4)

    async def answer(self, t, **kw):
        self.out.append(t)
        return types.SimpleNamespace(message_id=5)


class CB:
    def __init__(self, user, data, bot, chat_id=CHAT):
        self.from_user, self.data = user, data
        self.message = Msg(user, "", bot, chat_id)
        self.message.reply_markup = None
        self.message.edit_text = self._edit
        self.alerts = []

    async def _edit(self, t, **kw):
        return True

    async def answer(self, text="", show_alert=False):
        self.alerts.append(text)


async def wealth(users) -> int:
    total = 0
    for u in users:
        total += (await E.get_player(u.id))["money"]
    return total


async def main() -> None:
    db.path = ":memory:"
    await db.connect()
    await E.seed()
    bot = FakeBot()

    users = [U(i, f"P{i}") for i in range(1, 9)]
    for u in users:
        await E.ensure_player(u.id, u.full_name)
        await E.update(u.id, money=20_000)

    # ── escrow on join / refund on leave ─────────────────────────────────
    await H.open_run(Msg(users[0], "/convoy 2000", bot), bot)
    g = H.run_of(CHAT)
    H._cancel(g)
    assert g.stake == 2000 and g.pot == 2000
    assert (await E.get_player(1))["money"] == 18_000

    for u in users[1:6]:
        await H.join(CB(u, "cv:join", bot))
    assert len(g.players) == 6 and g.pot == 12_000

    # double join must not double-charge
    await H.join(CB(users[1], "cv:join", bot))
    assert (await E.get_player(2))["money"] == 18_000 and g.pot == 12_000

    # the host cannot bail out and strand the pot
    c = CB(users[0], "cv:leave", bot)
    await H.leave(c)
    assert 1 in g.players and g.pot == 12_000

    await H.leave(CB(users[5], "cv:leave", bot))
    assert (await E.get_player(6))["money"] == 20_000 and g.pot == 10_000

    # non-host cannot force departure
    c = CB(users[1], "cv:go", bot)
    await H.go(c, bot)
    assert "راننده" in c.alerts[-1]

    # ── departure deals private station prompts, not group ones ──────────
    bot.blocked.add(4)
    await H.depart(bot, g)
    H._cancel(g)
    assert g.phase is C.Phase.STATION and g.leg == 1
    for uid in (1, 2, 3, 5):
        assert bot.secrets.get(uid), f"crew {uid} never got a prompt"

    # ── picking a post ───────────────────────────────────────────────────
    c = CB(U(999, "ghost"), f"cv:s:{CHAT}:repair", bot)
    await H.pick_station(c, bot)
    assert "سوار این کاروان نیستی" in c.alerts[-1]

    ids = list(g.players)
    for uid in ids[:-1]:
        c = CB(U(uid, "x"), f"cv:s:{CHAT}:defend", bot)
        await H.pick_station(c, bot)
    H._cancel(g)
    assert not C.everyone_stationed(g)
    assert g.phase is C.Phase.STATION

    # the last pick auto-advances the phase
    c = CB(U(ids[-1], "x"), f"cv:s:{CHAT}:scout", bot)
    await H.pick_station(c, bot)
    H._cancel(g)
    assert g.phase is C.Phase.SPEED, "a full crew must move on immediately"
    assert g.scouted, "a scout was staffed"

    # ── speed vote ───────────────────────────────────────────────────────
    c = CB(U(999, "ghost"), "cv:v:reckless", bot)
    await H.pick_speed(c, bot)
    assert 999 not in g.players

    before_leg = g.leg
    for uid in ids:
        c = CB(U(uid, "x"), "cv:v:careful", bot)
        await H.pick_speed(c, bot)
    H._cancel(g)
    assert g.leg == before_leg + 1 or g.phase is C.Phase.ENDED, \
        "a unanimous vote must drive the convoy"

    # ── idle crew is auto-assigned rather than stalling ──────────────────
    if g.phase is C.Phase.STATION:
        H._cancel(g)
        await H.close_stations(bot, g)
        H._cancel(g)
        assert all(p.station is not None for p in g.players.values())
        assert g.phase in (C.Phase.SPEED, C.Phase.ENDED)

    # ── a lost run pays nobody, and the pot is gone ──────────────────────
    total_before = await wealth(users)
    pot = g.pot
    g.hull = 0
    C.check_end(g)
    assert g.winner == "lost"
    await H.finish(bot, g)
    assert await wealth(users) == total_before, "a failed run must not pay out"
    assert not H.RUNS and not H.RIDING

    # ── a successful run pays exactly the pot ────────────────────────────
    for u in users:
        await E.update(u.id, money=10_000)
    await H.open_run(Msg(users[0], "/convoy 1000", bot), bot)
    g = H.run_of(CHAT)
    H._cancel(g)
    for u in users[1:5]:
        await H.join(CB(u, "cv:join", bot))
    await H.depart(bot, g)
    H._cancel(g)
    pot = g.pot
    total_before = await wealth(users)
    g.distance = C.DISTANCE_GOAL
    C.check_end(g)
    assert g.winner == "escaped"
    await H.finish(bot, g)
    assert await wealth(users) == total_before + pot, "the pot must be paid in full"
    assert not H.RUNS

    # ── /cvstop refunds ──────────────────────────────────────────────────
    for u in users:
        await E.update(u.id, money=8_000)
    await H.open_run(Msg(users[0], "/convoy 900", bot), bot)
    g = H.run_of(CHAT)
    H._cancel(g)
    for u in users[1:4]:
        await H.join(CB(u, "cv:join", bot))
    m = Msg(users[2], "/cvstop", bot)
    await H.stop_run(m)
    assert H.run_of(CHAT) is not None, "only the driver may stop the convoy"
    await H.stop_run(Msg(users[0], "/cvstop", bot))
    for u in users[:4]:
        assert (await E.get_player(u.id))["money"] == 8_000
    assert not H.RUNS

    # ── shutdown refunds ─────────────────────────────────────────────────
    for u in users:
        await E.update(u.id, money=6_000)
    await H.open_run(Msg(users[0], "/convoy 750", bot), bot)
    g = H.run_of(CHAT)
    H._cancel(g)
    for u in users[1:4]:
        await H.join(CB(u, "cv:join", bot))
    assert await H.abort_all() == 1
    for u in users[:4]:
        assert (await E.get_player(u.id))["money"] == 6_000
    assert not H.RUNS and not H.RIDING

    # ── too few crew cancels and refunds ─────────────────────────────────
    await E.update(1, money=5_000)
    await H.open_run(Msg(users[0], "/convoy 800", bot), bot)
    g = H.run_of(CHAT)
    H._cancel(g)
    await H.depart(bot, g)
    assert (await E.get_player(1))["money"] == 5_000
    assert not H.RUNS

    await db.close()
    print("✅ CONVOY flow passed — escrow safe, posts private", flush=True)


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
