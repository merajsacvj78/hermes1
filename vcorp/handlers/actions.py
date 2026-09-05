"""Core gameplay actions: scavenge, combat, powers, mutation, serum, missions."""
from __future__ import annotations

import random

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..db import db
from ..game import engine as E
from ..game.content import ITEMS, MUTATIONS, PATHS
from ..ui import bar, card, kb, mention, money

router = Router(name="actions")
GROUP = F.chat.type.in_({"group", "supergroup"})
router.message.filter(GROUP)

SCAVENGE_CD = 240
ATTACK_CD = 300
MISSION_CD = 900

FIND_TEXTS = [
    "🚪 در یک آپارتمان متروک را باز کردی؛ بوی کلر و خون خشک.",
    "🚑 آمبولانس واژگون‌شده‌ای در بزرگراه، جعبه‌ها هنوز پلمب.",
    "🏭 انبار شرکتی؛ دوربین‌ها هنوز کار می‌کنند.",
    "🕳️ تونل فاضلاب — چیزی پشت سرت خش‌خش کرد.",
    "🏥 بخش ایزوله بیمارستان؛ سه تخت خالی، سه بند پاره.",
]


async def guard(message: Message, key: str, cd: int, energy: int = 0):
    u = message.from_user
    p = await E.ensure_player(u.id, u.full_name)
    if p["banned"]:
        await message.reply("🚫 دسترسی تو به جهان مسدود است.")
        return None
    left = await E.cooldown_left(u.id, key)
    if left:
        await message.reply(f"⏳ هنوز آماده نیستی — <b>{E.fmt_time(left)}</b>")
        return None
    if energy and p["energy"] < energy:
        await message.reply("🥱 انرژی کافی نداری. کمی صبر کن یا <code>/heal</code>.")
        return None
    return p


# ── scavenge ──────────────────────────────────────────────────────────────
@router.message(Command("scavenge", "s"))
async def scavenge(message: Message) -> None:
    p = await guard(message, "scavenge", SCAVENGE_CD, 8)
    if not p:
        return
    await E.set_cooldown(p["user_id"], "scavenge", SCAVENGE_CD)
    await E.add(p["user_id"], energy=-8)
    lines = [random.choice(FIND_TEXTS), ""]
    roll = random.randint(1, 100)
    cash = random.randint(80, 420) + p["level"] * 25
    await E.add(p["user_id"], money=cash)
    lines.append(f"💵 پیدا کردی: <b>{money(cash)}</b>")
    if roll > 60:
        code = random.choice(["medkit", "ammo", "antiviral", "vsample", "tracker"])
        await E.give_item(p["user_id"], code)
        lines.append(f"{ITEMS[code]['icon']} آیتم: <b>{ITEMS[code]['name']}</b>")
    if roll > 88:
        body = random.choice([
            "سند انتقال وجه بین V-CORP و یک پیمانکار ناشناس",
            "لیست پرسنل قرنطینه با سه نام خط‌خورده",
            "لاگ آزمایش VX-13 روی سوژه انسانی",
        ])
        await db.execute(
            "INSERT INTO evidence(owner_id,about_id,kind,body,value,created_at)"
            " VALUES(?,?,?,?,?,?)",
            (p["user_id"], None, "document", body, random.randint(800, 3000), E.NOW()))
        lines.append("🗂️ <b>مدرک</b> پیدا کردی — <code>/evidence</code>")
    if roll <= 22:
        inf = random.randint(3, 9)
        new, stage, changed = await E.apply_infection(p["user_id"], inf)
        lines.append(f"☣️ تماس آلوده! آلودگی <b>+{inf}</b> → {new}٪")
        if changed:
            lines.append(f"🩸 <b>مرحله جدید: {stage}</b>")
    gained = await E.grant_xp(p["user_id"], 35)
    if gained:
        lines.append(f"⬆️ <b>Level Up ×{gained}</b>")
    await message.reply(card("🔦 <b>جست‌وجو</b>", lines,
                             f"Cooldown {E.fmt_time(SCAVENGE_CD)}"))


# ── combat ────────────────────────────────────────────────────────────────
@router.message(Command("attack", "a"))
async def attack(message: Message) -> None:
    if not message.reply_to_message:
        return await message.reply("⚔️ روی پیام هدف ریپلای کن: <code>/attack</code>")
    tgt_user = message.reply_to_message.from_user
    if tgt_user.id == message.from_user.id or tgt_user.is_bot:
        return await message.reply("🤨 هدف نامعتبر.")
    p = await guard(message, "attack", ATTACK_CD, 12)
    if not p:
        return
    t = await E.get_player(tgt_user.id)
    if not t:
        return await message.reply("❓ هدف هنوز وارد جهان نشده است.")
    await E.set_cooldown(p["user_id"], "attack", ATTACK_CD)
    await E.add(p["user_id"], energy=-12)
    res = await E.resolve_attack(p, t)
    lines = [f"{mention(p['user_id'], p['name'])} ⚔️ {mention(t['user_id'], t['name'])}", ""]
    if not res["hit"]:
        lines.append("🌫️ ضربه خطا رفت — هدف جاخالی داد.")
        await E.grant_xp(p["user_id"], 10)
    else:
        hp, died = await E.damage_player(t["user_id"], res["damage"])
        lines.append(("💥 <b>CRITICAL!</b> " if res["crit"] else "🎯 ") +
                     f"آسیب <b>{res['damage']}</b>")
        eff = await E.effective(t)
        if died:
            lines.append(f"💀 <b>{t['name']} از پا درآمد.</b>")
            await E.kill_player(t["user_id"], p["user_id"])
            await _settle_contracts(message, p, t)
        else:
            lines.append(f"❤️ <code>{bar(hp, eff['max_hp'])}</code> {hp}/{eff['max_hp']}")
        await E.grant_xp(p["user_id"], 40)
        await E.add(p["user_id"], heat=4)
        # counter-attack
        if not died and random.randint(1, 100) <= 55:
            back = await E.resolve_attack(t, p)
            if back["hit"]:
                hp2, died2 = await E.damage_player(p["user_id"], back["damage"] // 2)
                lines.append(f"↩️ ضدحمله: <b>{back['damage'] // 2}</b> آسیب به تو"
                             + (" — 💀 کشته شدی!" if died2 else f" (❤️ {hp2})"))
    await message.reply(card("⚔️ <b>درگیری</b>", lines,
                             f"Heat +4 · Cooldown {E.fmt_time(ATTACK_CD)}"))


async def _settle_contracts(message: Message, killer: dict, victim: dict) -> None:
    rows = await db.fetchall(
        "SELECT * FROM contracts WHERE target_id=? AND status='open'", (victim["user_id"],))
    for c in rows:
        await E.add(killer["user_id"], money=c["reward"])
        await db.execute("UPDATE contracts SET status='done', taker_id=? WHERE id=?",
                         (killer["user_id"], c["id"]))
        await db.log("contract", f"قرارداد #{c['id']} روی {victim['name']} اجرا شد",
                     killer["user_id"], message.chat.id)
        await message.answer(card("🎯 <b>قرارداد اجرا شد</b>", [
            f"هدف: <b>{victim['name']}</b>",
            f"مجری: {mention(killer['user_id'], killer['name'])}",
            f"پاداش پرداختی: <b>{money(c['reward'])}</b>",
        ], "سفارش‌دهنده ناشناس ماند."))


@router.message(Command("heal"))
async def heal(message: Message) -> None:
    p = await guard(message, "heal", 600)
    if not p:
        return
    if await E.take_item(p["user_id"], "medkit"):
        eff = await E.effective(p)
        hp = min(eff["max_hp"], p["hp"] + 40)
        await E.update(p["user_id"], hp=hp, energy=min(100, p["energy"] + 20))
        await E.set_cooldown(p["user_id"], "heal", 600)
        return await message.reply(f"🩹 درمان شدی — ❤️ {hp}/{eff['max_hp']}")
    hp = min(p["max_hp"], p["hp"] + 12)
    await E.update(p["user_id"], hp=hp, energy=min(100, p["energy"] + 25))
    await E.set_cooldown(p["user_id"], "heal", 600)
    await message.reply(f"🛌 استراحت کردی — ❤️ {hp}/{p['max_hp']} · ⚡ انرژی بازگشت.\n"
                        f"<i>با 🩹 کیت درمان سریع‌تر می‌شود.</i>")


# ── powers ────────────────────────────────────────────────────────────────
@router.message(Command("power", "p"))
async def power_list(message: Message) -> None:
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    powers = await E.player_powers(p["user_id"])
    if not powers:
        return await message.reply(card("🦸 <b>قدرت‌ها</b>", [
            "هیچ قدرتی نداری.",
            "با 🧬 <b>V-SERUM</b> یک قدرت بگیر: <code>/black</code> سپس <code>/inject</code>",
        ]))
    lines, rows = [], []
    for pw in powers:
        left = await E.cooldown_left(p["user_id"], f"pw:{pw['code']}")
        lines.append(f"{pw['icon']} <b>{pw['name']}</b> — {pw['description']}")
        lines.append(f"   ⏱ {E.fmt_time(left)} · ⚠️ ریسک {pw['risk']}٪ · 🛡 ضد: {pw['counter']}")
        rows.append([(f"{pw['icon']} {pw['name']}", f"pw:{pw['code']}")])
    await message.reply(card("🦸 <b>زرادخانه V-SERUM</b>", lines,
                             "برای استفاده هدف‌دار: ریپلای + /use <کد>"),
                        reply_markup=kb(rows))


@router.message(Command("use"))
async def use_power(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("استفاده: <code>/use کد_قدرت</code> (ریپلای روی هدف)")
    code = parts[1].strip()
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    owned = {x["code"]: x for x in await E.player_powers(p["user_id"])}
    if code not in owned:
        return await message.reply("❌ این قدرت را نداری.")
    pw = owned[code]
    left = await E.cooldown_left(p["user_id"], f"pw:{code}")
    if left:
        return await message.reply(f"⏳ {pw['name']} در Cooldown — {E.fmt_time(left)}")
    target = None
    if message.reply_to_message and not message.reply_to_message.from_user.is_bot:
        target = await E.get_player(message.reply_to_message.from_user.id)
    lines = [f"{pw['icon']} <b>{pw['name']}</b> فعال شد."]
    await E.set_cooldown(p["user_id"], f"pw:{code}", pw["cooldown"])

    if pw["power_type"] == "offense":
        if not target:
            return await message.reply("🎯 این قدرت هدف می‌خواهد — ریپلای کن.")
        res = await E.resolve_attack(p, target, pw)
        if res["hit"]:
            hp, died = await E.damage_player(target["user_id"], res["damage"])
            lines.append(f"💥 {res['damage']} آسیب به <b>{target['name']}</b>")
            if code == "hemo_drain" and target["stage"] != "bioweapon":
                heal_amt = res["damage"] // 3
                await E.update(p["user_id"], hp=min(p["max_hp"], p["hp"] + heal_amt))
                lines.append(f"🩸 {heal_amt} HP جذب کردی.")
            if code == "viral_burst":
                new, st, ch = await E.apply_infection(target["user_id"], 12)
                lines.append(f"☣️ هدف آلوده شد → {new}٪")
            if died:
                lines.append(f"💀 <b>{target['name']} کشته شد.</b>")
                await E.kill_player(target["user_id"], p["user_id"])
                await _settle_contracts(message, p, target)
        else:
            lines.append(f"🛡 <b>{target['name']}</b> قدرت را دفع کرد ({pw['counter']}).")
    elif code == "static_veil":
        await E.update(p["user_id"], hidden=1)
        await E.set_cooldown(p["user_id"], "hidden", 1800)
        lines.append("🫥 آلودگی‌ات ۳۰ دقیقه از اسکن پنهان شد.")
    elif code == "phase_step":
        await E.set_cooldown(p["user_id"], "attack", 0)
        await E.update(p["user_id"], heat=max(0, p["heat"] - 10))
        lines.append("💠 از میدان خارج شدی. Heat کاهش یافت.")
    elif code == "carapace":
        await E.add(p["user_id"], defense=10)
        lines.append("🛡️ زره کیتینی — Defense +10 تا نبرد بعدی.")
    elif code == "overclock":
        await E.add(p["user_id"], attack=8, hp=-10)
        lines.append("⚡ اورکلاک — Attack +8 · ❤️ -10")
    elif code == "pathogen_read":
        if not target:
            return await message.reply("🎯 هدف لازم است — ریپلای کن.")
        icon, label, _ = PATHS.get(target["path"], PATHS["survivor"])
        lines.append(f"🔬 <b>{target['name']}</b>: آلودگی واقعی <b>{target['infection']}٪</b> "
                     f"· مسیر پنهان: {icon} {label}")
    elif code == "mind_thread":
        if not target:
            return await message.reply("🎯 هدف لازم است — ریپلای کن.")
        ev = await db.fetchone(
            "SELECT * FROM evidence WHERE owner_id=? ORDER BY value DESC LIMIT 1",
            (target["user_id"],))
        if ev:
            await db.execute("UPDATE evidence SET owner_id=? WHERE id=?",
                             (p["user_id"], ev["id"]))
            lines.append(f"🧠 رازی کشیدی بیرون: «{ev['body']}» — مدرک به تو منتقل شد.")
        else:
            lines.append("🧠 ذهن هدف خالی بود. چیزی برای دزدیدن نداشت.")
    elif code == "dead_switch":
        await E.set_cooldown(p["user_id"], "deadswitch", 3600)
        lines.append("💣 کلید مرده مسلح شد. قاتلت گران می‌پردازد.")

    if random.randint(1, 100) <= pw["risk"]:
        new, st, ch = await E.apply_infection(p["user_id"], random.randint(4, 10))
        lines.append(f"⚠️ عوارض سرم — آلودگی تو → <b>{new}٪</b>")
    await E.grant_xp(p["user_id"], 45)
    await message.reply(card("🦸 <b>قدرت</b>", lines,
                             f"Cooldown {E.fmt_time(pw['cooldown'])}"))


@router.callback_query(F.data.startswith("pw:"))
async def cb_power(cq: CallbackQuery) -> None:
    code = cq.data.split(":", 1)[1]
    pw = await E.power_row(code)
    left = await E.cooldown_left(cq.from_user.id, f"pw:{code}")
    if not pw:
        return await cq.answer("قدرت یافت نشد", show_alert=True)
    await cq.answer(f"{pw['name']}\n{pw['description']}\nCooldown: {E.fmt_time(left)}\n"
                    f"ضد: {pw['counter']}\nاستفاده: /use {code}", show_alert=True)


# ── serum / infection management ──────────────────────────────────────────
@router.message(Command("inject"))
async def inject(message: Message) -> None:
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    if not await E.take_item(p["user_id"], "vserum"):
        return await message.reply("🧬 V-SERUM نداری — <code>/black</code>")
    pw = await E.random_power_for(p["user_id"])
    lines = []
    if pw:
        await E.grant_power(p["user_id"], pw["code"])
        lines.append(f"{pw['icon']} قدرت جدید: <b>{pw['name']}</b>")
        lines.append(f"<i>{pw['description']}</i>")
        if p["path"] in ("survivor", "merc", "scientist"):
            await E.update(p["user_id"], path="vhero")
            lines.append("🦸 مسیرت به <b>ابرقدرت V-CORP</b> تغییر کرد.")
    else:
        await E.add(p["user_id"], attack=6, max_hp=15)
        lines.append("💉 بدنت به سرم عادت کرده — فقط تقویت جسمی. Attack +6 · HP +15")
    inf = random.randint(5, 18)
    new, stage, changed = await E.apply_infection(p["user_id"], inf)
    lines.append(f"☣️ آلودگی <b>+{inf}</b> → {new}٪")
    if changed:
        lines.append(f"🩸 مرحله جدید: <b>{stage}</b>")
    await message.reply(card("💉 <b>تزریق V-SERUM</b>", lines,
                             "هر قدرت بهایی دارد."))


@router.message(Command("hide"))
async def hide(message: Message) -> None:
    p = await guard(message, "hidecmd", 1800)
    if not p:
        return
    if not await E.take_item(p["user_id"], "suppressor"):
        return await message.reply("🫥 مهارکننده نداری — <code>/shop</code>")
    await E.update(p["user_id"], hidden=1)
    await E.set_cooldown(p["user_id"], "hidecmd", 1800)
    await message.reply("🫥 آلودگی‌ات پنهان شد. اسکن‌های عادی چیزی نمی‌بینند.")


@router.message(Command("cure"))
async def cure(message: Message) -> None:
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    if p["stage"] == "bioweapon":
        return await message.reply("👹 بازگشتی نیست. آنچه بودی دیگر وجود ندارد.")
    if await E.take_item(p["user_id"], "cure_proto"):
        new, st, ch = await E.apply_infection(p["user_id"], -40)
        return await message.reply(f"🔬 نمونه درمان تزریق شد — آلودگی → <b>{new}٪</b>")
    if await E.take_item(p["user_id"], "antiviral"):
        new, st, ch = await E.apply_infection(p["user_id"], -10)
        return await message.reply(f"💊 پادتن پایه — آلودگی → <b>{new}٪</b>")
    await message.reply("❌ داروی درمان نداری. <code>/shop</code> یا <code>/black</code>")


# ── mutation tree ─────────────────────────────────────────────────────────
@router.message(Command("mutate"))
async def mutate(message: Message) -> None:
    p = await E.ensure_player(message.from_user.id, message.from_user.full_name)
    owned = {r["node"] for r in await db.fetchall(
        "SELECT node FROM mutations WHERE user_id=?", (p["user_id"],))}
    avail = await E.auto_mutations(p["user_id"])
    lines = [f"☣️ آلودگی: <b>{p['infection']}٪</b>", ""]
    for code, m in MUTATIONS.items():
        mark = "✅" if code in owned else ("🔓" if code in avail else "🔒")
        req = f" (نیاز: {MUTATIONS[m['req']]['name']})" if m["req"] else ""
        lines.append(f"{mark} {m['icon']} <b>{m['name']}</b> · ☣️{m['inf']}٪{req}")
        lines.append(f"    <i>{m['desc']}</i>")
    rows = [[(f"{MUTATIONS[c]['icon']} {MUTATIONS[c]['name']}", f"mut:{c}")] for c in avail]
    await message.reply(card("🧬 <b>درخت جهش VX-13</b>", lines,
                             "جهش برگشت‌ناپذیر است."),
                        reply_markup=kb(rows) if rows else None)


@router.callback_query(F.data.startswith("mut:"))
async def cb_mut(cq: CallbackQuery) -> None:
    node = cq.data.split(":", 1)[1]
    ok = await E.unlock_mutation(cq.from_user.id, node)
    if not ok:
        return await cq.answer("❌ شرایط این جهش را نداری.", show_alert=True)
    m = MUTATIONS[node]
    await cq.answer(f"{m['icon']} {m['name']} فعال شد!", show_alert=True)
    await cq.message.answer(card("🧬 <b>جهش</b>", [
        f"{mention(cq.from_user.id, cq.from_user.full_name)} جهش یافت:",
        f"{m['icon']} <b>{m['name']}</b> — {m['desc']}",
        "اثر: " + " · ".join(f"{k} +{v}" for k, v in m["effect"].items()),
    ]))


# ── missions ──────────────────────────────────────────────────────────────
async def missions_card(user_id: int) -> tuple[str, list]:
    rows = await db.fetchall("SELECT * FROM missions WHERE active=1 ORDER BY difficulty")
    lines, btns = [], []
    for m in rows:
        lines.append(f"{m['title']} · ⚙️{m['difficulty']} · 💵{money(m['reward'])} "
                     f"· ☣️{m['infection']:+d} · 🏢{m['org'].upper()}")
        lines.append(f"   <i>{m['description']}</i>")
        btns.append((f"{m['title'][:18]}", f"ms:{m['id']}"))
    rows_kb = [btns[i:i + 2] for i in range(0, len(btns), 2)]
    return card("🎯 <b>تابلوی مأموریت</b>", lines, "یک مأموریت انتخاب کن."), rows_kb


@router.message(Command("mission", "m"))
async def missions(message: Message) -> None:
    await E.ensure_player(message.from_user.id, message.from_user.full_name)
    text, rows = await missions_card(message.from_user.id)
    await message.reply(text, reply_markup=kb(rows))


@router.callback_query(F.data == "ui:missions")
async def cb_missions(cq: CallbackQuery) -> None:
    text, rows = await missions_card(cq.from_user.id)
    await cq.message.edit_text(text, reply_markup=kb(rows))
    await cq.answer()


@router.callback_query(F.data.startswith("ms:"))
async def run_mission(cq: CallbackQuery) -> None:
    mid = int(cq.data.split(":", 1)[1])
    p = await E.ensure_player(cq.from_user.id, cq.from_user.full_name)
    left = await E.cooldown_left(p["user_id"], "mission")
    if left:
        return await cq.answer(f"⏳ {E.fmt_time(left)} تا مأموریت بعدی", show_alert=True)
    m = await db.fetchone("SELECT * FROM missions WHERE id=? AND active=1", (mid,))
    if not m:
        return await cq.answer("مأموریت بسته شده", show_alert=True)
    if p["energy"] < 15:
        return await cq.answer("🥱 انرژی کافی نداری", show_alert=True)
    await E.set_cooldown(p["user_id"], "mission", MISSION_CD)
    await E.add(p["user_id"], energy=-15)
    eff = await E.effective(p)
    score = eff["attack"] + eff["intellect"] + eff["stealth"] + random.randint(1, 40)
    need = m["difficulty"] * 18
    success = score >= need
    lines = [f"{m['title']}", f"<i>{m['description']}</i>", ""]
    if success:
        reward = m["reward"] + random.randint(0, m["reward"] // 3)
        await E.add(p["user_id"], money=reward)
        await E.grant_xp(p["user_id"], 60 + m["difficulty"] * 15)
        if m["org"] != "any":
            await E.rep_add(p["user_id"], m["org"], m["rep"])
        lines.append(f"✅ <b>موفق</b> — 💵 {money(reward)}")
        if m["code"] == "sample_run":
            await E.give_item(p["user_id"], "vsample")
            lines.append("🧫 نمونه VX-13 به کوله اضافه شد.")
        if m["code"] == "cure_research":
            cp = int(await db.world_get("cure_progress", 0)) + m["difficulty"] * 2
            await db.world_set("cure_progress", cp)
            lines.append(f"🔬 پیشرفت درمان جهانی: <b>{cp}٪</b>")
        if m["org"] != "any":
            lines.append(f"📊 شهرت {m['org'].upper()} {m['rep']:+d}")
    else:
        dmg = random.randint(8, 15 + m["difficulty"] * 3)
        hp, died = await E.damage_player(p["user_id"], dmg)
        lines.append(f"❌ <b>شکست</b> — ❤️ -{dmg}")
        if m["org"] != "any":
            await E.rep_add(p["user_id"], m["org"], -3)
        if died:
            lines.append("💀 در مأموریت کشته شدی. Legacy منتقل شد.")
    if m["infection"]:
        new, st, ch = await E.apply_infection(p["user_id"], m["infection"])
        lines.append(f"☣️ آلودگی → <b>{new}٪</b>")
    await db.execute("INSERT INTO mission_runs(user_id,mission_id,result,at) VALUES(?,?,?,?)",
                     (p["user_id"], mid, "success" if success else "fail", E.NOW()))
    await db.log("mission", f"{p['name']} · {m['title']} · "
                            f"{'موفق' if success else 'شکست'}", p["user_id"], cq.message.chat.id)
    await cq.message.answer(card("🎯 <b>گزارش مأموریت</b>", lines,
                                 f"{p['name']} · Cooldown {E.fmt_time(MISSION_CD)}"))
    await cq.answer()


@router.callback_query(F.data == "ui:power")
async def cb_pw_list(cq: CallbackQuery) -> None:
    powers = await E.player_powers(cq.from_user.id)
    await cq.answer("\n".join(f"{x['icon']} {x['name']} → /use {x['code']}" for x in powers)
                    or "قدرتی نداری. /inject", show_alert=True)


@router.callback_query(F.data == "ui:mutate")
async def cb_mut_list(cq: CallbackQuery) -> None:
    avail = await E.auto_mutations(cq.from_user.id)
    await cq.answer("جهش‌های در دسترس:\n" + ("\n".join(MUTATIONS[c]["name"] for c in avail)
                                             or "هیچ — آلودگی بیشتری لازم است"),
                    show_alert=True)
