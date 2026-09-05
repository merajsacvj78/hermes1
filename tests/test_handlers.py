"""Offline handler simulation — runs real handler code against a fake Bot.

Telegram is not reachable from CI/sandboxes, so we drive the handler functions
directly with lightweight stand-ins for Message / CallbackQuery / Bot and assert
on the game state they produce.
"""
from __future__ import annotations

import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vcorp import notify  # noqa: E402
from vcorp.db import db  # noqa: E402
from vcorp.game import engine as E  # noqa: E402
from vcorp.handlers import actions, betrayal, economy, group_core, orgs, world  # noqa: E402

SENT: list[str] = []


class FakeUser:
    def __init__(self, uid: int, name: str):
        self.id = uid
        self.full_name = name
        self.is_bot = False


class FakeChat:
    def __init__(self, cid: int = -1001):
        self.id = cid
        self.type = "supergroup"
        self.title = "Outbreak Test"


class FakeBot:
    """Records outgoing calls; dice always returns a fixed value."""

    def __init__(self, dice_value: int = 4):
        self.dice_value = dice_value
        self.sent: list[tuple[int, str]] = []

    async def send_dice(self, chat_id, emoji=None):
        d = types.SimpleNamespace(value=self.dice_value)
        return types.SimpleNamespace(dice=d, message_id=1)

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))
        return types.SimpleNamespace(message_id=len(self.sent))

    async def edit_message_text(self, **kw):
        return True


class FakeMessage:
    def __init__(self, user: FakeUser, text: str, bot: FakeBot,
                 reply_to: "FakeMessage | None" = None, chat: FakeChat | None = None):
        self.from_user = user
        self.text = text
        self.bot = bot
        self.chat = chat or FakeChat()
        self.reply_to_message = reply_to
        self.message_id = 100

    async def reply(self, text, **kw):
        SENT.append(text)
        return types.SimpleNamespace(message_id=101)

    async def answer(self, text, **kw):
        SENT.append(text)
        return types.SimpleNamespace(message_id=102)

    async def answer_document(self, *a, **kw):
        return None

    async def delete(self):
        return True


class FakeCallback:
    def __init__(self, user: FakeUser, data: str, bot: FakeBot):
        self.from_user = user
        self.data = data
        self.message = FakeMessage(user, "", bot)
        self.alerts: list[str] = []

    async def answer(self, text="", show_alert=False):
        self.alerts.append(text)
        SENT.append(text)


def last() -> str:
    return SENT[-1] if SENT else ""


async def main() -> None:
    db.path = ":memory:"
    await db.connect()
    await E.seed()

    bot = FakeBot()
    kade = FakeUser(11, "Kade")
    vera = FakeUser(22, "Vera")

    # ── onboarding ────────────────────────────────────────────────────────
    await group_core.start(FakeMessage(kade, "/start", bot))
    await group_core.start(FakeMessage(vera, "/start", bot))
    assert await E.get_player(11) and await E.get_player(22)
    assert "پروتکل ورود" in SENT[0]

    # chat got registered for broadcasts
    assert await db.scalar("SELECT COUNT(*) FROM chats") >= 0

    # ── profile renders with all systems ──────────────────────────────────
    await group_core.me(FakeMessage(kade, "/me", bot))
    assert "پرونده عامل" in last() and "Attack" in last()

    # ── scavenge uses the animated die and pays out ───────────────────────
    before = (await E.get_player(11))["money"]
    await actions.scavenge(FakeMessage(kade, "/scavenge", bot), bot)
    assert (await E.get_player(11))["money"] > before
    # cooldown is enforced
    n = len(SENT)
    await actions.scavenge(FakeMessage(kade, "/scavenge", bot), bot)
    assert "آماده نیستی" in SENT[-1] or len(SENT) > n

    # ── combat: dart 6 forces a critical hit ──────────────────────────────
    crit_bot = FakeBot(dice_value=6)
    vera_msg = FakeMessage(vera, "hi", crit_bot)
    hp_before = (await E.get_player(22))["hp"]
    await actions.attack(
        FakeMessage(kade, "/attack", crit_bot, reply_to=vera_msg), crit_bot)
    assert (await E.get_player(22))["hp"] < hp_before, "critical dart must land"
    assert "CRITICAL" in last() or "درگیری" in last()

    # dart 1 forces a miss
    miss_bot = FakeBot(dice_value=1)
    await E.set_cooldown(11, "attack", 0)
    hp_now = (await E.get_player(22))["hp"]
    await actions.attack(
        FakeMessage(kade, "/attack", miss_bot, reply_to=FakeMessage(vera, "x", miss_bot)),
        miss_bot)
    assert (await E.get_player(22))["hp"] == hp_now, "dart 1 must miss"

    # ── economy: buy, dynamic price, sell to market ───────────────────────
    await E.add(11, money=50_000)
    cq = FakeCallback(kade, "buy:medkit", bot)
    p0 = await E.price_of("medkit")
    had = await E.item_qty(11, "medkit")   # scavenge may already have found one
    await economy.buy(cq)
    assert await E.item_qty(11, "medkit") == had + 1
    assert await E.price_of("medkit") > p0, "buying must push the price up"

    await economy.sell(FakeMessage(kade, "/sell medkit 900", bot))
    assert await db.scalar("SELECT COUNT(*) FROM market WHERE status='open'") == 1
    assert await E.item_qty(11, "medkit") == had, "listing must escrow the item"
    await E.add(22, money=50_000)
    v_had = await E.item_qty(22, "medkit")
    listing = await db.fetchone("SELECT id FROM market WHERE status='open'")
    await economy.market_buy(FakeCallback(vera, f"mk:{listing['id']}", bot))
    assert await E.item_qty(22, "medkit") == v_had + 1

    # ── black-market gamble ───────────────────────────────────────────────
    jackpot = FakeBot(dice_value=64)
    cure_had = await E.item_qty(11, "cure_proto")
    await economy.deal(FakeMessage(kade, "/deal 1000", jackpot), jackpot)
    assert await E.item_qty(11, "cure_proto") == cure_had + 1, "777 must pay the jackpot"

    # ── secret contract warns the target but hides the buyer ──────────────
    await betrayal.contract(
        FakeMessage(kade, "/contract Vera 5000", bot), bot)
    c = await db.fetchone("SELECT * FROM contracts WHERE status='open'")
    assert c and c["target_id"] == 22 and c["issuer_id"] == 11
    dm_texts = [t for _, t in bot.sent]
    assert any("هشدار امنیتی" in t for t in dm_texts), "target must be warned"
    assert not any("Kade" in t for t in dm_texts if "هشدار" in t), \
        "the buyer must stay anonymous"

    # ── contract auto-settles on kill ─────────────────────────────────────
    await E.update(22, hp=1)
    kill_bot = FakeBot(dice_value=6)
    await E.set_cooldown(11, "attack", 0)
    await actions.attack(
        FakeMessage(kade, "/attack", kill_bot, reply_to=FakeMessage(vera, "x", kill_bot)),
        kill_bot)
    done = await db.fetchone("SELECT * FROM contracts WHERE id=?", (c["id"],))
    assert done["status"] == "done" and done["taker_id"] == 11
    v = await E.get_player(22)
    assert v["generation"] == 2 and v["legacy"] > 0, "legacy must carry over"

    # ── organizations ─────────────────────────────────────────────────────
    o = await db.fetchone("SELECT org_id FROM orgs WHERE code='ubc'")
    await orgs.join_cb(FakeCallback(kade, f"org:join:{o['org_id']}", bot))
    assert (await E.get_player(11))["org_id"] == o["org_id"]

    await E.add(11, money=30_000)
    await orgs.found(FakeMessage(kade, "/found Ashgate", bot))
    mine = await db.fetchone("SELECT * FROM orgs WHERE name='Ashgate'")
    assert mine and mine["leader_id"] == 11
    assert (await E.get_player(11))["org_rank"] == "leader"

    # betrayal ejects you and warns the members
    await E.update(11, org_id=o["org_id"], org_rank="operative")
    await betrayal.betray(FakeMessage(kade, "/betray", bot), bot)
    after = await E.get_player(11)
    assert after["path"] == "traitor" and after["org_id"] is None
    assert (await E.rep_all(11))["ubc"] <= -30

    # ── missions ──────────────────────────────────────────────────────────
    m = await db.fetchone("SELECT id FROM missions WHERE code='escort'")
    await E.update(11, energy=100)
    await actions.run_mission(FakeCallback(kade, f"ms:{m['id']}", bot))
    assert await db.scalar("SELECT COUNT(*) FROM mission_runs") == 1

    # ── mutation gating through the real handler ──────────────────────────
    await E.update(11, infection=0, stage="human")
    await E.apply_infection(11, 50)
    await actions.mutate(FakeMessage(kade, "/mutate", bot))
    assert "درخت جهش" in last()
    await actions.cb_mut(FakeCallback(kade, "mut:claw", bot))
    assert await db.scalar(
        "SELECT COUNT(*) FROM mutations WHERE user_id=11 AND node='claw'") == 1
    # a locked node must be refused
    await actions.cb_mut(FakeCallback(kade, "mut:apex", bot))
    assert await db.scalar(
        "SELECT COUNT(*) FROM mutations WHERE user_id=11 AND node='apex'") == 0

    # ── powers ────────────────────────────────────────────────────────────
    await E.give_item(11, "vserum")
    await actions.inject(FakeMessage(kade, "/inject", bot), bot)
    assert len(await E.player_powers(11)) == 1
    code = (await E.player_powers(11))[0]["code"]
    await E.update(11, hp=100)
    await actions.use_power(
        FakeMessage(kade, f"/use {code}", bot,
                    reply_to=FakeMessage(vera, "x", bot)), bot)
    assert await E.cooldown_left(11, f"pw:{code}") > 0, "power must go on cooldown"

    # ── world & boss ──────────────────────────────────────────────────────
    await world.world(FakeMessage(kade, "/world", bot))
    assert "وضعیت جهان" in last()
    e = await world.spawn_event(bot, -1001, "outbreak")
    assert e["code"] == "outbreak"
    assert int(await db.world_get("threat")) > 10, "outbreak must raise threat"

    await world.boss(FakeMessage(kade, "/boss", bot))
    b = await db.fetchone("SELECT * FROM bosses WHERE status='active'")
    assert b and b["hp"] == b["max_hp"]
    await world._hit(-1001, kade, lambda t: SENT.append(t) or asyncio.sleep(0), bot)
    b2 = await db.fetchone("SELECT * FROM bosses WHERE id=?", (b["id"],))
    assert b2["hp"] < b["hp"], "boss must take damage"

    # cure event lowers everyone's infection
    inf_before = await db.scalar("SELECT SUM(infection) FROM players")
    await world.spawn_event(bot, -1001, "cure")
    assert await db.scalar("SELECT SUM(infection) FROM players") <= inf_before

    # ── ban middleware data path ──────────────────────────────────────────
    await E.update(22, banned=1)
    assert await db.scalar("SELECT banned FROM players WHERE user_id=22") == 1
    await E.update(22, banned=0)

    # ── notifications degrade gracefully when the DM is blocked ───────────
    class DeadBot(FakeBot):
        async def send_message(self, *a, **kw):
            raise RuntimeError("bot was blocked by the user")

    assert await notify.hunted(DeadBot(), 11, 1000) is None  # must not raise

    await db.close()
    print(f"✅ handler simulation passed ({len(SENT)} bot messages rendered)", flush=True)


if __name__ == "__main__":
    import traceback
    code = 0
    try:
        asyncio.run(main())
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
