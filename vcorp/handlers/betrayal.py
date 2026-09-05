"""Secret contracts, wanted bounties, betrayal mechanics."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from ..db import db
from ..game import engine as E
from ..ui import card, mention, money

router = Router(name="betrayal")
GROUP = F.chat.type.in_({"group", "supergroup"})
router.message.filter(GROUP)


@router.message(Command("contract"))
async def contract(message: Message) -> None:
    parts = message.text.split()
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    target, amount = None, 0
    if message.reply_to_message and len(parts) >= 2 and parts[1].isdigit():
        target = await E.get_player(message.reply_to_message.from_user.id)
        amount = int(parts[1])
    elif len(parts) >= 3 and parts[-1].isdigit():
        target = await E.find_player(" ".join(parts[1:-1]))
        amount = int(parts[-1])
    if not target or amount < 500:
        return await message.reply(
            "🎯 <code>/contract &lt;نام&gt; &lt;مبلغ&gt;</code> (حداقل $500)\n"
            "<i>سفارش‌دهنده مخفی می‌ماند.</i>")
    if target["user_id"] == p["user_id"]:
        return await message.reply("🤨 قرارداد روی خودت؟ نه.")
    if p["money"] < amount:
        return await message.reply("💸 پول کافی برای ضمانت قرارداد نداری.")
    await E.add(p["user_id"], money=-amount)
    cur = await db.execute(
        "INSERT INTO contracts(issuer_id,target_id,reward,secret,status,chat_id,created_at)"
        " VALUES(?,?,?,1,'open',?,?)",
        (p["user_id"], target["user_id"], amount, message.chat.id, E.NOW()))
    cid = cur.lastrowid
    await db.log("contract", f"قرارداد #{cid} روی {target['name']} — {money(amount)}",
                 p["user_id"], message.chat.id)
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(card("🎯 <b>قرارداد مخفی</b>", [
        f"<b>شماره:</b> #{cid}",
        f"<b>هدف:</b> {mention(target['user_id'], target['name'])}",
        f"<b>پاداش:</b> {money(amount)}",
        "<b>سفارش‌دهنده:</b> ناشناس 🕵️",
        "",
        "هرکس هدف را از پا دربیاورد، پاداش را می‌گیرد.",
    ], "اعضای یک تیم هم می‌توانند مجری باشند."))


@router.message(Command("contracts"))
async def contracts(message: Message) -> None:
    rows = await db.fetchall(
        "SELECT c.*, p.name FROM contracts c JOIN players p ON p.user_id=c.target_id "
        "WHERE c.status='open' ORDER BY c.reward DESC LIMIT 12")
    if not rows:
        return await message.reply("🎯 قرارداد بازی وجود ندارد. <code>/contract</code>")
    lines = [f"#{r['id']} · هدف <b>{r['name']}</b> · پاداش <b>{money(r['reward'])}</b>"
             for r in rows]
    await message.reply(card("📂 <b>قراردادهای باز</b>", lines,
                             "هویت سفارش‌دهنده‌ها محرمانه است."))


@router.message(Command("wanted"))
async def wanted(message: Message) -> None:
    rows = await db.fetchall(
        "SELECT p.user_id, p.name, p.heat, p.kills, "
        "COALESCE((SELECT SUM(reward) FROM contracts c WHERE c.target_id=p.user_id "
        "AND c.status='open'),0) AS bounty "
        "FROM players p WHERE p.banned=0 "
        "ORDER BY bounty DESC, p.heat DESC LIMIT 10")
    lines = []
    for i, r in enumerate(rows, 1):
        if not r["bounty"] and not r["heat"]:
            continue
        lines.append(f"{i}. <b>{r['name']}</b> — 💰 {money(r['bounty'])} · "
                     f"🔥 Heat {r['heat']} · 💀 {r['kills']}")
    await message.reply(card("🚨 <b>فهرست تحت تعقیب</b>", lines or ["فعلاً همه پاک‌اند."],
                             "Heat بالا یعنی U.B.C دنبالت است."))


@router.message(Command("betray"))
async def betray(message: Message) -> None:
    """Sell out your organization for cash and reputation damage."""
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    if not p["org_id"]:
        return await message.reply("🗡️ عضو هیچ سازمانی نیستی که به آن خیانت کنی.")
    left = await E.cooldown_left(p["user_id"], "betray")
    if left:
        return await message.reply(f"⏳ بعد از خیانت قبلی زیر نظری — {E.fmt_time(left)}")
    org = await db.fetchone("SELECT * FROM orgs WHERE org_id=?", (p["org_id"],))
    payout = min(org["funds"], 3000 + p["level"] * 400)
    await db.execute("UPDATE orgs SET funds=funds-?, power=MAX(1,power-5) WHERE org_id=?",
                     (payout, org["org_id"]))
    await E.add(p["user_id"], money=payout, heat=10)
    await E.update(p["user_id"], path="traitor", org_id=None, org_rank="recruit")
    await E.rep_add(p["user_id"], org["code"], -30)
    await E.set_cooldown(p["user_id"], "betray", 7200)
    await db.execute(
        "INSERT INTO evidence(owner_id,about_id,kind,body,value,created_at)"
        " VALUES(?,?,?,?,?,?)",
        (p["user_id"], p["user_id"], "leak",
         f"اسناد داخلی {org['name']} — منبع: عضو سابق", payout, E.NOW()))
    await db.log("betray", f"{p['name']} به {org['name']} خیانت کرد", p["user_id"],
                 message.chat.id)
    await message.answer(card("🗡️ <b>خیانت</b>", [
        f"{mention(p['user_id'], p['name'])} اسناد <b>{org['name']}</b> را فروخت.",
        f"💵 دریافتی: <b>{money(payout)}</b> · 🔥 Heat +10",
        f"📉 شهرت {org['code'].upper()}: -30",
        "🗂️ یک مدرک قابل فروش به دستت رسید.",
    ], "مسیر تو حالا: 🗡️ خائن"))
