"""Shop, black market, player market, evidence trading, payments."""
from __future__ import annotations

import random

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..db import db
from ..game import engine as E
from ..game.content import BLACK_MARKET, ITEMS
from ..ui import card, kb, mention, money

router = Router(name="economy")
GROUP = F.chat.type.in_({"group", "supergroup"})
router.message.filter(GROUP)


async def shop_view(black: bool) -> tuple[str, list]:
    codes = BLACK_MARKET if black else [c for c in ITEMS if ITEMS[c]["legal"]]
    lines, btns = [], []
    for c in codes:
        it = ITEMS[c]
        pr = await E.price_of(c)
        trend = "📈" if pr > it["price"] else ("📉" if pr < it["price"] else "➖")
        lines.append(f"{it['icon']} <b>{it['name']}</b> — {money(pr)} {trend}")
        lines.append(f"   <i>{it['desc']}</i>")
        btns.append((f"{it['icon']} {money(pr)}", f"buy:{c}"))
    rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
    title = "🕳️ <b>بازار سیاه</b>" if black else "🛒 <b>فروشگاه</b>"
    foot = "خرید غیرقانونی Heat می‌آورد." if black else "قیمت‌ها با رفتار بازیکنان تغییر می‌کند."
    return card(title, lines, foot), rows


@router.message(Command("shop"))
async def shop(message: Message) -> None:
    await E.ensure_player(message.from_user.id, message.from_user.full_name)
    text, rows = await shop_view(False)
    await message.reply(text, reply_markup=kb(rows))


@router.message(Command("black"))
async def black(message: Message) -> None:
    await E.ensure_player(message.from_user.id, message.from_user.full_name)
    text, rows = await shop_view(True)
    await message.reply(text, reply_markup=kb(rows))


@router.callback_query(F.data.startswith("buy:"))
async def buy(cq: CallbackQuery) -> None:
    code = cq.data.split(":", 1)[1]
    if code not in ITEMS:
        return await cq.answer("آیتم ناشناخته", show_alert=True)
    p = await E.ensure_player(cq.from_user.id, cq.from_user.full_name)
    price = await E.price_of(code)
    if p["money"] < price:
        return await cq.answer(f"💸 پول کافی نداری ({money(price)})", show_alert=True)
    await E.add(p["user_id"], money=-price)
    await E.give_item(p["user_id"], code)
    await E.register_trade(code, +1)
    it = ITEMS[code]
    if not it["legal"]:
        await E.add(p["user_id"], heat=6)
        if random.randint(1, 100) <= 12:
            await db.log("blackmarket", f"معامله لو رفت: {p['name']} · {it['name']}",
                         p["user_id"], cq.message.chat.id)
            await cq.message.answer(card("🚨 <b>نشت اطلاعات</b>", [
                f"U.B.C معامله‌ی {mention(p['user_id'], p['name'])} را ثبت کرد.",
                f"{it['icon']} {it['name']} · Heat +6",
            ]))
    await cq.answer(f"✅ {it['name']} خریداری شد — {money(price)}", show_alert=True)
    text, rows = await shop_view(not it["legal"])
    try:
        await cq.message.edit_text(text, reply_markup=kb(rows))
    except Exception:
        pass


@router.message(Command("pay"))
async def pay(message: Message) -> None:
    parts = message.text.split()
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    target = None
    amount = 0
    if message.reply_to_message and len(parts) >= 2 and parts[1].isdigit():
        target = await E.get_player(message.reply_to_message.from_user.id)
        amount = int(parts[1])
    elif len(parts) >= 3 and parts[-1].isdigit():
        target = await E.find_player(" ".join(parts[1:-1]))
        amount = int(parts[-1])
    if not target or amount <= 0:
        return await message.reply("💵 <code>/pay &lt;نام&gt; &lt;مبلغ&gt;</code> یا ریپلای + مبلغ")
    if p["money"] < amount:
        return await message.reply("💸 موجودی کافی نیست.")
    await E.add(p["user_id"], money=-amount)
    await E.add(target["user_id"], money=amount)
    await db.log("pay", f"{p['name']} → {target['name']} : {money(amount)}", p["user_id"])
    await message.reply(card("💵 <b>انتقال وجه</b>", [
        f"{mention(p['user_id'], p['name'])} ➜ {mention(target['user_id'], target['name'])}",
        f"مبلغ: <b>{money(amount)}</b>",
    ], "پرداخت ثبت شد — دلیلش نه."))


# ── player-to-player market ───────────────────────────────────────────────
@router.message(Command("sell"))
async def sell(message: Message) -> None:
    parts = message.text.split()
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    if len(parts) < 3 or not parts[-1].isdigit():
        return await message.reply(
            "🏷️ <code>/sell &lt;کد_آیتم&gt; &lt;قیمت&gt;</code>\n"
            "یا <code>/sell ev &lt;شماره_مدرک&gt; &lt;قیمت&gt;</code>")
    price = int(parts[-1])
    if parts[1] == "ev":
        ev_id = int(parts[2])
        ev = await db.fetchone("SELECT * FROM evidence WHERE id=? AND owner_id=?",
                               (ev_id, p["user_id"]))
        if not ev:
            return await message.reply("❌ چنین مدرکی نداری.")
        await db.execute("INSERT INTO market(seller_id,kind,ref,qty,price,created_at)"
                         " VALUES(?,?,?,?,?,?)",
                         (p["user_id"], "evidence", str(ev_id), 1, price, E.NOW()))
        return await message.reply(f"🗂️ مدرک #{ev_id} برای {money(price)} عرضه شد. /market")
    code = parts[1]
    if code not in ITEMS or not await E.take_item(p["user_id"], code):
        return await message.reply("❌ این آیتم را نداری.")
    await db.execute("INSERT INTO market(seller_id,kind,ref,qty,price,created_at)"
                     " VALUES(?,?,?,?,?,?)",
                     (p["user_id"], "item", code, 1, price, E.NOW()))
    await E.register_trade(code, -1)
    await message.reply(f"{ITEMS[code]['icon']} {ITEMS[code]['name']} "
                        f"برای {money(price)} عرضه شد. /market")


@router.message(Command("market"))
async def market(message: Message) -> None:
    rows = await db.fetchall(
        "SELECT m.*, p.name FROM market m JOIN players p ON p.user_id=m.seller_id "
        "WHERE m.status='open' ORDER BY m.id DESC LIMIT 12")
    if not rows:
        return await message.reply("🏪 بازار خالی است. با <code>/sell</code> چیزی عرضه کن.")
    lines, btns = [], []
    for r in rows:
        if r["kind"] == "item":
            it = ITEMS.get(r["ref"], {"icon": "📦", "name": r["ref"]})
            label = f"{it['icon']} {it['name']}"
        else:
            label = "🗂️ مدرک محرمانه"
        lines.append(f"#{r['id']} {label} — <b>{money(r['price'])}</b> · فروشنده: {r['name']}")
        btns.append((f"#{r['id']} {money(r['price'])}", f"mk:{r['id']}"))
    await message.reply(card("🏪 <b>بازار بازیکنان</b>", lines,
                             "محتوای مدرک تا بعد از خرید نامعلوم است."),
                        reply_markup=kb([btns[i:i + 2] for i in range(0, len(btns), 2)]))


@router.callback_query(F.data.startswith("mk:"))
async def market_buy(cq: CallbackQuery) -> None:
    lid = int(cq.data.split(":", 1)[1])
    p = await E.ensure_player(cq.from_user.id, cq.from_user.full_name)
    r = await db.fetchone("SELECT * FROM market WHERE id=? AND status='open'", (lid,))
    if not r:
        return await cq.answer("این عرضه دیگر فعال نیست", show_alert=True)
    if r["seller_id"] == p["user_id"]:
        return await cq.answer("این عرضه خودت است", show_alert=True)
    if p["money"] < r["price"]:
        return await cq.answer("💸 پول کافی نداری", show_alert=True)
    await E.add(p["user_id"], money=-r["price"])
    await E.add(r["seller_id"], money=r["price"])
    await db.execute("UPDATE market SET status='sold' WHERE id=?", (lid,))
    if r["kind"] == "item":
        await E.give_item(p["user_id"], r["ref"])
        note = ITEMS.get(r["ref"], {}).get("name", r["ref"])
    else:
        await db.execute("UPDATE evidence SET owner_id=? WHERE id=?", (p["user_id"], r["ref"]))
        ev = await db.fetchone("SELECT body FROM evidence WHERE id=?", (r["ref"],))
        note = f"مدرک: {ev['body'] if ev else '—'}"
    await db.log("market", f"{p['name']} خرید #{lid} به {money(r['price'])}", p["user_id"])
    await cq.answer(f"✅ خریداری شد\n{note}", show_alert=True)


# ── evidence ──────────────────────────────────────────────────────────────
@router.message(Command("evidence"))
async def evidence(message: Message) -> None:
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    rows = await db.fetchall(
        "SELECT * FROM evidence WHERE owner_id=? ORDER BY value DESC LIMIT 10",
        (p["user_id"],))
    if not rows:
        return await message.reply("🗂️ مدرکی نداری. با <code>/scavenge</code> یا 🧠 نخ ذهنی پیدا کن.")
    lines = [f"#{r['id']} · <b>{money(r['value'])}</b>\n   <i>{r['body']}</i>" for r in rows]
    await message.reply(card("🗂️ <b>پرونده اطلاعات</b>", lines,
                             "فروش: /sell ev <شماره> <قیمت>"))
