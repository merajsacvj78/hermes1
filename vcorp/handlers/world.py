"""Living world: dynamic events, world state, world bosses."""
from __future__ import annotations

import json
import os
import random

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message

from .. import anim, channel, notify
from ..db import db
from ..game import bestiary as B
from ..game import engine as E
from ..game.content import EVENT_TYPES, ZONES
from ..ui import bar, card, kb, mention, money

router = Router(name="world")
GROUP = F.chat.type.in_({"group", "supergroup"})
router.message.filter(GROUP)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def boss_kind(row) -> B.BossKind:
    """The bestiary entry for a stored boss, tolerant of old rows."""
    try:
        return B.BY_KEY.get(row["kind"]) or B.BY_KEY["sector9"]
    except (KeyError, IndexError, TypeError):
        return B.BY_KEY["sector9"]


def boss_state(row) -> dict:
    try:
        return json.loads(row["state"]) or {}
    except (KeyError, IndexError, TypeError, ValueError):
        return {}


async def send_portrait(bot, chat_id: int, kind: B.BossKind, caption: str,
                        markup=None) -> int | None:
    """Send the boss's own portrait, falling back to text if it is missing."""
    path = os.path.join(ROOT, kind.art)
    try:
        if os.path.exists(path):
            msg = await bot.send_photo(chat_id, FSInputFile(path),
                                       caption=caption, reply_markup=markup)
            return msg.message_id
    except Exception:  # noqa: BLE001
        pass
    try:
        msg = await bot.send_message(chat_id, caption, reply_markup=markup)
        return msg.message_id
    except Exception:  # noqa: BLE001
        return None


@router.message(Command("world"))
async def world(message: Message) -> None:
    threat = int(await db.world_get("threat", 10))
    cure = int(await db.world_get("cure_progress", 0))
    stab = int(await db.world_get("vcorp_stability", 100))
    infected = await db.scalar("SELECT COUNT(*) FROM players WHERE infection>=20")
    total = await db.scalar("SELECT COUNT(*) FROM players")
    ev = await db.fetchone("SELECT * FROM events WHERE status='active' ORDER BY id DESC LIMIT 1")
    lines = [
        f"☣️ سطح تهدید <code>{bar(threat, 100)}</code> {threat}٪",
        f"🔬 پیشرفت درمان <code>{bar(cure, 100)}</code> {cure}٪",
        f"🏢 ثبات V-CORP <code>{bar(stab, 100)}</code> {stab}٪",
        f"👥 جمعیت: {total} · آلوده: {infected}",
    ]
    if ev:
        lines += ["", f"<b>رویداد فعال:</b> {ev['title']}", f"<i>{ev['body']}</i>"]
    await message.reply(card("🌎 <b>وضعیت جهان</b>", lines,
                             "هر اقدام گروه این اعداد را جابه‌جا می‌کند."),
                        reply_markup=kb([[("☣️ رویداد", "ui:event"), ("👹 باس", "ui:boss")]]))


@router.callback_query(F.data == "ui:world")
async def cb_world(cq: CallbackQuery) -> None:
    threat = int(await db.world_get("threat", 10))
    cure = int(await db.world_get("cure_progress", 0))
    await cq.answer(f"تهدید {threat}% · درمان {cure}%", show_alert=True)


async def spawn_event(bot: Bot, chat_id: int, code: str | None = None) -> dict:
    code = code or random.choice(list(EVENT_TYPES))
    icon, title, tmpl = EVENT_TYPES[code]
    zone = random.choice(ZONES)
    body = tmpl.format(zone=zone, a="V-CORP", b="U.B.C.")
    cur = await db.execute(
        "INSERT INTO events(code,title,body,chat_id,status,created_at) VALUES(?,?,?,?,?,?)",
        (code, f"{icon} {title}", body, chat_id, "active", E.NOW()))
    threat = int(await db.world_get("threat", 10))
    if code in ("outbreak", "escape", "globalmut"):
        await db.world_set("threat", min(100, threat + random.randint(5, 15)))
    if code == "cure":
        await db.world_set("threat", max(0, threat - 12))
        await db.execute("UPDATE players SET infection=MAX(0,infection-8) WHERE infection>0")
        await E.resync_stages()
    if code == "globalmut":
        await db.execute("UPDATE players SET infection=MIN(100,infection+7) "
                         "WHERE infection>0")
        await E.resync_stages()
    if code == "collapse":
        stab = int(await db.world_get("vcorp_stability", 100))
        await db.world_set("vcorp_stability", max(0, stab - 20))
    await db.log("event", f"{title} — {body}", None, chat_id)
    return {"id": cur.lastrowid, "icon": icon, "title": title, "body": body, "code": code}


@router.message(Command("event"))
async def event_cmd(message: Message, bot: Bot) -> None:
    ev = await db.fetchone(
        "SELECT * FROM events WHERE status='active' ORDER BY id DESC LIMIT 1")
    if not ev:
        e = await spawn_event(bot, message.chat.id)
        return await message.answer(card(f"{e['icon']} <b>{e['title']}</b>", [
            e["body"], "", "واکنش گروه تعیین می‌کند این چطور تمام شود."],
            "اقدام: /respond"))
    await message.reply(card(ev["title"], [ev["body"]], "واکنش: /respond"))


@router.callback_query(F.data == "ui:event")
async def cb_event(cq: CallbackQuery) -> None:
    ev = await db.fetchone(
        "SELECT * FROM events WHERE status='active' ORDER BY id DESC LIMIT 1")
    await cq.answer(f"{ev['title']}\n{ev['body']}" if ev else "رویداد فعالی نیست",
                    show_alert=True)


@router.message(Command("respond"))
async def respond(message: Message, bot: Bot) -> None:
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    ev = await db.fetchone(
        "SELECT * FROM events WHERE status='active' ORDER BY id DESC LIMIT 1")
    if not ev:
        return await message.reply("🌎 رویداد فعالی نیست. <code>/event</code>")
    left = await E.cooldown_left(p["user_id"], f"ev:{ev['id']}")
    if left:
        return await message.reply(f"⏳ در این رویداد شرکت کرده‌ای — {E.fmt_time(left)}")
    await E.set_cooldown(p["user_id"], f"ev:{ev['id']}", 1800)
    eff = await E.effective(p)
    score = eff["attack"] + eff["intellect"] + random.randint(1, 50)
    lines = [f"{ev['title']} — {ev['body']}", ""]
    if score >= 70:
        reward = random.randint(1200, 3500)
        await E.add(p["user_id"], money=reward)
        await E.grant_xp(p["user_id"], 80)
        threat = int(await db.world_get("threat", 10))
        await db.world_set("threat", max(0, threat - 3))
        lines.append(f"✅ مداخله موفق — 💵 {money(reward)} · ☣️ تهدید جهانی -3")
        await E.rep_add(p["user_id"], "ubc", 5)
        lines.append("📊 شهرت U.B.C +5")
    else:
        dmg = random.randint(10, 28)
        hp, died = await E.damage_player(p["user_id"], dmg)
        inf = random.randint(2, 8)
        new, st, ch = await E.apply_infection(p["user_id"], inf)
        lines.append(f"❌ اوضاع بدتر شد — ❤️ -{dmg} · ☣️ +{inf} → {new}٪")
        threat = int(await db.world_get("threat", 10))
        await db.world_set("threat", min(100, threat + 2))
        if ch:
            await anim.stage_animation(bot, message.chat.id, st)
            await notify.stage_up(bot, p["user_id"], st, new)
        if died:
            lines.append("💀 در میدان ماندی.")
    await message.reply(card("🚨 <b>واکنش به رویداد</b>", lines,
                             f"{p['name']}"))


# ── world boss ────────────────────────────────────────────────────────────
@router.message(Command("boss"))
async def boss(message: Message) -> None:
    b = await db.fetchone(
        "SELECT * FROM bosses WHERE chat_id=? AND status='active' ORDER BY id DESC LIMIT 1",
        (message.chat.id,))
    if not b:
        kind = B.pick()
        players = max(1, await db.scalar("SELECT COUNT(*) FROM players"))
        hp, atk, reward = B.scale(kind, players)
        cur = await db.execute(
            "INSERT INTO bosses(chat_id,name,hp,max_hp,attack,reward,status,"
            "created_at,kind,state) VALUES(?,?,?,?,?,?,'active',?,?,?)",
            (message.chat.id, f"{kind.icon} {kind.name}", hp, hp, atk, reward,
             E.NOW(), kind.key, json.dumps(dict(kind.init))))
        await db.log("boss", f"ظهور {kind.name}", None, message.chat.id)
        caption = card("👹 <b>تهدید بزرگ ظاهر شد</b>", [
            f"<b>{kind.icon} {kind.name}</b>",
            f"<i>{kind.tagline}</i>",
            "",
            f"❤️ <code>{bar(hp, hp)}</code> {hp}/{hp}",
            f"💰 جایزه کل: {money(reward)}",
            "",
            kind.mechanic_hint,
            "",
            "هیچ‌کس تنها این را نمی‌کشد.",
        ], "حمله: /hit")
        msg_id = await send_portrait(message.bot, message.chat.id, kind, caption,
                                     kb([[("⚔️ حمله", "boss:hit")]]))
        # remember the card so every hit edits this same live message
        await db.world_set(f"bosscard:{cur.lastrowid}",
                           {"chat": message.chat.id, "msg": msg_id,
                            "photo": True})
        return None
    kind = boss_kind(b)
    await message.reply(card("👹 <b>تهدید فعال</b>", [
        f"<b>{b['name']}</b>",
        f"❤️ <code>{bar(b['hp'], b['max_hp'])}</code> {b['hp']}/{b['max_hp']}",
        f"💰 جایزه کل: {money(b['reward'])}",
        "",
        kind.mechanic_hint,
    ], "حمله: /hit"), reply_markup=kb([[("⚔️ حمله", "boss:hit")]]))


@router.callback_query(F.data == "ui:boss")
async def cb_boss_info(cq: CallbackQuery) -> None:
    b = await db.fetchone(
        "SELECT * FROM bosses WHERE chat_id=? AND status='active'", (cq.message.chat.id,))
    await cq.answer(f"{b['name']} — {b['hp']}/{b['max_hp']}" if b
                    else "باس فعالی نیست. /boss", show_alert=True)


async def refresh_boss_card(bot, boss_id: int, extra: str | None = None) -> None:
    """Edit the original boss message in place so the group sees a live HP bar."""
    ref = await db.world_get(f"bosscard:{boss_id}")
    b = await db.fetchone("SELECT * FROM bosses WHERE id=?", (boss_id,))
    if not ref or not b:
        return
    dead = b["status"] != "active"
    lines = [
        f"<b>{b['name']}</b>",
        f"❤️ <code>{bar(b['hp'], b['max_hp'])}</code> {b['hp']}/{b['max_hp']}",
        f"💰 جایزه کل: {money(b['reward'])}",
    ]
    if extra:
        lines += ["", extra]
    kind = boss_kind(b)
    if not dead:
        lines += ["", kind.mechanic_hint]
    title = "☠️ <b>تهدید بزرگ — خنثی شد</b>" if dead else "👹 <b>تهدید بزرگ — فعال</b>"
    text = card(title, lines, "حمله: /hit" if not dead else "پرونده بسته شد.")
    markup = None if dead else kb([[("⚔️ حمله", "boss:hit")]])
    if not ref.get("msg"):
        return
    try:
        # boss cards are portraits, so the caption is what has to be edited
        if ref.get("photo"):
            await bot.edit_message_caption(
                chat_id=ref["chat"], message_id=ref["msg"],
                caption=text, reply_markup=markup)
        else:
            await bot.edit_message_text(
                chat_id=ref["chat"], message_id=ref["msg"],
                text=text, reply_markup=markup)
    except Exception:  # noqa: BLE001  (message too old / not modified)
        pass


async def _hit(chat_id: int, user, answer, bot=None) -> None:
    p = await E.ensure_player(user.id, user.full_name)
    b = await db.fetchone(
        "SELECT * FROM bosses WHERE chat_id=? AND status='active' ORDER BY id DESC LIMIT 1",
        (chat_id,))
    if not b:
        return await answer("👹 باس فعالی نیست. /boss")
    left = await E.cooldown_left(p["user_id"], "boss")
    if left:
        return await answer(f"⏳ نفس تازه کن — {E.fmt_time(left)}")
    await E.set_cooldown(p["user_id"], "boss", 420)
    eff = await E.effective(p)
    kind = boss_kind(b)
    state = boss_state(b)
    # 🎳 the strike animation scales the blow the whole group just watched
    pins = await anim.roll(bot, chat_id, anim.ROLL_STRIKE) if bot else 4
    raw = int((eff["attack"] * 2 + random.randint(0, 40)) * (0.5 + pins * 0.18))
    # the boss's own mechanic decides what that blow is actually worth
    blow = B.strike(kind, state, raw, pins, b["hp"], b["max_hp"])
    dmg = blow.damage
    hp = max(0, b["hp"] - dmg)
    if hp > 0:
        hp = B.post_hit(kind, state, hp, b["max_hp"])
    await db.execute("UPDATE bosses SET hp=?, state=? WHERE id=?",
                     (hp, json.dumps(state), b["id"]))
    await db.execute(
        "INSERT INTO boss_damage(boss_id,user_id,damage) VALUES(?,?,?) "
        "ON CONFLICT(boss_id,user_id) DO UPDATE SET damage=damage+?",
        (b["id"], p["user_id"], dmg, dmg))
    back = max(5, b["attack"] - eff["defense"] // 2 + random.randint(0, 15)
               + blow.recoil)
    php, died = await E.damage_player(p["user_id"], back)
    lines = [f"⚔️ {mention(p['user_id'], p['name'])} → <b>{dmg}</b> آسیب"
             + (" 🎳 <b>STRIKE!</b>" if pins >= 6 else ""),
             f"👹 <code>{bar(hp, b['max_hp'])}</code> {hp}/{b['max_hp']}",
             f"↩️ ضدحمله: <b>{back}</b>" + (" — 💀 کشته شدی" if died else f" (❤️ {php})")]
    if blow.note:
        lines.insert(1, blow.note)
    if hp <= 0:
        await db.execute("UPDATE bosses SET status='dead' WHERE id=?", (b["id"],))
        rows = await db.fetchall(
            "SELECT bd.user_id, bd.damage, p.name FROM boss_damage bd "
            "JOIN players p ON p.user_id=bd.user_id WHERE bd.boss_id=? "
            "ORDER BY bd.damage DESC", (b["id"],))
        total = sum(r["damage"] for r in rows) or 1
        lines += ["", f"🏆 <b>{b['name']} از پا درآمد!</b>", ""]
        for r in rows:
            share = int(b["reward"] * r["damage"] / total)
            await E.add(r["user_id"], money=share)
            await E.grant_xp(r["user_id"], 150)
            lines.append(f"• {r['name']} — {r['damage']} dmg → {money(share)}")
            if bot:
                await notify.loot(bot, r["user_id"], b["name"], r["damage"], share)
        threat = int(await db.world_get("threat", 10))
        await db.world_set("threat", max(0, threat - 10))
        await db.log("boss", f"{b['name']} کشته شد", None, chat_id)
        if bot:
            await anim.big_emoji(bot, chat_id, "🏆")
            # a fallen world boss is exactly the kind of rare, group-wide
            # moment the channel exists for
            if rows and channel.configured():
                chat = await db.fetchone(
                    "SELECT title FROM chats WHERE chat_id=?", (chat_id,))
                await channel.boss_defeated(
                    bot, b["name"], (chat["title"] if chat else "یک گروه"),
                    rows[0]["name"], rows[0]["damage"], b["reward"],
                    art=kind.art)
    await answer(card("👹 <b>تهدید بزرگ</b>", lines, "Cooldown 7 دقیقه"))
    if bot:
        await refresh_boss_card(bot, b["id"],
                                f"آخرین ضربه: {p['name']} — {dmg}")


@router.message(Command("hit"))
async def hit(message: Message, bot: Bot) -> None:
    async def ans(text):
        await message.reply(text)
    await _hit(message.chat.id, message.from_user, ans, bot)


@router.callback_query(F.data == "boss:hit")
async def cb_hit(cq: CallbackQuery, bot: Bot) -> None:
    async def ans(text):
        if len(text) < 190 and "\n" not in text:
            await cq.answer(text, show_alert=True)
        else:
            await cq.message.answer(text)
            await cq.answer()
    await _hit(cq.message.chat.id, cq.from_user, ans, bot)
