"""⚔️ جنگ جهانی — سیستم نظامی، شاخه‌های رزمی، زرادخانه ملی، بازار سیاه و ارتقا."""
import random
import db
import countries
import texts
from game import economy, state


def branch_name(p: dict) -> str:
    c = countries.COUNTRIES.get(p.get("country"))
    if not c or not p.get("branch"):
        return ""
    b = p["branch"]
    if isinstance(b, int) or (isinstance(b, str) and b.isdigit()):
        try:
            return c["branches"][int(b)]
        except Exception:
            return ""
    return b if b in c["branches"] else str(b)


def join_branch(uid: int, idx: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    if p.get("branch"):
        return "⚠️ شما قبلاً عضو یکی از شاخه‌های نظامی شده‌اید."
    c = countries.COUNTRIES.get(p["country"])
    if not c or idx < 0 or idx >= len(c["branches"]):
        return "⚠️ شاخه نظامی نامعتبر است."
    
    branch_title = c["branches"][idx]
    db.ex("UPDATE users SET branch=? WHERE uid=?", (branch_title, uid))
    t = texts
    k, rname, reff = role_of(state.active(uid))
    role_line = f"\n🎯 تخصص سازمانی: <b>{rname}</b> — {reff}" if k else ""
    return "\n".join([
        t.hdr("عضویت در نیروهای مسلح", "🎖️"),
        t.row("شاخه رزم", branch_title),
        t.row("کشور", f"{c['flag']} {c['name']}"),
        role_line,
        "",
        "🎖️ به رده‌های رزمی خوش آمدید! با شرکت در جنگ‌ها و رزم انفرادی درجه نظامی شما ارتقا خواهد یافت.",
    ])


BRANCH_ROLE_DEFS = {
    "atk":  ("خط مقدم و تهاجم ویژه", "+۱۵٪ قدرت تخریب در تمامی حملات"),
    "miss": ("فرماندهی موشکی", "+۲۰٪ قدرت ضربات موشک‌های بالستیک"),
    "air":  ("نیروی هوایی و پهپادی", "+۲۰٪ قدرت بمباران هوایی و پهپادی"),
    "sea":  ("ناوگان دریایی", "+۲۰٪ قدرت آتش در نبردهای دریایی"),
    "grd":  ("نیروی زرهی و مکانیزه", "+۲۰٪ قدرت پیشروی در فاز نبرد شهری"),
    "def":  ("سپر پدافند ملی", "کاهش ۱۵٪ خسارات وارده از حملات دشمن به کشور"),
    "eco":  ("لجستیک و پشتیبانی", "+۱۵٪ درآمد از شیفت‌های کاری و جیره"),
}

_NAME_RULES = (
    ("موشکی", "miss"), ("هوایی", "air"), ("پرواز", "air"), ("هواپیمایی", "air"),
    ("دریایی", "sea"), ("ناو", "sea"), ("زرهی", "grd"), ("تانک", "grd"),
    ("پدافند", "def"), ("مارینز", "atk"), ("دلتا", "atk"), ("اسپتسناز", "atk"),
    ("کماندو", "atk"), ("تکاور", "atk"), ("ویژه", "atk"),
)


def role_of(p: dict) -> tuple:
    if not p or not p.get("branch"):
        return ("", "", "")
    nm = branch_name(p)
    for word, key in _NAME_RULES:
        if word in nm:
            name, eff = BRANCH_ROLE_DEFS[key]
            return (key, name, eff)
    name, eff = BRANCH_ROLE_DEFS["atk"]
    return ("atk", name, eff)


def atk_mult(p: dict, kind: str) -> tuple[float, str]:
    k, name, _ = role_of(p)
    if not k:
        return 1.0, ""
    if k == "atk":
        return 1.15, f" ({name})"
    pairs = {"miss": "موشکی", "air": "هوایی", "sea": "دریایی", "grd": "زمینی"}
    if pairs.get(k) == kind or (k == "air" and kind == "پهپادی"):
        return 1.10, f" ({name})"
    return 1.0, ""


def def_mult(cid: str) -> float:
    n = 0
    for r in db.q("SELECT branch FROM users WHERE country=? AND branch IS NOT NULL", (cid,)):
        p = {"branch": r["branch"], "country": cid}
        if role_of(p)[0] == "def":
            n += 1
    return 1.0 - min(0.15, 0.05 * n)


def eco_mult(uid: int) -> float:
    p = state.active(uid)
    return 1.10 if p and role_of(p)[0] == "eco" else 1.0


# ═══════════ زرادخانه و تجهیزات ═══════════

def arsenal(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    c = countries.COUNTRIES[p["country"]]
    sp = countries.spec_of(p["country"])
    lines = [
        texts.hdr(f"زرادخانه نظامی {c['name']} {c['flag']}", "🏛️"),
        f"🎯 دکترین ویژه: <b>{sp[2]}</b> (+{texts.fa(sp[1])}٪ در حملات {sp[0]})",
        f"💰 موجودی خزانه: <b>{texts.money(p['country'], p['money'])}</b>",
        ""
    ]
    for iid in c["items"]:
        it = countries.ITEMS[iid]
        own = db.one("SELECT qty, dur FROM inventory WHERE uid=? AND iid=?", (uid, iid))
        price = economy.real_price(it[5])
        mark = f"📦 <b>{texts.fa(own['qty'])} عدد</b> (دوام {texts.fa(own['dur'])}٪)" if own else f"💵 {texts.money(p['country'], price)}"
        lines.append(f"{it[1]} <b>{it[0]}</b> — ⚔️ {texts.fa(it[3])} قدرت | 🛡️ {texts.fa(it[4])} پدافند\n   └ وضعیت: {mark}")
        
    deals = economy.daily_deals(p["country"])
    if deals:
        lines += ["", "🔥 <b>پیشنهاد ویژه روزانه (۲۰٪ تخفیف اختصاصی):</b>"]
        for diid in deals:
            it2 = countries.ITEMS[diid]
            dp = economy.deal_price(economy.real_price(it2[5]))
            lines.append(f"   ▫️ {it2[1]} {it2[0]} ➔ 💵 <b>{texts.money(p['country'], dp)}</b>")
            
    lines += ["", "🛒 <i>برای خرید تسلیحات از دکمه‌های زیر استفاده کنید (×۱ یا ×۵):</i>"]
    return "\n".join(lines)


MAX_QTY = 99


def buy(uid: int, iid: str, qty: int = 1) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    it = countries.ITEMS.get(iid)
    if not it or iid not in countries.COUNTRIES[p["country"]]["items"]:
        return "⚠️ این جنگ‌افزار در زرادخانه رسمی کشور شما موجود نیست."
        
    from game import infra as _if
    if not _if.power_ok(p["country"]) and it[5] >= 4000:
        return "⚡ شبکه برق کشورتان آسیب‌دیده است — خرید تجهیزات سنگین ممنوع است.\n(برای رفع: منوی نظامی ➔ تعمیر زیرساخت)"
        
    qty = max(1, min(5, int(qty)))
    deal = iid in economy.daily_deals(p["country"])
    if qty >= 5:
        qty = 5
        cost = int(economy.real_price(it[5]) * 5 * 0.90)  # تخفیف خرید عمده
    else:
        cost = int(economy.real_price(it[5]))
        
    if deal:
        cost = economy.deal_price(cost)
        
    row = db.one("SELECT qty FROM inventory WHERE uid=? AND iid=?", (uid, iid))
    have = row["qty"] if row else 0
    if have + qty > MAX_QTY:
        return f"⚠️ سقف نگهداری این تجهیز {texts.fa(MAX_QTY)} عدد است (موجودی فعلی: {texts.fa(have)})."
        
    if p["money"] < cost:
        return f"⚠️ بودجه ناکافی! قیمت: {texts.money(p['country'], cost)} (موجودی شما: {texts.money(p['country'], p['money'])})"
        
    db.ex("UPDATE users SET money=money-? WHERE uid=?", (cost, uid))
    db.ex("""
    INSERT INTO inventory(uid, iid, qty, dur)
    VALUES(?, ?, ?, 100)
    ON CONFLICT(uid, iid) DO UPDATE SET qty=qty+?, dur=100
    """, (uid, iid, qty, qty))
    
    from game import quests
    quests.on_event(uid, "خرید")
    t = texts
    return f"""✅ <b>خرید موفقیت‌آمیز از زرادخانه</b>
{texts.FULL}
📦 تجهیز: <b>{it[0]}</b> {it[1]} (تعداد: <b>{t.fa(qty)}</b>)
📈 موجودی جدید: <b>{t.fa(have + qty)} عدد</b> با دوام ۱۰۰٪
💵 مبلغ پرداختی: <b>{t.money(p['country'], cost)}</b>
💰 باقی‌مانده خزانه: <b>{t.money(p['country'], p['money'] - cost)}</b>"""


def black_sample(uid: int) -> list:
    p = state.active(uid)
    if not p:
        return []
    import random as _r
    _r.seed(db.now() // 3600 + uid)
    foreign = [iid for iid, it in countries.ITEMS.items() if it[2] != p["country"]]
    return _r.sample(foreign, k=min(8, len(foreign)))


def blackmarket(uid: int) -> str:
    from game import economy
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    lines = [
        texts.hdr("بازار سیاه تسلیحات بین‌الملل", "☠️"),
        "⚠️ خرید تسلیحات خارجی قاچاق با ضریب قیمت ۱.۶ برابر رسمی:",
        ""
    ]
    for iid in black_sample(uid):
        it = countries.ITEMS[iid]
        price = int(economy.real_price(it[5]) * 1.6)
        c = countries.COUNTRIES.get(it[2], {})
        own = db.one("SELECT qty FROM inventory WHERE uid=? AND iid=?", (uid, iid))
        mark = f"📦 موجودی: {texts.fa(own['qty'])}" if own else f"💵 {texts.money(p['country'], price)}"
        lines.append(f"{it[1]} <b>{it[0]}</b> ({c.get('flag','')}) — {mark}")
    lines += ["", "🛒 <i>لیست بازار سیاه هر ساعت تغییر می‌کند.</i>"]
    return "\n".join(lines)


def buy_black(uid: int, iid: str) -> str:
    from game import economy
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    it = countries.ITEMS.get(iid)
    if not it or it[2] == p["country"]:
        return "⚠️ این تجهیز متعلق به کشور خودتان است — از زرادخانه تهیه کنید."
    price = int(economy.real_price(it[5]) * 1.6)
    if p["money"] < price:
        return f"⚠️ بودجه ناکافی! قیمت بازار سیاه: {texts.money(p['country'], price)} (موجودی: {texts.money(p['country'], p['money'])})"
    db.ex("UPDATE users SET money=money-? WHERE uid=?", (price, uid))
    db.ex("""
    INSERT INTO inventory(uid, iid, qty, dur)
    VALUES(?, ?, 1, 100)
    ON CONFLICT(uid, iid) DO UPDATE SET qty=qty+1, dur=100
    """, (uid, iid))
    return f"☠️ جنگ‌افزار <b>{it[0]}</b> {it[1]} از بازار سیاه قاچاق و به زرادخانه شما افزوده شد!"


def item_level(uid: int, iid: str) -> int:
    return int(db.kv_get(f"itlvl:{uid}:{iid}", "1"))


def upgrade(uid: int, iid: str) -> str:
    from game import economy
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    it = countries.ITEMS.get(iid)
    if not it or not db.one("SELECT 1 FROM inventory WHERE uid=? AND iid=?", (uid, iid)):
        return "⚠️ این تجهیز را در زرادخانه خود ندارید."
    lvl = item_level(uid, iid)
    if lvl >= 3:
        return "🌟 این جنگ‌افزار در بالاترین سطح ارتقای فناوری (سطح ۳) قرار دارد."
    cost = int(economy.real_price(it[5]) * 0.5 * lvl)
    if p["money"] < cost:
        return f"⚠️ هزینه ارتقا: {texts.money(p['country'], cost)} (موجودی: {texts.money(p['country'], p['money'])})"
    db.ex("UPDATE users SET money=money-? WHERE uid=?", (cost, uid))
    db.kv_set(f"itlvl:{uid}:{iid}", str(lvl + 1))
    return f"🚀 <b>ارتقای فناوری نظامی!</b>\nجنگ‌افزار <b>{it[0]}</b> به سطح <b>{texts.fa(lvl + 1)}</b> ارتقا یافت (+۲۵٪ قدرت تخریب مضاعف)."


def repair(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    from game import economy
    rows = db.q("SELECT i.iid, i.dur FROM inventory i WHERE i.uid=? AND i.dur < 100", (uid,))
    if not rows:
        return "🛡️ تمامی تسلیحات شما با دوام ۱۰۰٪ کاملاً سالم و آماده رزم هستند."
    total, fixed = 0, 0
    for r in rows:
        it = countries.ITEMS.get(r["iid"])
        if not it:
            continue
        cost = max(15, economy.real_price(it[5]) * (100 - r["dur"]) // 200)
        if p["money"] < total + cost:
            break
        total += cost
        fixed += 1
        db.ex("UPDATE inventory SET dur=100 WHERE uid=? AND iid=?", (uid, r["iid"]))
    if total == 0:
        return "⚠️ بودجه کافی برای تعمیر تسلیحات ندارید."
    db.ex("UPDATE users SET money=money-? WHERE uid=?", (total, uid))
    t = texts
    return f"""🔧 <b>عملیات اورهال و تعمیرات زرادخانه</b>
{texts.FULL}
✅ تعداد <b>{t.fa(fixed)} جنگ‌افزار</b> بازسازی و با دوام ۱۰۰٪ آماده نبرد شدند.
💵 هزینه اورهال: <b>{t.money(p['country'], total)}</b>"""


ENEMIES = [
    ("جوخه تروریستی داعش", "تکفیری", 120, 35, 15, 0),
    ("نیروهای مزدور بلک‌واتر", "مزدور", 180, 50, 25, 1),
    ("لشکر کماندویی متخاصم", "تکاور", 260, 70, 40, 2),
    ("گردان زرهی متجاوز", "زرهی سنگین", 350, 95, 60, 3),
]


def battle(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    if p["hp"] < 25:
        return f"❤️ <b>سلامت شما ناکافی است ({texts.fa(p['hp'])} HP)!</b>\nابتدا از بخش استراحت سلامتی خود را بازیابی کنید."
    tier = min(len(ENEMIES) - 1, p["level"] // 3)
    name, mname, ehp, eatk, eguard, t_idx = ENEMIES[tier]
    a_it, d_it, atk, guard, a_iid, d_iid = loadout(uid)
    log = []
    rounds = random.randint(2, 4)
    for _ in range(rounds):
        dmg = max(15, int(atk * random.uniform(0.7, 1.2)) - eguard // 2)
        ehp -= dmg
        log.append(f"⚔️ شلیک به {name} ➔ <b>{texts.fa(dmg)} آسیب</b>")
        if ehp <= 0:
            break
        edmg = max(10, int(eatk * random.uniform(0.5, 1.0)) - guard // 3)
        db.ex("UPDATE users SET hp=MAX(0, hp-?) WHERE uid=?", (edmg, uid))
        p = state.active(uid)
        log.append(f"🛡️ ضدحمله دشمن ➔ <b>−{texts.fa(edmg)} HP</b>")
    
    for iid in (a_iid, d_iid):
        if iid:
            db.ex("UPDATE inventory SET dur=MAX(5, dur - ?) WHERE uid=? AND iid=?", (random.randint(2, 5), uid, iid))
            
    t = texts
    if ehp <= 0:
        loot = (tier + 1) * 350
        xp = 80 + tier * 50
        db.ex("UPDATE users SET money=money+?, kills=kills+1, hp=MAX(20, hp) WHERE uid=?", (loot, uid))
        state.gain_xp(uid, xp)
        from game import quests
        quests.on_event(uid, "رزم")
        quests.on_event(uid, "پیروزی")
        return "\n".join([
            t.hdr(f"پیروزی در رزم انفرادی — {name}", "🎖️"),
            t.row("نوع هدف", mname),
            "",
            *log[:6],
            "",
            t.row("غنیمت نبرد", f"💵 {t.money(p['country'], loot)} + ⭐ {t.fa(xp)} XP"),
            t.row("سلامت فعلی", f"❤️ {t.fa(p['hp'])} / {t.fa(p['max_hp'])} HP"),
        ])
    db.ex("UPDATE users SET hp=MAX(10, hp) WHERE uid=?", (uid,))
    return "\n".join([
        t.hdr(f"عقب‌نشینی تاکتیکی از نبرد با {name}", "⚠️"),
        "",
        *log[:6],
        "",
        "💡 <i>سلامت شما کاهش یافت — جهت درمان از بخش «استراحت» استفاده کنید.</i>"
    ])


def rest(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    last_rest = int(db.kv_get(f"rest:{uid}", "0") or 0)
    if db.now() - last_rest < 60:
        return "⏳ خدمات درمانی انجام شده است — ۱ دقیقه تا درخواست بعدی."
    cost = 150
    if p["money"] < cost:
        return f"⚠️ بودجه ناکافی! هزینه خدمات درمانی {texts.money(p['country'], cost)} است."
    db.kv_set(f"rest:{uid}", str(db.now()))
    db.ex("UPDATE users SET hp=max_hp, money=money-? WHERE uid=?", (cost, uid))
    return f"❤️ <b>بهداری ارتش — سلامت کامل بازیابی شد!</b>\nوضعیت: {texts.fa(p['max_hp'])} / {texts.fa(p['max_hp'])} HP\n💵 هزینه درمان: {texts.money(p['country'], cost)}"


def loadout(uid: int):
    rows = db.q("SELECT n.iid, n.dur FROM inventory n WHERE n.uid=? AND n.dur > 5", (uid,))
    if not rows:
        p = state.active(uid)
        cid = p["country"] if p else "ir"
        c_items = countries.COUNTRIES.get(cid, {}).get("items", [])
        if c_items:
            first_iid = c_items[0]
            it = countries.ITEMS.get(first_iid)
            if it:
                return it, it, it[3], it[4], first_iid, first_iid
        return None, None, 50, 50, None, None
    best_a = max(rows, key=lambda r: countries.ITEMS.get(r["iid"], [0, "", "", 10, 10, 100])[3] * r["dur"] // 100)
    best_d = max(rows, key=lambda r: countries.ITEMS.get(r["iid"], [0, "", "", 10, 10, 100])[4] * r["dur"] // 100)
    it_a = countries.ITEMS.get(best_a["iid"])
    it_d = countries.ITEMS.get(best_d["iid"])
    atk_val = it_a[3] if it_a else 50
    def_val = it_d[4] if it_d else 50
    return it_a, it_d, atk_val, def_val, best_a["iid"], best_d["iid"]
