"""LOCKDOWN — group-wide hidden-role rounds.

Night actions are taken in private chat, the day vote happens in the group.
The live round card is edited in place so the group watches one message.
"""
from __future__ import annotations

import asyncio
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .. import anim, channel, secret
from ..db import db
from ..game import engine as E
from ..game import lockdown as L
from ..ui import card, kb, mention, money

router = Router(name="lockdown")

GAMES: dict[int, L.Lockdown] = {}
# user_id -> chat_id, so private night actions know which round they belong to
PLAYING: dict[int, int] = {}

ENTRY_FEE_MAX = 50_000


def game_of(chat_id: int) -> L.Lockdown | None:
    return GAMES.get(chat_id)


def game_for_user(uid: int) -> L.Lockdown | None:
    cid = PLAYING.get(uid)
    return GAMES.get(cid) if cid is not None else None


def _register(g: L.Lockdown) -> None:
    GAMES[g.chat_id] = g
    for uid in g.players:
        PLAYING[uid] = g.chat_id


def _release(g: L.Lockdown) -> None:
    GAMES.pop(g.chat_id, None)
    for uid in list(PLAYING):
        if PLAYING[uid] == g.chat_id:
            PLAYING.pop(uid, None)


def _cancel(g: L.Lockdown) -> None:
    task = getattr(g, "_task", None)
    if task is not None:
        try:
            task.cancel()
        except Exception:  # noqa: BLE001
            pass
        g._task = None


# ── cards ─────────────────────────────────────────────────────────────────
def lobby_card(g: L.Lockdown) -> str:
    left = max(0, int(g.deadline - time.time()))
    names = [f"{i}. {p.name}" for i, p in enumerate(g.players.values(), 1)]
    lines = [
        "تأسیس قرنطینه شد. یکی از شما ویروس را حمل می‌کند.",
        "",
        f"👥 <b>{len(g.players)}</b>/{L.MAX_PLAYERS} نفر"
        f" (حداقل {L.MIN_PLAYERS})",
    ] + (names or ["هنوز کسی وارد نشده."])
    if g.stake:
        lines += ["", f"💵 ورودی: <b>{money(g.stake)}</b> · صندوق: {money(g.pot)}"]
    lines += ["", f"⏳ {left} ثانیه تا قفل درها"]
    return card("☣️ <b>پروتکل قرنطینه</b>", lines,
                "نقش‌ها در PV اعلام می‌شود — ربات را استارت کرده باش.")


def night_card(g: L.Lockdown) -> str:
    left = max(0, int(g.deadline - time.time()))
    alive = g.alive_players()
    lines = [
        f"🌑 <b>شب {g.round}</b> — چراغ‌ها خاموش است.",
        "",
        "نقش‌دارها همین حالا در <b>چت خصوصی</b> اقدام می‌کنند.",
        "بقیه فقط می‌توانند صبر کنند.",
        "",
        f"👥 زنده: <b>{len(alive)}</b> — " + " · ".join(p.name for p in alive),
        "",
        f"⏳ {left} ثانیه تا طلوع",
    ]
    return card("☣️ <b>پروتکل قرنطینه</b>", lines,
                "🦠 حامل‌ها یکدیگر را می‌شناسند. شما نه.")


def day_card(g: L.Lockdown, header: list[str] | None = None) -> str:
    left = max(0, int(g.deadline - time.time()))
    alive = g.alive_players()
    tally = L.vote_tally(g)
    lines = list(header or g.log)
    lines += ["", f"☀️ <b>روز {g.round}</b> — چه کسی را پاکسازی می‌کنید؟", ""]
    for p in alive:
        n = tally.get(p.user_id, 0)
        bar_ = "🟥" * n if n else "▫️"
        lines.append(f"{bar_} <b>{p.name}</b>" + (f" — {n}" if n else ""))
    skip = tally.get(0, 0)
    if skip:
        lines.append(f"⬜ رد کردن — {skip}")
    lines += ["", f"🗳️ {len(g.day_votes)}/{len(alive)} رأی · ⏳ {left} ثانیه"]
    return card("☣️ <b>پروتکل قرنطینه</b>", lines,
                "رأی علنی است. دروغ هم علنی است.")


def vote_kb(g: L.Lockdown) -> object:
    rows = []
    alive = g.alive_players()
    for i in range(0, len(alive), 2):
        rows.append([(p.name[:16], f"ld:v:{p.user_id}") for p in alive[i:i + 2]])
    rows.append([("⬜ رد کردن", "ld:v:0")])
    return kb(rows)


def action_kb(g: L.Lockdown, actor: L.LPlayer) -> object:
    """Private keyboard listing valid night targets for this role."""
    targets = [p for p in g.alive_players() if p.user_id != actor.user_id]
    if actor.role is L.Role.CARRIER:
        targets = [p for p in targets if p.role is not L.Role.CARRIER]
        tag = "c"
    elif actor.role is L.Role.SCREENER:
        tag = "s"
    elif actor.role is L.Role.ENFORCER:
        targets = [p for p in g.alive_players() if p.user_id != g.last_shield]
        tag = "e"
    else:
        return kb([])
    rows = []
    for i in range(0, len(targets), 2):
        rows.append([(p.name[:16], f"ld:{tag}:{g.chat_id}:{p.user_id}")
                     for p in targets[i:i + 2]])
    return kb(rows)


# ── lobby ─────────────────────────────────────────────────────────────────
@router.message(Command("lockdown"), F.chat.type.in_({"group", "supergroup"}))
async def open_lobby(message: Message, bot: Bot) -> None:
    host = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    if game_of(message.chat.id):
        return await message.reply("☣️ یک قرنطینه همین حالا در جریان است. <code>/join</code>")
    parts = message.text.split()
    stake = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    stake = min(stake, ENTRY_FEE_MAX)
    if stake and host["money"] < stake:
        return await message.reply("💸 خودت هم باید ورودی را بپردازی.")

    g = L.Lockdown(chat_id=message.chat.id, host_id=host["user_id"], stake=stake)
    g.add(host["user_id"], host["name"])
    if stake:
        await E.add(host["user_id"], money=-stake)
        g.pot = stake
    g.deadline = time.time() + L.LOBBY_SECONDS
    _register(g)
    await anim.big_emoji(bot, g.chat_id, "☣️")
    sent = await message.answer(lobby_card(g), reply_markup=kb([
        [("🚪 ورود", "ld:join"), ("🏃 خروج", "ld:leave")],
        [("▶️ شروع فوری", "ld:go")],
    ]))
    g.message_id = sent.message_id
    g._task = asyncio.create_task(lobby_timer(bot, g))


async def lobby_timer(bot: Bot, g: L.Lockdown) -> None:
    try:
        await asyncio.sleep(max(1, int(g.deadline - time.time())))
        if g.phase is L.Phase.LOBBY:
            await begin(bot, g)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "ld:join")
async def join(cq: CallbackQuery) -> None:
    g = game_of(cq.message.chat.id)
    if not g or g.phase is not L.Phase.LOBBY:
        return await cq.answer("ثبت‌نام بسته است.", show_alert=True)
    if cq.from_user.id in PLAYING and PLAYING[cq.from_user.id] != g.chat_id:
        return await cq.answer("تو در قرنطینه گروه دیگری هستی.", show_alert=True)
    p = await E.ensure_player(cq.from_user.id, cq.from_user.full_name)
    if g.stake and p["money"] < g.stake:
        return await cq.answer(f"💸 ورودی {money(g.stake)} است.", show_alert=True)
    if not g.add(p["user_id"], p["name"]):
        return await cq.answer("قبلاً واردی یا ظرفیت پر است.", show_alert=True)
    if g.stake:
        await E.add(p["user_id"], money=-g.stake)
        g.pot += g.stake
    PLAYING[p["user_id"]] = g.chat_id
    await cq.answer("وارد قرنطینه شدی.")
    try:
        await cq.message.edit_text(lobby_card(g), reply_markup=cq.message.reply_markup)
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "ld:leave")
async def leave(cq: CallbackQuery) -> None:
    g = game_of(cq.message.chat.id)
    if not g or g.phase is not L.Phase.LOBBY:
        return await cq.answer("دیگر نمی‌توانی خارج شوی.", show_alert=True)
    if not g.remove(cq.from_user.id):
        return await cq.answer("تو در فهرست نیستی.", show_alert=True)
    PLAYING.pop(cq.from_user.id, None)
    if g.stake:
        await E.add(cq.from_user.id, money=g.stake)
        g.pot -= g.stake
    await cq.answer("خارج شدی. ورودی برگشت.")
    try:
        await cq.message.edit_text(lobby_card(g), reply_markup=cq.message.reply_markup)
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "ld:go")
async def go(cq: CallbackQuery, bot: Bot) -> None:
    g = game_of(cq.message.chat.id)
    if not g or g.phase is not L.Phase.LOBBY:
        return await cq.answer("قابل شروع نیست.", show_alert=True)
    if cq.from_user.id != g.host_id:
        return await cq.answer("فقط میزبان می‌تواند زودتر شروع کند.", show_alert=True)
    if len(g.players) < L.MIN_PLAYERS:
        return await cq.answer(f"حداقل {L.MIN_PLAYERS} نفر لازم است.", show_alert=True)
    await cq.answer()
    await begin(bot, g)


async def begin(bot: Bot, g: L.Lockdown) -> None:
    _cancel(g)
    if len(g.players) < L.MIN_PLAYERS:
        if g.stake:
            for uid in g.players:
                await E.add(uid, money=g.stake)
        _release(g)
        return await bot.send_message(g.chat_id, card("☣️ <b>لغو شد</b>", [
            f"نفرات کافی نشدند (حداقل {L.MIN_PLAYERS}).",
            "ورودی‌ها برگشت داده شد." if g.stake else "",
        ]))
    L.start(g)
    await db.log("lockdown", f"شروع با {len(g.players)} نفر", None, g.chat_id)

    # Deal roles privately. Ephemeral messages land in the group but are
    # visible only to their owner, so players no longer need to have DMed
    # the bot first; DM is the fallback.
    carriers = g.carriers()
    parcels: list[tuple[int, str, object]] = []
    for p in g.players.values():
        icon, label, desc = L.ROLE_META[p.role]
        lines = [f"{icon} نقش تو: <b>{label}</b>", f"<i>{desc}</i>"]
        if p.role is L.Role.CARRIER:
            mates = [c.name for c in carriers if c.user_id != p.user_id]
            lines += ["", "🦠 هم‌تیمی‌ها: " + (", ".join(mates) if mates else "تنهایی")]
            lines.append("شب‌ها اینجا هدف را انتخاب کن. روزها دروغ بگو.")
        elif p.role is L.Role.SCREENER:
            lines.append("شب‌ها یک نفر را تست کن. نتیجه فقط به تو می‌رسد.")
        elif p.role is L.Role.ENFORCER:
            lines.append("شب‌ها از یک نفر محافظت کن. دو شب پیاپی یک نفر ممنوع.")
        else:
            lines.append("اقدام شبانه نداری. اما رأی و حرفت وزن دارد.")
        parcels.append((p.user_id,
                        card("☣️ <b>پرونده محرمانه</b>", lines), None))

    routes = await secret.deliver_many(bot, g.chat_id, parcels)
    missed = [g.players[uid].name for uid in secret.unreachable(routes)]
    if missed:
        await bot.send_message(g.chat_id, card("⚠️ <b>هشدار</b>", [
            "نقش این افراد قابل تحویل نبود:",
            ", ".join(missed),
            "",
            "یک‌بار به ربات پیام خصوصی بدهید تا این مشکل تکرار نشود.",
        ]))
    await enter_night(bot, g, first=True)


# ── night ─────────────────────────────────────────────────────────────────
async def enter_night(bot: Bot, g: L.Lockdown, first: bool = False) -> None:
    _cancel(g)
    g.phase = L.Phase.NIGHT
    g.deadline = time.time() + L.NIGHT_SECONDS
    sent = await bot.send_message(g.chat_id, night_card(g))
    g.message_id = sent.message_id
    for p in g.alive_players():
        if p.role is L.Role.SURVIVOR:
            continue
        icon, label, _ = L.ROLE_META[p.role]
        prompt = {
            L.Role.CARRIER: "🦠 چه کسی را تبدیل می‌کنی؟",
            L.Role.SCREENER: "🔬 خون چه کسی را تست می‌کنی؟",
            L.Role.ENFORCER: "🪖 از چه کسی محافظت می‌کنی؟",
        }[p.role]
        await secret.deliver(bot, g.chat_id, p.user_id,
                             card(f"{icon} <b>شب {g.round}</b>", [prompt]),
                             action_kb(g, p))
    g._task = asyncio.create_task(night_timer(bot, g, g.round))


async def night_timer(bot: Bot, g: L.Lockdown, rnd: int) -> None:
    try:
        await asyncio.sleep(max(1, int(g.deadline - time.time())))
        if g.phase is L.Phase.NIGHT and g.round == rnd:
            await close_night(bot, g)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        pass


def night_done(g: L.Lockdown) -> bool:
    need_c = bool(g.carriers()) and g.round > 1
    if need_c and not g.convert_votes:
        return False
    if g.role_holder(L.Role.SCREENER) and not g.screen_pick:
        return False
    if g.role_holder(L.Role.ENFORCER) and not g.shield_pick:
        return False
    return True


@router.callback_query(F.data.startswith("ld:c:"))
async def act_convert(cq: CallbackQuery, bot: Bot) -> None:
    await _night_action(cq, bot, "c")


@router.callback_query(F.data.startswith("ld:s:"))
async def act_screen(cq: CallbackQuery, bot: Bot) -> None:
    await _night_action(cq, bot, "s")


@router.callback_query(F.data.startswith("ld:e:"))
async def act_shield(cq: CallbackQuery, bot: Bot) -> None:
    await _night_action(cq, bot, "e")


async def _night_action(cq: CallbackQuery, bot: Bot, kind: str) -> None:
    _, _, chat_id, target_id = cq.data.split(":")
    g = GAMES.get(int(chat_id))
    if not g or g.phase is not L.Phase.NIGHT:
        return await cq.answer("الان شب نیست.", show_alert=True)
    uid, tid = cq.from_user.id, int(target_id)
    if kind == "c":
        ok, err = L.set_convert(g, uid, tid)
        msg = "🦠 هدف ثبت شد."
    elif kind == "s":
        ok, err = L.set_screen(g, uid, tid)
        msg = "🔬 نمونه گرفته شد. نتیجه هنگام طلوع."
    else:
        ok, err = L.set_shield(g, uid, tid)
        msg = "🪖 محافظت ثبت شد."
    if not ok:
        return await cq.answer(err, show_alert=True)
    await cq.answer(msg)
    try:
        await cq.message.edit_text(
            card("✅ <b>ثبت شد</b>", [f"{msg}", f"هدف: <b>{g.players[tid].name}</b>"]),
            reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    if night_done(g):
        await close_night(bot, g)


async def close_night(bot: Bot, g: L.Lockdown) -> None:
    _cancel(g)
    if g.phase is not L.Phase.NIGHT:
        return
    screening = L.screening_result(g)
    out = L.resolve_night(g)

    if screening:
        sid, tname, is_carrier = screening
        verdict = ("🦠 <b>مثبت</b> — او حامل است." if is_carrier
                   else "✅ <b>منفی</b> — خون او پاک است.")
        await secret.deliver(bot, g.chat_id, sid,
                             card("🔬 <b>نتیجه غربالگری</b>", [
                                 f"نمونه: <b>{tname}</b>", "", verdict,
                             ], "این را بگو یا نگه‌دار — به خودت بستگی دارد."))
    g.screen_pick.clear()

    if L.check_win(g):
        return await finish(bot, g)
    await enter_day(bot, g, out)


# ── day ───────────────────────────────────────────────────────────────────
async def enter_day(bot: Bot, g: L.Lockdown, header: list[str]) -> None:
    _cancel(g)
    g.phase = L.Phase.DAY
    g.deadline = time.time() + L.DAY_SECONDS
    g.log = header
    sent = await bot.send_message(g.chat_id, day_card(g, header),
                                  reply_markup=vote_kb(g))
    g.message_id = sent.message_id
    g._task = asyncio.create_task(day_timer(bot, g, g.round))


async def day_timer(bot: Bot, g: L.Lockdown, rnd: int) -> None:
    try:
        await asyncio.sleep(max(1, int(g.deadline - time.time())))
        if g.phase is L.Phase.DAY and g.round == rnd:
            await close_day(bot, g)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("ld:v:"))
async def vote(cq: CallbackQuery, bot: Bot) -> None:
    g = game_of(cq.message.chat.id)
    if not g or g.phase is not L.Phase.DAY:
        return await cq.answer("الان روز نیست.", show_alert=True)
    tid = int(cq.data.rsplit(":", 1)[1])
    ok, err = L.set_vote(g, cq.from_user.id, tid)
    if not ok:
        return await cq.answer(err, show_alert=True)
    name = "رد کردن" if tid == 0 else g.players[tid].name
    await cq.answer(f"رأی تو: {name}")
    try:
        await cq.message.edit_text(day_card(g), reply_markup=vote_kb(g))
    except Exception:  # noqa: BLE001
        pass
    if L.everyone_voted(g):
        await close_day(bot, g)


async def close_day(bot: Bot, g: L.Lockdown) -> None:
    _cancel(g)
    if g.phase is not L.Phase.DAY:
        return
    out = L.resolve_day(g)
    try:
        await bot.edit_message_reply_markup(chat_id=g.chat_id,
                                            message_id=g.message_id,
                                            reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await bot.send_message(g.chat_id, card("🗳️ <b>نتیجه رأی‌گیری</b>", out))
    if L.check_win(g):
        return await finish(bot, g)
    await enter_night(bot, g)


# ── end ───────────────────────────────────────────────────────────────────
async def finish(bot: Bot, g: L.Lockdown) -> None:
    _cancel(g)
    pay = L.payouts(g)
    for uid, amount in pay.items():
        if amount:
            await E.add(uid, money=amount)
        await E.grant_xp(uid, 90)
    for p in g.players.values():
        if p.user_id not in pay:
            await E.grant_xp(p.user_id, 30)

    title = ("🦠 <b>حامل‌ها پیروز شدند</b>" if g.winner == "carriers"
             else "🪖 <b>قرنطینه موفق بود</b>")
    body = ("ویروس تأسیسات را گرفت. کسی بیرون نرفت."
            if g.winner == "carriers"
            else "همه حامل‌ها پاکسازی شدند. تأسیسات نجات یافت.")
    lines = [body, "", "<b>پرونده کامل</b>"] + L.summary(g)
    if g.pot and pay:
        share = next(iter(pay.values()))
        lines += ["", f"💵 صندوق {money(g.pot)} بین {len(pay)} برنده — "
                      f"هرکدام {money(share)}"]
    await anim.big_emoji(bot, g.chat_id, "☣️" if g.winner == "carriers" else "🪖")
    await bot.send_message(g.chat_id, card("☣️ <b>پایان قرنطینه</b>", lines,
                                           "دور بعد: /lockdown"))
    await db.log("lockdown", f"پایان — برنده {g.winner}", None, g.chat_id)
    if channel.configured():
        chat = await db.fetchone("SELECT title FROM chats WHERE chat_id=?",
                                 (g.chat_id,))
        await channel.round_ended(
            bot, "lockdown", chat["title"] if chat else "یک گروه",
            "قرنطینه به پایان رسید",
            f"{'🦠 حامل‌ها بردند' if g.winner == 'carriers' else '🪖 تأسیسات نجات یافت'}"
            f" — {len(g.players)} بازیکن، {g.round} دور")
    _release(g)


@router.message(Command("ldstop"), F.chat.type.in_({"group", "supergroup"}))
async def stop_game(message: Message) -> None:
    from ..config import config
    g = game_of(message.chat.id)
    if not g:
        return await message.reply("قرنطینه‌ای در جریان نیست.")
    if message.from_user.id != g.host_id and not config.is_admin(message.from_user.id):
        return await message.reply("فقط میزبان یا ادمین می‌تواند لغو کند.")
    _cancel(g)
    if g.stake:
        for uid in g.players:
            await E.add(uid, money=g.stake)
    _release(g)
    await message.reply(card("🛑 <b>قرنطینه لغو شد</b>",
                             ["ورودی‌ها برگشت داده شد." if g.stake else "دور متوقف شد."]))


async def abort_all() -> int:
    """Refund every open round — used on shutdown."""
    n = 0
    for g in list(GAMES.values()):
        _cancel(g)
        if g.stake:
            for uid in g.players:
                await E.add(uid, money=g.stake)
        _release(g)
        n += 1
    return n
