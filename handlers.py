"""‌ جنگ جهانی — رابط کاربری: کاملاً
                                     فارسی، دکمه‌ای، تمیز."""
import asyncio
import contextlib
import os
import time
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (CallbackQuery, FSInputFile, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)
import config
import countries
import db
import texts
from game import ai, defense, economy, events, geo, guide, infra, invest, military, politics, quests, state, toll, war, welfare, un
router = Router()
def handlers_bot():
    """نمونه‌ی بات برای ویرایش پیام — از بیرون هم در دسترس."""
    return globals().get("bot")
# ‌ فقط همین دستورهای متنی زنده‌اند — همه‌چیز دیگر از «منو»
TEST_MODE = False
bot = None  # ← run.py تزریق می‌کند
# دکمه‌هایی که هر کسی می‌تواند بزند (پاسخ اتحاد/صلح/نبرد/رویداد/چرا-نه)
MENU_BYPASS = ("aac:", "pac:", "dac:", "gno:", "evc:")
def _own(c, sent, uid):
    """ثبت مالک منوی تازه‌فرستاده‌شده — دکمه‌هایش فقط برای خودش."""
    with contextlib.suppress(Exception):
        db.kv_set(f"mown:{c.chat.id}:{sent.message_id}", str(uid))
def _menu_locked(c) -> str:
    """اگر دکمه‌ی منوی دیگری باشد، پیام رد؛ وگرنه خالی."""
    d = c.data or ""
    if d.startswith(MENU_BYPASS):
        return ""
    try:
        key = f"mown:{c.message.chat.id}:{c.message.message_id}"
    except AttributeError:
        return ""
    owner = db.kv_get(key)
    if owner and str(owner) != str(c.from_user.id):
        u = state.get(int(owner))
        nm = (u["name"] if u else "") or "بازیکن دیگر"
        return f"‌ این منوی {nm} است — خودت بنویس «منو» تا منوی خودت بیاید."
    return ""
@router.callback_query.middleware()
async def menu_lock_mw(handler, event: CallbackQuery, data):
    """‌ هیچ‌کس منوی دیگری را کنترل نمی‌کند."""
    msg = _menu_locked(event)
    if msg:
        with contextlib.suppress(Exception):
            await event.answer(msg[:180])
        return
    return await handler(event, data)
TEXT_ALLOWED = {
    "شروع", "استارت", "منو",                                # بازی
    "راهنما", "تجارت", "پروفایل", "نظامی", "جهان", "جنگ",  # دستورهای فارسی
    "حمله", "نبرد", "خرید", "زرادخانه", "تجهیزات",        # نام‌های رایج
    "دستورها", "دستور", "دستورات", "کمک",                 # فهرست دستورها
    "سرمایه", "سرمایه‌گذاری", "معدن", "دارایی",           # سرمایه‌گذاری
    "زیرساخت", "انقلاب", "شورش",                          # زیرساخت + انقلاب
    "رفاه", "عوارض",                                       # رفاه + تنگه
    "رهبر", "ثبت", "تغییر", "تنظیم",                      # ابزار مالک
}
bot: Bot = None
WORLD_OF = None   # ‌ حلقه‌ی پیوی → دنیای بازیکن (run.py در بوت ست می‌کند)
STICKERS: dict = {}   # ‌ پک استیکر دارک‌زون — ایموجی → file_id (run.py پر می‌کند)
async def _sticker(chat, emoji: str):
    """‌ استیکر مرتبط را می‌فرستد — اگر پک آماده باشد."""
    fid = STICKERS.get(emoji)
    if fid:
        with contextlib.suppress(Exception):
            await chat.send_sticker(fid)
# ═══════════ ‌ پنل مدیریت مالک ═══════════
def kb_help(page: int = 1) -> InlineKeyboardMarkup:
    """‌ راهنمای صفحه‌بندی‌شده — بدون شلوغی."""
    n = len(texts.HELP_PAGES)
    page = max(1, min(n, page))
    row = []
    if page > 1:
        row.append(InlineKeyboardButton(text="◀‌ قبلی", callback_data=f"hp:{page-1}"))
    row.append(InlineKeyboardButton(text=f"‌ {page}/{n}",
                                    callback_data=f"hp:{page}"))
    if page < n:
        row.append(InlineKeyboardButton(text="بعدی ▶‌", callback_data=f"hp:{page+1}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        row,
        [InlineKeyboardButton(text="‌ راهنمای کشور", callback_data="mn:cguide"),
         InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")]])
def kb_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‌ آمار جهان", callback_data="ad:stats"),
         InlineKeyboardButton(text="‌ بازیکنان", callback_data="ad:players")],
        [InlineKeyboardButton(text="‌ اعلام فراخوان", callback_data="ad:callup"),
         InlineKeyboardButton(text="‌ سربازها", callback_data="ad:troops")],
        [InlineKeyboardButton(text="‌‌✈‌ ثبت بازیکن", callback_data="ad:reg"),
         InlineKeyboardButton(text="‌ تغییر کشور", callback_data="ad:chg")],
        [InlineKeyboardButton(text="‌ رهبر دادن", callback_data="ad:lead"),
         InlineKeyboardButton(
             text="‌ خبرنامه: " + ("خاموش ‌" if db.kv_get("bl_off") else "روشن ‌"),
             callback_data="ad:tog:bl")],
        [InlineKeyboardButton(
            text="⚡ رویداد گروهی: " + ("خاموش ‌" if db.kv_get("ev_off") else "روشن ‌"),
            callback_data="ad:tog:ev")],
        [InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")]])
def _admin_callup_parts() -> list:
    """‌ اعلام‌نظام — همه‌ی سربازان با تگ، گروه‌بندی با کشور (تکه‌های امن)."""
    rows = db.q("SELECT uid, name, country, level FROM users "
                "WHERE country IS NOT NULL ORDER BY country, level DESC")
    t = texts
    if not rows:
        return ["هنوز بازیکنی ثبت نشده — «ثبت آیدی کشور»"]
    groups = {}
    for r in rows:
        groups.setdefault(r["country"], []).append(r)
    parts, cur = [], [t.hdr("اعلام عمومی سربازان", "‌"),
                      "به میدان بیایید — جنگ جهانی آغاز شده!", ""]
    for cid in sorted(groups, key=lambda c: -len(groups[c])):
        c = countries.COUNTRIES.get(cid)
        if not c:
            continue
        tags = " ".join(t.mention(r["uid"], (r["name"] or "سرباز")[:20])
                        for r in groups[cid])
        block = [f"{c['flag']} <b>{c['name']}</b> ({t.fa(len(groups[cid]))}):",
                 tags, ""]
        if len("\n".join(cur + block)) > 3500:
            parts.append("\n".join(cur))
            cur = []
        cur += block
    cur.append("‌ در گروه بنویس: «منو»")
    parts.append("\n".join(cur))
    return parts
def _admin_stats() -> str:
    n = db.one("SELECT COUNT(*) c FROM users WHERE country IS NOT NULL")["c"]
    wars = db.one("SELECT COUNT(*) c FROM wars WHERE status='active'")["c"]
    parties = db.one("SELECT COUNT(*) c FROM parties")["c"]
    from game import economy
    w = economy.world()
    return "\n".join([
        texts.hdr("پنل مدیریت", "‌"),
        texts.row("بازیکنان ثبت‌شده", n),
        texts.row("احزاب", parties),
        texts.row("جنگ‌های فعال", wars),
        texts.row("نفت / دلار / تورم",
                  f"${w['oil']:.0f} · ×{w['dollar']:.2f} · {w['inflation']*100:.1f}٪"),
        "",
        "‌ ثبت بازیکن: <code>ثبت آیدی کشور</code>",
        "مثال: <code>ثبت 8694290031 ایران</code>",
        "",
        "‌ رهبر کشور: ریپلای روی پیام بازیکن + «رهبر کشور»",
        "یا: <code>رهبر آیدی کشور</code> · <code>رهبر @آیدی کشور</code>",
        "خلع ← NPC: <code>رهبر خالی آمریکا</code>",
        "",
        "‌ تغییر کشور: <code>تغییر آیدی کشور</code>",
        "مثال: <code>تغییر 8694290031 روسیه</code>"])
def _admin_register(uid_target: int, country_name: str) -> str:
    cid = _find_country(country_name or "")
    if not cid:
        return "‌ کشور نامعتبر — مثال: ایران · آمریکا · روسیه"
    p = state.get(uid_target)
    if p and p["country"]:
        return (f"‌‌ {uid_target} قبلاًثبت شده — برای تغییر: "
                f"<code>تغییر {uid_target} {countries.COUNTRIES[cid]['name']}</code>")
    if not state.enlist(uid_target, cid, f"Player{uid_target % 1000}"):
        return "‌ خطا در ثبت."
    c = countries.COUNTRIES[cid]
    return f"‌ بازیکن <code>{uid_target}</code> ثبت شد در {c['flag']} {c['name']}"
def _admin_change(uid_target: int, country_name: str) -> str:
    p = state.get(uid_target)
    if not p:
        return f"‌ بازیکن {uid_target} ثبت نشده — اول: <code>ثبت {uid_target} کشور</code>"
    cid = _find_country(country_name or "")
    if not cid:
        return "‌ کشور نامعتبر."
    db.ex("UPDATE users SET country=? WHERE uid=?", (cid, uid_target))
    c = countries.COUNTRIES[cid]
    return f"‌ کشور بازیکن <code>{uid_target}</code> ← {c['flag']} {c['name']}"
def _set_leader(uid_t: int, cname: str) -> str:
    """‌ رهبر کردن بازیکن مشخص در کشور — ثبت خودکار هم دارد."""
    cid = _find_country(cname or "")
    if not cid:
        return "‌ کشور نامعتبر — مثال: <code>رهبر آمریکا</code>"
    p = state.get(uid_t)
    if p and p["country"] and p["country"] != cid:
        return (f"‌ بازیکن در کشور دیگری است — اول: "
                f"<code>تغییر {uid_t} {countries.COUNTRIES[cid]['name']}</code>")
    if not p or not p["country"]:
        if not state.enlist(uid_t, cid, f"Player{uid_t % 1000}"):
            return "‌ خطا در ثبت."
    db.ex("UPDATE users SET is_leader=0 WHERE country=? AND is_leader=1", (cid,))
    db.ex("UPDATE users SET is_leader=1 WHERE uid=?", (uid_t,))
    c = countries.COUNTRIES[cid]
    return f"‌ بازیکن <code>{uid_t}</code> رهبر {c['flag']} {c['name']} شد!"""
def _admin_leader(arg: str) -> str:
    """‌ تعیین/خلع رهبر کشور — با آیدی عددی یا «خالی» برای NPC."""
    parts = arg.split()
    # ‌ خلع: رهبر خالی آمریکا → کشور NPC می‌شود
    if parts and parts[0] in ("خالی", "-"):
        cid = _find_country(" ".join(parts[1:]))
        if not cid:
            return "‌ کشور نامعتبر — مثال: <code>رهبر خالی آمریکا</code>"
        c = countries.COUNTRIES[cid]
        db.ex("UPDATE users SET is_leader=0 WHERE country=? AND is_leader=1", (cid,))
        # ‌ ثبت‌های اشتباه قدیمی (Player بدون فعالیت) پاک می‌شوند
        db.ex("DELETE FROM users WHERE country=? AND chat_id IS NULL "
              "AND (name LIKE 'Player%') AND branch IS NULL", (cid,))
        return f"♻‌ {c['flag']} {c['name']} بدون رهبر شد — دولت NPC."
    if len(parts) >= 2 and parts[0].isdigit():
        return _set_leader(int(parts[0]), " ".join(parts[1:]))
    return ("‌ الگو: روی پیام بازیکن ریپلای کن و بنویس <code>رهبر کشور</code>\n"
            "یا: <code>رهبر آیدی‌عددی کشور</code> · <code>رهبر @آیدی کشور</code> · "
            "خلع: <code>رهبر خالی کشور</code>")
@router.callback_query(F.data.startswith("ad:"))
async def cb_admin(c: CallbackQuery):
    if c.from_user.id != config.OWNER_ID:
        await c.answer("‌ فقط مالک!", show_alert=True)
        return
    what = c.data.split(":", 1)[1]
    if what == "stats":
        await _edit(c, _admin_stats(), kb_admin())
    elif what == "players":
        rows = db.q("SELECT uid, name, country, level FROM users "
                    "WHERE country IS NOT NULL ORDER BY level DESC LIMIT 15")
        lines = [texts.hdr("بازیکنان", "‌"), ""]
        for r in rows:
            cc = countries.COUNTRIES.get(r["country"], {})
            lines.append(f"▫‌ <code>{r['uid']}</code> — {r['name']} · "
                         f"{cc.get('flag', '')} سطح {r['level']}")
        lines.append("")
        lines.append(texts.DASH)
        await _edit(c, "\n".join(lines), kb_admin())
    elif what == "lead":
        _pend_set(config.OWNER_ID, c.message.chat.id, "alead")
        await _edit(c, "\n".join([
            texts.hdr("تعیین یا خلع رهبر", "‌"), "",
            "✍‌ الگو را بفرست:",
            "▫‌ <code>آیدی‌عددی نام‌کشور</code> — بازیکن رهبر شود",
            "▫‌ <code>خالی نام‌کشور</code> — کشور بدون رهبر (NPC)",
            "", "«لغو» برای انصراف"]), kb_admin())
    elif what == "tog:bl":
        db.kv_set("bl_off", "" if db.kv_get("bl_off") else "1")
        await _edit(c, "\n".join([
            texts.hdr("تنظیمات", "⚙"), "",
            "‌ خبرنامه‌ی گروه: " +
            ("خاموش شد ‌" if db.kv_get("bl_off") else "روشن شد ‌")]), kb_admin())
    elif what == "tog:ev":
        db.kv_set("ev_off", "" if db.kv_get("ev_off") else "1")
        await _edit(c, "\n".join([
            texts.hdr("تنظیمات", "⚙"), "",
            "⚡ رویداد گروهی: " +
            ("خاموش شد ‌" if db.kv_get("ev_off") else "روشن شد ‌")]), kb_admin())
    elif what in ("reg", "chg"):
        _pend_set(config.OWNER_ID, c.message.chat.id,
                  "areg" if what == "reg" else "achg")
        await _edit(c, "\n".join([
            texts.hdr("ثبت یا تغییر کشور بازیکن" if what == "reg"
                      else "تغییر کشور بازیکن", "‌"), "",
            "✍‌ همین الگو را بفرست: <code>آیدی‌عددی نام‌کشور</code>",
            "مثال: <code>123456 ایران</code>",
            "", "«لغو» برای انصراف"]), kb_admin())
    elif what in ("callup", "troops"):
        for part in _admin_callup_parts():
            with contextlib.suppress(Exception):
                await c.message.answer(part, parse_mode="HTML")
        await c.answer("‌ فراخوان فرستاده شد")
        return
    await c.answer()
# ═══════════ ‌ کیبوردها ═══════════
def _taken(cid: str) -> bool:
    """آیا این کشور در همین گروه گرفته شده؟ (هر گروه دنیای خودش)"""
    return bool(db.one("SELECT 1 FROM users WHERE country=? LIMIT 1", (cid,)))
def _cy_label(cid: str) -> str:
    c = countries.COUNTRIES[cid]
    mark = " ✓" if _taken(cid) else ""
    return f"{c['flag']} {c['name']}{mark}"
def kb_countries(page=0) -> InlineKeyboardMarkup:
    ids = list(countries.COUNTRIES)
    per, p = 10, page
    chunk = ids[p * per:(p + 1) * per]
    if not chunk:
        return InlineKeyboardMarkup(inline_keyboard=[])
    rows = []
    for a, b in zip(chunk[::2], chunk[1::2]):
        rows.append([InlineKeyboardButton(text=_cy_label(a), callback_data=f"cy:{a}"),
                     InlineKeyboardButton(text=_cy_label(b), callback_data=f"cy:{b}")])
    if len(chunk) % 2:
        rows.append([InlineKeyboardButton(text=_cy_label(chunk[-1]),
                                          callback_data=f"cy:{chunk[-1]}")])
    nav = []
    if p > 0:
        nav.append(InlineKeyboardButton(text="◀‌ صفحه قبل", callback_data=f"cyp:{p-1}"))
    if (p + 1) * per < len(ids):
        nav.append(InlineKeyboardButton(text="صفحه بعد ▶‌", callback_data=f"cyp:{p+1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_un(uid) -> InlineKeyboardMarkup:
    """کیبورد اختصاصی سازمان ملل و شورای امنیت."""
    rows = [
        [InlineKeyboardButton(text="🕊️ آتش‌بس فوری", callback_data="unp:ceasefire"),
         InlineKeyboardButton(text="🚫 تحریم همه‌جانبه", callback_data="unp:sanctions")],
        [InlineKeyboardButton(text="🟢 لغو تحریم‌ها", callback_data="unp:lift_sanctions"),
         InlineKeyboardButton(text="🛡️ حافظ صلح (کلاه آبی)", callback_data="unp:peacekeeping")],
        [InlineKeyboardButton(text="💵 کمک بلاعوض اقتصادی", callback_data="unp:aid")],
        [InlineKeyboardButton(text="🗳️ رأی‌گیری قطعنامه‌ها", callback_data="unv:")],
        [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="mn:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_un_vote(res_id: int, is_p5_member: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🟢 موافق (Yes)", callback_data=f"unv:yes:{res_id}"),
         InlineKeyboardButton(text="🔴 مخالف (No)", callback_data=f"unv:no:{res_id}")],
    ]
    if is_p5_member:
        rows.append([InlineKeyboardButton(text="⛔ اعمال حق وتو (VETO)", callback_data=f"unv:veto:{res_id}")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت به سازمان ملل", callback_data="mn:un")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_straits_v40(uid) -> InlineKeyboardMarkup:
    """کیبورد تنگه‌های استراتژیک نسخه ۴۰."""
    p = state.active(uid)
    cid = p["country"] if p else None
    rows = []
    for key, s in toll.STRAITS.items():
        is_my = cid in s["owners"]
        status_txt = "⛔ مسدود" if toll.is_closed(key) else "🟢 باز"
        prefix = "⭐ " if is_my else ""
        rows.append([
            InlineKeyboardButton(text=f"{prefix}{s['name']} ({status_txt})", callback_data=f"strv40:{key}")
        ])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_strait_manage(uid, strait_key: str) -> InlineKeyboardMarkup:
    p = state.active(uid)
    cid = p["country"] if p else None
    s = toll.STRAITS.get(strait_key, {})
    is_my = cid in s.get("owners", [])
    rows = []
    if is_my:
        closed = toll.is_closed(strait_key)
        rows.append([
            InlineKeyboardButton(text="🟢 بازگشایی آبراه" if closed else "⛔ مسدود کردن آبراه", callback_data=f"strop:toggle_close:{strait_key}"),
            InlineKeyboardButton(text="💰 خاموش/روشن عوارض", callback_data=f"strop:toggle_toll:{strait_key}"),
        ])
        rows.append([InlineKeyboardButton(text="💵 برداشت درآمد صندوق", callback_data=f"strop:collect:{strait_key}")])
    else:
        rows.append([InlineKeyboardButton(text="🚢 پرداخت عوارض عبور", callback_data=f"strop:pay:{strait_key}")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت به تنگه‌ها", callback_data="mn:straits")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_bases(uid) -> InlineKeyboardMarkup:
    """کیبورد ساخت پایگاه در شهرهای کشور."""
    p = state.active(uid)
    if not p:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="mn:main")]])
    cid = p["country"]
    cities = geo.get_cities(cid)[:6]
    rows = []
    for c_name in cities:
        rows.append([
            InlineKeyboardButton(text=f"🛫 پایگاه هوایی {c_name}", callback_data=f"bldbase:airbase:{c_name}"),
            InlineKeyboardButton(text=f"🛡️ پادگان زرهی {c_name}", callback_data=f"bldbase:garrison:{c_name}"),
        ])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_operation_stages(uid, target_cid: str) -> InlineKeyboardMarkup:
    """کیبورد حملات ۵ مرحله‌ای استراتژیک."""
    rows = [
        [InlineKeyboardButton(text="۱. ⚡ انهدام برق و رادار (C4ISR)", callback_data=f"opstg:1:{target_cid}")],
        [InlineKeyboardButton(text="۲. 🛫 بمباران پایگاه‌های دشمن", callback_data=f"opstg:2:{target_cid}")],
        [InlineKeyboardButton(text="۳. 🛡️ سرکوب پدافند هوایی (SEAD)", callback_data=f"opstg:3:{target_cid}")],
        [InlineKeyboardButton(text="۴. 🚀 تهاجم موشکی و برتری هوایی", callback_data=f"opstg:4:{target_cid}")],
        [InlineKeyboardButton(text="۵. 🏙️ نبرد شهری و پیشروی لشکرها", callback_data=f"opstg:5:{target_cid}")],
        [InlineKeyboardButton(text="🏳️ تسلیم رسمی کشور", callback_data="sur:"),
         InlineKeyboardButton(text="🔙 بازگشت به جنگ", callback_data="mn:war")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_main(uid=None) -> InlineKeyboardMarkup:
    """🏛️ منوی اصلی بازی دارک‌زون — دسترسی کامل به تمام سیستم‌ها."""
    rows = [
        [InlineKeyboardButton(text="⚔️ عملیات و نبرد", callback_data="mn:war"),
         InlineKeyboardButton(text="🎖️ ارتش و زرادخانه", callback_data="mn:mil")],
        [InlineKeyboardButton(text="🏛️ سازمان ملل", callback_data="mn:un"),
         InlineKeyboardButton(text="🌊 تنگه‌ها و عوارض", callback_data="mn:straits")],
        [InlineKeyboardButton(text="🏗️ ساخت پایگاه", callback_data="mn:bases"),
         InlineKeyboardButton(text="🛡️ سپر پدافند", callback_data="mn:def")],
        [InlineKeyboardButton(text="📈 سرمایه‌گذاری", callback_data="inv:"),
         InlineKeyboardButton(text="🚢 تجارت و قرارداد", callback_data="mn:trade")],
        [InlineKeyboardButton(text="👥 سیاست و احزاب", callback_data="mn:pol"),
         InlineKeyboardButton(text="🏥 رفاه و مسکن", callback_data="mn:welf")],
        [InlineKeyboardButton(text="🎁 جایزه روزانه", callback_data="dl:"),
         InlineKeyboardButton(text="💼 کار و اشتغال", callback_data="wk:")],
        [InlineKeyboardButton(text="🌍 وضعیت جهان", callback_data="mn:world"),
         InlineKeyboardButton(text="👤 مشخصات من", callback_data="mn:me")],
        [InlineKeyboardButton(text="💸 انتقال وجه", callback_data="pay:"),
         InlineKeyboardButton(text="📖 راهنمای کامل", callback_data="mn:help")],
    ]
    if uid == config.OWNER_ID:
        rows.append([InlineKeyboardButton(text="⚙️ پنل ویژه مالک", callback_data="ad:stats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_trade(uid) -> InlineKeyboardMarkup:
    """‌ میز تجارت — + واردات (خرید) · − صادرات (فروش)."""
    rows = []
    for gid, nm, em, _ in economy.GOODS:
        rows.append([
            InlineKeyboardButton(text=f"{em} {nm} +۱", callback_data=f"tb:{gid}:1"),
            InlineKeyboardButton(text="+۵", callback_data=f"tb:{gid}:5"),
            InlineKeyboardButton(text="−۱", callback_data=f"ts:{gid}:1"),
            InlineKeyboardButton(text="−۵", callback_data=f"ts:{gid}:5")])
    if state.active(uid):
        rows.append([InlineKeyboardButton(text="‌ قرارداد تجاری", callback_data="tct:")])
    rows.append([InlineKeyboardButton(text="‌ میز تجارت", callback_data="mn:trade"),
                 InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def _howto(uid) -> str:
    """‌ راهنمای کوچک هوشمند — بر اساس وضعیت بازیکن می‌گوید چی بزن."""
    p = state.active(uid)
    lines = [texts.hdr("چی بزنم؟", "‌")]
    if not p:
        lines += ["", "‌ تازه‌ای؟ از منوی شروع کشورت را انتخاب کن.",
                  "بعد هر روز: ‌ جایزه → ‌ کار → ‌ مأموریت."]
        return "\n".join(lines)
    lines += [
        "",
        "‌ پول رایگان هر روز:",
        "▫‌ ‌ جایزه‌ی روزانه — با رگه‌ی پیوسته بیشتر می‌شود",
        "▫‌ ‌ کار کن — هر ۵ دقیقه یک شیفت",
        "▫‌ ‌ مأموریت روزانه — سه هدف، جایزه نقدی",
        "▫‌ ⚡ رویداد گروهی — هر ۴۰ دقیقه، اولین دکمه‌بزن برنده",
        "",
        "‌ پول بیشتر؟ ‌ تجارت — ارزان وارد کن، گران صادر کن؛",
        "   ‌ قرارداد تجاری — پاداش ۱۵ تا ۴۵ درصد.",
    ]
    w = war.war_of(p["country"])
    lines.append("‌ رهبری: " + ("⚔‌ در جنگی — ‌ نظامی → فرماندهی جنگ"
                                if w else "‌ در صلحی — ‌ پدافند را قوی نگه دار"))
    return "\n".join(lines)
def kb_infra(uid) -> InlineKeyboardMarkup:
    """‌ زیرساخت + ساخت‌وساز ملی — تعمیر و ساخت."""
    rows = []
    for key, name, price in infra.INFRA:
        rows.append([InlineKeyboardButton(text=f"‌ تعمیر {name}",
                                          callback_data=f"ifix:{key}")])
    for key, name, price, eff in infra.BUILDINGS:
        rows.append([InlineKeyboardButton(text=f"‌ ساخت {name} — {eff}",
                                          callback_data=f"ibld:{key}")])
    rows.append([InlineKeyboardButton(text="‌ فرماندهی نظامی", callback_data="mn:mil"),
                 InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_revolt(uid) -> InlineKeyboardMarkup:
    """‌ شورش — آغاز یا حمایت."""
    from game import politics as _po
    from game import state as _st
    p = _st.active(uid)
    rows = []
    if p:
        cid = p["country"]
        if _po._revolt(cid):
            rows.append([InlineKeyboardButton(text="‌ حمایت از شورش",
                                              callback_data="rv:x")])
        else:
            rows.append([InlineKeyboardButton(text="‌ شورش را آغاز کن",
                                              callback_data="rv:go")])
    rows.append([InlineKeyboardButton(text="‌ دفتر سیاسی", callback_data="mn:pol"),
                 InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_mil() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔‌ رزم", callback_data="mn:battle"),
         InlineKeyboardButton(text="‌ استراحت", callback_data="mn:rest")],
        [InlineKeyboardButton(text="‌ تجهیزات", callback_data="mn:arsenal"),
         InlineKeyboardButton(text="‌ تعمیر", callback_data="mn:repair")],
        [InlineKeyboardButton(text="‌ زیرساخت کشور", callback_data="mn:infra"),
         InlineKeyboardButton(text="‌ جیره", callback_data="mn:ration")],
        [InlineKeyboardButton(text="‌ عضویت نظامی", callback_data="mn:branch"),
         InlineKeyboardButton(text="‌ مأموریت روزانه", callback_data="mn:quest")],
        [InlineKeyboardButton(text="☠ بازار سیاه", callback_data="mn:black"),
         InlineKeyboardButton(text="⬆‌ ارتقای تجهیزات", callback_data="mn:upgrade")],
        [InlineKeyboardButton(text="⚔‌ نبرد تن‌به‌تن", callback_data="mn:duel"),
         InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")]])
def kb_pol() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‌ انقلاب مردمی — تغییر رژیم", callback_data="rv:")],
        [InlineKeyboardButton(text="‌ احزاب", callback_data="mn:parties"),
         InlineKeyboardButton(text="‌ شورش", callback_data="mn:rebel")],
        [InlineKeyboardButton(text="‌ جاسوسی", callback_data="mn:spy"),
         InlineKeyboardButton(text="‌ اتحاد", callback_data="mn:ally")],
        [InlineKeyboardButton(text="⚔‌ جنگ و حمله", callback_data="mn:war"),
         InlineKeyboardButton(text="‌ بیانیه", callback_data="mn:stmt")],
        [InlineKeyboardButton(text="‌ درخواست صلح", callback_data="mn:peace"),
         InlineKeyboardButton(text="‌ کمک اتحاد", callback_data="mn:helpally")],
        [InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")]])
def kb_world() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‌ وضعیت جهان", callback_data="mn:wstat"),
         InlineKeyboardButton(text="‌ رتبه", callback_data="mn:lb")],
        [InlineKeyboardButton(text="‌ قدرت کشورها", callback_data="mn:power"),
         InlineKeyboardButton(text="‌ مستعمره‌ها", callback_data="mn:colonies")],
        [InlineKeyboardButton(text="‌ بازار", callback_data="mn:market"),
         InlineKeyboardButton(text="‌ نقشه‌ی کشور", callback_data="mn:map")],
        [InlineKeyboardButton(text="‌ اخبار", callback_data="mn:news"),
         InlineKeyboardButton(text="‌ جبهه", callback_data="mn:front")],
        [InlineKeyboardButton(text="‌ ارتش کشور", callback_data="mn:army"),
         InlineKeyboardButton(text="‌ سپر ملی", callback_data="mn:def")],
        [InlineKeyboardButton(text="‌ راهنمای کشور", callback_data="mn:cguide"),
         InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")]])
def kb_def() -> InlineKeyboardMarkup:
    """تقویت لایه‌های سپر ملی — هر عضو کشور سهم دارد."""
    L = defense.LAYERS
    keys = list(L)
    rows = []
    for a, b in zip(keys[::2], keys[1::2]):
        rows.append([InlineKeyboardButton(text=f"‌ {L[a]}", callback_data=f"df:{a}"),
                     InlineKeyboardButton(text=f"‌ {L[b]}", callback_data=f"df:{b}")])
    rows.append([InlineKeyboardButton(text="‌ جبهه", callback_data="mn:front"),
                 InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_welfare(uid) -> InlineKeyboardMarkup:
    """‌ رفاه — ساخت مسجد/کلیسا/معبد/بیمارستان/مسکن."""
    from game import state as _st
    rows = []
    p = _st.active(uid)
    if p:
        nd = welfare.needs(p["country"])
        for k in nd:
            rows.append([InlineKeyboardButton(
                text=f"‌ ساخت {welfare.NAME[k]} — {texts.fa(welfare.PRICE[k])} دلار",
                callback_data=f"wbuild:{k}")])
    rows.append([InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_toll(uid) -> InlineKeyboardMarkup:
    """‌ عوارض تنگه — پرداخت / مدیریت ایران."""
    from game import state as _st
    rows = []
    p = _st.active(uid)
    if p and toll.is_on() and p["country"] != "ir":
        rows.append([InlineKeyboardButton(text="‌ پرداخت عوارض امروز",
                                          callback_data="tollpay:")])
    if p and p["country"] == "ir":
        rows.append([InlineKeyboardButton(
            text=("‌ خاموش کردن عوارض" if toll.is_on()
                  else "‌ روشن کردن عوارض"),
            callback_data="tolltog:")])
        rows.append([InlineKeyboardButton(text="‌ برداشت صندوق",
                                          callback_data="tollget:")])
    rows.append([InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_invest(uid) -> InlineKeyboardMarkup:
    """‌ سرمایه‌گذاری — خرید دارایی + برداشت درآمد ساعتی."""
    rows = []
    for key, name, price, inc in invest.ASSETS:
        rows.append([InlineKeyboardButton(
            text=f"{name} — {texts.fa(price)} دلار",
            callback_data=f"ivb:{key}")])
    rows.append([InlineKeyboardButton(text="‌ برداشت درآمد", callback_data="ivc:")])
    rows.append([InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_branches(uid) -> InlineKeyboardMarkup:
    p = state.active(uid)
    c = countries.COUNTRIES.get(p["country"]) if p else None
    rows = []
    if c:
        for i, b in enumerate(c["branches"]):
            rows.append([InlineKeyboardButton(text=f"‌ {b}", callback_data=f"br:{i}")])
    rows.append([InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_arsenal(uid) -> InlineKeyboardMarkup:
    p = state.active(uid)
    c = countries.COUNTRIES.get(p["country"]) if p else None
    rows = []
    if c:
        for iid in c["items"]:
            it = countries.ITEMS[iid]
            row_ = db.one("SELECT qty FROM inventory WHERE uid=? AND iid=?", (uid, iid))
            have = row_["qty"] if row_ else 0
            mark = f"‌{texts.fa(have)}" if have else "—"
            rows.append([
                InlineKeyboardButton(
                    text=f"{it[1]} {it[0]} · {mark}",
                    callback_data=f"wp:{iid}"),
                InlineKeyboardButton(text="×۵ خرید", callback_data=f"wp5:{iid}")])
    rows.append([InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_targets(uid, action, page=0) -> InlineKeyboardMarkup:
    """لیست صفحه‌بندی‌شده‌ی کشورها برای جاسوسی/اتحاد/جنگ/تحریم."""
    p = state.active(uid)
    own = p["country"] if p else None
    ids = [cid for cid in countries.COUNTRIES if cid != own]
    per = 10
    page = max(0, min(page, (len(ids) - 1) // per))
    chunk = ids[page * per:(page + 1) * per]
    rows = []
    for a, b in zip(chunk[::2], chunk[1::2]):
        rows.append([InlineKeyboardButton(
                         text=countries.COUNTRIES[a]["flag"] + " " + countries.COUNTRIES[a]["name"],
                         callback_data=f"{action}:{a}"),
                     InlineKeyboardButton(
                         text=countries.COUNTRIES[b]["flag"] + " " + countries.COUNTRIES[b]["name"],
                         callback_data=f"{action}:{b}")])
    if len(chunk) % 2:
        rows.append([InlineKeyboardButton(
            text=countries.COUNTRIES[chunk[-1]]["flag"] + " " + countries.COUNTRIES[chunk[-1]]["name"],
            callback_data=f"{action}:{chunk[-1]}")])
    n_pages = max(1, (len(ids) + per - 1) // per)
    if n_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀‌ صفحه قبل",
                                            callback_data=f"tp:{action}:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"‌ {texts.fa(page+1)}/{texts.fa(n_pages)}",
                                        callback_data=f"tp:{action}:{page}"))
        if (page + 1) * per < len(ids):
            nav.append(InlineKeyboardButton(text="صفحه بعد ▶‌",
                                            callback_data=f"tp:{action}:{page+1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
STRIKE_KINDS = [("موشکی", "‌", (1, 3, 5)), ("هوایی", "✈‌", (1, 3, 5)),
               ("دریایی", "‌", (1, 3)), ("زمینی", "‌", (1, 3)), ("پهپادی", "‌", (1,))]
def kb_strikes(uid=None) -> InlineKeyboardMarkup:
    """⚔‌ دکمه‌های حمله — در جنگ فقط انواع مجازِ
                                                 جغرافیایی + دکمه‌ی «چرا نه»."""
    rows = []
    p = state.active(uid) if uid else None
    w = war.war_of(p["country"]) if p else None
    for kind, emo, cnts in STRIKE_KINDS:
        ok = True
        if w:
            ok, _ = war.can_strike_kind(p["country"], war._enemy(p["country"], w), kind)
        if ok:
            rows.append([InlineKeyboardButton(text=f"{emo} {kind} {n}×",
                                              callback_data=f"st:{kind}:{n}") for n in cnts])
        else:
            why = "مرز مشترک نیست" if kind == "زمینی" else "دسترسی دریایی نیست"
            gno = "land" if kind == "زمینی" else "sea"
            rows.append([InlineKeyboardButton(text=f"‌ {kind} — {why}",
                                              callback_data=f"gno:{gno}")])
    rows.append([InlineKeyboardButton(text="‌ حمله‌ی هدفمند — انتخاب بخش",
                                      callback_data="aim:")])
    rows.append([InlineKeyboardButton(text="‌ جبهه", callback_data="mn:front"),
                 InlineKeyboardButton(text="‌ پدافند", callback_data="mn:def")])
    rows.append([InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_aims(uid=None) -> InlineKeyboardMarkup:
    """‌ انتخاب بخش زیرساخت دشمن برای حمله‌ی هدفمند."""
    rows = []
    for key, name, price in infra.INFRA:
        rows.append([InlineKeyboardButton(text=f"‌ {name}",
                                          callback_data=f"aimk:{key}")])
    rows.append([InlineKeyboardButton(text="⚔‌ حمله‌ی معمولی",
                                      callback_data="mn:front"),
                 InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_aim_kinds(uid, target: str) -> InlineKeyboardMarkup:
    """‌ نوع و تعداد حمله به بخش انتخابی."""
    rows = []
    p = state.active(uid) if uid else None
    w = war.war_of(p["country"]) if p else None
    for kind, emo, cnts in STRIKE_KINDS:
        ok = True
        if w:
            ok, _ = war.can_strike_kind(p["country"], war._enemy(p["country"], w), kind)
        if ok:
            rows.append([InlineKeyboardButton(text=f"{emo} {kind} {n}×",
                                              callback_data=f"st:{kind}:{n}:{target}")
                         for n in cnts])
    rows.append([InlineKeyboardButton(text="‌ تغییر هدف", callback_data="aim:"),
                 InlineKeyboardButton(text="‌ جبهه", callback_data="mn:front")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_duel(uid) -> InlineKeyboardMarkup:
    """⚔‌ انتخاب حریف نبرد تن‌به‌تن — بازیکنان فعالِ
                                                     همین جهان."""
    rows = db.q("SELECT uid, name, country FROM users "
                "WHERE country IS NOT NULL AND branch IS NOT NULL AND uid!=? "
                "ORDER BY last_active DESC LIMIT 12", (uid,))
    keys = []
    for r in rows:
        cc = countries.COUNTRIES.get(r["country"], {})
        keys.append([InlineKeyboardButton(
            text=f"{cc.get('flag', '')} {r['name'] or 'سرباز'}",
            callback_data=f"du:{r['uid']}")])
    if not keys:
        keys.append([InlineKeyboardButton(text="‌ حریفی نیست — بازیکنان باید عضو شاخه شوند",
                                          callback_data="mn:mil")])
    keys.append([InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=keys)
def kb_duel_accept() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔‌ قبول نبرد", callback_data="dac:")],
        [InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")]])
def kb_peace_accept() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‌ قبول صلح", callback_data="pac:")],
        [InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")]])
def kb_ally_accept(cid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‌ قبول اتحاد", callback_data=f"aac:{cid}")],
        [InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")]])
def kb_surrender() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‌‌ بله، تسلیم می‌شوم", callback_data="sury:")],
        [InlineKeyboardButton(text="↩‌ نه، برگشت", callback_data="mn:pol")]])
def kb_declare(uid) -> InlineKeyboardMarkup:
    """⚔‌ انتخاب کشور برای اعلام جنگ — صفحه‌بندی‌شده."""
    return kb_targets(uid, "dwr")
def kb_market() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‌ تحریم کشور", callback_data="snc:"),
         InlineKeyboardButton(text="‌ تنگه‌ها", callback_data="str:")],
        [InlineKeyboardButton(text="‌ بازار جهانی", callback_data="mn:market"),
         InlineKeyboardButton(text="‌ شورای امنیت", callback_data="mn:world")]])
def kb_straits() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‌ هرمز", callback_data="str:هرمز"),
         InlineKeyboardButton(text="‌ باب‌المندب", callback_data="str:باب‌المندب")],
        [InlineKeyboardButton(text="‌ تایوان", callback_data="str:تایوان"),
         InlineKeyboardButton(text="‌ سوئز", callback_data="str:سوئز")],
        [InlineKeyboardButton(text="‌ بازار جهانی", callback_data="mn:market"),
         InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")]])
def kb_sanction(uid) -> InlineKeyboardMarkup:
    """‌ انتخاب کشور برای تحریم — صفحه‌بندی‌شده."""
    return kb_targets(uid, "snc")
def kb_black(uid) -> InlineKeyboardMarkup:
    """☠ دکمه‌های خرید قاچاق — همان نمونه‌ی ساعتی بازار سیاه."""
    rows = []
    for iid in military.black_sample(uid):
        it = countries.ITEMS[iid]
        c = countries.COUNTRIES[it[2]]
        own = db.one("SELECT 1 FROM inventory WHERE uid=? AND iid=?", (uid, iid))
        mark = "‌" if own else "‌"
        rows.append([InlineKeyboardButton(
            text=f"{it[1]} {it[0]} ({c['flag']}) — {mark}",
            callback_data=f"bb:{iid}")])
    rows.append([InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_quests() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‌ دریافت جایزه", callback_data="qc:")],
        [InlineKeyboardButton(text="‌ مأموریت‌ها", callback_data="mn:quest"),
         InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")]])
def kb_parties(uid) -> InlineKeyboardMarkup:
    """‌ فهرست احزاب با دکمه‌ی عضویت + حزب جدید."""
    p = state.active(uid)
    rows = []
    if p:
        for r in db.q("SELECT id, name, members FROM parties WHERE country=? "
                      "ORDER BY power DESC LIMIT 10", (p["country"],)):
            rows.append([InlineKeyboardButton(
                text=f"‌ {r['name']} — ‌{texts.fa(r['members'])}",
                callback_data=f"pj:{r['id']}")])
    rows.append([InlineKeyboardButton(text="‌ حزب جدید", callback_data="pnew:")])
    rows.append([InlineKeyboardButton(text="‌ دفتر سیاسی", callback_data="mn:pol"),
                 InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def kb_cancel_pol() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‌ لغو", callback_data="pcancel:")],
        [InlineKeyboardButton(text="‌ دفتر سیاسی", callback_data="mn:pol")]])
# ✍‌ ورودی آزاد در انتظار: بیانیه / حزب — بعد از دکمه، پیام بعدی کاربر همین می‌شود
_pending: dict = {}
def _pend_set(uid: int, chat_id: int, kind: str, ttl: int = 300):
    _pending[(uid, chat_id)] = (kind, time.time() + ttl)
def _pend_pop(uid: int, chat_id: int):
    kind, exp = _pending.pop((uid, chat_id), (None, 0))
    return kind if kind and time.time() <= exp else None
# ═══════════ ‌ شروع ═══════════
def _join_text(gid, uname: str = "") -> str:
    """⚔‌ متن خوش‌آمد گروه — یک بار، پین می‌شود."""
    lines = [texts.hdr("جنگ جهانی آغاز شد", "⚔‌"), "",
             "‌ کشورت را انتخاب کن — هر که انتخاب کند ‌ رهبر همان کشور است.",
             "‌ کشور گرفته‌شده قفل می‌شود — عجله کن!",
             f"‌ جهان این گروه: <code>{texts.fa(gid) if gid > 0 else texts.fa(-gid)}</code>"]
    if uname:
        lines.append(f"‌ ربات: @{uname}")
    lines += ["",
              "‌ اشتباهی کشورت را زدی؟ آیدی عددی‌ات را (از ‌ پروفایل) برای مالک بفرست",
              "   تا کشورت را عوض کند — فقط مالک می‌تواند.",
              "", "‌ شروع: دکمه‌های زیر یا نوشتن «شروع»"]
    return "\n".join(lines)
async def _group_hello(bt, gid: int, uname: str = ""):
    """⚔‌ یک‌بار برای هر گروه: معرفی + انتخاب کشور + پین.
    زمینه‌ی دیتابیس موقتاً
                           به دنیای همین گروه می‌رود و در پایان برمی‌گردد.
    """
    if gid >= 0:
        return
    prev = db.GAME.get()
    try:
        with contextlib.suppress(Exception):
            db.GAME.set(gid)      # چک و نوشتن در دیتابیسِ همین گروه
        if db.kv_get(f"joined:{gid}") or not bt:
            return
        db.kv_set(f"joined:{gid}", "1")
        with contextlib.suppress(Exception):
            sent = await bt.send_message(gid, _join_text(gid, uname),
                                         reply_markup=kb_countries())
            with contextlib.suppress(Exception):
                await bt.pin_chat_message(gid, sent.message_id,
                                          disable_notification=True)
    finally:
        with contextlib.suppress(Exception):
            db.GAME.set(prev)
@router.my_chat_member()
async def on_my_chat_member(ev):
    """‌ ربات به گروه اضافه شد → خوش‌آمد + پین (یک بار)."""
    st = ""
    with contextlib.suppress(Exception):
        st = ev.new_chat_member.status
    if st in ("member", "administrator") and ev.chat.id < 0:
        uname = ""
        with contextlib.suppress(Exception):
            me = await ev.bot.get_me()
            uname = me.username
        await _group_hello(ev.bot, ev.chat.id, uname)
# ═══════════ ‌ شروع ═══════════
# ═══ ⌨‌ پل دستورهای اسلش — حتی با پرایوسی‌مودِ تلگرام، /دستورها همیشه می‌رسند ═══
_SLASH_MAP = {
    "menu": "منو", "help": "راهنما", "commands": "دستورها", "cmds": "دستورها",
    "buy": "خرید", "shop": "خرید", "arsenal": "زرادخانه",
    "attack": "حمله", "war": "جنگ", "fight": "حمله",
    "trade": "تجارت", "profile": "پروفایل", "me": "پروفایل", "world": "جهان",
    "invest": "سرمایه", "mine": "معدن", "infra": "زیرساخت",
    "revolt": "انقلاب", "welfare": "رفاه", "toll": "عوارض",
}
@router.message(Command(*list(_SLASH_MAP)))
async def cmd_slash_bridge(m: Message):
    """/menu → منو و ... — همان نتیجه، مسیر همیشه‌سالم."""
    if not m.text:
        return
    name = m.text.split()[0][1:].split("@")[0].lower()
    word = _SLASH_MAP.get(name)
    if not word:
        return
    m.text = word
    return await fa_words(m)
@router.message(Command("start"))
@router.message(F.text.in_(["شروع", "استارت", "شروع کن", "شروع بازی", "استارت کن"]))
async def cmd_start(m: Message):
    state.ensure(m.from_user.id, m.from_user.first_name, m.chat.id)
    await _group_hello(bot, m.chat.id)
    if state.active(m.from_user.id):
        sent = await m.answer(state.card(m.from_user.id), parse_mode="HTML",
                              reply_markup=kb_main(m.from_user.id))
        _own(m, sent, m.from_user.id)
        return
    if os.path.exists("assets/img/cover.jpg"):
        with open("assets/img/cover.jpg", "rb"):
            sent = await m.answer_photo(FSInputFile("assets/img/cover.jpg"),
                                        caption=texts.WELCOME, parse_mode="HTML",
                                        reply_markup=kb_countries())
            _own(m, sent, m.from_user.id)
    else:
        sent = await m.answer(texts.WELCOME, parse_mode="HTML",
                              reply_markup=kb_countries())
        _own(m, sent, m.from_user.id)
@router.callback_query(F.data.startswith("cyp:"))
async def cb_cy_page(c: CallbackQuery):
    await c.message.edit_reply_markup(reply_markup=kb_countries(int(c.data.split(":")[1])))
    await c.answer()
@router.callback_query(F.data.startswith("cy:"))
async def cb_country(c: CallbackQuery):
    uid = c.from_user.id
    if state.active(uid):
        await c.answer("قبلاًثبت‌نام کردی.", show_alert=True)
        return
    cid = c.data.split(":")[1]
    if _taken(cid):                       # ✓ کشور گرفته‌شده — در همین گروه
        await c.answer("✓ این کشور قبلاًگرفته شده — کشور دیگری انتخاب کن",
                       show_alert=True)
        return
    ok = state.enlist(uid, cid, c.from_user.first_name or "سرباز")
    if not ok:
        await c.answer("خطا — دوباره امتحان کن.", show_alert=True)
        return
    db.ex("UPDATE users SET is_leader=1 WHERE uid=?", (uid,))   # ‌ بازیکن = رهبر
    co = countries.COUNTRIES[cid]
    t = texts
    await c.message.delete()
    await c.message.answer("\n".join([
        t.hdr("ثبت‌نام تکمیل شد", "‌"),
        t.row("کشور", f"{co['flag']} {co['name']}"),
        t.row("نقش", "‌ رهبر کشور"),
        t.row("خزانه", "‌ ۱٬۰۰۰"),
        "", "‌ اولین قدم: «عضویت نظامی» — سپس تجهیزات بخر.",
        "‌ منوی اصلی: «منو»"]), parse_mode="HTML", reply_markup=kb_mil())
    await c.answer()
# ═══════════ ‌ منوها ═══════════
async def _edit(c: CallbackQuery, text: str, kb=None):
    try:
        await c.message.edit_text(text[:4000], parse_mode="HTML",
                                  reply_markup=kb or kb_main())
    except Exception:
        sent = await c.message.answer(text[:4000], parse_mode="HTML",
                                      reply_markup=kb or kb_main())
        _own(c.message, sent, c.from_user.id)
@router.callback_query(F.data.startswith("hp:"))
async def cb_helppage(c: CallbackQuery):
    try:
        page = max(1, min(len(texts.HELP_PAGES), int(c.data.split(":")[1])))
    except ValueError:
        page = 1
    body = texts.HELP_PAGES[page - 1]
    # ‌ جایزه‌ی مطالعه — همه‌ی صفحات را بخوان، 300 دلار + نشان
    uid = c.from_user.id
    if state.active(uid):
        read = int(db.kv_get(f"read:{uid}", "0") or 0)
        if page > read:
            db.kv_set(f"read:{uid}", str(page))
            read = page
        last = len(texts.HELP_PAGES)
        if read >= last and not db.kv_get(f"guide_done:{uid}"):
            db.kv_set(f"guide_done:{uid}", "1")
            db.ex("UPDATE users SET money=money+300 WHERE uid=?", (uid,))
            body = (body + "\n\n" + texts.hdr("جایزه‌ی مطالعه", "‌") +
                    "‌ همه‌ی راهنما را خواندی! +300 دلار جایزه" +
                    " + نشان «‌ دانش‌آموخته» به پروفایلت اضافه شد"
                    )[:4000]
    await _edit(c, body, kb_help(page))
    await c.answer()
@router.callback_query(F.data.startswith("df:"))
async def cb_defense(c: CallbackQuery):
    uid = c.from_user.id
    layer = c.data.split(":", 1)[1]
    msg = defense.strengthen(uid, layer)
    p = state.active(uid)
    if p:
        msg += "\n\n" + defense.status(p["country"])
    await _edit(c, msg, kb_def())
    await c.answer()
@router.callback_query(F.data.startswith("mn:"))
async def cb_menu(c: CallbackQuery):
    uid = c.from_user.id
    what = c.data.split(":", 1)[1]
    if not state.active(uid) and what not in ("help",):
        await c.answer("‌ اول «شروع»", show_alert=True)
        return
    if what == "main":
        await _edit(c, state.card(uid), kb_main())
    elif what == "mil":
        await _edit(c, texts.hdr("فرماندهی نظامی", "‌") + "\n\nیکی را انتخاب کن:", kb_mil())
    elif what == "infra":
        await _edit(c, infra.view(uid) + "\n\n" + infra.buildings_view(uid),
                    kb_infra(uid))
    elif what == "welf":
        await _edit(c, welfare.view(uid), kb_welfare(uid))
    elif what == "pol":
        await _edit(c, texts.hdr("دفتر سیاسی", "‌") + "\n\nیکی را انتخاب کن:", kb_pol())
    elif what == "world":
        await _edit(c, texts.hdr("شورای امنیت", "‌") + "\n\nیکی را انتخاب کن:", kb_world())
    elif what == "me":
        await _edit(c, state.card(uid), kb_main())
    elif what == "battle":
        await _edit(c, military.battle(uid), kb_mil())
    elif what == "rest":
        await _edit(c, military.rest(uid), kb_mil())
    elif what == "arsenal":
        await _edit(c, military.arsenal(uid), kb_arsenal(uid))
    elif what == "repair":
        await _edit(c, military.repair(uid), kb_mil())
    elif what == "ration":
        await _edit(c, state.ration(uid), kb_mil())
    elif what == "branch":
        c2 = countries.COUNTRIES.get(p["country"]) if (p := state.active(uid)) else None
        blines = []
        if c2:
            for i, b in enumerate(c2["branches"]):
                _k, _rn, _rf = military.role_of({"branch": i, "country": p["country"]})
                blines.append(f"‌ <b>{b}</b>\n   ‌ {_rn} — {_rf}")
        await _edit(c, texts.hdr("انتخاب شاخه", "‌") + "\n\nهر شاخه یک اثر واقعی دارد:\n\n"
                    + "\n\n".join(blines), kb_branches(uid))
    elif what == "parties":
        await _edit(c, politics.list_parties(uid), kb_parties(uid))
    elif what == "rebel":
        await _edit(c, politics.rebel(uid), kb_pol())
    elif what == "stmt":
        _pend_set(uid, c.message.chat.id, "stmt")
        await _edit(c, "\n".join([
            texts.hdr("بیانیه‌ی رسمی", "‌"), "",
            "‌ <b>متن بیانیه را در همین گروه بنویس</b>",
            "هر پیامی که بفرستی، بیانیه‌ی رسمی حزب می‌شود.", "",
            "‌ حداقل ۱۰ حرف · ثبت دائمی · ⚡ قدرت حزب +۱۰", "",
            "‌ لغو: بنویس «لغو»"]), kb_cancel_pol())
    elif what == "spy":
        await _edit(c, texts.hdr("عملیات جاسوسی", "‌") + "\n\nکشور هدف را انتخاب کن:",
                    kb_targets(uid, "spy"))
    elif what == "ally":
        await _edit(c, texts.hdr("پیشنهاد اتحاد", "‌") + "\n\nبا کدام کشور؟",
                    kb_targets(uid, "ally"))
    elif what == "war":
        p = state.active(uid)
        if p and war.war_of(p["country"]):
            await _edit(c, war.front(uid), kb_strikes(uid))
        else:
            await _edit(c, "\n".join([
                texts.hdr("فرماندهی جنگ", "⚔‌"), "",
                "‌ کشورت در جنگ نیست.", "",
                "کشور هدف را انتخاب کن — ‌ فقط رهبر:"]), kb_declare(uid))
    elif what == "wstat":
        await _edit(c, war.world_status(), kb_world())
    elif what == "power":
        await _edit(c, war.power_rank(), kb_world())
    elif what == "colonies":
        await _edit(c, war.colonies(), kb_world())
    elif what == "lb":
        await _edit(c, war.leaderboard(), kb_world())
    elif what == "market":
        await _edit(c, economy.market(), kb_market())
    elif what == "map":
        p = state.active(uid)
        await _edit(c, geo.country_map(p["country"]) if p else "‌ اول «شروع»", kb_world())
    elif what == "help":
        await _edit(c, texts.HELP_PAGES[0], kb_help(1))
    elif what == "cguide":
        p = state.active(uid)
        await _edit(c, guide.guide(p["country"]) if p else "‌ اول «شروع»", kb_world())
    elif what == "news":
        await _edit(c, ai.news_feed(), kb_world())
    elif what == "trade":
        await _edit(c, economy.trade_view(uid), kb_trade(uid))
    elif what == "howto":
        await _edit(c, _howto(uid), kb_main(uid))
    elif what == "events":
        st = db.jload(db.kv_get(f"ev:{c.message.chat.id}"), None) or {}
        if st.get("active") and db.now() < int(st.get("deadline", 0)):
            ev_txt = next((e[0] for e in events.EVENTS
                           if e[1] == st.get("word")), "⚡ رویداد زنده است")
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚡ شرکت در رویداد",
                                      callback_data=f"evc:{st['word']}")],
                [InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")]])
            await _edit(c, texts.hdr("رویداد زنده", "⚡") + "\n\n" + ev_txt, kb)
        else:
            await _edit(c, "\n".join([
                texts.hdr("رویدادهای گروهی", "⚡"), "",
                "‌ هر ۴۰ دقیقه یک رویداد در گروه می‌آید —",
                "اولین دکمه‌بزن جایزه می‌گیرد:",
                "‌ قرارداد تسلیحاتی ‌۴۰۰ · ‌ فراخوان رزمی ‌۱۲۰XP · ‌ رمز ‌۲۰۰",
                "", "چشم انتظار باش!"]), kb_main(uid))
    elif what == "front":
        await _edit(c, war.front(uid), kb_strikes(uid))
    elif what == "army":
        await _edit(c, war.army(uid), kb_world())
    elif what == "def":
        p = state.active(uid)
        await _edit(c, defense.status(p["country"]) if p else "‌ اول «شروع»", kb_def())
    elif what == "quest":
        await _edit(c, quests.view(uid), kb_quests())
    elif what == "black":
        await _edit(c, military.blackmarket(uid), kb_black(uid))
    elif what == "upgrade":
        p = state.active(uid)
        if not p:
            await _edit(c, "‌ اول «شروع»", kb_mil())
        else:
            own = db.q("SELECT iid FROM inventory WHERE uid=?", (uid,))
            rows = []
            for r in own:
                it = countries.ITEMS[r["iid"]]
                lvl = military.item_level(uid, r["iid"])
                rows.append([InlineKeyboardButton(
                    text=f"{it[1]} {it[0]} — سطح {texts.fa(lvl)}"
                    + (" (مکس)" if lvl >= 3 else " ⬆‌"),
                    callback_data=f"up:{r['iid']}")])
            rows.append([InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")])
            await _edit(c, texts.hdr("ارتقای تجهیزات", "⬆‌") + "\n\nتجهیزات خودت:",
                        InlineKeyboardMarkup(inline_keyboard=rows))
    elif what == "duel":
        await _edit(c, "\n".join([
            texts.hdr("نبرد تن‌به‌تن", "⚔‌"), "",
            "حریفت را انتخاب کن:", "",
            "‌ برنده: ‌ ۶۰۰ · ‌ ۱۵۰ XP",
            "‌ بازنده: −۳۰ جان",
            "‌ حریف ۵ دقیقه فرصت دارد قبول کند."]), kb_duel(uid))
    elif what == "peace":
        msg = war.peace_request(uid)
        await _edit(c, msg, kb_peace_accept() if "ارسال شد" in msg else kb_pol())
    elif what == "helpally":
        await _edit(c, war.call_help(uid), kb_pol())
    await c.answer()
@router.callback_query(F.data == "aim:")
async def cb_aim(c: CallbackQuery):
    """‌ انتخاب بخش زیرساخت دشمن."""
    p = state.active(c.from_user.id)
    if not p or not war.war_of(p["country"]):
        return await c.answer("⚔‌ اول در جنگ باشی!", show_alert=True)
    await _edit(c, texts.hdr("حمله‌ی هدفمند", "‌") +
                "\n\nکدام بخشِزیرساخت دشمن را بزنیم؟\n"
                "‌ هدفمند = ۵۰٪ شانس آسیب مستقیم ۱۰–۱۶٪ به همان بخش.",
                kb_aims(c.from_user.id))
@router.callback_query(F.data.startswith("aimk:"))
async def cb_aim_kind(c: CallbackQuery):
    """‌ نوع حمله به بخش انتخابی."""
    tgt = c.data.split(":", 1)[1]
    await _edit(c, texts.hdr("حمله‌ی هدفمند", "‌") + "\n\nنوع و تعداد حمله:",
                kb_aim_kinds(c.from_user.id, tgt))
@router.callback_query(F.data.startswith("rv:"))
async def cb_revolt(c: CallbackQuery):
    """‌ شورش — آغاز یا حمایت."""
    if c.data == "rv:":
        out = politics.revolt_view(c.from_user.id)
    elif c.data == "rv:s":
        out = politics.revolt_view(c.from_user.id)      # فقط دیدن وضعیت
    elif c.data == "rv:go":
        out = politics.revolt_start(c.from_user.id)
    else:
        out = politics.revolt_support(c.from_user.id)
    await _edit(c, out, kb_revolt(c.from_user.id))
    # ‌ خبر شورش موفق
    bbc = war.bbc_pop()
    if bbc and not TEST_MODE:
        with contextlib.suppress(Exception):
            await c.message.answer(texts.fx(bbc), parse_mode="HTML")
    await c.answer()
# ═══ ‌ پنل دائمی گروه — دکمه‌ها همیشه کار می‌کنند (حتی با پرایوسی‌مود) ═══
PANEL_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="‌ منوی من", callback_data="pm:menu"),
     InlineKeyboardButton(text="‌ راهنما", callback_data="pm:help")],
    [InlineKeyboardButton(text="‌ رفاه", callback_data="pm:welf"),
     InlineKeyboardButton(text="‌ عوارض", callback_data="pm:toll"),
     InlineKeyboardButton(text="‌ سرمایه", callback_data="pm:inv")],
    [InlineKeyboardButton(text="⚔‌ حمله و جنگ", callback_data="pm:war")]])
def panel_text() -> str:
    return "\n".join([
        texts.hdr("پنل بازی — همیشه فعال", "‌"),
        "‌ هر دکمه‌ای را بزنی، <b>منوی خودت</b> همین‌جا پایین چت می‌آید.",
        "این پنل همیشه کار می‌کند — نیازی به دستور متنی نیست.",
        "",
        "⌨‌ راه‌های دیگر: دکمه‌ی «/» گوشه‌ی چت · ریپلای به بات · @REDarkZoneBot منو"])
@router.callback_query(F.data.startswith("pm:"))
async def cb_panel(c: CallbackQuery):
    """‌ پنل — منوی تازه و خصوصی برای زننده‌ی دکمه."""
    uid = c.from_user.id
    what = c.data.split(":", 1)[1]
    p = state.active(uid)
    if not p:
        sent = await c.message.answer(texts.WELCOME, parse_mode="HTML",
                                      reply_markup=kb_countries())
        _own(c, sent, uid)
        await c.answer()
        return
    views = {"menu": (state.card(uid), kb_main(uid)),
             "help": (texts.HELP_PAGES[0], kb_help(1)),
             "welf": (welfare.view(uid), kb_welfare(uid)),
             "toll": (toll.status(uid), kb_toll(uid)),
             "inv": (invest.view(uid), kb_invest(uid))}
    txt, kb = views.get(what, (state.card(uid), kb_main(uid)))
    with contextlib.suppress(Exception):
        txt = txt[:4000]
    sent = await c.message.answer(txt, parse_mode="HTML", reply_markup=kb)
    _own(c, sent, uid)
    await c.answer()
@router.callback_query(F.data.startswith("wbuild:"))
async def cb_welfare_build(c: CallbackQuery):
    """‌ ساخت اماکن رفاه."""
    await _edit(c, welfare.build(c.from_user.id, c.data.split(":", 1)[1]),
                kb_welfare(c.from_user.id))
    await _send_bbc(c.message.chat.id)
@router.callback_query(F.data == "toll:")
async def cb_toll(c: CallbackQuery):
    """‌ وضعیت عوارض تنگه."""
    await _edit(c, toll.status(c.from_user.id), kb_toll(c.from_user.id))
@router.callback_query(F.data == "tollpay:")
async def cb_toll_pay(c: CallbackQuery):
    await _edit(c, toll.pay(c.from_user.id), kb_toll(c.from_user.id))
@router.callback_query(F.data == "tolltog:")
async def cb_toll_toggle(c: CallbackQuery):
    msg, ann = toll.toggle(c.from_user.id)
    await _edit(c, msg, kb_toll(c.from_user.id))
    if ann:
        with contextlib.suppress(Exception):
            await c.message.answer(texts.fx(ann), parse_mode="HTML")
@router.callback_query(F.data == "tollget:")
async def cb_toll_get(c: CallbackQuery):
    await _edit(c, toll.collect(c.from_user.id), kb_toll(c.from_user.id))
@router.callback_query(F.data.startswith("ibld:"))
async def cb_infra_build(c: CallbackQuery):
    """‌ ساخت ساختمان ملی."""
    await _edit(c, infra.build(c.from_user.id, c.data.split(":", 1)[1]),
                kb_infra(c.from_user.id))
@router.callback_query(F.data.startswith("ifix:"))
async def cb_infra_fix(c: CallbackQuery):
    """‌ تعمیر زیرساخت با دلار."""
    await _edit(c, infra.repair(c.from_user.id, c.data.split(":", 1)[1]),
                kb_infra(c.from_user.id))
@router.callback_query(F.data == "inv:")
async def cb_invest(c: CallbackQuery):
    """‌ سرمایه‌گذاری — دارایی‌های درآمد ساعتی."""
    await _edit(c, invest.view(c.from_user.id), kb_invest(c.from_user.id))
@router.callback_query(F.data.startswith("ivb:"))
async def cb_invest_buy(c: CallbackQuery):
    await _edit(c, invest.buy(c.from_user.id, c.data.split(":", 1)[1]),
                kb_invest(c.from_user.id))
@router.callback_query(F.data == "ivc:")
async def cb_invest_collect(c: CallbackQuery):
    await _edit(c, invest.collect(c.from_user.id), kb_invest(c.from_user.id))
@router.callback_query(F.data.startswith("br:"))
async def cb_branch(c: CallbackQuery):
    await c.message.edit_text(military.join_branch(c.from_user.id, int(c.data.split(":")[1])),
                              parse_mode="HTML", reply_markup=kb_mil())
    await c.answer()
@router.callback_query(F.data.startswith("wp5:"))
@router.callback_query(F.data.startswith("wp:"))
async def cb_buy(c: CallbackQuery):
    uid = c.from_user.id
    qty = 5 if c.data.startswith("wp5:") else 1
    iid = c.data.split(":")[1]
    msg = military.buy(uid, iid, qty)
    await c.answer(msg[:180], show_alert=not msg.startswith("‌"))
    if msg.startswith("‌"):
        with contextlib.suppress(Exception):
            await c.message.edit_text(military.arsenal(uid), parse_mode="HTML",
                                      reply_markup=kb_arsenal(uid))
        # ‌ عکس تجهیزات — اختصاصی اگر باشد، وگرنه عکس دسته‌ای
        # ‌ حداکثر یک عکس در ۹۰ ثانیه — ضدفلود تلگرام
        it = countries.ITEMS.get(iid)
        if it and db.now() - int(db.kv_get(f"bph:{uid}", "0")) > 90:
            db.kv_set(f"bph:{uid}", str(db.now()))
            own = f"assets/img/{it[6]}" if it[6] else ""
            img = own if (own and os.path.exists(own)) else countries.category_img(it[0])
            if os.path.exists(img):
                with contextlib.suppress(Exception):
                    with open(img, "rb"):
                        await c.message.answer_photo(
                            FSInputFile(img),
                            caption=(f"{it[1]} <b>{it[0]}</b>\n"
                                     f"⚔‌ حمله {it[3]} · ‌ دفاع {it[4]}\n"
                                     f"‌ دوام ۱۰۰٪ — حالا قسمت توست."),
                            parse_mode="HTML")
    return
@router.callback_query(F.data.startswith("up:"))
async def cb_upgrade(c: CallbackQuery):
    await c.message.edit_text(military.upgrade(c.from_user.id, c.data.split(":")[1]),
                              parse_mode="HTML", reply_markup=kb_mil())
    await c.answer()
@router.callback_query(F.data.startswith("spy:"))
async def cb_spy(c: CallbackQuery):
    await c.message.edit_text(politics.spy(c.from_user.id, c.data.split(":")[1]),
                              parse_mode="HTML", reply_markup=kb_pol())
    await c.answer()
@router.callback_query(F.data.startswith("ally:"))
async def cb_ally(c: CallbackQuery):
    cid = c.data.split(":")[1]
    msg = war.alliance_request(c.from_user.id, cid)
    p = state.active(c.from_user.id)
    # دکمه‌ی قبول باید کشورِ درخواست‌دهنده را ببرد — نه هدف را
    kb = kb_ally_accept(p["country"]) if ("ارسال شد" in msg and p) else kb_pol()
    await c.message.edit_text(msg, parse_mode="HTML", reply_markup=kb)
    await c.answer()
async def _send_bbc(chat_id):
    """‌ خبر فوری معلق را با ایموجی جنگی بفرست."""
    bbc = war.bbc_pop()
    if bbc and bot:
        with contextlib.suppress(Exception):
            await bot.send_message(chat_id, texts.fx(bbc), parse_mode="HTML")
async def _delayed_missile(chat_id, uid):
    """‌ برخورد موج موشکی بعد از زمان پرواز — ارسال خودکار به گروه."""
    await asyncio.sleep(war.MISSILE_FLIGHT)
    msg = war.resolve_missile(uid)
    if msg and bot:
        with contextlib.suppress(Exception):
            await bot.send_message(chat_id, texts.fx(msg), parse_mode="HTML")
        bbc = war.bbc_pop()
        if bbc:
            with contextlib.suppress(Exception):
                await bot.send_message(chat_id, texts.fx(bbc), parse_mode="HTML")
@router.callback_query(F.data.startswith("gno:"))
async def cb_geo_no(c: CallbackQuery):
    """توضیح اینکه چرا این نوع حمله جغرافیایی ممکن نیست."""
    why = ("‌ حمله‌ی زمینی مرز زمینی مشترک می‌خواهد — کشورت و دشمن همسایه نیستند. "
           "از حمله‌ی هوایی، موشکی یا پهپادی استفاده کن." if c.data == "gno:land" else
           "‌ حمله‌ی دریایی به آب‌های آزاد نیاز دارد — یک طرف به دریا دسترسی ندارد. "
           "از حمله‌ی هوایی، موشکی یا پهپادی استفاده کن.")
    await c.answer(why, show_alert=True)
@router.callback_query(F.data.startswith("st:"))
async def cb_strike(c: CallbackQuery):
    uid = c.from_user.id
    parts = c.data.split(":")
    kind = parts[1]
    count = int(parts[2]) if len(parts) > 2 else 1
    target = parts[3] if len(parts) > 3 else None
    if kind == "موشکی":
        # ‌ پرتاب — برخورد بعد از زمان پرواز؛ دشمن فرصت تقویت پدافند دارد
        msg = war.launch_missile(uid, count, target)
        if "در راه" in msg:
            await _sticker(c.message.chat, "‌")
            if TEST_MODE:
                msg += "\n\n" + war.resolve_missile(uid)
            else:
                asyncio.create_task(_delayed_missile(c.message.chat.id, uid))
    else:
        msg = war.strike(uid, kind, count, target)
    try:
        await c.message.edit_text(texts.fx(msg), parse_mode="HTML",
                                  reply_markup=kb_strikes(uid))
    except Exception:
        await c.message.edit_text(msg, parse_mode="HTML",
                                  reply_markup=kb_strikes(uid))
    # ‌ خبر فوری بی‌بی‌سی — جداگانه در گروه، با ایموجی جنگی
    bbc = war.bbc_pop()
    if bbc and not TEST_MODE:
        with contextlib.suppress(Exception):
            await c.message.answer(texts.fx(bbc), parse_mode="HTML")
    await c.answer()
# ═══════════ ‌ درآمد و تجارت — کاملاً دکمه‌ای ═══════════
@router.callback_query(F.data == "dl:")
async def cb_daily(c: CallbackQuery):
    await _edit(c, state.daily(c.from_user.id), kb_main(c.from_user.id))
    await c.answer()
@router.callback_query(F.data == "wk:")
async def cb_work(c: CallbackQuery):
    await _edit(c, state.work(c.from_user.id), kb_main(c.from_user.id))
    await c.answer()
@router.callback_query(F.data.startswith("evc:"))
async def cb_evc(c: CallbackQuery):
    """⚡ شرکت در رویداد — روی خود پیام رویداد؛ نتیجه همان‌جا."""
    word = c.data.split(":", 1)[1]
    r = events.claim(c.message.chat.id, c.from_user.id, word)
    if not r:
        return await c.answer("‌ دیر رسیدی — رویداد تمام شد یا کسی زودتر زد.")
    base = (getattr(c.message, "text", "") or "").strip()
    txt = (base + "\n────\n" + r) if base else r
    with contextlib.suppress(Exception):
        await c.message.edit_text(txt[:4000], parse_mode="HTML")
    await c.answer("‌ ثبت شد!")
@router.callback_query(F.data.startswith("tb:"))
async def cb_tbuy(c: CallbackQuery):
    uid = c.from_user.id
    _, gid, q = c.data.split(":")
    msg = economy.trade_buy(uid, gid, int(q))
    if msg.startswith("‌"):
        msg += "\n\n" + economy.trade_view(uid)
    await _edit(c, msg, kb_trade(uid))
    await c.answer()
@router.callback_query(F.data.startswith("ts:"))
async def cb_tsell(c: CallbackQuery):
    uid = c.from_user.id
    _, gid, q = c.data.split(":")
    msg = economy.trade_sell(uid, gid, int(q))
    if msg.startswith("‌"):
        msg += "\n\n" + economy.trade_view(uid)
    await _edit(c, msg, kb_trade(uid))
    await c.answer()
@router.callback_query(F.data == "tct:")
async def cb_tcontract(c: CallbackQuery):
    uid = c.from_user.id
    p = state.active(uid)
    if not p:
        await _edit(c, "‌ اول «شروع» — کشورت را انتخاب کن.", kb_trade(uid))
    else:
        await _edit(c, texts.hdr("قرارداد تجاری", "‌") + "\n\nبا کدام کشور؟",
                    kb_targets(uid, "ct"))
    await c.answer()
@router.callback_query(F.data.startswith("ct:"))
async def cb_contract(c: CallbackQuery):
    uid = c.from_user.id
    msg = economy.contract(uid, c.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‌ میز تجارت", callback_data="mn:trade")],
        [InlineKeyboardButton(text="‌ منوی اصلی", callback_data="mn:main")]])
    await _edit(c, msg, kb)
    await c.answer()
# ═══════════ ⚔‌ نبرد تن‌به‌تن — کاملاً دکمه‌ای ═══════════
@router.callback_query(F.data.startswith("du:"))
async def cb_duel(c: CallbackQuery):
    uid = c.from_user.id
    try:
        target_uid = int(c.data.split(":")[1])
    except ValueError:
        target_uid = 0
    target = state.get(target_uid)
    if not target:
        await c.answer("‌ حریف پیدا نشد.", show_alert=True)
        return
    msg = war.duel_request(uid, target["name"] or "سرباز", target_uid)
    await _edit(c, msg, kb_duel_accept() if "چالش" in msg else kb_mil())
    await c.answer()
@router.callback_query(F.data.startswith("dac:"))
async def cb_duel_accept(c: CallbackQuery):
    await _edit(c, war.duel_accept(c.from_user.id), kb_mil())
    await c.answer()
# ═══════════ ‌ صلح · ‌ اتحاد · ‌ تسلیم ═══════════
@router.callback_query(F.data.startswith("pac:"))
async def cb_peace_accept(c: CallbackQuery):
    await _edit(c, war.peace_accept(c.from_user.id), kb_pol())
    await c.answer()
@router.callback_query(F.data.startswith("aac:"))
async def cb_ally_accept(c: CallbackQuery):
    await _edit(c, war.alliance_accept(c.from_user.id, c.data.split(":")[1]), kb_pol())
    await c.answer()
@router.callback_query(F.data.startswith("sury:"))
async def cb_surrender_yes(c: CallbackQuery):
    await _edit(c, war.surrender(c.from_user.id), kb_pol())
    await c.answer()
@router.callback_query(F.data.startswith("sur:"))
async def cb_surrender(c: CallbackQuery):
    p = state.active(c.from_user.id)
    if not p:
        await c.answer("‌ اول «شروع» — کشورت را انتخاب کن.", show_alert=True)
        return
    await _edit(c, "\n".join([
        texts.hdr("تسلیم در جنگ", "‌"), "",
        "غرامت سنگین می‌دهی، جنگ تمام می‌شود و شهرها می‌مانند.", "",
        "<b>مطمئنی؟</b>"]), kb_surrender())
    await c.answer()
@router.callback_query(F.data.startswith("tp:"))
async def cb_target_page(c: CallbackQuery):
    """‌ صفحه‌بندی پیکر کشورها — جاسوسی/اتحاد/جنگ/تحریم."""
    parts = c.data.split(":")
    action, page = parts[1], (int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0)
    await c.message.edit_reply_markup(reply_markup=kb_targets(c.from_user.id, action, page))
    await c.answer()
# ═══════════ ⚔‌ اعلام جنگ — دکمه‌ای ═══════════
@router.callback_query(F.data.startswith("dwr:"))
async def cb_declare_war(c: CallbackQuery):
    uid = c.from_user.id
    msg = war.declare(uid, c.data.split(":")[1])
    p = state.active(uid)
    kb = kb_strikes(uid) if (p and war.war_of(p["country"])) else kb_pol()
    await _edit(c, msg, kb)
    if "اعلام جنگ" in msg:
        await _sticker(c.message.chat, "‌")
    await c.answer()

# ═══════════ سیستم‌های پیشرفته نسخه ۴۰ (سازمان ملل، تنگه‌ها، پایگاه‌ها، حملات ۵ مرحله‌ای) ═══════════

@router.callback_query(F.data.startswith("unp:"))
async def cb_un_propose(c: CallbackQuery):
    res_type = c.data.split(":")[1]
    prompt_text = "🏛️ <b>سازمان ملل متحد — ثبت قطعنامه</b>\nنوع: <b>" + str(un.RESOLUTION_TYPES.get(res_type, res_type)) + "</b>\n\nکشور هدف را از فهرست زیر انتخاب کنید:"
    await _edit(c, prompt_text, kb_targets(c.from_user.id, "unsub:" + res_type))
    await c.answer()

@router.callback_query(F.data.startswith("unsub:"))
async def cb_un_submit(c: CallbackQuery):
    parts = c.data.split(":")
    res_type = parts[1]
    target_cid = parts[2]
    msg, ann = un.propose_resolution(c.from_user.id, res_type, target_cid)
    await _edit(c, msg, kb_un(c.from_user.id))
    if ann:
        with contextlib.suppress(Exception):
            await c.message.answer(ann, parse_mode="HTML")
    await c.answer()

@router.callback_query(F.data == "unv:")
async def cb_un_vote_list(c: CallbackQuery):
    rows = db.q("SELECT * FROM un_resolutions WHERE status='voting' ORDER BY id DESC LIMIT 5")
    if not rows:
        await _edit(c, "🏛️ در حال حاضر قطعنامه‌ای در جریان رأی‌گیری نیست.", kb_un(c.from_user.id))
        return await c.answer()
    p = state.active(c.from_user.id)
    is_p5 = un.is_p5(p["country"]) if p else False
    btn_rows = []
    for r in rows:
        btn_rows.append([InlineKeyboardButton(text="🗳️ رأی به قطعنامه #" + str(r['id']), callback_data="unpick:" + str(r['id']))])
    btn_rows.append([InlineKeyboardButton(text="🔙 بازگشت به سازمان ملل", callback_data="mn:un")])
    await _edit(c, un.list_active_resolutions(), InlineKeyboardMarkup(inline_keyboard=btn_rows))
    await c.answer()

@router.callback_query(F.data.startswith("unpick:"))
async def cb_un_pick(c: CallbackQuery):
    res_id = int(c.data.split(":")[1])
    p = state.active(c.from_user.id)
    is_p5 = un.is_p5(p["country"]) if p else False
    res = db.one("SELECT * FROM un_resolutions WHERE id=?", (res_id,))
    if not res:
        return await c.answer("قطعنامه یافت نشد.", show_alert=True)
    body = "🏛️ <b>رأی‌گیری قطعنامه #" + str(res['id']) + "</b>\nعنوان: <b>" + str(res['title']) + "</b>\n\nآرای ثبت‌شده:\n🟢 موافق: " + str(res['votes_yes']) + " | 🔴 مخالف: " + str(res['votes_no']) + "\n\nرأی خود را انتخاب کنید:"
    await _edit(c, body, kb_un_vote(res_id, is_p5))
    await c.answer()

@router.callback_query(F.data.startswith("unv:"))
async def cb_un_cast_vote(c: CallbackQuery):
    parts = c.data.split(":")
    if len(parts) >= 3:
        vote = parts[1]
        res_id = int(parts[2])
        msg, ann = un.vote_resolution(c.from_user.id, res_id, vote)
        await _edit(c, msg, kb_un(c.from_user.id))
        if ann:
            with contextlib.suppress(Exception):
                await c.message.answer(ann, parse_mode="HTML")
        await c.answer()

@router.callback_query(F.data.startswith("strv40:"))
async def cb_strait_view(c: CallbackQuery):
    key = c.data.split(":")[1]
    s = toll.STRAITS.get(key)
    if not s:
        return await c.answer("تنگه نامعتبر است.", show_alert=True)
    owner_str = " / ".join(countries.COUNTRIES.get(o,{}).get('name',o) for o in s["owners"])
    closed = toll.is_closed(key)
    toll_amt = toll.get_toll(key)
    st_status = "⛔ مسدود" if closed else "🟢 آزاد و باز"
    desc = "🌊 <b>آبراه " + s['name'] + "</b> (" + s['flag'] + ")\n" + texts.FULL + "\n▫️ حاکمیت قانونی: <b>" + owner_str + "</b>\n▫️ وضعیت: <b>" + st_status + "</b>\n▫️ نرخ عوارض: <b>" + texts.money('us', toll_amt) + "</b>\n▫️ صندوق: <b>" + texts.money('us', toll.get_pot(key)) + "</b>\n\n" + s['desc']
    await _edit(c, desc, kb_strait_manage(c.from_user.id, key))
    await c.answer()

@router.callback_query(F.data.startswith("strop:"))
async def cb_strait_op(c: CallbackQuery):
    parts = c.data.split(":")
    op = parts[1]
    key = parts[2]
    if op == "toggle_close":
        msg, ann = toll.toggle_closure(c.from_user.id, key)
    elif op == "toggle_toll":
        msg, ann = toll.toggle_toll(c.from_user.id, key)
    elif op == "collect":
        msg = toll.collect_pot(c.from_user.id, key)
        ann = ""
    elif op == "pay":
        msg = toll.pay_user_toll(c.from_user.id, key)
        ann = ""
    else:
        msg, ann = "⚠️ عملیات نامعتبر است.", ""
    await _edit(c, msg, kb_straits_v40(c.from_user.id))
    if ann:
        with contextlib.suppress(Exception):
            await c.message.answer(ann, parse_mode="HTML")
    await c.answer()

@router.callback_query(F.data.startswith("bldbase:"))
async def cb_build_base(c: CallbackQuery):
    parts = c.data.split(":")
    btype = parts[1]
    city = parts[2]
    msg = geo.build_base(c.from_user.id, city, btype)
    await _edit(c, msg, kb_bases(c.from_user.id))
    await c.answer()

@router.callback_query(F.data.startswith("opstg:"))
async def cb_operation_stage(c: CallbackQuery):
    parts = c.data.split(":")
    stage = int(parts[1])
    target_cid = parts[2]
    msg, ann = war.strike_stage(c.from_user.id, target_cid, stage)
    await _edit(c, msg, kb_operation_stages(c.from_user.id, target_cid))
    if ann:
        with contextlib.suppress(Exception):
            await c.message.answer(ann, parse_mode="HTML")
    await c.answer()

@router.callback_query(F.data.startswith("newop:"))
async def cb_new_operation(c: CallbackQuery):
    target_cid = c.data.split(":")[1]
    _pend_set(c.from_user.id, c.message.chat.id, "opname:" + target_cid)
    t_info = countries.COUNTRIES.get(target_cid, {})
    await _edit(c, "🚩 <b>طراحی عملیات نظامی جدید علیه " + str(t_info.get('name','')) + "</b>\n\n✍️ لطفاً <b>نام عملیات دلخواه خود</b> را در گروه بفرستید:\n(مثال: <code>عملیات وعده صادق</code> یا <code>Operation Overlord</code>)\n\nبرای لغو بنویسید: <b>لغو</b>", kb_cancel_pol())
    await c.answer()

# ═══════════ پردازشگر دستورهای متنی و ورودی‌های منتظر ═══════════

def _find_country(txt: str):
    """جستجوی دقیق نام کشور با اصلاح حروف فارسی/عربی."""
    def _n(s):
        return (s or "").replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک").strip()
    t = _n(txt)
    if not t:
        return None
    for cid, c in countries.COUNTRIES.items():
        if t in (c["name"], cid) or _n(c["name"]) == t:
            return cid
    for cid, c in countries.COUNTRIES.items():
        cn = _n(c["name"])
        if cn and (t in cn or cn in t):
            return cid
    return None

@router.message()
async def fa_words(m: Message):
    t = (m.text or "").strip()
    if not t:
        return
    # پاکسازی منشن ربات
    if "@REDarkZoneBot" in t:
        t = t.replace("@REDarkZoneBot", "").strip()
        if not t:
            t = "منو"
        elif not t.isdigit():
            t = next((w for w in t.split() if w in TEXT_ALLOWED), "منو")
    parts = t.split(maxsplit=1)
    w = parts[0]
    if w in ("/menu", "منو"):
        w = "منو"
    arg = parts[1] if len(parts) > 1 else ""
    uid = m.from_user.id

    if m.chat.type == "private":
        if WORLD_OF is None or not WORLD_OF(uid):
            return await m.answer(texts.PM_GUIDE, parse_mode="HTML")

    state.ensure(uid, m.from_user.first_name,
                 None if m.chat.type == "private" else m.chat.id,
                 getattr(m.from_user, "username", None))

    # بررسی ورودی‌های در انتظار (Pending inputs)
    pend = _pend_pop(uid, m.chat.id)
    if pend:
        if w == "لغو":
            return await m.answer("✅ عملیات جاری لغو شد. می‌توانید از «منو» مجدداً اقدام کنید.", parse_mode="HTML")

        if pend.startswith("opname:"):
            target_cid = pend.split(":", 1)[1]
            msg, ann = war.create_operation(uid, target_cid, t)
            sent = await m.answer(msg, parse_mode="HTML", reply_markup=kb_operation_stages(uid, target_cid))
            _own(m, sent, uid)
            if ann:
                with contextlib.suppress(Exception):
                    await m.answer(ann, parse_mode="HTML")
            return sent

        if pend.startswith("pay:"):
            to = int(pend.split(":", 1)[1])
            amt = texts.to_int(w)
            me = db.one("SELECT country, money FROM users WHERE uid=?", (uid,))
            dst = db.one("SELECT name FROM users WHERE uid=?", (to,))
            if not dst or not me:
                return await m.answer("⚠️ گیرنده یافت نشد.", parse_mode="HTML")
            if not amt or amt < 1:
                return await m.answer("⚠️ لطفاً فقط مبلغ عددی بنویسید (مثال: <code>5000</code>).", parse_mode="HTML")
            if amt > me["money"]:
                return await m.answer(f"⚠️ موجودی کافی نیست. موجودی شما: {texts.money(me['country'], me['money'])}", parse_mode="HTML")
            db.ex("UPDATE users SET money=money-? WHERE uid=?", (amt, uid))
            db.ex("UPDATE users SET money=money+? WHERE uid=?", (amt, to))
            sender_tag = texts.mention(uid, m.from_user.first_name)
            receiver_tag = texts.mention(to, dst["name"])
            return await m.answer(f"💸 <b>انتقال موفقیت‌آمیز وجه</b>\n\nمبلغ <b>{texts.money(me['country'], amt)}</b> از طرف {sender_tag} به حساب {receiver_tag} واریز شد.", parse_mode="HTML")

        if pend == "stmt":
            sent = await m.answer(politics.statement(uid, t), parse_mode="HTML", reply_markup=kb_pol())
            _own(m, sent, uid)
            return sent

        if pend == "alead":
            sent = await m.answer(_admin_leader(t), parse_mode="HTML", reply_markup=kb_admin())
            _own(m, sent, uid)
            return sent

        if pend in ("areg", "achg"):
            parts2 = t.split()
            if len(parts2) >= 2 and parts2[0].isdigit():
                fn = _admin_register if pend == "areg" else _admin_change
                sent = await m.answer(fn(int(parts2[0]), " ".join(parts2[1:])), parse_mode="HTML", reply_markup=kb_admin())
                _own(m, sent, uid)
                return sent
            _pend_set(uid, m.chat.id, pend)
            sent = await m.answer("⚠️ الگو: <code>آیدی‌عددی نام‌کشور</code> — مثال: <code>8694290031 ایران</code>", parse_mode="HTML", reply_markup=kb_admin())
            _own(m, sent, uid)
            return sent

        if pend == "party":
            nm, _, ideo = t.partition("|")
            sent = await m.answer(politics.found(uid, nm.strip(), ideo.strip() or "ملی"), parse_mode="HTML", reply_markup=kb_pol())
            _own(m, sent, uid)
            return sent

    # دستورهای متنی
    if w in ("دستورها", "دستور", "دستورات", "کمک", "/commands"):
        sent = await m.answer(texts.COMMANDS, parse_mode="HTML", reply_markup=kb_help(1))
        _own(m, sent, uid)
        return sent

    if w in ("/help", "راهنما"):
        sent = await m.answer(texts.HELP_PAGES[0], parse_mode="HTML", reply_markup=kb_help(1))
        _own(m, sent, uid)
        return sent

    if w in ("منو", "/menu"):
        sent = await m.answer(state.card(uid), parse_mode="HTML", reply_markup=kb_main(uid))
        _own(m, sent, uid)
        return sent

    if w in ("نظامی", "/military", "ارتش"):
        sent = await m.answer(texts.hdr("فرماندهی نظامی", "🎖️") + "\n\nیکی را انتخاب کن:", parse_mode="HTML", reply_markup=kb_mil())
        _own(m, sent, uid)
        return sent

    if w in ("خرید", "زرادخانه", "تجهیزات", "/buy"):
        sent = await m.answer(military.arsenal(uid), parse_mode="HTML", reply_markup=kb_arsenal(uid))
        _own(m, sent, uid)
        return sent

    if w in ("حمله", "جنگ", "/war", "/attack"):
        p = state.active(uid)
        if p and war.war_of(p["country"]):
            sent = await m.answer(war.front(uid), parse_mode="HTML", reply_markup=kb_strikes(uid))
        else:
            sent = await m.answer(texts.hdr("فرماندهی جنگ و عملیات", "⚔️") + "\n\nکشور هدف را برای اعلان جنگ یا آغاز عملیات انتخاب کنید:", parse_mode="HTML", reply_markup=kb_declare(uid))
        _own(m, sent, uid)
        return sent

    if w in ("سازمان ملل", "/un"):
        sent = await m.answer(un.list_active_resolutions(), parse_mode="HTML", reply_markup=kb_un(uid))
        _own(m, sent, uid)
        return sent

    if w in ("تنگه", "تنگه‌ها", "عوارض", "/toll"):
        sent = await m.answer(toll.straits_overview(uid), parse_mode="HTML", reply_markup=kb_straits_v40(uid))
        _own(m, sent, uid)
        return sent

    if w in ("پایگاه", "پایگاه‌ها", "/bases"):
        p = state.active(uid)
        if p:
            sent = await m.answer(texts.hdr("احداث پایگاه‌های نظامی در شهرها", "🏗️"), parse_mode="HTML", reply_markup=kb_bases(uid))
            _own(m, sent, uid)
            return sent

    if w in ("سرمایه", "سرمایه‌گذاری", "معدن", "/invest"):
        sent = await m.answer(invest.view(uid), parse_mode="HTML", reply_markup=kb_invest(uid))
        _own(m, sent, uid)
        return sent

    if w in ("پروفایل", "/profile", "کارت"):
        sent = await m.answer(state.card(uid), parse_mode="HTML", reply_markup=kb_main(uid))
        _own(m, sent, uid)
        return sent

    if w in ("جهان", "/world"):
        sent = await m.answer(war.world_status(), parse_mode="HTML", reply_markup=kb_world())
        _own(m, sent, uid)
        return sent

    # ابزارهای مالک
    if w == "رهبر":
        if uid != config.OWNER_ID:
            return await m.answer("🚫 این دستور فقط برای مالک ربات مجاز است.", parse_mode="HTML")
        parts_l = arg.split() if arg else []
        ru = getattr(m.reply_to_message, "from_user", None) if m.reply_to_message else None
        if ru and parts_l and parts_l[0] not in ("خالی", "-"):
            return await m.answer(_set_leader(ru.id, " ".join(parts_l)), parse_mode="HTML", reply_markup=kb_admin())
        if parts_l and parts_l[0].startswith("@") and parts_l[0][1:]:
            r = db.one("SELECT uid FROM users WHERE username=? COLLATE NOCASE", (parts_l[0][1:],))
            if r:
                return await m.answer(_set_leader(r["uid"], " ".join(parts_l[1:])), parse_mode="HTML", reply_markup=kb_admin())
        sent = await m.answer(_admin_leader(arg), parse_mode="HTML", reply_markup=kb_admin())
        _own(m, sent, uid)
        return sent
