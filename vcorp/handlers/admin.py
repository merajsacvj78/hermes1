"""Full admin control panel (works in private and groups, admins only)."""
from __future__ import annotations

import json
import os
import shutil
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..config import config
from ..db import db
from ..game import engine as E
from ..game.content import ITEMS
from ..ui import card, kb, money

router = Router(name="admin")


def is_admin(uid: int) -> bool:
    return config.is_admin(uid)


PANEL = [
    [("📊 آمار", "ad:stats"), ("👥 گروه‌ها", "ad:chats")],
    [("🚫 Ban/Mute", "ad:mod"), ("🎁 Give", "ad:give")],
    [("🧬 Infection", "ad:inf"), ("🦸 Powers", "ad:powers")],
    [("☣️ Event", "ad:event"), ("🎯 Mission", "ad:mission")],
    [("🏢 Orgs", "ad:orgs"), ("⚙️ Economy", "ad:econ")],
    [("📢 Broadcast", "ad:bc"), ("📜 Logs", "ad:logs")],
    [("💾 Backup", "ad:backup"), ("🔧 SQL", "ad:sql")],
]

HELP = card("👑 <b>پنل ادمین</b>", [
    "<code>/astats</code> آمار کلی",
    "<code>/agive &lt;نام&gt; money|item &lt;کد|مبلغ&gt; [تعداد]</code>",
    "<code>/ainf &lt;نام&gt; &lt;عدد|+n|-n&gt;</code> تغییر آلودگی",
    "<code>/aban &lt;نام&gt;</code> · <code>/aunban</code> · <code>/amute &lt;نام&gt; &lt;دقیقه&gt;</code>",
    "<code>/apower &lt;نام&gt; &lt;کد_قدرت&gt;</code> اعطای قدرت",
    "<code>/anewpower کد|نام|آیکن|نوع|cooldown|risk|magnitude|counter|توضیح</code>",
    "<code>/aevent [کد]</code> ساخت رویداد جهانی",
    "<code>/amission کد|عنوان|org|سختی|پاداش|infection|rep|توضیح</code>",
    "<code>/aorg &lt;کد&gt; funds|power|research &lt;عدد&gt;</code>",
    "<code>/aecon &lt;کد_آیتم&gt; &lt;قیمت&gt;</code>",
    "<code>/abroadcast &lt;متن&gt;</code> ارسال به همه گروه‌ها",
    "<code>/abackup</code> · <code>/arestore</code> (ریپلای روی فایل)",
    "<code>/asql &lt;کوئری&gt;</code> مدیریت مستقیم دیتابیس",
    "<code>/alogs [تعداد]</code>",
], "دسترسی: فقط ADMIN_IDS")


@router.message(Command("admin", "panel"))
async def panel(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.reply(HELP, reply_markup=kb(PANEL))


@router.callback_query(F.data.startswith("ad:"))
async def panel_cb(cq: CallbackQuery, bot: Bot) -> None:
    if not is_admin(cq.from_user.id):
        return await cq.answer("🚫 دسترسی نداری", show_alert=True)
    key = cq.data.split(":", 1)[1]
    if key == "stats":
        return await cq.message.answer(await stats_text())
    if key == "chats":
        rows = await db.fetchall("SELECT chat_id,title,active FROM chats ORDER BY added_at DESC")
        return await cq.message.answer(card("👥 <b>گروه‌ها</b>", [
            f"{'🟢' if r['active'] else '🔴'} <code>{r['chat_id']}</code> {r['title']}"
            for r in rows] or ["هیچ گروهی ثبت نشده."]))
    if key == "logs":
        return await cq.message.answer(await logs_text(15))
    if key == "backup":
        return await do_backup(cq.message)
    if key == "powers":
        rows = await db.fetchall("SELECT code,icon,name,power_type FROM powers")
        return await cq.message.answer(card("🦸 <b>قدرت‌ها</b>", [
            f"{r['icon']} <code>{r['code']}</code> — {r['name']} ({r['power_type']})"
            for r in rows], "افزودن: /anewpower"))
    if key == "orgs":
        rows = await db.fetchall("SELECT code,name,funds,power,research FROM orgs")
        return await cq.message.answer(card("🏢 <b>سازمان‌ها</b>", [
            f"<code>{r['code']}</code> {r['name']} · 💵{money(r['funds'])} "
            f"· ⚔️{r['power']} · 🔬{r['research']}" for r in rows], "ویرایش: /aorg"))
    if key == "econ":
        rows = await db.fetchall("SELECT code,price,demand FROM economy")
        return await cq.message.answer(card("⚙️ <b>اقتصاد</b>", [
            f"<code>{r['code']}</code> {money(r['price'])} · تقاضا {r['demand']:+d}"
            for r in rows], "تنظیم: /aecon <کد> <قیمت>"))
    if key == "mission":
        rows = await db.fetchall("SELECT code,title,active FROM missions")
        return await cq.message.answer(card("🎯 <b>مأموریت‌ها</b>", [
            f"{'🟢' if r['active'] else '🔴'} <code>{r['code']}</code> {r['title']}"
            for r in rows], "افزودن: /amission"))
    hints = {
        "mod": "/aban <نام> · /aunban <نام> · /amute <نام> <دقیقه>",
        "give": "/agive <نام> money 5000  |  /agive <نام> item medkit 2",
        "inf": "/ainf <نام> +20  یا  /ainf <نام> 0",
        "event": "/aevent outbreak|escape|theft|revolt|collapse|globalmut|cure|orgwar",
        "bc": "/abroadcast <متن>",
        "sql": "/asql SELECT * FROM players LIMIT 5",
    }
    await cq.answer(hints.get(key, "—"), show_alert=True)


async def stats_text() -> str:
    total = await db.scalar("SELECT COUNT(*) FROM players")
    alive = await db.scalar("SELECT COUNT(*) FROM players WHERE hp>0 AND banned=0")
    infected = await db.scalar("SELECT COUNT(*) FROM players WHERE infection>=20")
    bio = await db.scalar("SELECT COUNT(*) FROM players WHERE stage='bioweapon'")
    cash = await db.scalar("SELECT SUM(money) FROM players")
    chats = await db.scalar("SELECT COUNT(*) FROM chats WHERE active=1")
    orgs = await db.scalar("SELECT COUNT(*) FROM orgs")
    contracts = await db.scalar("SELECT COUNT(*) FROM contracts WHERE status='open'")
    threat = await db.world_get("threat", 10)
    return card("📊 <b>آمار جهان</b>", [
        f"👥 بازیکنان: <b>{total}</b> (فعال {alive})",
        f"☣️ آلوده: {infected} · 👹 Bio-Weapon: {bio}",
        f"💵 نقدینگی کل: {money(int(cash or 0))}",
        f"🏢 سازمان‌ها: {orgs} · 🎯 قرارداد باز: {contracts}",
        f"👥 گروه‌ها: {chats} · 🌎 تهدید: {threat}٪",
    ])


async def logs_text(n: int = 15) -> str:
    rows = await db.fetchall("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (n,))
    return card("📜 <b>Logs</b>", [
        f"<code>{time.strftime('%m-%d %H:%M', time.localtime(r['at']))}</code> "
        f"[{r['kind']}] {r['text']}" for r in rows] or ["خالی"])


def admin_only(func):
    async def wrapper(message: Message, *a, **kw):
        if not is_admin(message.from_user.id):
            return
        return await func(message, *a, **kw)
    wrapper.__name__ = func.__name__
    return wrapper


@router.message(Command("astats"))
@admin_only
async def astats(message: Message) -> None:
    await message.reply(await stats_text())


@router.message(Command("alogs"))
@admin_only
async def alogs(message: Message) -> None:
    parts = message.text.split()
    n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 15
    await message.reply(await logs_text(min(n, 40)))


@router.message(Command("agive"))
@admin_only
async def agive(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 4:
        return await message.reply("/agive <نام> money 5000 | /agive <نام> item medkit 2")
    target = await E.find_player(parts[1])
    if not target:
        return await message.reply("❌ بازیکن پیدا نشد.")
    kind = parts[2]
    if kind == "money":
        await E.add(target["user_id"], money=int(parts[3]))
        await db.log("admin", f"give money {parts[3]} → {target['name']}",
                     message.from_user.id)
        return await message.reply(f"✅ {money(int(parts[3]))} به {target['name']} داده شد.")
    if kind == "item":
        code = parts[3]
        if code not in ITEMS:
            return await message.reply("❌ کد آیتم نامعتبر.")
        qty = int(parts[4]) if len(parts) > 4 else 1
        await E.give_item(target["user_id"], code, qty)
        return await message.reply(f"✅ {ITEMS[code]['name']} ×{qty} → {target['name']}")
    await message.reply("❌ نوع نامعتبر (money|item)")


@router.message(Command("ainf"))
@admin_only
async def ainf(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply("/ainf <نام> +20 | /ainf <نام> 0")
    target = await E.find_player(parts[1])
    if not target:
        return await message.reply("❌ بازیکن پیدا نشد.")
    val = parts[2]
    if val.startswith(("+", "-")):
        new, st, _ = await E.apply_infection(target["user_id"], int(val))
    else:
        await E.update(target["user_id"], infection=0, stage="human")
        new, st, _ = await E.apply_infection(target["user_id"], int(val))
    await message.reply(f"🧬 {target['name']} → آلودگی <b>{new}٪</b> ({st})")


@router.message(Command("aban"))
@admin_only
async def aban(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    t = await E.find_player(parts[1]) if len(parts) > 1 else None
    if not t:
        return await message.reply("/aban <نام>")
    await E.update(t["user_id"], banned=1)
    await db.log("admin", f"ban {t['name']}", message.from_user.id)
    await message.reply(f"🚫 {t['name']} مسدود شد.")


@router.message(Command("aunban"))
@admin_only
async def aunban(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    t = await E.find_player(parts[1]) if len(parts) > 1 else None
    if not t:
        return await message.reply("/aunban <نام>")
    await E.update(t["user_id"], banned=0)
    await message.reply(f"✅ {t['name']} آزاد شد.")


@router.message(Command("amute"))
@admin_only
async def amute(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply("/amute <نام> <دقیقه>")
    t = await E.find_player(parts[1])
    if not t:
        return await message.reply("❌ بازیکن پیدا نشد.")
    until = E.NOW() + int(parts[2]) * 60
    await db.execute("INSERT INTO mutes(user_id,until,reason) VALUES(?,?,'admin') "
                     "ON CONFLICT(user_id) DO UPDATE SET until=excluded.until",
                     (t["user_id"], until))
    await message.reply(f"🔇 {t['name']} تا {parts[2]} دقیقه بی‌صداست.")


@router.message(Command("apower"))
@admin_only
async def apower(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply("/apower <نام> <کد_قدرت>")
    t = await E.find_player(parts[1])
    if not t:
        return await message.reply("❌ بازیکن پیدا نشد.")
    ok = await E.grant_power(t["user_id"], parts[2])
    await message.reply("✅ قدرت داده شد." if ok else "❌ کد نامعتبر یا از قبل دارد.")


@router.message(Command("anewpower"))
@admin_only
async def anewpower(message: Message) -> None:
    raw = message.text.split(maxsplit=1)
    if len(raw) < 2 or raw[1].count("|") < 8:
        return await message.reply(
            "/anewpower کد|نام|آیکن|نوع|cooldown|risk|magnitude|counter|توضیح")
    f = [x.strip() for x in raw[1].split("|")]
    await db.execute(
        "INSERT INTO powers(code,name,icon,description,cooldown,risk,counter,"
        "power_type,magnitude,custom) VALUES(?,?,?,?,?,?,?,?,?,1) "
        "ON CONFLICT(code) DO UPDATE SET name=excluded.name, icon=excluded.icon, "
        "description=excluded.description, cooldown=excluded.cooldown, risk=excluded.risk, "
        "counter=excluded.counter, power_type=excluded.power_type, magnitude=excluded.magnitude",
        (f[0], f[1], f[2], f[8], int(f[4]), int(f[5]), f[7], f[3], int(f[6])))
    await message.reply(f"🦸 قدرت <code>{f[0]}</code> ثبت شد.")


@router.message(Command("amission"))
@admin_only
async def amission(message: Message) -> None:
    raw = message.text.split(maxsplit=1)
    if len(raw) < 2 or raw[1].count("|") < 7:
        return await message.reply(
            "/amission کد|عنوان|org|سختی|پاداش|infection|rep|توضیح")
    f = [x.strip() for x in raw[1].split("|")]
    await db.execute(
        "INSERT INTO missions(code,title,org,difficulty,reward,infection,rep,description,active)"
        " VALUES(?,?,?,?,?,?,?,?,1) ON CONFLICT(code) DO UPDATE SET title=excluded.title,"
        " org=excluded.org, difficulty=excluded.difficulty, reward=excluded.reward,"
        " infection=excluded.infection, rep=excluded.rep, description=excluded.description,"
        " active=1",
        (f[0], f[1], f[2], int(f[3]), int(f[4]), int(f[5]), int(f[6]), f[7]))
    await message.reply(f"🎯 مأموریت <code>{f[0]}</code> ثبت شد.")


@router.message(Command("aevent"))
@admin_only
async def aevent(message: Message, bot: Bot) -> None:
    from .world import spawn_event
    parts = message.text.split()
    code = parts[1] if len(parts) > 1 else None
    e = await spawn_event(bot, message.chat.id, code)
    text = card(f"{e['icon']} <b>{e['title']}</b>", [e["body"], "", "واکنش: /respond"],
                "رویداد جهانی فعال شد")
    chats = await db.fetchall("SELECT chat_id FROM chats WHERE active=1")
    for c in chats:
        try:
            await bot.send_message(c["chat_id"], text)
        except Exception:
            pass
    await message.reply("☣️ رویداد منتشر شد.")


@router.message(Command("aorg"))
@admin_only
async def aorg(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 4 or parts[2] not in ("funds", "power", "research"):
        return await message.reply("/aorg <کد> funds|power|research <عدد>")
    await db.execute(f"UPDATE orgs SET {parts[2]}=? WHERE code=?", (int(parts[3]), parts[1]))
    await message.reply("✅ اعمال شد.")


@router.message(Command("aecon"))
@admin_only
async def aecon(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply("/aecon <کد_آیتم> <قیمت>")
    await db.execute("INSERT INTO economy(code,price,demand) VALUES(?,?,0) "
                     "ON CONFLICT(code) DO UPDATE SET price=excluded.price",
                     (parts[1], int(parts[2])))
    await message.reply("⚙️ قیمت به‌روزرسانی شد.")


@router.message(Command("abroadcast"))
@admin_only
async def abroadcast(message: Message, bot: Bot) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("/abroadcast <متن>")
    text = card("📢 <b>اعلان V-CORP</b>", [parts[1]])
    rows = await db.fetchall("SELECT chat_id FROM chats WHERE active=1")
    ok = 0
    for r in rows:
        try:
            await bot.send_message(r["chat_id"], text)
            ok += 1
        except Exception:
            await db.execute("UPDATE chats SET active=0 WHERE chat_id=?", (r["chat_id"],))
    await message.reply(f"📢 ارسال شد به {ok}/{len(rows)} گروه.")


async def do_backup(message: Message) -> None:
    path = db.path
    tmp = f"{path}.backup"
    if db.conn:
        await db.conn.commit()
    shutil.copyfile(path, tmp)
    with open(tmp, "rb") as fh:
        data = fh.read()
    os.remove(tmp)
    await message.answer_document(
        BufferedInputFile(data, filename=f"vcorp-backup-{int(time.time())}.sqlite3"),
        caption="💾 نسخه پشتیبان کامل دیتابیس")


@router.message(Command("abackup"))
@admin_only
async def abackup(message: Message) -> None:
    await do_backup(message)


@router.message(Command("arestore"))
@admin_only
async def arestore(message: Message, bot: Bot) -> None:
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("💾 روی فایل بکاپ ریپلای کن و /arestore بزن.")
    f = await bot.get_file(message.reply_to_message.document.file_id)
    dest = f"{db.path}.restore"
    await bot.download_file(f.file_path, dest)
    await db.close()
    shutil.move(dest, db.path)
    await db.connect()
    await E.seed()
    await message.reply("✅ دیتابیس بازیابی شد.")


@router.message(Command("asql"))
@admin_only
async def asql(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("/asql <کوئری>")
    q = parts[1].strip()
    try:
        if q.lower().startswith("select"):
            rows = await db.fetchall(q)
            out = json.dumps([dict(r) for r in rows[:20]], ensure_ascii=False, indent=1)
            return await message.reply(f"<pre>{out[:3500]}</pre>")
        cur = await db.execute(q)
        await message.reply(f"✅ اجرا شد · rowcount={cur.rowcount}")
    except Exception as exc:  # noqa: BLE001
        await message.reply(f"❌ خطا: <code>{exc}</code>")
