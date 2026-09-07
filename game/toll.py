"""🌊 جنگ جهانی — سیستم حاکمیتی تنگه‌ها و عوارض کشتیرانی.
هر تنگه متعلق به کشورهای ساحلی و حاکم بر آن است:
• تنگه هرمز: ایران (ir) و عمان
• تنگه باب‌المندب: یمن (ye) و عربستان (sa)
• کانال سوئز: مصر (eg)
• تنگه بسفر و داردانل: ترکیه (tr)
• تنگه مالاکا: مالزی (my) و اندونزی (id)
• کانال پاناما: آمریکا (us)
• تنگه جبل‌الطارق: اسپانیا (es) و بریتانیا (gb)
• تنگه تایوان: چین (cn)

هیچ کشوری نمی‌تواند تنگه کشور دیگر را ببندد یا عوارض آن را تصاحب کند!
"""
import db
import texts
import countries

STRAITS = {
    "hormuz": {
        "name": "تنگه هرمز",
        "owners": ["ir"],
        "flag": "🇮🇷",
        "desc": "شاهراه ترانزیت نفت خلیج فارس",
        "default_toll": 250,
    },
    "bab": {
        "name": "تنگه باب‌المندب",
        "owners": ["ye", "sa"],
        "flag": "🇾🇪",
        "desc": "دروازه ورودی دریای سرخ و آبراه استراتژیک",
        "default_toll": 200,
    },
    "suez": {
        "name": "کانال سوئز",
        "owners": ["eg"],
        "flag": "🇪🇬",
        "desc": "شریان حیاتی پیوند دریای سرخ به مدیترانه",
        "default_toll": 300,
    },
    "bosphorus": {
        "name": "تنگه بسفر و داردانل",
        "owners": ["tr"],
        "flag": "🇹🇷",
        "desc": "گذرگاه دریای سیاه به آب‌های آزاد جهان",
        "default_toll": 200,
    },
    "malacca": {
        "name": "تنگه مالاکا",
        "owners": ["my", "id"],
        "flag": "🇲🇾",
        "desc": "بزرگ‌ترین گلوگاه تجاری شرق آسیا",
        "default_toll": 220,
    },
    "panama": {
        "name": "کانال پاناما",
        "owners": ["us"],
        "flag": "🇺🇸",
        "desc": "اتصال اقیانوس اطلس به آرام",
        "default_toll": 350,
    },
    "gibraltar": {
        "name": "تنگه جبل‌الطارق",
        "owners": ["es", "gb"],
        "flag": "🇬🇧",
        "desc": "ورودی اقیانوس اطلس به دریای مدیترانه",
        "default_toll": 200,
    },
    "taiwan": {
        "name": "تنگه تایوان",
        "owners": ["cn"],
        "flag": "🇨🇳",
        "desc": "شریان ترانزیت نیمه‌هادی‌ها و تجارت شرق آسیا",
        "default_toll": 250,
    },
}

PENALTY = 0.10


def is_closed(strait_key: str) -> bool:
    """آیا این تنگه بسته شده است؟"""
    return db.kv_get(f"strait_closed:{strait_key}") == "1"


def is_toll_on(strait_key: str) -> bool:
    """آیا عوارض این تنگه فعال است؟"""
    return db.kv_get(f"strait_toll_on:{strait_key}", "1") == "1"


def get_toll(strait_key: str) -> int:
    return int(db.kv_get(f"strait_toll_amt:{strait_key}", str(STRAITS.get(strait_key, {}).get("default_toll", 200))))


def get_pot(strait_key: str) -> int:
    return int(db.kv_get(f"strait_pot:{strait_key}", "0") or 0)


def can_manage(cid: str, strait_key: str) -> bool:
    s = STRAITS.get(strait_key)
    if not s:
        return False
    return cid in s["owners"]


def toggle_closure(uid: int, strait_key: str) -> tuple[str, str]:
    """بستن یا باز کردن تنگه توسط کشور حاکم."""
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا با دستور «شروع» کشورتان را انتخاب کنید.", ""

    s = STRAITS.get(strait_key)
    if not s:
        return "⚠️ تنگه نامعتبر است.", ""

    cid = p["country"]
    if not can_manage(cid, strait_key):
        owner_names = " / ".join(countries.COUNTRIES.get(o, {}).get("name", o) for o in s["owners"])
        return f"🚫 <b>عدم حاکمیت!</b>\nشما کنترل <b>{s['name']}</b> را در اختیار ندارید.\nتنها رهبران <b>{owner_names}</b> حق تصمیم‌گیری برای این تنگه را دارند.", ""

    closed = is_closed(strait_key)
    new_state = not closed
    db.kv_set(f"strait_closed:{strait_key}", "1" if new_state else "0")

    c_info = countries.COUNTRIES.get(cid, {})
    user_tag = texts.mention(uid, p["name"])

    if new_state:
        msg = f"⛔ <b>{s['name']} مسدود شد!</b>\nرهبر {c_info.get('flag','')} {c_info.get('name','')} تنگه را بست. عبور ناوگان متوقف شد و قیمت نفت جهانی بالا رفت."
        ann = f"🚨 <b>اعلامیه فوری بین‌المللی — انسداد {s['name']}</b>\n{user_tag} به نمایندگی از {c_info.get('flag','')} <b>{c_info.get('name','')}</b> آبراه <b>{s['name']}</b> را مسدود کرد!\n🛢️ شوک به بازارهای جهانی انرژی و نفت."
    else:
        msg = f"✅ <b>{s['name']} بازگشایی شد.</b>\nکشتیرانی آزاد از سر گرفته شد."
        ann = f"🌊 <b>اطلاعیه رسمی — بازگشایی {s['name']}</b>\n{user_tag} از طرف {c_info.get('flag','')} <b>{c_info.get('name','')}</b> آبراه <b>{s['name']}</b> را بازگشایی کرد."

    return msg, ann


def toggle_toll(uid: int, strait_key: str) -> tuple[str, str]:
    """روشن/خاموش کردن دریافت عوارض روزانه از کشتی‌ها."""
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا با دستور «شروع» کشورتان را انتخاب کنید.", ""

    s = STRAITS.get(strait_key)
    if not s:
        return "⚠️ تنگه نامعتبر است.", ""

    cid = p["country"]
    if not can_manage(cid, strait_key):
        owner_names = " / ".join(countries.COUNTRIES.get(o, {}).get("name", o) for o in s["owners"])
        return f"🚫 <b>عدم حاکمیت!</b>\nتنها رهبران <b>{owner_names}</b> می‌توانند عوارض {s['name']} را تغییر دهند.", ""

    cur_on = is_toll_on(strait_key)
    new_on = not cur_on
    db.kv_set(f"strait_toll_on:{strait_key}", "1" if new_on else "0")

    toll_amt = get_toll(strait_key)
    c_info = countries.COUNTRIES.get(cid, {})

    if new_on:
        msg = f"💰 <b>عوارض {s['name']} فعال شد.</b>\nنرخ عوارض: {texts.money(cid, toll_amt)} در روز"
        ann = f"📢 <b>ابلاغیه رسمی عوارض کشتیرانی</b>\nکشور {c_info.get('flag','')} <b>{c_info.get('name','')}</b> عوارض عبور از <b>{s['name']}</b> را فعال کرد ({texts.money(cid, toll_amt)})."
    else:
        msg = f"💰 <b>عوارض {s['name']} خاموش شد.</b> عبور رایگان شد."
        ann = f"🌊 <b>اطلاعیه رسمی</b>\nعوارض عبور از <b>{s['name']}</b> توسط {c_info.get('flag','')} {c_info.get('name','')} رایگان شد."

    return msg, ann


def collect_pot(uid: int, strait_key: str) -> str:
    """برداشت درآمد عوارض انباشته‌شده به خزانه‌ی کشور حاکم."""
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا کشورتان را انتخاب کنید."

    s = STRAITS.get(strait_key)
    if not s:
        return "⚠️ تنگه نامعتبر است."

    cid = p["country"]
    if not can_manage(cid, strait_key):
        return f"🚫 شما حاکم {s['name']} نیستید!"

    pot = get_pot(strait_key)
    if pot <= 0:
        return f"💰 صندوق عوارض <b>{s['name']}</b> فعلاً خالی است."

    db.ex("UPDATE users SET money=money+? WHERE uid=?", (pot, uid))
    db.kv_set(f"strait_pot:{strait_key}", "0")
    return f"✅ مبلغ <b>{texts.money(cid, pot)}</b> از درآمد عوارض <b>{s['name']}</b> به خزانه‌ی شما واریز شد."


def pay_user_toll(uid: int, strait_key: str) -> str:
    """پرداخت عوارض روزانه عبور توسط بازیکن کشورهای غیرحاکم."""
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا با دستور «شروع» وارد بازی شوید."

    s = STRAITS.get(strait_key)
    if not s:
        return "⚠️ تنگه یافت نشد."

    cid = p["country"]
    if can_manage(cid, strait_key):
        return f"🌟 کشور شما حاکم <b>{s['name']}</b> است و از پرداخت عوارض معاف هستید!"

    if not is_toll_on(strait_key):
        return f"🌊 عبور از <b>{s['name']}</b> در حال حاضر رایگان است."

    day = db.day_index()
    if db.kv_get(f"strait_paid:{strait_key}:{uid}") == str(day):
        return f"✅ عوارض امروز <b>{s['name']}</b> را قبلاً پرداخت کرده‌اید."

    toll_amt = get_toll(strait_key)
    if p["money"] < toll_amt:
        return f"⚠️ موجودی ناکافی! عوارض {texts.money(cid, toll_amt)} است اما شما {texts.money(cid, p['money'])} دارید."

    db.ex("UPDATE users SET money=money-? WHERE uid=?", (toll_amt, uid))
    cur_pot = get_pot(strait_key) + toll_amt
    db.kv_set(f"strait_pot:{strait_key}", str(cur_pot))
    db.kv_set(f"strait_paid:{strait_key}:{uid}", str(day))

    return f"🚢 مبلغ <b>{texts.money(cid, toll_amt)}</b> عوارض عبور از <b>{s['name']}</b> پرداخت شد. ترانزیت امن تا پایان روز برقرار است."


def straits_overview(uid: int) -> str:
    """نمای کلی تنگه‌های جهان و دسترسی‌های کاربر."""
    from game import state
    p = state.active(uid)
    my_cid = p["country"] if p else None

    lines = [
        texts.hdr("وضعیت تنگه‌های استراتژیک جهان", "🌊"),
        "کنترل تنگه‌ها منحصراً در اختیار کشورهای حاکم است:\n"
    ]

    for key, s in STRAITS.items():
        closed = is_closed(key)
        toll_on = is_toll_on(key)
        toll_amt = get_toll(key)
        pot = get_pot(key)
        owner_str = " / ".join(f"{countries.COUNTRIES.get(o,{}).get('flag','')} {countries.COUNTRIES.get(o,{}).get('name',o)}" for o in s["owners"])

        status_icon = "⛔ مسدود" if closed else ("🟢 باز" + (f" (عوارض: {texts.money('us', toll_amt)})" if toll_on else " (رایگان)"))
        lines.append(f"▫️ <b>{s['name']}</b> ({s['flag']}): {status_icon}")
        lines.append(f"   🏛️ حاکمیت: <b>{owner_str}</b> | 💰 درآمد صندوق: <b>{texts.money('us', pot)}</b>")
        if my_cid in s["owners"]:
            lines.append("   ⭐ <i>شما حاکم این آبراه هستید.</i>")
        lines.append("")

    return "\n".join(lines)


def daily_announce_needed() -> bool:
    day = db.day_index()
    last = db.kv_get("toll_ann_day")
    if last == str(day):
        return False
    db.kv_set("toll_ann_day", str(day))
    return True


def is_on(strait_key: str = "hormuz") -> bool:
    return is_toll_on(strait_key)


def status(uid: int = None) -> str:
    return straits_overview(uid)


def pay(uid: int, strait_key: str = "hormuz") -> str:
    return pay_user_toll(uid, strait_key)


def toggle(uid: int, strait_key: str = "hormuz") -> tuple[str, str]:
    return toggle_toll(uid, strait_key)


def collect(uid: int, strait_key: str = "hormuz") -> str:
    return collect_pot(uid, strait_key)


def enforce(uid: int, strait_key: str = "hormuz"):
    from game import state
    p = state.active(uid)
    if not p:
        return
    s = STRAITS.get(strait_key, {})
    if p["country"] in s.get("owners", []):
        return
    day = db.day_index()
    if db.kv_get(f"toll_enforced:{uid}:{day}"):
        return
    db.kv_set(f"toll_enforced:{uid}:{day}", "1")
    fine = int(p["money"] * 0.10)
    db.ex("UPDATE users SET money=money-? WHERE uid=?", (fine, uid))
