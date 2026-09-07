"""🏗️ جنگ جهانی — زیرساخت‌های ملی: شبکه برق، فرودگاه، بنادر و صنایع سنگین."""
import json
import countries
import db
import texts

INFRA = [
    ("power", "⚡ شبکه سراسری برق و C4ISR", 2500),
    ("airport", "🛫 پایگاه‌های هوایی و فرودگاه", 3000),
    ("port", "⚓ بنادر و تأسیسات ساحلی", 3000),
    ("industry", "🏭 مجتمع‌های صنایع سنگین و نظامی", 4000),
]

_I = {k: (k, n, p) for k, n, p in INFRA}


def state_of(cid: str) -> dict:
    """HP هر زیرساخت کشور — پیش‌فرض ۱۰۰٪."""
    st = db.jload(db.kv_get(f"infra:{cid}"), {}) or {}
    return {k: max(0, min(100, int(st.get(k, 100)))) for k, _, _ in INFRA}


def _save(cid: str, st: dict):
    db.kv_set(f"infra:{cid}", json.dumps(st, ensure_ascii=False))


def output_mult(cid: str) -> float:
    """ضریب درآمد ملی — میانگین سلامت زیرساخت."""
    st = state_of(cid)
    base = (sum(st.values()) / (100 * len(st))) if st else 1.0
    return base * 1.10 if built(cid).get("housing") else base


def power_ok(cid: str) -> bool:
    return state_of(cid)["power"] >= 40


def port_ok(cid: str) -> bool:
    return state_of(cid)["port"] >= 40


def airport_mult(cid: str) -> float:
    return 0.80 if state_of(cid)["airport"] < 40 else 1.0


def limit_notes(cid: str) -> list:
    st = state_of(cid)
    out = []
    if st["power"] < 40:
        out.append("⚡ خاموشی شبکه برق — خرید تجهیزات فوق سنگین ممنوع شده است.")
    if st["airport"] < 40:
        out.append("🛫 آسیب باند فرودگاه‌ها — ضربات هوایی و پهپادی ۲۰٪ ضعیف‌تر شده است.")
    if st["port"] < 40:
        out.append("⚓ آسیب تأسیسات بندری — صادرات و واردات دریایی متوقف شده است.")
    if st["industry"] < 40:
        out.append("🏭 تخریب صنایع — تولید ناخالص و درآمد ملی به شدت کاهش یافته است.")
    return out


def damage(cid: str, key: str, pct: int) -> dict:
    st = state_of(cid)
    st[key] = max(0, st[key] - pct)
    _save(cid, st)
    return {"key": key, "hp": st[key]}


def random_damage(cid: str, rnd) -> dict:
    key = rnd.choice([k for k, _, _ in INFRA])
    return damage(cid, key, rnd.randint(10, 25))


def _bar(hp: int) -> str:
    if hp >= 75:
        return "🟢"
    if hp >= 50:
        return "🟡"
    if hp >= 25:
        return "🟠"
    return "🔴"


def view(uid: int) -> str:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    c = countries.COUNTRIES[p["country"]]
    st = state_of(p["country"])
    t = texts
    lines = [
        t.hdr(f"وضعیت زیرساخت‌های ملی {c['name']} {c['flag']}", "🏗️"),
        f"📊 ضریب بازدهی اقتصاد ملی: <b>{t.fa(int(output_mult(p['country']) * 100))}٪</b>",
        ""
    ]
    for key, name, price in INFRA:
        cur_hp = st[key]
        lines.append(f"{_bar(cur_hp)} <b>{name}</b>: {t.fa(cur_hp)}٪"
                     + (f" (هزینه تعمیر کامل: {t.money(p['country'], price * (100 - cur_hp) // 100)})"
                        if cur_hp < 100 else " — ✅ کاملاً سالم"))
    notes = limit_notes(p["country"])
    if notes:
        lines += ["", "⚠️ <b>محدودیت‌های فعال به دلیل خسارات جنگی:</b>"] + [f"▫️ {n}" for n in notes]
    lines += ["", "🔧 <i>تمامی شهروندان و فرماندهان می‌توانند در بازسازی زیرساخت‌ها مشارکت کنند.</i>"]
    return "\n".join(lines)


def repair(uid: int, key: str) -> str:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    if key not in _I:
        return "⚠️ زیرساخت نامعتبر است."
    _, name, full = _I[key]
    st = state_of(p["country"])
    missing = 100 - st[key]
    if missing <= 0:
        return f"✅ تأسیسات <b>{name}</b> کاملاً سالم است و نیازی به بازسازی ندارد."
    cost = max(50, full * missing // 100)
    if p["money"] < cost:
        return f"⚠️ بودجه ناکافی! هزینه بازسازی: {texts.money(p['country'], cost)} (موجودی: {texts.money(p['country'], p['money'])})"
    db.ex("UPDATE users SET money=money-? WHERE uid=?", (cost, uid))
    st[key] = 100
    _save(p["country"], st)
    return f"""✅ <b>بازسازی کامل زیرساخت</b>
{texts.FULL}
🏗️ پروژه: <b>{name}</b> بازسازی شد (سلامت: ۱۰۰٪).
💵 هزینه بازسازی: <b>{texts.money(p['country'], cost)}</b>
📊 بازدهی جدید اقتصاد ملی: <b>{texts.fa(int(output_mult(p['country']) * 100))}٪</b>"""


# ═══════════ پروژه‌های عمرانی راهبردی ═══════════

BUILDINGS = [
    ("base", "🎖️ قرارگاه فرماندهی مرکزی", 8000, "+۱۵٪ قدرت آتش ارتش"),
    ("housing", "🏘️ شهرک‌های مسکونی پیشرفته", 6000, "+۱۵٪ درآمد عمومی شهروندان"),
    ("bunker", "🛡️ شبکه پناهگاه‌های ضد بمب اتمی", 7000, "کاهش ۲۰٪ آسیب بمباران‌های دشمن"),
]

_B = {k: (k, n, p, e) for k, n, p, e in BUILDINGS}


def built(cid: str) -> dict:
    st = db.jload(db.kv_get(f"built:{cid}"), {}) or {}
    return {k: bool(st.get(k)) for k, _, _, _ in BUILDINGS}


def build(uid: int, key: str) -> str:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    if key not in _B:
        return "⚠️ پروژه عمرانی نامعتبر است."
    _, name, price, eff = _B[key]
    b = built(p["country"])
    if b.get(key):
        return f"✅ پروژه <b>{name}</b> قبلاً احداث شده و اثرات آن فعال است."
    if p["money"] < price:
        return f"⚠️ بودجه ناکافی! هزینه احداث: {texts.money(p['country'], price)} (موجودی: {texts.money(p['country'], p['money'])})"
    db.ex("UPDATE users SET money=money-? WHERE uid=?", (price, uid))
    b[key] = True
    db.kv_set(f"built:{p['country']}", json.dumps(b, ensure_ascii=False))
    return f"""🏗️ <b>افتتاح پروژه ملی</b>
{texts.FULL}
🏛️ نام پروژه: <b>{name}</b> با موفقیت احداث شد!
✨ مزیت دائمی: <b>{eff}</b>
💵 هزینه سرمایه‌گذاری: <b>{texts.money(p['country'], price)}</b>"""


def strike_mult(cid: str) -> float:
    return 1.15 if built(cid).get("base") else 1.0


def damage_in_mult(cid: str) -> float:
    return 0.80 if built(cid).get("bunker") else 1.0


def buildings_view(uid: int) -> str:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    b = built(p["country"])
    lines = [
        texts.hdr("پروژه‌های عمرانی راهبردی کشور", "🏛️"),
        "✨ احداث دائمی پروژه‌ها با مزایای سراسری برای تمامی اعضای کشور:",
        ""
    ]
    for key, name, price, eff in BUILDINGS:
        mark = "✅ <b>احداث شده</b>" if b.get(key) else f"💵 {texts.money(p['country'], price)}"
        lines.append(f"▫️ <b>{name}</b>\n   اثر: {eff}\n   وضعیت: {mark}\n")
    return "\n".join(lines)
