"""THE HOLLOW — group PvP: challenges, the live duel card, ranking."""
from __future__ import annotations

import asyncio
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .. import anim, notify
from ..db import db
from ..game import duel as D
from ..game import engine as E
from ..ui import bar, card, kb, mention, money

router = Router(name="pvp")
GROUP = F.chat.type.in_({"group", "supergroup"})
router.message.filter(GROUP)

# pending challenges: (chat_id, target_id) -> dict
PENDING: dict[tuple[int, int], dict] = {}
CHALLENGE_TTL = 120


def rank_of(elo: int) -> tuple[str, str]:
    for floor, icon, name in (
        (1600, "👑", "افسانه گودال"),
        (1400, "🩸", "خون‌ریز"),
        (1250, "⚔️", "مبارز رینگ"),
        (1100, "🔪", "چاقوکش"),
        (950, "🥊", "تازه‌وارد"),
    ):
        if elo >= floor:
            return icon, name
    return "🐀", "طعمه"


def duel_card(d: D.Duel, note: str = "") -> str:
    a, b = d.a, d.b
    waiting = []
    if a.move is None:
        waiting.append(a.name)
    if b.move is None:
        waiting.append(b.name)
    left = max(0, int(d.deadline - time.time()))
    lines = [
        f"🩸 <b>{a.name}</b>",
        f"❤️ <code>{bar(a.hp, a.max_hp)}</code> {a.hp}/{a.max_hp}"
        f"  ⚡{a.adrenaline}  👁{a.poise}",
        "",
        f"🩸 <b>{b.name}</b>",
        f"❤️ <code>{bar(b.hp, b.max_hp)}</code> {b.hp}/{b.max_hp}"
        f"  ⚡{b.adrenaline}  👁{b.poise}",
    ]
    if d.log:
        lines += ["", "<b>راند قبل</b>"] + d.log[-4:]
    if note:
        lines += ["", note]
    if not d.finished:
        lines += ["", f"⏳ راند <b>{d.round}</b>/{D.MAX_ROUNDS} · {left} ثانیه"]
        if waiting:
            lines.append("در انتظار: " + " و ".join(f"<b>{w}</b>" for w in waiting))
    foot = (f"شرط: {money(d.stake)} از هر طرف" if d.stake
            else "بدون شرط — فقط آبرو و Elo")
    return card("⚔️ <b>THE HOLLOW — گودال</b>", lines, foot)


def move_kb() -> object:
    return kb([
        [("⚔️ ضربه", "d:strike"), ("🛡️ گارد", "d:guard")],
        [("🩸 توحش", "d:feral"), ("👁️ خوانش", "d:read")],
        [("📖 حرکت‌ها چه می‌کنند؟", "d:help")],
    ])


@router.message(Command("duel"))
async def challenge(message: Message, bot: Bot) -> None:
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    if not message.reply_to_message or message.reply_to_message.from_user.is_bot:
        return await message.reply(
            "⚔️ روی پیام حریف ریپلای کن: <code>/duel</code> یا <code>/duel 5000</code>\n"
            "<i>گودال جای حرف نیست.</i>")
    tgt_user = message.reply_to_message.from_user
    if tgt_user.id == p["user_id"]:
        return await message.reply("🤨 با خودت؟ نه.")
    t = await E.get_player(tgt_user.id)
    if not t:
        return await message.reply("❓ حریف هنوز وارد جهان نشده — <code>/start</code>")

    if D.duel_for_user(p["user_id"]) or D.duel_for_user(t["user_id"]):
        return await message.reply("⚔️ یکی از شما همین حالا در گودال است.")
    if D.duel_of(message.chat.id):
        return await message.reply("⏳ یک دوئل دیگر در این گروه جریان دارد.")

    parts = message.text.split()
    stake = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    if stake:
        if p["money"] < stake:
            return await message.reply("💸 پول کافی برای این شرط نداری.")
        if t["money"] < stake:
            return await message.reply(f"💸 <b>{t['name']}</b> توان این شرط را ندارد.")

    key = (message.chat.id, t["user_id"])
    PENDING[key] = {"from": p["user_id"], "stake": stake, "at": time.time(),
                    "name": p["name"]}
    ei, en = rank_of(p["elo"])
    ti, tn = rank_of(t["elo"])
    await message.answer(card("🩸 <b>دعوت به گودال</b>", [
        f"{mention(p['user_id'], p['name'])} {ei} <i>{en}</i> ({p['elo']})",
        "⚔️",
        f"{mention(t['user_id'], t['name'])} {ti} <i>{tn}</i> ({t['elo']})",
        "",
        f"💰 شرط: <b>{money(stake)}</b> از هر طرف" if stake else "بدون شرط.",
    ], f"{t['name']} باید ظرف {CHALLENGE_TTL} ثانیه بپذیرد."),
        reply_markup=kb([[("✅ می‌پذیرم", f"dc:ok:{t['user_id']}"),
                          ("🚪 فرار", f"dc:no:{t['user_id']}")]]))


@router.callback_query(F.data.startswith("dc:"))
async def challenge_answer(cq: CallbackQuery, bot: Bot) -> None:
    _, action, tid = cq.data.split(":")
    tid = int(tid)
    if cq.from_user.id != tid:
        return await cq.answer("این دعوت برای تو نیست.", show_alert=True)
    key = (cq.message.chat.id, tid)
    pend = PENDING.get(key)
    if not pend:
        return await cq.answer("این دعوت منقضی شده.", show_alert=True)
    if time.time() - pend["at"] > CHALLENGE_TTL:
        PENDING.pop(key, None)
        return await cq.answer("زمان دعوت تمام شد.", show_alert=True)

    if action == "no":
        PENDING.pop(key, None)
        await E.add(tid, heat=2)
        await cq.message.edit_text(card("🚪 <b>فرار از گودال</b>", [
            f"<b>{cq.from_user.full_name}</b> دعوت "
            f"<b>{pend['name']}</b> را رد کرد.",
            "گودال فراموش نمی‌کند.",
        ]))
        return await cq.answer()

    a = await E.get_player(pend["from"])
    b = await E.get_player(tid)
    if not a or not b:
        PENDING.pop(key, None)
        return await cq.answer("بازیکن یافت نشد.", show_alert=True)
    stake = pend["stake"]
    if stake and (a["money"] < stake or b["money"] < stake):
        PENDING.pop(key, None)
        return await cq.answer("یکی از طرفین دیگر توان شرط را ندارد.", show_alert=True)
    if D.duel_of(cq.message.chat.id):
        return await cq.answer("یک دوئل دیگر جریان دارد.", show_alert=True)

    PENDING.pop(key, None)
    if stake:
        await E.add(a["user_id"], money=-stake)
        await E.add(b["user_id"], money=-stake)

    d = D.Duel(chat_id=cq.message.chat.id,
               a=await D.make_fighter(a), b=await D.make_fighter(b), stake=stake)
    D.register(d)
    await anim.big_emoji(bot, d.chat_id, "🩸")
    sent = await cq.message.answer(duel_card(d, "🔔 <b>زنگ آغاز!</b> حرکتت را مخفیانه انتخاب کن."),
                                   reply_markup=move_kb())
    d.message_id = sent.message_id
    d._task = asyncio.create_task(turn_timer(bot, d, d.round))
    await cq.answer("وارد گودال شدی.")


async def turn_timer(bot: Bot, d: D.Duel, round_no: int) -> None:
    """If someone stalls, auto-play GUARD so the ring never freezes."""
    try:
        await asyncio.sleep(max(1, int(d.deadline - time.time())))
        if d.finished or d.round != round_no:
            return
        stalled = []
        for f in (d.a, d.b):
            if f.move is None:
                f.move = "guard"
                stalled.append(f.name)
        if stalled:
            await advance(bot, d, "⏱ " + " و ".join(stalled) + " دیر کرد — گارد خودکار.")
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("d:"))
async def pick_move(cq: CallbackQuery, bot: Bot) -> None:
    move = cq.data.split(":", 1)[1]
    if move == "help":
        return await cq.answer(
            "⚔️ ضربه: پایدار، گارد را می‌شکند (۲⚡)\n"
            "🛡️ گارد: جذب + شارژ آدرنالین، توحش را برمی‌گرداند (+۲⚡)\n"
            "🩸 توحش: سنگین‌ترین آسیب، ولی آلودگی می‌آورد (۳⚡)\n"
            "👁️ خوانش: توحش را کامل خنثی می‌کند (۱⚡)\n\n"
            "تکرار یک حرکت آن را لو می‌دهد و ضعیفش می‌کند.",
            show_alert=True)
    d = D.duel_of(cq.message.chat.id)
    if not d or d.finished:
        return await cq.answer("دوئلی جریان ندارد.", show_alert=True)
    me = d.side(cq.from_user.id)
    if not me:
        return await cq.answer("تو در این دوئل نیستی. تماشا کن.", show_alert=True)
    if me.move is not None:
        return await cq.answer("حرکتت ثبت شده. منتظر حریف بمان.", show_alert=True)
    if move not in D.MOVES:
        return await cq.answer("حرکت نامعتبر.", show_alert=True)
    icon, name, desc = D.MOVES[move]
    me.move = move
    await cq.answer(f"{icon} {name} ثبت شد — مخفی می‌ماند.", show_alert=False)
    if d.both_ready():
        await advance(bot, d)
    else:
        try:
            await bot.edit_message_text(
                chat_id=d.chat_id, message_id=d.message_id,
                text=duel_card(d, "🤫 یک حرکت ثبت شد..."), reply_markup=move_kb())
        except Exception:  # noqa: BLE001
            pass


async def advance(bot: Bot, d: D.Duel, note: str = "") -> None:
    if d.finished:
        return
    if d._task:
        d._task.cancel()
    d.log = D.resolve_round(d)
    d.round += 1
    ended = D.check_end(d)
    if not ended:
        d.deadline = time.time() + D.TURN_SECONDS
        try:
            await bot.edit_message_text(
                chat_id=d.chat_id, message_id=d.message_id,
                text=duel_card(d, note), reply_markup=move_kb())
        except Exception:  # noqa: BLE001
            pass
        d._task = asyncio.create_task(turn_timer(bot, d, d.round))
        return

    res = await D.settle(d)
    try:
        await bot.edit_message_text(chat_id=d.chat_id, message_id=d.message_id,
                                    text=duel_card(d, "🔚 <b>پایان.</b>"),
                                    reply_markup=None)
    except Exception:  # noqa: BLE001
        pass

    lines = list(d.log)
    if d.winner is None:
        lines += ["", f"🤝 <b>{d.reason}</b>", "شرط‌ها برگشت."]
    else:
        w = res.get("winner_name", "?")
        l = res.get("loser_name", "?")
        lines += ["", f"🏆 <b>{w}</b> برنده شد — <i>{d.reason}</i>"]
        if res.get("pot"):
            lines.append(f"💰 {money(res['pot'])} برداشت")
        lines.append(f"📈 Elo <b>+{res.get('delta', 0)}</b> · "
                     f"<b>{l}</b> −{res.get('delta', 0)}")
        if res.get("streak", 0) >= 3:
            lines.append(f"🔥 <b>{res['streak']} برد پیاپی!</b>")
        await anim.big_emoji(bot, d.chat_id, "🏆")
    for tag in ("a", "b"):
        if res.get(f"{tag}_stage_changed"):
            f = d.a if tag == "a" else d.b
            lines.append(f"🧬 <b>{f.name}</b> پیشروی VX-13 → {res[f'{tag}_stage']}")
            await notify.stage_up(bot, f.user_id, res[f"{tag}_stage"],
                                  res[f"{tag}_inf"])
    await bot.send_message(d.chat_id, card("🩸 <b>نتیجه گودال</b>", lines,
                                           "رینگ آزاد شد. /duel"))


@router.message(Command("forfeit"))
async def forfeit(message: Message, bot: Bot) -> None:
    d = D.duel_of(message.chat.id)
    if not d or not d.side(message.from_user.id):
        return await message.reply("در دوئلی نیستی.")
    me = d.side(message.from_user.id)
    me.hp = 0
    await advance(bot, d, f"🏳️ <b>{me.name}</b> تسلیم شد.")


@router.message(Command("arena", "pvptop"))
async def arena(message: Message) -> None:
    rows = await db.fetchall(
        "SELECT name,elo,duel_wins,duel_losses,streak FROM players "
        "WHERE banned=0 AND (duel_wins>0 OR duel_losses>0) "
        "ORDER BY elo DESC LIMIT 10")
    if not rows:
        return await message.reply(card("⚔️ <b>گودال</b>", [
            "هنوز کسی وارد رینگ نشده.",
            "روی حریف ریپلای کن و <code>/duel</code> بزن.",
        ]))
    medals = ["🥇", "🥈", "🥉"] + ["▫️"] * 7
    lines = []
    for i, r in enumerate(rows):
        icon, name = rank_of(r["elo"])
        s = f" 🔥{r['streak']}" if r["streak"] >= 3 else ""
        lines.append(f"{medals[i]} {icon} <b>{r['name']}</b> — {r['elo']} "
                     f"· {r['duel_wins']}W/{r['duel_losses']}L{s}")
    await message.reply(card("⚔️ <b>رتبه‌بندی گودال</b>", lines,
                             "Elo فقط با دوئل واقعی تغییر می‌کند."))
