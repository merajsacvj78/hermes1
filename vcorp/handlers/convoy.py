"""THE CONVOY — cooperative escape run for the whole group.

Posts are chosen privately so nobody can free-ride on someone else's pick,
then the speed vote happens publicly on a live card the group watches.
"""
from __future__ import annotations

import asyncio
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .. import anim, channel, secret
from ..db import db
from ..game import convoy as C
from ..game import engine as E
from ..ui import bar, card, kb, money

router = Router(name="convoy")

RUNS: dict[int, C.Convoy] = {}
RIDING: dict[int, int] = {}           # user_id -> chat_id

ENTRY_FEE_MAX = 50_000


def run_of(chat_id: int) -> C.Convoy | None:
    return RUNS.get(chat_id)


def _register(g: C.Convoy) -> None:
    RUNS[g.chat_id] = g
    for uid in g.players:
        RIDING[uid] = g.chat_id


def _release(g: C.Convoy) -> None:
    RUNS.pop(g.chat_id, None)
    for uid in list(RIDING):
        if RIDING[uid] == g.chat_id:
            RIDING.pop(uid, None)


def _cancel(g: C.Convoy) -> None:
    task = getattr(g, "_task", None)
    if task is not None:
        try:
            task.cancel()
        except Exception:  # noqa: BLE001
            pass
        g._task = None


async def _refund(g: C.Convoy) -> None:
    if g.stake:
        for uid in g.players:
            await E.add(uid, money=g.stake)
        g.pot = 0


# ── cards ─────────────────────────────────────────────────────────────────
def vitals(g: C.Convoy) -> list[str]:
    return [
        f"🔩 بدنه   <code>{bar(g.hull, C.CAP)}</code> {g.hull}",
        f"⛽ سوخت  <code>{bar(g.fuel, C.CAP)}</code> {g.fuel}",
        f"🫀 روحیه  <code>{bar(g.morale, C.CAP)}</code> {g.morale}",
        f"🛞 مسافت <code>{bar(g.distance, C.DISTANCE_GOAL)}</code> "
        f"{min(g.distance, C.DISTANCE_GOAL)}/{C.DISTANCE_GOAL}",
    ]


def lobby_card(g: C.Convoy) -> str:
    left = max(0, int(g.deadline - time.time()))
    names = [f"{i}. {p.name}" for i, p in enumerate(g.players.values(), 1)]
    lines = [
        "سه کامیون، یک جاده، و منطقه‌ای که پشت سرتان بسته می‌شود.",
        "این‌بار کسی خائن نیست — یا همه می‌رسید، یا هیچ‌کس.",
        "",
        f"👥 <b>{len(g.players)}</b>/{C.MAX_PLAYERS} خدمه"
        f" (حداقل {C.MIN_PLAYERS})",
    ] + (names or ["هنوز کسی سوار نشده."])
    if g.stake:
        lines += ["", f"💵 سهم: <b>{money(g.stake)}</b> · صندوق: {money(g.pot)}"]
    lines += ["", f"⏳ {left} ثانیه تا حرکت"]
    return card("🚚 <b>کاروان</b>", lines,
                "پست‌ها در PV انتخاب می‌شود — ربات را استارت کرده باش.")


def station_card(g: C.Convoy) -> str:
    left = max(0, int(g.deadline - time.time()))
    have = C.staffing(g)
    picked = sum(1 for p in g.players.values() if p.station is not None)
    lines = [f"<b>مرحله {g.leg}</b> از {C.MAX_LEGS}", ""] + vitals(g)
    lines += ["", "🎒 همه در <b>چت خصوصی</b> پست خود را انتخاب می‌کنند.", ""]
    for st in C.Station:
        icon, label, _ = C.STATION_META[st]
        n = have[st]
        lines.append(f"{icon} {label} — {'🟩' * n if n else '▫️'}")
    lines += ["", f"✅ {picked}/{len(g.players)} انتخاب کرده‌اند · ⏳ {left} ثانیه"]
    return card("🚚 <b>کاروان</b>", lines,
                "خطر بعدی را فقط دیده‌بان می‌بیند.")


def speed_card(g: C.Convoy) -> str:
    left = max(0, int(g.deadline - time.time()))
    tally = C.speed_tally(g)
    hz = g.hazard
    lines = [f"<b>مرحله {g.leg}</b>", ""] + vitals(g) + [""]
    if g.scouted:
        lines += [f"🔭 دیده‌بان گزارش می‌دهد: <b>{hz.icon} {hz.title}</b>",
                  f"<i>{hz.body}</i>", ""]
    else:
        lines += ["🌫️ بدون دیده‌بان، جاده جلوتر دیده نمی‌شود.", ""]
    lines.append("چقدر فشار بیاوریم؟")
    for sp in C.Speed:
        icon, label, dist, burn, sev, drift = C.SPEED_META[sp]
        n = tally[sp]
        lines.append(f"{icon} <b>{label}</b> — {dist}km · سوخت {burn}"
                     + (f" · {'🟥' * n}" if n else ""))
    cast = sum(1 for p in g.players.values() if p.speed_vote is not None)
    lines += ["", f"🗳️ {cast}/{len(g.players)} رأی · ⏳ {left} ثانیه"]
    return card("🚚 <b>کاروان</b>", lines, "اکثریت تصمیم می‌گیرد.")


def station_kb(g: C.Convoy) -> object:
    rows = []
    items = list(C.Station)
    for i in range(0, len(items), 2):
        rows.append([(f"{C.STATION_META[s][0]} {C.STATION_META[s][1]}",
                      f"cv:s:{g.chat_id}:{s.value}") for s in items[i:i + 2]])
    return kb(rows)


def speed_kb() -> object:
    return kb([[(f"{C.SPEED_META[s][0]} {C.SPEED_META[s][1]}", f"cv:v:{s.value}")]
               for s in C.Speed])


# ── lobby ─────────────────────────────────────────────────────────────────
@router.message(Command("convoy"), F.chat.type.in_({"group", "supergroup"}))
async def open_run(message: Message, bot: Bot) -> None:
    host = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    if run_of(message.chat.id):
        return await message.reply("🚚 یک کاروان همین حالا در راه است.")
    parts = message.text.split()
    stake = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    stake = min(stake, ENTRY_FEE_MAX)
    if stake and host["money"] < stake:
        return await message.reply("💸 خودت هم باید سهم بگذاری.")

    g = C.Convoy(chat_id=message.chat.id, host_id=host["user_id"], stake=stake)
    g.add(host["user_id"], host["name"])
    if stake:
        await E.add(host["user_id"], money=-stake)
        g.pot = stake
    g.deadline = time.time() + C.LOBBY_SECONDS
    _register(g)
    await anim.big_emoji(bot, g.chat_id, "🚚")
    sent = await message.answer(lobby_card(g), reply_markup=kb([
        [("🎒 سوار می‌شوم", "cv:join"), ("🚶 پیاده می‌شوم", "cv:leave")],
        [("▶️ حرکت", "cv:go")],
    ]))
    g.message_id = sent.message_id
    g._task = asyncio.create_task(_lobby_timer(bot, g))


async def _lobby_timer(bot: Bot, g: C.Convoy) -> None:
    try:
        await asyncio.sleep(max(1, int(g.deadline - time.time())))
        if g.phase is C.Phase.LOBBY:
            await depart(bot, g)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "cv:join")
async def join(cq: CallbackQuery) -> None:
    g = run_of(cq.message.chat.id)
    if not g or g.phase is not C.Phase.LOBBY:
        return await cq.answer("کاروان دیگر منتظر نمی‌ماند.", show_alert=True)
    if cq.from_user.id in RIDING and RIDING[cq.from_user.id] != g.chat_id:
        return await cq.answer("تو سوار کاروان گروه دیگری هستی.", show_alert=True)
    p = await E.ensure_player(cq.from_user.id, cq.from_user.full_name)
    if g.stake and p["money"] < g.stake:
        return await cq.answer(f"💸 سهم {money(g.stake)} است.", show_alert=True)
    if not g.add(p["user_id"], p["name"]):
        return await cq.answer("قبلاً سواری یا ظرفیت پر است.", show_alert=True)
    if g.stake:
        await E.add(p["user_id"], money=-g.stake)
        g.pot += g.stake
    RIDING[p["user_id"]] = g.chat_id
    await cq.answer("سوار شدی.")
    try:
        await cq.message.edit_text(lobby_card(g), reply_markup=cq.message.reply_markup)
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "cv:leave")
async def leave(cq: CallbackQuery) -> None:
    g = run_of(cq.message.chat.id)
    if not g or g.phase is not C.Phase.LOBBY:
        return await cq.answer("دیر شد، کاروان راه افتاده.", show_alert=True)
    if not g.remove(cq.from_user.id):
        return await cq.answer("راننده نمی‌تواند پیاده شود.", show_alert=True)
    RIDING.pop(cq.from_user.id, None)
    if g.stake:
        await E.add(cq.from_user.id, money=g.stake)
        g.pot -= g.stake
    await cq.answer("پیاده شدی. سهمت برگشت.")
    try:
        await cq.message.edit_text(lobby_card(g), reply_markup=cq.message.reply_markup)
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "cv:go")
async def go(cq: CallbackQuery, bot: Bot) -> None:
    g = run_of(cq.message.chat.id)
    if not g or g.phase is not C.Phase.LOBBY:
        return await cq.answer("قابل شروع نیست.", show_alert=True)
    if cq.from_user.id != g.host_id:
        return await cq.answer("فقط راننده می‌تواند زودتر حرکت کند.", show_alert=True)
    if len(g.players) < C.MIN_PLAYERS:
        return await cq.answer(f"حداقل {C.MIN_PLAYERS} نفر لازم است.", show_alert=True)
    await cq.answer()
    await depart(bot, g)


async def depart(bot: Bot, g: C.Convoy) -> None:
    _cancel(g)
    if len(g.players) < C.MIN_PLAYERS:
        await _refund(g)
        _release(g)
        return await bot.send_message(g.chat_id, card("🚚 <b>لغو شد</b>", [
            f"خدمه کافی نشد (حداقل {C.MIN_PLAYERS}).",
            "سهم‌ها برگشت داده شد." if g.stake else "",
        ]))
    C.start(g)
    await db.log("convoy", f"حرکت با {len(g.players)} خدمه", None, g.chat_id)
    await bot.send_message(g.chat_id, card("🚚 <b>کاروان راه افتاد</b>", [
        f"👥 {len(g.players)} نفر · مقصد: حصار در {C.DISTANCE_GOAL} کیلومتری",
        "",
        *vitals(g),
        "",
        "هر مرحله یک خطر دارد. پست‌ها را پر کنید وگرنه جاده تاوانش را می‌گیرد.",
    ], "موفق باشید."))
    await enter_stations(bot, g)


# ── station phase ─────────────────────────────────────────────────────────
async def enter_stations(bot: Bot, g: C.Convoy) -> None:
    _cancel(g)
    g.phase = C.Phase.STATION
    g.deadline = time.time() + C.STATION_SECONDS
    sent = await bot.send_message(g.chat_id, station_card(g))
    g.message_id = sent.message_id
    prompt = card(
        f"🎒 <b>مرحله {g.leg}</b>",
        ["کدام پست را می‌گیری؟", "",
         *[f"{i} <b>{l}</b> — {d}"
           for i, l, d in (C.STATION_META[s] for s in C.Station)]])
    # posts stay hidden so nobody can free-ride on someone else's pick
    await secret.deliver_many(
        bot, g.chat_id,
        [(p.user_id, prompt, station_kb(g)) for p in g.players.values()])
    g._task = asyncio.create_task(_station_timer(bot, g, g.leg))


async def _station_timer(bot: Bot, g: C.Convoy, leg: int) -> None:
    try:
        await asyncio.sleep(max(1, int(g.deadline - time.time())))
        if g.phase is C.Phase.STATION and g.leg == leg:
            await close_stations(bot, g)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("cv:s:"))
async def pick_station(cq: CallbackQuery, bot: Bot) -> None:
    _, _, chat_id, value = cq.data.split(":")
    g = RUNS.get(int(chat_id))
    if not g or g.phase is not C.Phase.STATION:
        return await cq.answer("الان زمان انتخاب پست نیست.", show_alert=True)
    ok, err = C.set_station(g, cq.from_user.id, C.Station(value))
    if not ok:
        return await cq.answer(err, show_alert=True)
    icon, label, _ = C.STATION_META[C.Station(value)]
    await cq.answer(f"{icon} {label}")
    try:
        await cq.message.edit_text(
            card("✅ <b>پست ثبت شد</b>",
                 [f"{icon} <b>{label}</b>", "",
                  "می‌توانی تا پایان مهلت تغییرش دهی."]),
            reply_markup=station_kb(g))
    except Exception:  # noqa: BLE001
        pass
    if C.everyone_stationed(g):
        await close_stations(bot, g)


async def close_stations(bot: Bot, g: C.Convoy) -> None:
    _cancel(g)
    if g.phase is not C.Phase.STATION:
        return
    # anyone who never answered gets put on rations rather than stalling the run
    for p in g.players.values():
        if p.station is None:
            p.station = C.Station.RATION
    C.close_stations(g)
    await enter_speed(bot, g)


# ── speed phase ───────────────────────────────────────────────────────────
async def enter_speed(bot: Bot, g: C.Convoy) -> None:
    _cancel(g)
    g.phase = C.Phase.SPEED
    g.deadline = time.time() + C.SPEED_SECONDS
    sent = await bot.send_message(g.chat_id, speed_card(g), reply_markup=speed_kb())
    g.message_id = sent.message_id
    g._task = asyncio.create_task(_speed_timer(bot, g, g.leg))


async def _speed_timer(bot: Bot, g: C.Convoy, leg: int) -> None:
    try:
        await asyncio.sleep(max(1, int(g.deadline - time.time())))
        if g.phase is C.Phase.SPEED and g.leg == leg:
            await drive(bot, g)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("cv:v:"))
async def pick_speed(cq: CallbackQuery, bot: Bot) -> None:
    g = run_of(cq.message.chat.id)
    if not g or g.phase is not C.Phase.SPEED:
        return await cq.answer("الان زمان رأی نیست.", show_alert=True)
    ok, err = C.set_speed(g, cq.from_user.id, C.Speed(cq.data.rsplit(":", 1)[1]))
    if not ok:
        return await cq.answer(err, show_alert=True)
    await cq.answer("رأیت ثبت شد.")
    try:
        await cq.message.edit_text(speed_card(g), reply_markup=speed_kb())
    except Exception:  # noqa: BLE001
        pass
    if C.everyone_voted_speed(g):
        await drive(bot, g)


async def drive(bot: Bot, g: C.Convoy) -> None:
    _cancel(g)
    if g.phase is not C.Phase.SPEED:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=g.chat_id,
                                            message_id=g.message_id,
                                            reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    out = C.resolve_leg(g)
    await bot.send_message(g.chat_id, card("🛣️ <b>جاده</b>", out))
    if C.check_end(g):
        return await finish(bot, g)
    await enter_stations(bot, g)


# ── end ───────────────────────────────────────────────────────────────────
async def finish(bot: Bot, g: C.Convoy) -> None:
    _cancel(g)
    escaped = g.winner == "escaped"
    pay = C.payouts(g)
    for uid, amount in pay.items():
        if amount:
            await E.add(uid, money=amount)
    for p in g.players.values():
        await E.grant_xp(p.user_id, 120 if escaped else 40)
    if not escaped and g.stake:
        # the road took the money; nobody is paid, so log where it went
        await db.log("convoy", f"صندوق {money(g.pot)} در جاده ماند",
                     None, g.chat_id)

    title = "🏁 <b>کاروان رسید</b>" if escaped else "💀 <b>کاروان از دست رفت</b>"
    lines = [g.cause, ""] + C.summary(g)
    if escaped and pay:
        lines += ["", f"💵 صندوق {money(g.pot)} بین {len(pay)} نفر تقسیم شد:"]
        for uid, amount in sorted(pay.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"• {g.players[uid].name} — {money(amount)}")
    await anim.big_emoji(bot, g.chat_id, "🏁" if escaped else "💀")
    await bot.send_message(g.chat_id, card(title, lines, "دوباره: /convoy"))
    await db.log("convoy", f"پایان — {g.winner}", None, g.chat_id)
    if channel.configured():
        chat = await db.fetchone("SELECT title FROM chats WHERE chat_id=?",
                                 (g.chat_id,))
        await channel.round_ended(
            bot, "convoy", chat["title"] if chat else "یک گروه",
            "کاروان رسید" if escaped else "کاروان از دست رفت",
            f"{g.cause} — {len(g.players)} خدمه، {g.leg - 1} مرحله")
    _release(g)


@router.message(Command("cvstop"), F.chat.type.in_({"group", "supergroup"}))
async def stop_run(message: Message) -> None:
    from ..config import config
    g = run_of(message.chat.id)
    if not g:
        return await message.reply("کاروانی در راه نیست.")
    if message.from_user.id != g.host_id and not config.is_admin(message.from_user.id):
        return await message.reply("فقط راننده یا ادمین می‌تواند متوقف کند.")
    _cancel(g)
    await _refund(g)
    _release(g)
    await message.reply(card("🛑 <b>کاروان متوقف شد</b>",
                             ["سهم‌ها برگشت داده شد." if g.stake else "کاروان ایستاد."]))


async def abort_all() -> int:
    """Refund every convoy still on the road — used on shutdown."""
    n = 0
    for g in list(RUNS.values()):
        _cancel(g)
        await _refund(g)
        _release(g)
        n += 1
    return n
