"""THE HOLLOW duel tests: rules, edge cases, money safety, no dominant move."""
from __future__ import annotations

import asyncio
import collections
import os
import random
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vcorp.db import db  # noqa: E402
from vcorp.game import duel as D  # noqa: E402
from vcorp.game import engine as E  # noqa: E402
from vcorp.handlers import pvp  # noqa: E402


class FakeBot:
    def __init__(self):
        self.sent = []
        self.edits = 0

    async def send_message(self, chat_id, text, **kw):
        self.sent.append(text)
        return types.SimpleNamespace(message_id=len(self.sent) + 500)

    async def edit_message_text(self, **kw):
        self.edits += 1
        return True

    async def send_dice(self, chat_id, emoji=None):
        return types.SimpleNamespace(dice=types.SimpleNamespace(value=4))


class FakeUser:
    def __init__(self, uid, name):
        self.id, self.full_name, self.is_bot = uid, name, False


class FakeMsg:
    def __init__(self, user, text, bot, reply_to=None, chat_id=-500):
        self.from_user, self.text, self.bot = user, text, bot
        self.chat = types.SimpleNamespace(id=chat_id, type="supergroup", title="Ring")
        self.reply_to_message = reply_to
        self.message_id = 7
        self.out = []

    async def reply(self, t, **kw):
        self.out.append(t)
        return types.SimpleNamespace(message_id=8)

    async def answer(self, t, **kw):
        self.out.append(t)
        return types.SimpleNamespace(message_id=9)

    async def edit_text(self, t, **kw):
        self.out.append(t)
        return True


class FakeCB:
    def __init__(self, user, data, bot, chat_id=-500):
        self.from_user, self.data = user, data
        self.message = FakeMsg(user, "", bot, chat_id=chat_id)
        self.alerts = []

    async def answer(self, text="", show_alert=False):
        self.alerts.append(text)


def fighter(uid, name, **kw):
    base = dict(hp=120, max_hp=120, attack=25, defense=15, infection=0)
    base.update(kw)
    return D.Fighter(user_id=uid, name=name, **base)


async def main() -> None:
    db.path = ":memory:"
    await db.connect()
    await E.seed()
    bot = FakeBot()

    # ── rock-paper-scissors core is a closed loop ─────────────────────────
    assert D._beats("strike", "guard") == 1
    assert D._beats("guard", "feral") == 1
    assert D._beats("feral", "strike") == 1
    assert D._beats("read", "feral") == 1
    assert D._beats("strike", "strike") == 0
    for m in D.MOVES:
        assert any(D._beats(o, m) == 1 for o in D.MOVES), f"{m} has no counter"

    # ── a correct READ fully negates FERAL ────────────────────────────────
    a, b = fighter(1, "A"), fighter(2, "B")
    d = D.Duel(chat_id=-1, a=a, b=b)
    a.move, b.move = "read", "feral"
    D.resolve_round(d)
    assert a.hp == a.max_hp, "read must fully negate feral"
    assert b.hp < b.max_hp, "feral read must be punished"

    # ── FERAL raises infection through settle() ───────────────────────────
    await E.ensure_player(1, "A")
    await E.ensure_player(2, "B")
    a2, b2 = fighter(1, "A"), fighter(2, "B")
    d2 = D.Duel(chat_id=-2, a=a2, b=b2)
    D.register(d2)
    a2.feral_used = 3
    b2.hp = 0
    D.check_end(d2)
    res = await D.settle(d2)
    assert (await E.get_player(1))["infection"] > 0, "feral must cost infection"
    assert res["winner"] == 1

    # ── a duel never kills; the loser leaves at >=1 HP ────────────────────
    assert (await E.get_player(2))["hp"] >= 1, "the ring must not execute"
    assert (await E.get_player(2))["generation"] == 1, "no legacy burn in the ring"

    # ── stakes: escrow, payout, and refunds ───────────────────────────────
    await E.update(1, money=10_000)
    await E.update(2, money=10_000)
    a3, b3 = fighter(1, "A"), fighter(2, "B")
    d3 = D.Duel(chat_id=-3, a=a3, b=b3, stake=2_000)
    D.register(d3)
    await E.add(1, money=-2_000)   # escrow as the handler does
    await E.add(2, money=-2_000)
    b3.hp = 0
    D.check_end(d3)
    r3 = await D.settle(d3)
    assert (await E.get_player(1))["money"] == 10_000 + 2_000, "winner takes the pot"
    assert (await E.get_player(2))["money"] == 8_000
    assert r3["delta"] > 0

    # draw refunds both sides exactly
    await E.update(1, money=5_000)
    await E.update(2, money=5_000)
    a4, b4 = fighter(1, "A", hp=60), fighter(2, "B", hp=60)
    d4 = D.Duel(chat_id=-4, a=a4, b=b4, stake=1_500)
    D.register(d4)
    await E.add(1, money=-1_500)
    await E.add(2, money=-1_500)
    d4.round = D.MAX_ROUNDS + 1
    assert D.check_end(d4) and d4.winner is None
    await D.settle(d4)
    assert (await E.get_player(1))["money"] == 5_000
    assert (await E.get_player(2))["money"] == 5_000

    # abort refunds too (server restart safety)
    await E.update(1, money=1_000)
    await E.update(2, money=1_000)
    a5, b5 = fighter(1, "A"), fighter(2, "B")
    d5 = D.Duel(chat_id=-5, a=a5, b=b5, stake=400)
    D.register(d5)
    await E.add(1, money=-400)
    await E.add(2, money=-400)
    assert await D.abort_all() == 1
    assert (await E.get_player(1))["money"] == 1_000
    assert (await E.get_player(2))["money"] == 1_000
    assert not D.ACTIVE and not D.BUSY, "registries must be clean after abort"

    # ── poise decides a close judged fight ────────────────────────────────
    a6, b6 = fighter(1, "A", hp=100), fighter(2, "B", hp=100)
    d6 = D.Duel(chat_id=-6, a=a6, b=b6)
    a6.poise, b6.poise = 9, 2
    d6.round = D.MAX_ROUNDS + 1
    D.check_end(d6)
    assert d6.winner == 1 and "تکنیکی" in d6.reason

    # ── elo is symmetric and rewards upsets ───────────────────────────────
    assert D.elo_delta(1000, 1000) == 16
    assert D.elo_delta(900, 1300) > D.elo_delta(1300, 900), "upsets pay more"
    assert D.elo_delta(2000, 500) >= 5, "elo delta never collapses to zero"

    # ── adrenaline can never go negative or unbounded ─────────────────────
    a7, b7 = fighter(1, "A"), fighter(2, "B")
    d7 = D.Duel(chat_id=-7, a=a7, b=b7)
    for i in range(40):
        a7.move = random.choice(list(D.MOVES))
        b7.move = random.choice(list(D.MOVES))
        D.resolve_round(d7)
        assert 0 <= a7.adrenaline <= 9, a7.adrenaline
        assert 0 <= b7.adrenaline <= 9, b7.adrenaline
        assert a7.hp >= 0 and b7.hp >= 0
        if a7.hp == 0 or b7.hp == 0:
            a7.hp, b7.hp = 120, 120

    # a move you cannot afford degrades instead of going negative
    a8, b8 = fighter(1, "A", ), fighter(2, "B")
    a8.adrenaline = 0
    d8 = D.Duel(chat_id=-8, a=a8, b=b8)
    a8.move, b8.move = "feral", "guard"
    D.resolve_round(d8)
    assert a8.adrenaline >= 0

    # ── no dominant pure strategy (the whole point of the design) ─────────
    def sim(sa, sb, n=600):
        w = collections.Counter()
        for _ in range(n):
            x, y = fighter(1, "A"), fighter(2, "B")
            dd = D.Duel(chat_id=-9, a=x, b=y)
            for r in range(1, D.MAX_ROUNDS + 1):
                dd.round = r
                x.move, y.move = sa(x), sb(y)
                D.resolve_round(dd)
                if D.check_end(dd):
                    break
            else:
                dd.round = D.MAX_ROUNDS + 1
                D.check_end(dd)
            w[dd.winner] += 1
        return (w[1] + 0.5 * w[None]) / n

    def afford(f):
        opts = [m for m in D.MOVES if D.COST[m] <= f.adrenaline]
        return random.choice(opts or ["guard"])

    scores = {m: sim(lambda f, m=m: m, afford, 700) for m in D.MOVES}
    top = max(scores.values())
    assert top < 0.80, f"a pure strategy dominates: {scores}"
    assert D.MAX_ROUNDS >= 6

    # mirror match must be fair
    mirror = sim(afford, afford, 1200)
    assert 0.40 < mirror < 0.60, f"mirror match is biased: {mirror}"

    # ── handler flow: challenge → accept → duel runs ──────────────────────
    await E.update(1, money=20_000)
    await E.update(2, money=20_000)
    u1, u2 = FakeUser(1, "A"), FakeUser(2, "B")
    msg = FakeMsg(u1, "/duel 1000", bot, reply_to=FakeMsg(u2, "hi", bot))
    await pvp.challenge(msg, bot)
    assert (-500, 2) in pvp.PENDING, "challenge must be pending"

    # only the challenged player may accept
    wrong = FakeCB(FakeUser(3, "C"), "dc:ok:2", bot)
    await pvp.challenge_answer(wrong, bot)
    assert "برای تو نیست" in wrong.alerts[0]

    ok = FakeCB(u2, "dc:ok:2", bot)
    await pvp.challenge_answer(ok, bot)
    live = D.duel_of(-500)
    assert live is not None, "duel must start"
    assert (await E.get_player(1))["money"] == 19_000, "stake must be escrowed"
    if live._task:
        live._task.cancel()

    # a spectator cannot pick a move
    spec = FakeCB(FakeUser(3, "C"), "d:strike", bot)
    await pvp.pick_move(spec, bot)
    assert "در این دوئل نیستی" in spec.alerts[-1]

    # a fighter cannot change a locked move
    c1 = FakeCB(u1, "d:strike", bot)
    await pvp.pick_move(c1, bot)
    c1b = FakeCB(u1, "d:guard", bot)
    await pvp.pick_move(c1b, bot)
    assert "ثبت شده" in c1b.alerts[-1]

    # both ready → round resolves
    rounds_before = live.round
    c2 = FakeCB(u2, "d:guard", bot)
    await pvp.pick_move(c2, bot)
    assert live.round > rounds_before or live.finished
    if live._task:
        live._task.cancel()

    # play it out; money must be conserved overall
    guard = 0
    while not live.finished and guard < 40:
        guard += 1
        for f, u in ((live.a, u1), (live.b, u2)):
            if f.move is None:
                f.move = random.choice(list(D.MOVES))
        await pvp.advance(bot, live)
        if live._task:
            live._task.cancel()
    assert live.finished, "duel must terminate"
    total = (await E.get_player(1))["money"] + (await E.get_player(2))["money"]
    assert total == 40_000, f"money leaked or was minted: {total}"
    assert not D.ACTIVE, "ring must be released"

    # ── you cannot be in two duels at once ────────────────────────────────
    a9, b9 = fighter(1, "A"), fighter(2, "B")
    d9 = D.Duel(chat_id=-77, a=a9, b=b9)
    D.register(d9)
    assert D.duel_for_user(1) is d9
    m2 = FakeMsg(u1, "/duel", bot, reply_to=FakeMsg(u2, "x", bot), chat_id=-88)
    await pvp.challenge(m2, bot)
    assert any("گودال است" in t for t in m2.out), "double-duel must be blocked"
    await D.abort_all()

    # ── ranks are ordered and total ───────────────────────────────────────
    last = -1
    for elo in (0, 900, 1000, 1200, 1300, 1500, 1700, 3000):
        icon, name = pvp.rank_of(elo)
        assert icon and name
    assert pvp.rank_of(3000)[1] != pvp.rank_of(0)[1]

    await db.close()
    print(f"✅ PvP suite passed — best pure strategy {top*100:.0f}%, "
          f"mirror {mirror*100:.0f}%", flush=True)


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
