"""💵 جنگ جهانی — سیستم اقتصاد زنده: نفت، دلار، تورم، تجارت کالاها، صادرات/واردات، قراردادها و تحریم‌ها."""
import json
import random
import db
import texts
import countries

DEFAULTS = dict(oil=82.0, dollar=1.0, inflation=0.03)

# کالاهای بازرگانی جهانی (شناسه، نام، ایموجی، قیمت پایه)
GOODS = [
    ("wheat", "گندم و غلات", "🌾", 120),
    ("steel", "فولاد و فلزات", "⚙️", 350),
    ("chip", "نیمه‌هادی و تراشه", "💾", 850),
    ("oil", "نفت خام", "🛢️", 450),
    ("gold", "شمش طلا", "🥇", 2400),
]
GOODS_MAP = {g[0]: g for g in GOODS}

# سهم تولید نفت روزانه کشورها (هزار بشکه)
OIL_BPD = {
    "ir": 3400, "us": 13200, "ru": 9800, "cn": 4200, "sa": 9000,
    "ae": 3200, "iq": 4300, "kw": 2600, "no": 1800, "br": 3400,
    "ca": 4800, "mx": 1900, "qa": 1300, "ng": 1500, "kz": 1900,
}


def world() -> dict:
    raw = db.kv_get("world_econ")
    if not raw:
        w = dict(DEFAULTS)
        _save(w)
        return w
    d = db.jload(raw, {}) or {}
    for k, v in DEFAULTS.items():
        d.setdefault(k, v)
    return d


def _save(w: dict):
    db.kv_set("world_econ", json.dumps(w))


def price_factor() -> float:
    w = world()
    return max(0.60, min(3.50, (w["dollar"] * 0.5 + 0.5) * (1.0 + w["inflation"])))


def real_price(base: int) -> int:
    return max(10, int(base * price_factor()))


def tick() -> dict:
    w = world()
    oil_delta = random.uniform(-1.5, 1.8)
    from game import toll
    for key in toll.STRAITS:
        if toll.is_closed(key):
            oil_delta += 4.5
            w["inflation"] += 0.005

    w["oil"] = max(40.0, min(220.0, w["oil"] + oil_delta))
    w["dollar"] = max(0.70, min(2.00, w["dollar"] + random.uniform(-0.01, 0.015)))
    active_wars_cnt = len(db.q("SELECT id FROM wars WHERE status='active'"))
    w["inflation"] = max(0.01, min(0.45, w["inflation"] + active_wars_cnt * 0.002 - 0.001))
    _save(w)
    return w


def is_sanctioned(cid: str) -> bool:
    return db.kv_get(f"sanctioned:{cid}") == "1"


def sanctioned(cid: str) -> bool:
    return is_sanctioned(cid)


def set_sanction(leader_uid: int, target_cid: str) -> tuple[str, str]:
    from game import state
    p = state.active(leader_uid)
    if not p:
        return "⚠️ ابتدا با دستور «شروع» کشورتان را ثبت کنید.", ""
    cid = p["country"]
    if cid == target_cid:
        return "⚠️ نمی‌توانید کشور خودتان را تحریم کنید!", ""
    t_info = countries.COUNTRIES.get(target_cid, {})
    c_info = countries.COUNTRIES.get(cid, {})
    db.kv_set(f"sanctioned:{target_cid}", "1")
    user_tag = texts.mention(leader_uid, p["name"])
    ann = f"""🚫 <b>وضع تحریم‌های اقتصادی</b>
{texts.FULL}
رهبر {c_info.get('flag','')} <b>{c_info.get('name','')}</b> ({user_tag}) کشور {t_info.get('flag','')} <b>{t_info.get('name','')}</b> را تحت <b>تحریم کامل تجاری</b> قرار داد."""
    msg = f"🚫 تحریم‌ها علیه {t_info.get('name','')} برقرار شد."
    return msg, ann


def lift_sanction(leader_uid: int, target_cid: str) -> tuple[str, str]:
    from game import state
    p = state.active(leader_uid)
    if not p:
        return "⚠️ ابتدا وارد بازی شوید.", ""
    cid = p["country"]
    t_info = countries.COUNTRIES.get(target_cid, {})
    c_info = countries.COUNTRIES.get(cid, {})
    db.kv_set(f"sanctioned:{target_cid}", "0")
    user_tag = texts.mention(leader_uid, p["name"])
    ann = f"""🟢 <b>رفع رسمی تحریم‌های اقتصادی</b>
{texts.FULL}
کشور {c_info.get('flag','')} <b>{c_info.get('name','')}</b> با اعلام {user_tag} کلیه تحریم‌های تجاری {t_info.get('flag','')} <b>{t_info.get('name','')}</b> را <b>لغو</b> کرد."""
    msg = f"🟢 تحریم‌های {t_info.get('name','')} لغو گردید."
    return msg, ann


def sanction(leader_uid: int, target_cid: str) -> str:
    msg, _ = set_sanction(leader_uid, target_cid)
    return msg


def daily_deals(cid: str) -> list:
    return ["f35", "sejjil", "shahed", "abrams"]


# ═══════════ سیستم تجارت کالا و قراردادها ═══════════

def _user_cargo(uid: int) -> dict:
    return db.jload(db.kv_get(f"cargo:{uid}"), {}) or {}


def trade_view(uid: int) -> str:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا وارد بازی شوید."
    cargo = _user_cargo(uid)
    lines = [
        texts.hdr("میز تجارت و بازرگانی بین‌الملل", "🚢"),
        f"💰 خزانه‌ی شما: <b>{texts.money(p['country'], p['money'])}</b>\n",
        "📦 <b>موجودی انبار کالاها:</b>"
    ]
    for gid, name, em, base in GOODS:
        cnt = cargo.get(gid, 0)
        p_buy = real_price(base)
        p_sell = int(p_buy * 0.9)
        lines.append(f"▫️ {em} <b>{name}</b> (موجودی: <b>{texts.fa(cnt)}</b>)\n   خرید: {texts.money(p['country'], p_buy)} | فروش: {texts.money(p['country'], p_sell)}")
    lines += [
        texts.DASH,
        "💡 <i>از دکمه‌های زیر برای واردات (خرید) و صادرات (فروش) استفاده کنید.</i>"
    ]
    return "\n".join(lines)


def trade_buy(uid: int, gid: str, qty: int = 1) -> str:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    g = GOODS_MAP.get(gid)
    if not g:
        return "⚠️ کالای نامعتبر."
    cost = real_price(g[3]) * qty
    if p["money"] < cost:
        return f"⚠️ موجودی ناکافی! هزینه: {texts.money(p['country'], cost)} (موجودی: {texts.money(p['country'], p['money'])})"
    db.ex("UPDATE users SET money=money-? WHERE uid=?", (cost, uid))
    cargo = _user_cargo(uid)
    cargo[gid] = cargo.get(gid, 0) + qty
    db.kv_set(f"cargo:{uid}", json.dumps(cargo, ensure_ascii=False))
    return f"✅ تعداد {texts.fa(qty)} واحد <b>{g[1]}</b> به مبلغ {texts.money(p['country'], cost)} وارد شد."


def trade_sell(uid: int, gid: str, qty: int = 1) -> str:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    g = GOODS_MAP.get(gid)
    if not g:
        return "⚠️ کالای نامعتبر."
    cargo = _user_cargo(uid)
    have = cargo.get(gid, 0)
    if have < qty:
        return f"⚠️ موجودی انبار شما برای {g[1]} کافی نیست (موجودی: {texts.fa(have)})."
    revenue = int(real_price(g[3]) * 0.95) * qty
    db.ex("UPDATE users SET money=money+? WHERE uid=?", (revenue, uid))
    cargo[gid] = have - qty
    db.kv_set(f"cargo:{uid}", json.dumps(cargo, ensure_ascii=False))
    return f"💰 تعداد {texts.fa(qty)} واحد <b>{g[1]}</b> صادر شد و مبلغ {texts.money(p['country'], revenue)} به خزانه‌تان واریز گردید."


def contract_view(uid: int) -> str:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    return f"""🤝 <b>قراردادهای تجاری دوطرفه</b>
{texts.FULL}
کشورهای طرف قرارداد از +۲۵٪ سود بازرگانی بهره‌مند می‌شوند.
برای امضای پیمان با کشورهای دیگر، کشور مقصد را انتخاب کنید:"""


def contract(uid: int, target_cid: str) -> str:
    msg, _ = sign_trade_agreement(uid, target_cid)
    return msg


def sign_trade_agreement(uid: int, partner_cid: str) -> tuple[str, str]:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا وارد بازی شوید.", ""
    cid = p["country"]
    if cid == partner_cid:
        return "⚠️ تجارت آزاد با خودتان معنی ندارد!", ""
    existing = db.one("SELECT * FROM trade_agreements WHERE (a=? AND b=?) OR (a=? AND b=?)", (cid, partner_cid, partner_cid, cid))
    if existing:
        return "⚠️ پیمان تجارت آزاد بین این دو کشور قبلاً امضا شده است.", ""
    cost = 2000
    if p["money"] < cost:
        return f"⚠️ هزینه تأسیس خطوط بازرگانی {texts.money(cid, cost)} است (موجودی: {texts.money(cid, p['money'])}).", ""
    db.ex("UPDATE users SET money=money-? WHERE uid=?", (cost, uid))
    db.ex("INSERT INTO trade_agreements(a, b, created) VALUES(?, ?, ?)", (cid, partner_cid, db.now()))
    c_info = countries.COUNTRIES[cid]
    t_info = countries.COUNTRIES[partner_cid]
    user_tag = texts.mention(uid, p["name"])
    ann = f"""🤝 <b>امضای پیمان تجارت آزاد</b>
{texts.FULL}
کشورهای {c_info['flag']} <b>{c_info['name']}</b> ({user_tag}) و {t_info['flag']} <b>{t_info['name']}</b> پیمان تجارت آزاد امضا کردند!"""
    msg = f"✅ پیمان تجارت آزاد با {t_info['name']} برقرار شد."
    return msg, ann


def market() -> str:
    return market_overview()


def market_overview() -> str:
    w = world()
    lines = [
        texts.hdr("تابلوی اقتصاد و بازارهای جهانی", "📊"),
        f"▫️ <b>قیمت نفت خام برنت:</b> 🛢️ <code>${w['oil']:.2f}</code> بر بشکه",
        f"▫️ <b>شاخص دلار جهانی:</b> 💵 <code>{w['dollar']:.2f}x</code>",
        f"▫️ <b>نرخ تورم جهانی:</b> 📈 <code>{w['inflation']*100:.1f}٪</code>",
        f"▫️ <b>ضریب قیمت کالاها:</b> 🏷️ <code>{price_factor():.2f}x</code>",
        texts.DASH,
        "💡 <i>در تورم بالا، هزینه‌ی تجهیزات و ارتقای پایگاه‌ها افزایش می‌یابد.</i>",
    ]
    return "\n".join(lines)
