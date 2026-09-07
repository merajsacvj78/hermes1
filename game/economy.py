"""💵 جنگ جهانی — سیستم اقتصاد زنده: نفت، دلار، تورم، تجارت کالاها، صادرات/واردات، قراردادها و تحریم‌ها."""
import json
import random
import db
import texts
import countries

DEFAULTS = dict(oil=82.0, dollar=1.0, inflation=0.03)

SPREAD = 0.10

GOODS = [
    ("wheat", "گندم و غلات", "🌾", 120),
    ("steel", "فولاد و فلزات", "⚙️", 350),
    ("chip", "نیمه‌هادی و تراشه", "💾", 850),
    ("oil", "نفت خام", "🛢️", 450),
    ("gold", "شمش طلا", "🥇", 2400),
    ("copper", "مس صنعتی", "🧱", 200),
]
GOODS_MAP = {g[0]: g for g in GOODS}

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


def good_price(gid: str) -> int:
    g = GOODS_MAP.get(gid)
    return real_price(g[3]) if g else 100


def deal_price(price: int) -> int:
    return max(10, int(price * 0.80))


def fx(cid: str) -> float:
    c = countries.COUNTRIES.get(cid, {})
    base = float(c.get("fx", 1.0)) if c else 1.0
    if is_sanctioned(cid) or sanctioned(cid) or int(db.kv_get(f"sanction:{cid}", "0") or 0) > 0:
        return base * 1.35
    return base


def oil_share(cid: str) -> int:
    bpd = OIL_BPD.get(cid, 1000)
    base = max(50, bpd // 25)
    if is_sanctioned(cid) or sanctioned(cid) or int(db.kv_get(f"sanction:{cid}", "0") or 0) > 0:
        return base // 2
    return base


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


def set_sanction(cid: str, state_bool: bool):
    db.kv_set(f"sanctioned:{cid}", "1" if state_bool else "0")
    if state_bool:
        db.kv_set(f"sanction:{cid}", str(db.now()))
    else:
        db.kv_del(f"sanction:{cid}")


def lift_sanction(cid: str):
    set_sanction(cid, False)


def sanction(leader_uid: int, target_cid: str) -> str:
    from game import state
    p = state.active(leader_uid)
    if not p:
        return "⚠️ اول «شروع»"
    if not p.get("is_leader"):
        return "⚠️ تنها رهبر کشور می‌تواند تحریم وضع یا لغو کند."
    if target_cid not in countries.COUNTRIES:
        return "⚠️ کشور نامعتبر است."
    if target_cid == p["country"]:
        return "⚠️ نمی‌توانید خودتان را تحریم کنید!"

    t_info = countries.COUNTRIES[target_cid]
    if is_sanctioned(target_cid):
        lift_sanction(target_cid)
        return f"🕊️ تحریم‌های اقتصادی علیه <b>{t_info['name']}</b> لغو و برداشته شد."
    else:
        set_sanction(target_cid, True)
        return f"🚫 <b>تحریم‌ها علیه {t_info['name']} برقرار شد.</b>\nصادرات نفت و ارزش پول این کشور تضعیف شد."


def daily_deals(cid: str) -> list:
    c_items = countries.COUNTRIES.get(cid, {}).get("items", [])
    if c_items:
        return c_items[:2]
    return ["f35", "sejjil", "shahed", "abrams"]


# ═══════════ سیستم تجارت کالا و قراردادها ═══════════

def _user_cargo(uid: int) -> dict:
    return db.jload(db.kv_get(f"cargo:{uid}"), {}) or {}


def _save_cargo(uid: int, cargo: dict):
    db.kv_set(f"cargo:{uid}", json.dumps(cargo, ensure_ascii=False))


def holdings(uid: int) -> dict:
    return _user_cargo(uid)


def trade_view(uid: int) -> str:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا وارد بازی شوید."
    cargo = _user_cargo(uid)
    lines = [
        texts.hdr("میز بازرگانی و تجارت بین‌الملل", "🚢"),
        f"💰 موجودی خزانه شما: <b>{texts.money(p['country'], p['money'])}</b>\n",
        "📦 <b>موجودی انبار کالاها (حداکثر ۲۰ واحد):</b>"
    ]
    for gid, name, em, base in GOODS:
        cnt = cargo.get(gid, 0)
        p_buy = int(good_price(gid) * (1 + SPREAD))
        p_sell = int(good_price(gid) * (1 - SPREAD))
        lines.append(f"▫️ {em} <b>{name}</b> (انبار: <b>{texts.fa(cnt)}</b>)\n   خرید: {texts.money(p['country'], p_buy)} | فروش: {texts.money(p['country'], p_sell)}")
    lines += [
        texts.DASH,
        "💡 <i>با استفاده از دکمه‌های زیر کالاها را وارد کنید و در بازارهای جهانی صادر نمایید.</i>"
    ]
    return "\n".join(lines)


def trade_buy(uid: int, gid: str, qty: int = 1) -> str:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    g = GOODS_MAP.get(gid)
    if not g:
        return "⚠️ کالای نامعتبر است."
    cargo = _user_cargo(uid)
    current_cnt = cargo.get(gid, 0)
    if current_cnt + qty > 20:
        return f"⚠️ انبار کالا پر است! سقف گنجایش ۲۰ واحد است (موجودی فعلی: {current_cnt})."
    unit_p = int(good_price(gid) * (1 + SPREAD))
    cost = unit_p * qty
    if p["money"] < cost:
        return f"⚠️ موجودی ناکافی! هزینه: {texts.money(p['country'], cost)} (موجودی شما: {texts.money(p['country'], p['money'])})"
    db.ex("UPDATE users SET money=money-? WHERE uid=?", (cost, uid))
    cargo[gid] = current_cnt + qty
    _save_cargo(uid, cargo)
    return f"🚢 <b>واردات موفق:</b> {texts.fa(qty)} واحد {g[1]} {g[2]} خریداری شد ({texts.money(p['country'], cost)} کسر گردید — انبار: {texts.fa(cargo[gid])})."


def trade_sell(uid: int, gid: str, qty: int = 1) -> str:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    g = GOODS_MAP.get(gid)
    if not g:
        return "⚠️ کالای نامعتبر است."
    cargo = _user_cargo(uid)
    have = cargo.get(gid, 0)
    if have < qty:
        return f"⚠️ این کالا را در انبارت نداری (موجودی: {texts.fa(have)})."
    unit_s = int(good_price(gid) * (1 - SPREAD))
    gain = unit_s * qty
    db.ex("UPDATE users SET money=money+? WHERE uid=?", (gain, uid))
    cargo[gid] = have - qty
    _save_cargo(uid, cargo)
    return f"💰 <b>صادرات موفق:</b> {texts.fa(qty)} واحد {g[1]} {g[2]} صادر شد و مبلغ {texts.money(p['country'], gain)} به خزانه‌تان واریز گردید."


def contract_view(uid: int) -> str:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا وارد بازی شوید."
    c = countries.COUNTRIES[p["country"]]
    rows = db.q("SELECT * FROM trade_agreements WHERE a=? OR b=?", (p["country"], p["country"]))
    lines = [
        texts.hdr(f"پیمان‌های تجارت آزاد و خطوط بازرگانی {c['name']} {c['flag']}", "📜"),
        f"تعداد پیمان‌های فعال: <b>{texts.fa(len(rows))} پیمان تجاری</b>\n"
    ]
    if not rows:
        lines.append("🌐 هیچ پیمان تجارت آزادی برقرار نیست — با سایر کشورها توافق‌نامه امضا کنید.")
    else:
        for r in rows:
            partner = r["b"] if r["a"] == p["country"] else r["a"]
            p_info = countries.COUNTRIES.get(partner, {})
            lines.append(f"▫️ تجارت آزاد با {p_info.get('flag','')} <b>{p_info.get('name','')}</b> (+۱۵٪ درآمد بازرگانی)")
    lines += ["", "💼 <i>برای تأسیس خط تجاری جدید از دکمه‌های زیر استفاده کنید (هزینه: ۲٬۰۰۰ دلار).</i>"]
    return "\n".join(lines)


def contract(uid: int) -> str:
    return contract_view(uid)


def sign_trade_agreement(uid: int, target_cid: str) -> tuple[str, str]:
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا با دستور «شروع» کشورتان را تعیین کنید.", ""

    cid = p["country"]
    if cid == target_cid:
        return "⚠️ نمی‌توانید با کشور خودتان پیمان تجاری ببندید!", ""

    if target_cid not in countries.COUNTRIES:
        return "⚠️ کشور مقصد یافت نشد.", ""

    cost = 2000
    if p["money"] < cost:
        return f"⚠️ هزینه تأسیس خطوط بازرگانی {texts.money(cid, cost)} است (موجودی: {texts.money(cid, p['money'])}).", ""

    existing = db.one("SELECT 1 FROM trade_agreements WHERE (a=? AND b=?) OR (a=? AND b=?)", (cid, target_cid, target_cid, cid))
    if existing:
        return "⚠️ پیمان تجاری با این کشور از قبل فعال است.", ""

    db.ex("UPDATE users SET money=money-? WHERE uid=?", (cost, uid))
    db.ex("INSERT INTO trade_agreements(a, b, created) VALUES(?, ?, ?)", (cid, target_cid, db.now()))

    c_info = countries.COUNTRIES[cid]
    t_info = countries.COUNTRIES[target_cid]
    user_tag = texts.mention(uid, p["name"])

    ann = f"""🚢 <b>انعقاد پیمان تجارت آزاد و ترانزیت کالا</b>
{texts.FULL}
کشورهای {c_info['flag']} <b>{c_info['name']}</b> (به نمایندگی {user_tag}) و {t_info['flag']} <b>{t_info['name']}</b> رسماً خطوط تجارت آزاد را برقرار کردند!
📈 عواید حاصل از صادرات و تعرفه‌های گمرکی برای طرفین فعال گردید."""

    msg = f"✅ پیمان تجارت آزاد با {t_info['name']} برقرار شد."
    return msg, ann


def market() -> str:
    return market_overview()


def market_overview() -> str:
    w = world()
    t = texts
    d_str = f"{w['dollar']:.2f}"
    o_str = f"{w['oil']:.1f}"
    i_str = f"{w['inflation'] * 100:.1f}"
    lines = [
        t.hdr("تابلوی اقتصاد و بازارهای مالی جهان", "📊"),
        f"💵 <b>شاخص جهانی دلار:</b> ×{t.fa(d_str)}",
        f"🛢️ <b>قیمت هر بشکه نفت برنت:</b> ${t.fa(o_str)}",
        f"📈 <b>نرخ تورم بازارهای جهانی:</b> {t.fa(i_str)}٪",
        "",
        "💡 <i>نوسانات بازار بر قیمت تسلیحات نظامی، عوارض تنگه‌ها و کالاهای بازرگانی تأثیر مستقیم دارد.</i>"
    ]
    return "\n".join(lines)
