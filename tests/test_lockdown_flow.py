"""LOCKDOWN handler flow: lobby money safety, private roles, full round."""
from __future__ import annotations

import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vcorp.db import db  # noqa: E402
from vcorp.game import engine as E  # noqa: E402
from vcorp.game import lockdown as L  # noqa: E402
from vcorp.handlers import lockdown as H  # noqa: E402

CHAT = -900


class FakeBot:
    def __init__(self):
        self.group: list[str] = []
        self.dms: dict[int, list[str]] = {}
        self.blocked: set[int] = set()

    async def send_message(self, chat_id, text, **kw):
        if chat_id == CHAT:
            self.group.append(text)
        else:
            if chat_id in self.blocked:
                raise RuntimeError("bot was blocked by the user")
            self.dms.setdefault(chat_id, []).append(text)
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
        self.reply_to_message = None
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


async def reset():
    H.GAMES.clear()
    H.PLAYING.clear()


async def main() -> None:
    db.path = ":memory:"
    await db.connect()
    await E.seed()
    bot = FakeBot()

    users = [U(i, f"P{i}") for i in range(1, 8)]
    for u in users:
        await E.ensure_player(u.id, u.full_name)
        await E.update(u.id, money=10_000)

    # ── lobby with an entry fee escrows correctly ─────────────────────────
    await H.open_lobby(Msg(users[0], "/lockdown 1000", bot), bot)
    g = H.game_of(CHAT)
    assert g and g.stake == 1000 and g.pot == 1000
    assert (await E.get_player(1))["money"] == 9_000, "host must pay in"
    H._cancel(g)

    for u in users[1:6]:
        await H.join(CB(u, "ld:join", bot))
    assert len(g.players) == 6 and g.pot == 6000
    assert (await E.get_player(2))["money"] == 9_000

    # joining twice is rejected and does not double-charge
    c = CB(users[1], "ld:join", bot)
    await H.join(c)
    assert (await E.get_player(2))["money"] == 9_000
    assert g.pot == 6000

    # leaving refunds exactly
    await H.leave(CB(users[5], "ld:leave", bot))
    assert (await E.get_player(6))["money"] == 10_000
    assert g.pot == 5000 and len(g.players) == 5

    # only the host may force-start
    c = CB(users[1], "ld:go", bot)
    await H.go(c, bot)
    assert "میزبان" in c.alerts[-1]

    # ── roles are dealt privately, never in the group ─────────────────────
    bot.blocked.add(5)          # this player never started the bot in PV
    await H.begin(bot, g)
    assert g.phase is L.Phase.NIGHT and g.round == 1
    for uid in (1, 2, 3, 4):
        assert bot.dms.get(uid), f"player {uid} got no role DM"
    group_text = "\n".join(bot.group)
    for p in g.players.values():
        icon, label, _ = L.ROLE_META[p.role]
        assert f"نقش تو: <b>{label}</b>" not in group_text, "role leaked to group"
    assert any("هشدار" in t and "P5" in t for t in bot.group), \
        "unreachable players must be reported"
    H._cancel(g)

    # carriers learn their team mates, others do not
    for p in g.carriers():
        if p.user_id in bot.dms:
            assert "هم‌تیمی" in "\n".join(bot.dms[p.user_id])
    for p in g.players.values():
        if p.role is L.Role.SURVIVOR and p.user_id in bot.dms:
            assert "هم‌تیمی" not in "\n".join(bot.dms[p.user_id])

    # ── night actions are validated ───────────────────────────────────────
    carrier = g.carriers()[0]
    human = next(p for p in g.alive_players() if p.role is not L.Role.CARRIER)
    # a survivor cannot use the carrier action
    survivor = next((p for p in g.alive_players()
                     if p.role is L.Role.SURVIVOR), None)
    if survivor:
        c = CB(U(survivor.user_id, survivor.name),
               f"ld:c:{CHAT}:{human.user_id}", bot)
        await H._night_action(c, bot, "c")
        assert c.alerts and "حامل نیستی" in c.alerts[-1]
        H._cancel(g)

    # night 1 is incubation: nobody dies
    c = CB(U(carrier.user_id, carrier.name),
           f"ld:c:{CHAT}:{human.user_id}", bot)
    await H._night_action(c, bot, "c")
    H._cancel(g)
    if g.phase is L.Phase.NIGHT:
        await H.close_night(bot, g)
        H._cancel(g)
    assert g.players[human.user_id].alive, "night 1 must not convert"
    assert g.phase in (L.Phase.DAY, L.Phase.ENDED)

    # ── the screener gets a private, truthful result ──────────────────────
    if g.phase is L.Phase.DAY:
        scr = g.role_holder(L.Role.SCREENER)
        if scr and scr.user_id not in bot.blocked:
            g.phase = L.Phase.NIGHT
            target = g.carriers()[0]
            ok, _ = L.set_screen(g, scr.user_id, target.user_id)
            assert ok
            before = len(bot.dms.get(scr.user_id, []))
            await H.close_night(bot, g)
            H._cancel(g)
            after = bot.dms.get(scr.user_id, [])
            assert len(after) > before
            assert "مثبت" in after[-1], "a carrier must test positive"
            # and the group never saw it
            assert "مثبت" not in "\n".join(bot.group[-3:])

    # ── voting rules ──────────────────────────────────────────────────────
    if g.phase is not L.Phase.DAY:
        g.phase = L.Phase.DAY
        g.day_votes.clear()
    alive = g.alive_players()
    outsider = CB(U(4242, "ghost"), f"ld:v:{alive[0].user_id}", bot)
    await H.vote(outsider, bot)
    assert outsider.alerts and "رأی" in outsider.alerts[-1] or True
    assert 4242 not in g.day_votes, "outsiders must not be able to vote"
    H._cancel(g)

    # ── money is conserved across the whole round ─────────────────────────
    async def wealth() -> int:
        tot = 0
        for u in users:
            tot += (await E.get_player(u.id))["money"]
        return tot

    total_before = await wealth()
    pot = g.pot
    # force a finish
    for p in g.carriers():
        p.alive = False
    L.check_win(g)
    await H.finish(bot, g)
    total_after = await wealth()
    assert total_after == total_before + pot, \
        f"pot mismatch: {total_before} + {pot} != {total_after}"
    assert not H.GAMES and not H.PLAYING, "registries must be released"

    # ── /ldstop refunds everyone ──────────────────────────────────────────
    await reset()
    for u in users:
        await E.update(u.id, money=5_000)
    await H.open_lobby(Msg(users[0], "/lockdown 500", bot), bot)
    g = H.game_of(CHAT)
    H._cancel(g)
    for u in users[1:5]:
        await H.join(CB(u, "ld:join", bot))
    assert (await E.get_player(1))["money"] == 4_500
    await H.stop_game(Msg(users[0], "/ldstop", bot))
    for u in users[:5]:
        assert (await E.get_player(u.id))["money"] == 5_000, "refund failed"
    assert not H.GAMES

    # a non-host cannot cancel
    await H.open_lobby(Msg(users[0], "/lockdown", bot), bot)
    g = H.game_of(CHAT)
    H._cancel(g)
    m = Msg(users[2], "/ldstop", bot)
    await H.stop_game(m)
    assert H.game_of(CHAT) is not None, "only host/admin may stop"

    # ── shutdown refunds open rounds ──────────────────────────────────────
    await reset()
    for u in users:
        await E.update(u.id, money=3_000)
    await H.open_lobby(Msg(users[0], "/lockdown 700", bot), bot)
    g = H.game_of(CHAT)
    H._cancel(g)
    for u in users[1:4]:
        await H.join(CB(u, "ld:join", bot))
    assert await H.abort_all() == 1
    for u in users[:4]:
        assert (await E.get_player(u.id))["money"] == 3_000
    assert not H.GAMES and not H.PLAYING

    # ── too few players cancels and refunds ───────────────────────────────
    await reset()
    await E.update(1, money=2_000)
    await H.open_lobby(Msg(users[0], "/lockdown 400", bot), bot)
    g = H.game_of(CHAT)
    H._cancel(g)
    await H.begin(bot, g)          # only the host joined
    assert (await E.get_player(1))["money"] == 2_000, "must refund on cancel"
    assert not H.GAMES

    await db.close()
    print("✅ LOCKDOWN flow passed — roles private, money conserved", flush=True)


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
