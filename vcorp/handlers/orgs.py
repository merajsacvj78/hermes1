"""Organizations: join, found, manage, fund, research, war."""
from __future__ import annotations

import random
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..db import db
from ..game import engine as E
from ..game.content import ORG_RANKS
from ..ui import card, kb, mention, money

router = Router(name="orgs")
GROUP = F.chat.type.in_({"group", "supergroup"})
router.message.filter(GROUP)

FOUND_COST = 25_000


@router.message(Command("orgs"))
async def orgs(message: Message) -> None:
    rows = await db.fetchall("SELECT * FROM orgs ORDER BY power DESC, funds DESC LIMIT 15")
    lines, btns = [], []
    for o in rows:
        members = await db.scalar("SELECT COUNT(*) FROM players WHERE org_id=?", (o["org_id"],))
        lines.append(f"{o['icon']} <b>{o['name']}</b> · 👥{members} · ⚔️{o['power']} "
                     f"· 🔬{o['research']} · 💵{money(o['funds'])}")
        btns.append((f"{o['icon']} {o['name']}", f"org:join:{o['org_id']}"))
    await message.reply(
        card("🏢 <b>سازمان‌ها</b>", lines,
             f"ساخت سازمان: /found <نام> ({money(FOUND_COST)})"),
        reply_markup=kb([btns[i:i + 2] for i in range(0, len(btns), 2)]))


@router.callback_query(F.data.startswith("org:join:"))
async def join_cb(cq: CallbackQuery) -> None:
    oid = int(cq.data.rsplit(":", 1)[1])
    p = await E.ensure_player(cq.from_user.id, cq.from_user.full_name)
    o = await db.fetchone("SELECT * FROM orgs WHERE org_id=?", (oid,))
    if not o:
        return await cq.answer("سازمان یافت نشد", show_alert=True)
    if p["org_id"] == oid:
        return await cq.answer("عضو همین سازمانی", show_alert=True)
    rep = (await E.rep_all(p["user_id"])).get(o["code"], 0)
    if rep <= -20:
        return await cq.answer("🚫 شهرت تو نزد این سازمان منفی است.", show_alert=True)
    path = p["path"]
    if o["code"] == "ubc" and path in ("survivor", "infected"):
        path = "ubc"
    elif o["code"] == "vcorp" and path == "survivor":
        path = "vhero"
    elif o["code"] == "umbra" and path == "survivor":
        path = "double"
    await E.update(p["user_id"], org_id=oid, org_rank="recruit", path=path)
    await db.log("org", f"{p['name']} به {o['name']} پیوست", p["user_id"], cq.message.chat.id)
    await cq.answer(f"✅ به {o['name']} پیوستی", show_alert=True)
    await cq.message.answer(card("🏢 <b>استخدام</b>", [
        f"{mention(p['user_id'], p['name'])} به {o['icon']} <b>{o['name']}</b> پیوست.",
        "رتبه: recruit",
    ], "با مأموریت و شهرت ارتقا بگیر: /org"))


@router.message(Command("join"))
async def join(message: Message) -> None:
    await orgs(message)


@router.message(Command("found"))
async def found(message: Message) -> None:
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply(f"🏢 <code>/found &lt;نام سازمان&gt;</code> — {money(FOUND_COST)}")
    name = parts[1].strip()[:32]
    if p["money"] < FOUND_COST:
        return await message.reply(f"💸 برای تأسیس {money(FOUND_COST)} لازم است.")
    code = re.sub(r"[^a-z0-9]+", "", name.lower()) or f"org{p['user_id'] % 9999}"
    if await db.fetchone("SELECT 1 FROM orgs WHERE code=?", (code,)):
        code = f"{code}{random.randint(10, 99)}"
    await E.add(p["user_id"], money=-FOUND_COST)
    cur = await db.execute(
        "INSERT INTO orgs(code,name,icon,leader_id,funds,research,power,founded_at,system)"
        " VALUES(?,?,?,?,?,?,?,?,0)",
        (code, name, "🏴", p["user_id"], FOUND_COST // 2, 0, 10, E.NOW()))
    oid = cur.lastrowid
    await E.update(p["user_id"], org_id=oid, org_rank="leader", path="leader")
    await db.log("org", f"{p['name']} سازمان {name} را تأسیس کرد", p["user_id"], message.chat.id)
    await message.answer(card("🏴 <b>سازمان جدید</b>", [
        f"<b>{name}</b> تأسیس شد. (کد: <code>{code}</code>)",
        f"👑 رهبر: {mention(p['user_id'], p['name'])}",
        f"💵 خزانه اولیه: {money(FOUND_COST // 2)}",
    ], "اعضا با /orgs می‌توانند بپیوندند."))


@router.message(Command("org"))
async def org_panel(message: Message) -> None:
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    if not p["org_id"]:
        return await message.reply("🏢 عضو سازمانی نیستی. <code>/orgs</code>")
    o = await db.fetchone("SELECT * FROM orgs WHERE org_id=?", (p["org_id"],))
    members = await db.fetchall(
        "SELECT name,org_rank,level FROM players WHERE org_id=? "
        "ORDER BY level DESC LIMIT 10", (p["org_id"],))
    rep = (await E.rep_all(p["user_id"])).get(o["code"], 0)
    lines = [
        f"{o['icon']} <b>{o['name']}</b>",
        f"💵 خزانه {money(o['funds'])} · ⚔️ قدرت {o['power']} · 🔬 تحقیق {o['research']}",
        f"🎖 رتبه تو: <b>{p['org_rank']}</b> · 📊 شهرت {rep:+d}",
        "",
        "<b>اعضا</b>",
    ] + [f"• {m['name']} — {m['org_rank']} (Lv.{m['level']})" for m in members]
    rows = [[("💵 کمک مالی", "org:fund"), ("🔬 تحقیق", "org:research")],
            [("🎖 ارتقا", "org:promote")]]
    await message.reply(card("🏢 <b>مرکز فرماندهی</b>", lines,
                             "جنگ: /war <سازمان>"), reply_markup=kb(rows))


@router.callback_query(F.data == "org:fund")
async def fund(cq: CallbackQuery) -> None:
    p = await E.ensure_player(cq.from_user.id, cq.from_user.full_name)
    if not p["org_id"] or p["money"] < 1000:
        return await cq.answer("حداقل $1,000 و عضویت لازم است", show_alert=True)
    await E.add(p["user_id"], money=-1000)
    await db.execute("UPDATE orgs SET funds=funds+1000, power=power+1 WHERE org_id=?",
                     (p["org_id"],))
    o = await db.fetchone("SELECT code FROM orgs WHERE org_id=?", (p["org_id"],))
    await E.rep_add(p["user_id"], o["code"], 3)
    await cq.answer("💵 $1,000 به خزانه واریز شد · شهرت +3", show_alert=True)


@router.callback_query(F.data == "org:research")
async def research(cq: CallbackQuery) -> None:
    p = await E.ensure_player(cq.from_user.id, cq.from_user.full_name)
    if not p["org_id"]:
        return await cq.answer("عضو سازمان نیستی", show_alert=True)
    if not await E.take_item(p["user_id"], "vsample"):
        return await cq.answer("🧫 نمونه VX-13 لازم است", show_alert=True)
    gain = random.randint(3, 9)
    await db.execute("UPDATE orgs SET research=research+? WHERE org_id=?",
                     (gain, p["org_id"]))
    cp = int(await db.world_get("cure_progress", 0)) + gain // 2
    await db.world_set("cure_progress", cp)
    o = await db.fetchone("SELECT code FROM orgs WHERE org_id=?", (p["org_id"],))
    await E.rep_add(p["user_id"], o["code"], 4)
    await E.grant_xp(p["user_id"], 50)
    await cq.answer(f"🔬 تحقیق +{gain} · پیشرفت درمان جهانی {cp}%", show_alert=True)


@router.callback_query(F.data == "org:promote")
async def promote(cq: CallbackQuery) -> None:
    p = await E.ensure_player(cq.from_user.id, cq.from_user.full_name)
    if not p["org_id"]:
        return await cq.answer("عضو سازمان نیستی", show_alert=True)
    o = await db.fetchone("SELECT code FROM orgs WHERE org_id=?", (p["org_id"],))
    rep = (await E.rep_all(p["user_id"])).get(o["code"], 0)
    idx = ORG_RANKS.index(p["org_rank"]) if p["org_rank"] in ORG_RANKS else 0
    need = (idx + 1) * 25
    if idx >= len(ORG_RANKS) - 2:
        return await cq.answer("بالاترین رتبه قابل ارتقا را داری", show_alert=True)
    if rep < need:
        return await cq.answer(f"📊 شهرت {rep}/{need} — کافی نیست", show_alert=True)
    await E.update(p["user_id"], org_rank=ORG_RANKS[idx + 1])
    await cq.answer(f"🎖 ارتقا به {ORG_RANKS[idx + 1]}", show_alert=True)


@router.message(Command("war"))
async def war(message: Message) -> None:
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    if not p["org_id"] or p["org_rank"] not in ("director", "leader"):
        return await message.reply("⚔️ فقط director یا leader می‌تواند اعلام جنگ کند.")
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("⚔️ <code>/war &lt;نام سازمان&gt;</code>")
    left = await E.cooldown_left(p["user_id"], "war")
    if left:
        return await message.reply(f"⏳ نیروها بازسازی می‌شوند — {E.fmt_time(left)}")
    tgt = await db.fetchone(
        "SELECT * FROM orgs WHERE lower(name)=lower(?) OR code=lower(?)",
        (parts[1].strip(), parts[1].strip()))
    if not tgt or tgt["org_id"] == p["org_id"]:
        return await message.reply("❌ سازمان هدف نامعتبر است.")
    mine = await db.fetchone("SELECT * FROM orgs WHERE org_id=?", (p["org_id"],))
    await E.set_cooldown(p["user_id"], "war", 3600)
    a = mine["power"] + random.randint(1, 40)
    b = tgt["power"] + random.randint(1, 40)
    loot = min(tgt["funds"], 5000 + mine["power"] * 100)
    if a >= b:
        await db.execute("UPDATE orgs SET funds=funds+?, power=power+3 WHERE org_id=?",
                         (loot, mine["org_id"]))
        await db.execute("UPDATE orgs SET funds=funds-?, power=MAX(1,power-4) WHERE org_id=?",
                         (loot, tgt["org_id"]))
        res = [f"🏆 <b>{mine['name']}</b> پیروز شد.",
               f"💵 غنیمت: {money(loot)} · ⚔️ قدرت +3"]
    else:
        await db.execute("UPDATE orgs SET power=MAX(1,power-4) WHERE org_id=?",
                         (mine["org_id"],))
        await db.execute("UPDATE orgs SET power=power+3 WHERE org_id=?", (tgt["org_id"],))
        res = [f"💀 <b>{mine['name']}</b> شکست خورد.", "⚔️ قدرت -4"]
    await db.execute(
        "INSERT INTO events(code,title,body,chat_id,status,created_at) VALUES(?,?,?,?,?,?)",
        ("orgwar", "⚔️ جنگ سازمان‌ها",
         f"{mine['name']} vs {tgt['name']}", message.chat.id, "resolved", E.NOW()))
    await db.log("war", f"{mine['name']} vs {tgt['name']}", p["user_id"], message.chat.id)
    await message.answer(card("⚔️ <b>جنگ سازمان‌ها</b>", [
        f"{mine['icon']} {mine['name']} ⚔️ {tgt['icon']} {tgt['name']}", "", *res,
    ], "خسارت واقعی است."))
