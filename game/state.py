"""⚔️ جنگ جهانی — وضعیت بازیکنان: شهروند → رزمنده → فرمانده کل + پروفایل سراسری و قدرت متناسب با زمان بازی."""
import contextlib
import json
import db
import texts
import countries


def active(uid: int) -> dict | None:
    """بازیکن ثبت‌نام‌شده با کشور — یا None."""
    p = get(uid)
    return p if p and p.get("country") else None


def get(uid: int) -> dict | None:
    r = db.one("SELECT * FROM users WHERE uid=?", (uid,))
    if not r:
        return None
    res = dict(r)
    # تضمین موجودی منصفانه (حداقل ۳۰ هزار دلار برای همه بازیکنان)
    if res.get("country") and (res.get("money") is None or res.get("money", 0) < 30000):
        db.ex("UPDATE users SET money=30000 WHERE uid=?", (uid,))
        res["money"] = 30000
    return res


def calculate_player_power(uid: int) -> int:
    """محاسبه قدرت استراتژیک بازیکن بر اساس زمان بازی، لول، انهدام‌ها و ارزش تجهیزات."""
    p = get(uid)
    if not p:
        return 10
    base = p["level"] * 30 + p["kills"] * 20 + p["xp"] // 8
    inv = db.q("SELECT iid, qty, dur FROM inventory WHERE uid=?", (uid,))
    eq_power = 0
    for it in inv:
        item_data = countries.ITEMS.get(it["iid"])
        if item_data:
            eq_power += (item_data[3] + item_data[4]) * it["qty"] * it["dur"] // 100
    return base + eq_power // 2


def balance_country_command(cid: str):
    """مدیریت چندفرماندهی در یک کشور:
    اگر چند بازیکن در یک گروه عضو یک کشور باشند، بازیکنی که بیشتر پلی داده و لول بالاتری دارد رهبر کل و بقیه فرمانده ارشد خواهند بود.
    """
    commanders = db.q("SELECT uid, level, xp, kills FROM users WHERE country=? ORDER BY level DESC, kills DESC, xp DESC", (cid,))
    if not commanders:
        return
    # نفر اول لیدر، بقیه فرماندهان ارشد
    top_uid = commanders[0]["uid"]
    db.ex("UPDATE users SET is_leader=1 WHERE uid=?", (top_uid,))
    for sub in commanders[1:]:
        db.ex("UPDATE users SET is_leader=0 WHERE uid=?", (sub["uid"],))


def ensure(uid: int, name=None, chat_id=None, username=None):
    clean_name = texts.esc(name or "")[:32]
    db.ex("""
    INSERT OR IGNORE INTO users(uid, name, joined, last_active, chat_id, username, money)
    VALUES(?, ?, ?, ?, ?, ?, 30000)
    """, (uid, clean_name, db.now(), db.now(), chat_id, username))
    
    db.ex("UPDATE users SET last_active=?, chat_id=COALESCE(?, chat_id) WHERE uid=?",
          (db.now(), chat_id, uid))
    
    if name or username:
        row = db.one("SELECT name, username FROM users WHERE uid=?", (uid,))
        if row:
            old = row["name"] or ""
            if name and (not old or old.startswith("Player")):
                db.ex("UPDATE users SET name=? WHERE uid=?", (clean_name, uid))
            if username and username != (row["username"] or ""):
                db.ex("UPDATE users SET username=? WHERE uid=?", (username, uid))


def enlist(uid: int, country: str, name: str) -> bool:
    """ثبت‌نام رسمی در کشور و اعطای هدایای ورود و تسلیحات کامل سازمانی."""
    if country not in countries.COUNTRIES:
        return False
    p = get(uid)
    clean_name = texts.esc(name)[:32]
    if p:
        if p["country"]:
            return False
        db.ex("""
        UPDATE users SET
            country=?,
            money=CASE WHEN money >= 30000 THEN money ELSE 30000 END,
            name=CASE WHEN name='' OR name IS NULL OR name LIKE 'Player%' THEN ? ELSE name END,
            last_active=?
        WHERE uid=?
        """, (country, clean_name, db.now(), uid))
        _starter_kit(uid, country)
        balance_country_command(country)
        return True

    db.ex("""
    INSERT INTO users(uid, name, country, money, joined, last_active)
    VALUES(?, ?, ?, 30000, ?, ?)
    """, (uid, clean_name, country, db.now(), db.now()))
    _starter_kit(uid, country)
    balance_country_command(country)
    return True


def _starter_kit(uid: int, country: str):
    """اعطای زرادخانه اولیه — ۲ عدد از تمام جنگ‌افزارهای مدرن کشور با دوام ۱۰۰٪."""
    c_info = countries.COUNTRIES.get(country)
    if not c_info:
        return
    for iid in c_info.get("items", []):
        db.ex("""
        INSERT INTO inventory(uid, iid, qty, dur)
        VALUES(?, ?, 2, 100)
        ON CONFLICT(uid, iid) DO UPDATE SET qty=MAX(inventory.qty, 2), dur=100
        """, (uid, iid))


def xp_need(level: int) -> int:
    return 120 + level * 80


def gain_xp(uid: int, xp: int):
    p = get(uid)
    if not p:
        return
    lv, x = p["level"], p["xp"] + xp
    while x >= xp_need(lv):
        x -= xp_need(lv)
        lv += 1
    db.ex("UPDATE users SET xp=?, level=? WHERE uid=?", (x, lv, uid))
    if p.get("country"):
        balance_country_command(p["country"])


def card(uid: int) -> str:
    p = active(uid)
    if not p:
        return "⚠️ ثبت‌نام نکرده‌اید — از دستور «شروع» استفاده کنید."
    c = countries.COUNTRIES.get(p["country"], {})
    t = texts
    import game.military as mil
    from game import politics
    party = politics.my_party(uid)
    from game import invest as _iv
    _rate = _iv.rate(uid)
    spec, pct, sname = countries.spec_of(p["country"])
    role_title = "👑 رهبر کل کشور" if p.get("is_leader") else "🎖️ سرلشکر ارشد"
    tot_power = calculate_player_power(uid)
    
    return "\n".join([
        t.hdr(f"پرونده نظامی {p['name']}", "🪖"),
        t.row("فرمانده", texts.mention(uid, p["name"])),
        t.row("کشور", f"{c.get('flag', '')} {c.get('name', '—')}" + (f" ({politics.regime_of(p['country'])})" if politics.regime_of(p['country']) else "")),
        t.row("سمت", role_title),
        t.row("قدرت کل", f"⚡ <b>{t.fa(tot_power)} واحد توان رزمی</b>"),
        t.DASH,
        t.row("دکترین", f"🎯 {sname} — +{t.fa(pct)}٪ قدرت {spec}"),
        t.row("شاخه رزم", mil.branch_name(p) or "نیروهای مسلح مشترک"),
        t.row("تخصص شاخه", " ".join(mil.role_of(p)[1:]) or "خط مقدم"),
        t.row("درجه نظامی", countries.rank_name(p["level"])),
        t.row("امتیاز رزم", f"{t.fa(p['xp'])} / {t.fa(xp_need(p['level']))} XP"),
        t.DASH,
        t.row("خزانه مالی", f"💵 {t.money(p['country'], p['money'])}"),
        *([t.row("سود سرمایه‌گذاری", f"📈 {t.money(p['country'], _rate)} در ساعت")] if _rate else []),
        t.row("سلامت جسمانی", f"❤️ {t.fa(p['hp'])} / {t.fa(p['max_hp'])} HP"),
        t.row("آمار تلفات/جاسوسی", f"⚔️ {t.fa(p['kills'])} انهدام | 🕵️ {t.fa(p['spy_ops'])} مأموریت"),
        t.row("حزب سیاسی", party["name"] if party else "مستقل"),
    ] + ([t.DASH, medals(uid)] if medals(uid) else []))


def medals(uid: int) -> str:
    """مدال‌های افتخار نظامی."""
    p = get(uid)
    if not p:
        return ""
    out = []
    if p["kills"] >= 10:
        out.append("🎖️ نشان دلاوری")
    if p["spy_ops"] >= 5:
        out.append("🕵️ نشان مأمور ویژه")
    if p["level"] >= 5:
        out.append("⭐ مدال افسری")
    if p["level"] >= 10:
        out.append("🌟 مدال سرلشکری")
    if int(db.kv_get(f"streak:{uid}", "0")) >= 5:
        out.append("🛡️ سرباز فداکار")
    if db.kv_get(f"guide_done:{uid}"):
        out.append("📚 دانش‌آموخته دکترین جنگ")
    return "🏅 " + " · ".join(out) if out else ""


def geo_colony(cid: str):
    from game import geo
    return geo.colony_of(cid)


def geo_colonies(cid: str):
    from game import geo
    return geo.colonies_of(cid)


def ration(uid: int) -> str:
    """جیره روزانه + زنجیره حضور."""
    p = active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    day = db.day_index()
    if db.kv_get(f"ration:{uid}") == str(day):
        return "⏳ جیره امروز را دریافت کرده‌اید — فردا مجدداً مراجعه کنید."
    
    streak = int(db.kv_get(f"streak:{uid}", "0"))
    if db.kv_get(f"ration:{uid}") == str(day - 1):
        streak += 1
    else:
        streak = 1
        
    t = texts
    from game import military as _mil2
    from game import infra as _ifr2
    from game import welfare as _wl2
    
    amount = int((500 + min(7, streak) * 150) * _mil2.eco_mult(uid)
                 * _ifr2.output_mult(p["country"])
                 * _wl2.welfare_mult(p["country"]))
    
    tax_note = ""
    col = geo_colony(p["country"])
    if col:
        cut = amount * 3 // 10
        amount -= cut
        tax_note = f"\n💸 مالیات مستعمراتی به {countries.COUNTRIES[col]['name']}: −{t.money(p['country'], cut)}"
        
    mine = geo_colonies(p["country"])
    if mine:
        add = amount * len(mine) // 5
        amount += add
        tax_note = f"\n👑 خراج دریافتی از {t.fa(len(mine))} مستعمره: +{t.money(p['country'], add)}"
        
    from game import economy as _eco
    oil = _eco.oil_share(p["country"])
    amount += oil
    oil_note = f"\n🛢️ سهم درآمد صادرات نفت: +{t.money(p['country'], oil)}" if oil >= 10 else ""
    
    db.ex("UPDATE users SET money=money+? WHERE uid=?", (amount, uid))
    db.kv_set(f"ration:{uid}", str(day))
    db.kv_set(f"streak:{uid}", str(streak))
    
    from game import quests
    quests.on_event(uid, "جیره")
    
    bonus = ""
    if streak >= 3:
        import random as _r
        if _r.random() < 0.40:
            own = {r["iid"] for r in db.q("SELECT iid FROM inventory WHERE uid=?", (uid,))}
            cands = [iid for iid in countries.COUNTRIES[p["country"]]["items"] if iid not in own]
            if cands:
                iid = _r.choice(cands)
                db.ex("INSERT OR REPLACE INTO inventory(uid,iid,qty,dur) VALUES(?,?,1,100)", (uid, iid))
                it = countries.ITEMS[iid]
                bonus = f"\n🎁 <b>صندوق ویژه لجستیک ارتش:</b> ۱ واحد {it[1]} {it[0]} رایگان تحویل شد!"
            else:
                db.ex("UPDATE users SET money=money+500 WHERE uid=?", (uid,))
                bonus = "\n🎁 <b>صندوق ویژه لجستیک ارتش:</b> +۵۰۰ دلار پاداش نقدی وفاداری!"
                
    cur = texts.money(p["country"], amount)
    return (f"📦 <b>جیره و مواجب رزمی روزانه:</b> {cur}{oil_note}\n"
            f"🔥 <b>زنجیره حضور فعال:</b> {texts.fa(streak)} روز پیوسته\n"
            f"💰 <b>موجودی کل خزانه:</b> {texts.money(p['country'], get(uid)['money'])}{tax_note}{bonus}")


def daily(uid: int) -> str:
    """جایزه روزانه با زنجیره پیوسته."""
    p = active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    t = texts
    day = db.day_index()
    st = db.jload(db.kv_get(f"daily:{uid}"), None) or {}
    last, streak = st.get("day"), int(st.get("streak", 0))
    if last == day:
        nxt = 300 + 200 * min(streak + 1, 7)
        return "\n".join([
            t.hdr("پاداش حضور روزانه", "🎁"),
            f"✅ امروز پاداش خود را دریافت کرده‌اید — 🔥 زنجیره: {t.fa(streak)} روز",
            f"💵 پاداش فردا: {t.money(p['country'], nxt)}",
            "📌 هر روز سر بزنید تا زنجیره پاداش قطع نشود!",
        ])
    streak = streak + 1 if last == day - 1 else 1
    prize = 300 + 200 * min(streak, 7)
    db.ex("UPDATE users SET money=money+? WHERE uid=?", (prize, uid))
    db.kv_set(f"daily:{uid}", json.dumps({"day": day, "streak": streak}, ensure_ascii=False))
    lines = [
        t.hdr("پاداش حضور روزانه", "🎁"),
        f"🔥 زنجیره حضور متوالی: <b>{t.fa(streak)}</b> روز",
        f"💵 مبلغ <b>+{t.money(p['country'], prize)}</b> به خزانه شما واریز گردید.",
    ]
    if last is not None and last < day - 1:
        lines.append("⚠️ زنجیره شما به دلیل عدم حضور قطع شده بود و از نو آغاز شد.")
    if streak >= 7:
        lines.append("🌟 هفته طلایی تکمیل شد! حداکثر پاداش برای شما فعال است.")
    lines.append(f"🔮 پاداش فردا: <b>{t.money(p['country'], 300 + 200 * min(streak + 1, 7))}</b>")
    return "\n".join(lines)


WORK_CD = 600


def work(uid: int) -> str:
    """شیفت کاری و خدمت نظامی."""
    p = active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    t = texts
    last_work = int(db.kv_get(f"work:{uid}", "0") or 0)
    if db.now() - last_work < WORK_CD:
        left = WORK_CD - (db.now() - last_work)
        return f"⏳ به استراحت نیاز دارید! لطفاً <b>{t.fa(max(1, (left + 59) // 60))} دقیقه</b> دیگر تلاش کنید."
        
    db.kv_set(f"work:{uid}", str(db.now()))
    from game import military as _mil
    from game import infra as _ifr
    from game import welfare as _wl
    
    pay = int((300 + p["level"] * 25) * _mil.eco_mult(uid)
              * _ifr.output_mult(p["country"]) * _wl.welfare_mult(p["country"]))
    db.ex("UPDATE users SET money=money+? WHERE uid=?", (pay, uid))
    
    wl = [
        t.hdr("پایان شیفت کاری و مأموریت", "💼"),
        f"💵 دستمزد مأموریت: <b>+{t.money(p['country'], pay)}</b>",
        f"💰 موجودی کل خزانه: <b>{t.money(p['country'], p['money'] + pay)}</b>",
        f"⏱️ شیفت بعدی: {t.fa(WORK_CD // 60)} دقیقه دیگر — با ارتقای درجه، دستمزد افزایش می‌یابد.",
    ]
    if _ifr.output_mult(p["country"]) < 1:
        wl.append("⚠️ زیرساخت کشور آسیب‌دیده است — درآمد کاری کاهش یافته (تعمیر: نظامی → زیرساخت).")
    return "\n".join(wl)
