"""💰 جنگ جهانی — سرمایه‌گذاری، درآمدهای ساعتی دقیق به وقت ایران و منابع پایدار."""
import json
import db
import texts
from game import state

ASSETS = [
    # (کلید، نام، قیمت، درآمد هر ساعت)
    ("mine", "⛏️ معدن طلا و عناصر نادر", 5000, 220),
    ("oil", "🛢️ دکل و چاه نفت فراساحلی", 12000, 580),
    ("ref", "🏭 پالایشگاه پتروشیمی", 30000, 1450),
    ("fac", "⚙️ مجتمع صنایع سنگین نظامی", 80000, 3800),
    ("bank", "🏦 بانک بین‌المللی سرمایه‌گذاری", 200000, 9500),
]
_A = {a[0]: a for a in ASSETS}


def _bag(uid) -> dict:
    return db.jload(db.kv_get(f"inv:{uid}"), {}) or {}


def _last(uid) -> int:
    return int(db.kv_get(f"invt:{uid}", "0") or 0)


def rate(uid) -> int:
    """مجموع درآمد ساعتی دارایی‌های بازیکن."""
    bag = _bag(uid)
    return sum(_A[k][3] * q for k, q in bag.items() if k in _A)


def view(uid) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا با دستور «شروع» کشورتان را ثبت کنید."

    t = texts
    bag = _bag(uid)
    rt = rate(uid)
    lines = [
        t.hdr("مرکز سرمایه‌گذاری و درآمدهای پایدار", "📈"),
        f"💰 خزانه‌ی شما: <b>{t.money(p['country'], p['money'])}</b>"
    ]

    last = _last(uid)
    if rt and last:
        elapsed_sec = db.now() - last
        h = elapsed_sec / 3600
        accumulated = int(rt * (elapsed_sec // 3600))
        lines += [
            f"▫️ مجموع درآمد ساعتی: <b>{t.money(p['country'], rt)}</b>",
            f"▫️ زمان انباشته: <b>{t.fa(f'{h:.1f}')} ساعت</b> (مبلغ آماده برداشت: <b>{t.money(p['country'], accumulated)}</b>)",
        ]
    else:
        lines += ["", "هنوز دارایی نخریده‌اید — هر دارایی در هر ساعت سود خالص تولید می‌کند:"]

    lines.append(t.DASH)
    for key, name, price, inc in ASSETS:
        own = bag.get(key, 0)
        own_s = f" (تعداد: <b>{t.fa(own)}</b>)" if own else ""
        lines.append(f"{name}{own_s}\n   💵 قیمت: {t.money(p['country'], price)} | 📈 درآمد: {t.money(p['country'], inc)}/ساعت")

    lines += [
        t.DASH,
        "💡 <i>درآمدها به وقت رسمی تهران محاسبه می‌شوند و دقیقه‌های ناقص نمی‌سوزند.</i>",
        "برای واریز به خزانه دکمه‌ی «برداشت درآمد» را لمس کنید."
    ]
    return "\n".join(lines)


def buy(uid, key: str) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا با دستور «شروع» وارد شوید."

    if key not in _A:
        return "⚠️ دارایی نامعتبر است."

    _, name, price, inc = _A[key]
    if p["money"] < price:
        return (f"⚠️ موجودی ناکافی! قیمت {name} برابر {texts.money(p['country'], price)} است.\n"
                f"موجودی شما: {texts.money(p['country'], p['money'])}")

    db.ex("UPDATE users SET money=money-? WHERE uid=?", (price, uid))
    bag = _bag(uid)
    bag[key] = bag.get(key, 0) + 1
    db.kv_set(f"inv:{uid}", json.dumps(bag, ensure_ascii=False))

    if not _last(uid):
        db.kv_set(f"invt:{uid}", str(db.now()))

    return "\n".join([
        texts.hdr("خرید موفقیت‌آمیز دارایی", "✅"),
        f"▫️ {name} به مجموعه‌ی سرمایه‌گذاری شما افزوده شد (دارایی: {texts.fa(bag[key])} واحد).",
        f"▫️ نرخ درآمد ساعتی جدید شما: <b>{texts.money(p['country'], rate(uid))}</b>",
        f"▫️ مانده خزانه: {texts.money(p['country'], p['money'] - price)}"
    ])


def collect(uid) -> str:
    """برداشت سود انباشته‌شده — انتقال کامل به خزانه‌ی کاربر."""
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا با دستور «شروع» وارد شوید."

    rt = rate(uid)
    if not rt:
        return "⚠️ شما هنوز دارایی فعالی ندارید. ابتدا از فهرست زیر یک مجتمع یا معدن خریداری کنید."

    last = _last(uid)
    if not last:
        db.kv_set(f"invt:{uid}", str(db.now()))
        return "⏳ شمارشگر درآمد ساعتی شما از همین لحظه فعال شد. ۶۰ دقیقه دیگر برای برداشت مراجعه کنید."

    elapsed = db.now() - last
    hours = elapsed // 3600
    if hours < 1:
        left_min = 60 - (elapsed // 60)
        return f"⏳ هنوز یک ساعت کامل سپری نشده است. لطفاً <b>{texts.fa(left_min)} دقیقه دیگر</b> برای برداشت مراجعه کنید."

    from game import infra as _ifr
    from game import welfare as _wl

    mult = _ifr.output_mult(p["country"]) * _wl.welfare_mult(p["country"])
    pay = int(rt * hours * mult)

    db.ex("UPDATE users SET money=money+? WHERE uid=?", (pay, uid))
    # دقیقه‌های اضافی حفظ می‌شوند
    db.kv_set(f"invt:{uid}", str(last + hours * 3600))

    return "\n".join([
        texts.hdr("واریز موفقیت‌آمیز درآمد ساعتی", "💵"),
        f"▫️ مدت زمان محاسبه‌شده: <b>{texts.fa(hours)} ساعت</b>",
        f"▫️ سود پایه: {texts.money(p['country'], rt * hours)}",
        f"▫️ ضریب زیرساخت و رفاه ملی: {texts.fa(f'{mult:.2f}')}x",
        f"▫️ مبلغ واریزی به خزانه: <b>{texts.money(p['country'], pay)}</b>",
        texts.DASH,
        f"💰 موجودی کل خزانه: <b>{texts.money(p['country'], p['money'] + pay)}</b>"
    ])


def distribute_hourly_payouts_for_all(chat_id: int = None) -> list[str]:
    """واریز خودکار سر ساعت برای تمام بازیکنانی که دارایی دارند و ارسال پیام اطلاع‌رسانی با تگ."""
    rows = db.q("SELECT uid, name, country, money FROM users WHERE country IS NOT NULL")
    paid_users = []
    total_distributed = 0
    
    current_hour = db.now() // 3600
    last_ann = db.kv_get("last_hourly_ann_hour")
    
    for r in rows:
        uid = r["uid"]
        rt = rate(uid)
        last = _last(uid)
        if not last:
            db.kv_set(f"invt:{uid}", str(db.now()))
            continue
        elapsed = db.now() - last
        hours = elapsed // 3600
        if hours >= 1:
            from game import infra as _ifr
            from game import welfare as _wl
            from game import economy as _eco
            mult = _ifr.output_mult(r["country"]) * _wl.welfare_mult(r["country"])
            inv_pay = int((rt or 0) * hours * mult)
            oil_pay = int(_eco.oil_share(r["country"]) * hours)
            total_pay = inv_pay + oil_pay
            if total_pay > 0:
                db.ex("UPDATE users SET money=money+? WHERE uid=?", (total_pay, uid))
                paid_users.append((uid, r["name"], r["country"], total_pay))
                total_distributed += total_pay
            db.kv_set(f"invt:{uid}", str(last + hours * 3600))
            
    notifications = []
    if str(current_hour) != last_ann and paid_users:
        db.kv_set("last_hourly_ann_hour", str(current_hour))
        tags = " ".join(texts.mention(u[0], u[1]) for u in paid_users[:12])
        msg = f"""💰 <b>واریز خودکار درآمدهای ساعتی و سهم نفت ملی</b>
{texts.FULL}
{tags}

📊 <b>گزارش خزانه مرکزی:</b>
سود مجتمع‌های سرمایه‌گذاری، صنایع و سهم فروش نفت به حساب کلیه فرماندهان فعال واریز گردید (مجموع واریزی: <b>{texts.money('us', total_distributed)}</b>).
💡 موجودی و تراکنش‌های خود را از «منو ➔ مشخصات من» بررسی کنید."""
        notifications.append(msg)
        
    return notifications
