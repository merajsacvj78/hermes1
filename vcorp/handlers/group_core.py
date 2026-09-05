"""Group: onboarding, profile, help, leaderboard, logs."""
from __future__ import annotations

import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..db import db
from ..game import content
from ..game.engine import (add, effective, ensure_player, get_player, inventory,
                           player_powers, rep_all, update)
from ..game.content import ITEMS, MUTATIONS, PATHS, stage_for
from ..ui import bar, card, kb, mention, money

router = Router(name="group")
GROUP = F.chat.type.in_({"group", "supergroup"})
router.message.filter(GROUP)

HELP = card("📖 <b>راهنمای V-CORP: OUTBREAK</b>", [
    "🧬 <b>هسته</b>",
    "<code>/start</code> ورود به جهان · <code>/me</code> پروفایل · <code>/scan &lt;نام&gt;</code> اسکن",
    "",
    "⚔️ <b>اقدام</b>",
    "<code>/scavenge</code> جست‌وجو · <code>/attack</code> (ریپلای) · <code>/heal</code>",
    "<code>/mission</code> مأموریت‌ها · <code>/power</code> قدرت‌ها · <code>/mutate</code> درخت جهش",
    "<code>/inject</code> تزریق سرم · <code>/hide</code> پنهان‌سازی آلودگی · <code>/cure</code> درمان",
    "",
    "💰 <b>اقتصاد</b>",
    "<code>/shop</code> · <code>/black</code> بازار سیاه · <code>/inv</code> · <code>/pay</code>",
    "<code>/market</code> عرضه‌ها · <code>/sell</code> فروش · <code>/evidence</code> اطلاعات",
    "",
    "🎯 <b>خیانت</b>",
    "<code>/contract &lt;نام&gt; &lt;مبلغ&gt;</code> قرارداد مخفی · <code>/contracts</code> · <code>/wanted</code>",
    "",
    "🏢 <b>سازمان</b>",
    "<code>/orgs</code> · <code>/join</code> · <code>/found &lt;نام&gt;</code> · <code>/org</code> · <code>/war</code>",
    "",
    "🌎 <b>جهان</b>",
    "<code>/world</code> وضعیت · <code>/event</code> رویداد فعال · <code>/boss</code> · <code>/hit</code>",
    "<code>/top</code> رتبه‌بندی · <code>/log</code> لاگ اتفاقات · <code>/legends</code>",
    "",
    "🎮 <b>حالت‌های گروهی</b> — <code>/modes</code>",
    "<code>/duel</code> گودال · <code>/lockdown</code> قرنطینه · <code>/convoy</code> کاروان",
], "تازه‌واردی؟ /guide — آموزش کوتاه گام‌به‌گام.")


async def register_chat(message: Message) -> None:
    await db.execute(
        "INSERT INTO chats(chat_id,title,active,added_at) VALUES(?,?,1,?) "
        "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, active=1",
        (message.chat.id, message.chat.title or "", int(time.time())),
    )


@router.message(Command("start"))
async def start(message: Message) -> None:
    await register_chat(message)
    u = message.from_user
    existed = await get_player(u.id)
    p = await ensure_player(u.id, u.full_name)
    icon, label, desc = PATHS[p["path"]]
    if existed:
        text = card("☣️ <b>V-CORP: OUTBREAK</b>", [
            f"{mention(u.id, u.full_name)} از قبل در جهان ثبت شده است.",
            f"{icon} مسیر: <b>{label}</b> · نسل {p['generation']}",
            "با <code>/me</code> وضعیتت را ببین.",
        ])
    else:
        text = card("☣️ <b>پروتکل ورود</b>", [
            f"{mention(u.id, u.full_name)} وارد منطقه آلوده شد.",
            "",
            f"{icon} <b>{label}</b> — {desc}",
            f"💵 {money(p['money'])} · ❤️ {p['hp']}/{p['max_hp']} · ☣️ {p['infection']}٪",
            "",
            "مسیرت را انتخاب‌ها می‌سازند، نه منوها.",
        ], "شروع کن: /scavenge یا /mission")
    await message.answer(text, reply_markup=kb([
        [("🧬 پروفایل", "ui:me"), ("🎯 مأموریت", "ui:missions")],
        [("🌎 جهان", "ui:world"), ("📚 آموزش", "gd:0")],
        [("🎮 حالت‌های گروهی", "ui:modes")],
    ]))


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await message.answer(HELP)


MODES = card("🎮 <b>حالت‌های گروهی</b>", [
    "سه بازی کامل، هرکدام برای یک نوع جمع:",
    "",
    "⚔️ <b>گودال</b> — <code>/duel @کسی</code>",
    "دوئل تن‌به‌تن با حرکت مخفی و همزمان. برد با خواندن حریف است.",
    "",
    "☣️ <b>پروتکل قرنطینه</b> — <code>/lockdown</code>",
    "نقش مخفی برای ۴+ نفر. حامل‌ها شب تبدیل می‌کنند، گروه روز رأی می‌دهد.",
    "همه علیه همه‌ی نادیده‌ها.",
    "",
    "🚚 <b>کاروان</b> — <code>/convoy</code>",
    "همکاری خالص برای ۳+ نفر. پست بگیرید، سرعت را رأی بدهید،",
    "و کاروان را تا حصار برسانید. یا همه می‌رسید، یا هیچ‌کس.",
    "",
    "👹 <b>باس جهانی</b> — <code>/boss</code>",
    "هر باس مکانیک و ضعف خودش را دارد. تنهایی شکست نمی‌خورد.",
], "آموزش کامل: /guide")


@router.message(Command("modes"))
async def modes_cmd(message: Message) -> None:
    await message.answer(MODES, reply_markup=kb([
        [("☣️ قرنطینه", "ui:go:lockdown"), ("🚚 کاروان", "ui:go:convoy")],
        [("📚 آموزش کامل", "gd:0")],
    ]))


@router.callback_query(F.data == "ui:modes")
async def cb_modes(cq: CallbackQuery) -> None:
    await cq.message.answer(MODES, reply_markup=kb([
        [("☣️ قرنطینه", "ui:go:lockdown"), ("🚚 کاروان", "ui:go:convoy")],
        [("📚 آموزش کامل", "gd:0")],
    ]))
    await cq.answer()


@router.callback_query(F.data.startswith("ui:go:"))
async def cb_go(cq: CallbackQuery) -> None:
    """Point at the command rather than starting a round on someone's behalf."""
    which = cq.data.rsplit(":", 1)[1]
    cmd = "/lockdown" if which == "lockdown" else "/convoy"
    await cq.answer(f"برای شروع، {cmd} را بفرست.", show_alert=True)


async def profile_text(user_id: int) -> str:
    p = await get_player(user_id)
    if not p:
        return "❌ هنوز وارد جهان نشده‌ای. <code>/start</code>"
    eff = await effective(p)
    icon, label, _ = PATHS.get(p["path"], PATHS["survivor"])
    _, sicon, sname = stage_for(p["infection"])
    powers = await player_powers(user_id)
    muts = await db.fetchall("SELECT node FROM mutations WHERE user_id=?", (user_id,))
    rep = await rep_all(user_id)
    org = await db.fetchone("SELECT name,icon FROM orgs WHERE org_id=?", (p["org_id"],)) \
        if p["org_id"] else None
    lines = [
        f"{icon} <b>{p['name']}</b> · {label} · Lv.{p['level']} · نسل {p['generation']}",
        f"❤️ <code>{bar(p['hp'], eff['max_hp'])}</code> {p['hp']}/{eff['max_hp']}",
        f"⚡ <code>{bar(p['energy'], 100)}</code> {p['energy']}/100",
        f"{sicon} <code>{bar(p['infection'], 100)}</code> {p['infection']}٪ · {sname}"
        + (" 🫥" if p["hidden"] else ""),
        "",
        f"🗡️ Attack <b>{eff['attack']}</b> · 🛡️ Defense <b>{eff['defense']}</b>",
        f"🥷 Stealth <b>{eff['stealth']}</b> · 🧠 Intellect <b>{eff['intellect']}</b>",
        f"💵 {money(p['money'])} · 🔥 Heat {p['heat']} · 🏅 Legacy {p['legacy']}",
        f"💀 Kills {p['kills']} · ⚰️ Deaths {p['deaths']}",
    ]
    if org:
        lines.append(f"{org['icon']} سازمان: <b>{org['name']}</b> ({p['org_rank']})")
    if powers:
        lines.append("🦸 قدرت‌ها: " + " ".join(f"{x['icon']}{x['name']}" for x in powers))
    if muts:
        lines.append("🧬 جهش‌ها: " + " ".join(
            MUTATIONS[m["node"]]["icon"] + MUTATIONS[m["node"]]["name"]
            for m in muts if m["node"] in MUTATIONS))
    lines.append("📊 شهرت: " + " · ".join(
        f"{c.upper()} {v:+d}" for c, v in rep.items()))
    return card("🧬 <b>پرونده عامل</b>", lines)


@router.message(Command("me", "profile"))
async def me(message: Message) -> None:
    await ensure_player(message.from_user.id, message.from_user.full_name)
    await message.answer(await profile_text(message.from_user.id), reply_markup=kb([
        [("🎒 کوله", "ui:inv"), ("🦸 قدرت", "ui:power")],
        [("🧬 جهش", "ui:mutate"), ("🎯 مأموریت", "ui:missions")],
    ]))


@router.callback_query(F.data == "ui:me")
async def cb_me(cq: CallbackQuery) -> None:
    await cq.message.edit_text(await profile_text(cq.from_user.id))
    await cq.answer()


@router.callback_query(F.data == "ui:help")
async def cb_help(cq: CallbackQuery) -> None:
    await cq.message.edit_text(HELP)
    await cq.answer()


@router.message(Command("scan"))
async def scan(message: Message) -> None:
    from ..game.engine import cooldown_left, find_player, set_cooldown
    me_p = await ensure_player(message.from_user.id, message.from_user.full_name)
    target = None
    if message.reply_to_message:
        target = await get_player(message.reply_to_message.from_user.id)
    else:
        arg = message.text.split(maxsplit=1)
        if len(arg) > 1:
            target = await find_player(arg[1])
    if not target:
        return await message.reply("🔍 استفاده: ریپلای روی بازیکن یا <code>/scan نام</code>")
    left = await cooldown_left(me_p["user_id"], "scan")
    if left:
        return await message.reply(f"⏳ اسکنر داغ است — {left} ثانیه.")
    await set_cooldown(me_p["user_id"], "scan", 90)
    eff = await effective(target)
    icon, label, _ = PATHS.get(target["path"], PATHS["survivor"])
    hidden = target["hidden"] and (await effective(me_p))["intellect"] < eff["stealth"] + 10
    inf = "??? (مسدود شده 🫥)" if hidden else f"{target['infection']}٪"
    shown_path = "نامشخص" if hidden else label
    await message.reply(card(f"📡 <b>اسکن — {target['name']}</b>", [
        f"{icon} مسیر: <b>{shown_path}</b> · Lv.{target['level']}",
        f"❤️ {target['hp']}/{eff['max_hp']} · ☣️ آلودگی: {inf}",
        f"🗡️ ~{eff['attack']} · 🛡️ ~{eff['defense']} · 🔥 Heat {target['heat']}",
    ], "اسکن ناقص است — دشمن می‌تواند دروغ بگوید."))


@router.message(Command("inv"))
async def inv(message: Message) -> None:
    await ensure_player(message.from_user.id, message.from_user.full_name)
    items = await inventory(message.from_user.id)
    if not items:
        return await message.reply("🎒 کوله‌ات خالی است. <code>/shop</code>")
    lines = [f"{ITEMS[c]['icon']} <b>{ITEMS[c]['name']}</b> ×{q}"
             for c, q in items if c in ITEMS]
    p = await get_player(message.from_user.id)
    await message.reply(card("🎒 <b>کوله</b>", lines, f"💵 {money(p['money'])}"))


@router.callback_query(F.data == "ui:inv")
async def cb_inv(cq: CallbackQuery) -> None:
    items = await inventory(cq.from_user.id)
    lines = [f"{ITEMS[c]['icon']} {ITEMS[c]['name']} ×{q}" for c, q in items if c in ITEMS]
    await cq.answer("\n".join(lines) or "کوله خالی است", show_alert=True)


@router.message(Command("top"))
async def top(message: Message) -> None:
    rows = await db.fetchall(
        "SELECT name,level,money,kills,infection,legacy FROM players "
        "WHERE banned=0 ORDER BY level DESC, kills DESC, money DESC LIMIT 10")
    medals = ["🥇", "🥈", "🥉"] + ["▫️"] * 7
    lines = [f"{medals[i]} <b>{r['name']}</b> — Lv.{r['level']} · 💀{r['kills']} · "
             f"{money(r['money'])} · ☣️{r['infection']}٪"
             for i, r in enumerate(rows)]
    await message.reply(card("🏆 <b>رتبه‌بندی جهانی</b>", lines or ["هنوز کسی نیست."]))


@router.message(Command("log"))
async def logs(message: Message) -> None:
    rows = await db.fetchall("SELECT kind,text,at FROM logs ORDER BY id DESC LIMIT 12")
    lines = [f"<code>{time.strftime('%H:%M', time.localtime(r['at']))}</code> "
             f"· {r['text']}" for r in rows]
    await message.reply(card("📜 <b>لاگ اتفاقات</b>", lines or ["ساکت است... فعلاً."]))


@router.message(Command("legends"))
async def legends(message: Message) -> None:
    lines = []
    for c in content.LEGENDS:
        lines.append(f"{c['icon']} <b>{c['name']}</b> — <i>{c['title']}</i>")
        lines.append(f"   {c['desc']}")
        lines.append(f"   💰 جایزه سر: {money(c['bounty'])}")
        lines.append("")
    await message.reply(card("👤 <b>چهره‌های شناخته‌شده</b>", lines,
                             "شخصیت‌های اصلی V-CORP: OUTBREAK"))
