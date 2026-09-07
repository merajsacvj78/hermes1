"""🛡️ جنگ جهانی — سپر پدافندی ملی و سامانه‌های دفاع هوایی چندلایه."""
import random
import countries
import db
import texts

LAYERS = {
    "ضد موشک": "🛡️",
    "ضد هوایی": "✈️",
    "ضد پهپاد": "📡",
    "ضد دریایی": "⚓",
    "دفاع زمینی": "🏰",
    "جنگ الکترونیک": "⚡",
}

# نوع حمله → لایه دفاعی مقابله‌کننده
KIND_LAYER = {
    "موشکی": "ضد موشک",
    "هوایی": "ضد هوایی",
    "پهپادی": "ضد پهپاد",
    "دریایی": "ضد دریایی",
    "زمینی": "دفاع زمینی",
    "توپخانه": "ضد موشک",
    "پدافندی": "جنگ الکترونیک",
}

# نام سامانه‌های پدافند بومی هر کشور
COUNTRY_DEF_SYSTEMS = {
    "ir": {"ضد موشک": "سامانه باور ۳۷۳", "ضد هوایی": "سامانه سوم خرداد / ۱۵ خرداد", "ضد پهپاد": "سامانه جنگال صیاد", "ضد دریایی": "سامانه موشکی قدیر / نصر", "دفاع زمینی": "استحکامات ذوالفقار", "جنگ الکترونیک": "شبکه جنگال بصیر"},
    "us": {"ضد موشک": "سامانه تاد (THAAD) و پاتریوت PAC-3", "ضد هوایی": "پدافند پاتریوت و ناوهای Aegis", "ضد پهپاد": "سامانه لیزری HELIOS و جمر", "ضد دریایی": "سامانه ضدناو هارپون و فالانکس", "دفاع زمینی": "شبکه زرهی آبرامز", "جنگ الکترونیک": "سامانه سایبری و اخلالگر Growler"},
    "ru": {"ضد موشک": "سامانه اس-۴۰۰ تریومف", "ضد هوایی": "سامانه پنتسیر-اس۱ و اس-۳۵۰", "ضد پهپاد": "سامانه جنگال کراسوخا-۴", "ضد دریایی": "سامانه باستیون و یاخونت", "دفاع زمینی": "خطوط دفاعی کورگان", "جنگ الکترونیک": "شبکه اخلالگر مورمانسک"},
    "cn": {"ضد موشک": "سامانه HQ-19 و HQ-9B", "ضد هوایی": "سامانه پدافندی HQ-16", "ضد پهپاد": "سامانه خاموش‌ساز لیزری", "ضد دریایی": "سامانه موشکی YJ-18 ساحلی", "دفاع زمینی": "دیوار آتش زرهی تایپ ۹۹", "جنگ الکترونیک": "جنگال ماهواره‌ای پکن"},
    "il": {"ضد موشک": "سامانه پیکان ۳ (Arrow-3)", "ضد هوایی": "سامانه فلاخن داوود", "ضد پهپاد": "سامانه گنبد آهنین (Iron Dome)", "ضد دریایی": "سامانه باراک-۸", "دفاع زمینی": "استحکامات مرکاوا", "جنگ الکترونیک": "شبکه جنگال التا"},
    "uk": {"ضد موشک": "سامانه Sky Sabre (CAMM)", "ضد هوایی": "سامانه پدافند Sea Viper", "ضد پهپاد": "سامانه ضد ریزپرنده Blighter", "ضد دریایی": "سامانه Sea Ceptor", "دفاع زمینی": "سنگرهای چلنجر", "جنگ الکترونیک": "جنگال اسکای‌نت"},
    "de": {"ضد موشک": "سامانه پاتریوت و Arrow-3", "ضد هوایی": "سامانه IRIS-T SLM", "ضد پهپاد": "سامانه مانتیس (MANTIS)", "ضد دریایی": "سامانه RBS-15", "دفاع زمینی": "خطوط لئوپارد ۲", "جنگ الکترونیک": "شبکه راداری هنسولت"},
    "fr": {"ضد موشک": "سامانه SAMP/T مامبا", "ضد هوایی": "سامانه آستر ۳۰", "ضد پهپاد": "سامانه PARADE", "ضد دریایی": "سامانه اگزوسه", "دفاع زمینی": "واحدهای لکلرک", "جنگ الکترونیک": "شبکه تالس"},
    "kp": {"ضد موشک": "سامانه پونگی-۶ (KN-06)", "ضد هوایی": "سامانه پدافند هوایی سامی", "ضد پهپاد": "جمرهای سیگنالی پیونگ‌یانگ", "ضد دریایی": "سامانه ساحلی کومسونگ-۳", "دفاع زمینی": "استحکامات زیرزمینی", "جنگ الکترونیک": "اخلالگرهای نظامی"},
    "sa": {"ضد موشک": "سامانه پاتریوت PAC-3 و THAAD", "ضد هوایی": "سامانه شاهین", "ضد پهپاد": "سامانه Silent Hunter", "ضد دریایی": "سامانه اتومات", "دفاع زمینی": "واحدهای زرهی گارد ملی", "جنگ الکترونیک": "رادارهای هشدار زودهنگام"},
    "tr": {"ضد موشک": "سامانه اس-۴۰۰ و سیپر (SIPER)", "ضد هوایی": "سامانه حصار (HISAR-O)", "ضد پهپاد": "سامانه کورال و ایهالار", "ضد دریایی": "سامانه اتماجا", "دفاع زمینی": "لشکرهای آلتای", "جنگ الکترونیک": "شبکه جنگ الکترونیک کُرال"},
    "pk": {"ضد موشک": "سامانه HQ-9/P", "ضد هوایی": "سامانه عنزه و Spada 2000", "ضد پهپاد": "سامانه ضد ریزپرنده تکاور", "ضد دریایی": "سامانه ضربت ضرب", "دفاع زمینی": "تیپ‌های الخالد", "جنگ الکترونیک": "رادارهای شاهین"},
    "in": {"ضد موشک": "سامانه اس-۴۰۰ سودارشان", "ضد هوایی": "سامانه باراک-۸ و آکاش", "ضد پهپاد": "سامانه درووا دیفنس", "ضد دریایی": "سامانه براهموس ساحلی", "دفاع زمینی": "لشکرهای آرجون و تی-۹۰", "جنگ الکترونیک": "شبکه سامیوکتا"},
}


def get_system_name(cid: str, layer: str) -> str:
    c_sys = COUNTRY_DEF_SYSTEMS.get(cid, {})
    return c_sys.get(layer, f"سامانه پدافند {layer}")


def ensure(cid: str):
    """ساخت یا تنظیم لایه‌های دفاعی کشور در دیتابیس."""
    c = countries.COUNTRIES.get(cid)
    if not c:
        return
    base = 25 + c["mil"] * 5 + c["tech"] * 4
    spec, pct, _ = countries.spec_of(cid)
    if spec == "پدافندی":
        base += pct // 2
    base = max(20, min(85, base))
    for layer in LAYERS:
        lv = base + random.randint(-2, 3)
        if layer == "جنگ الکترونیک":
            lv = base - 3
        db.ex("INSERT OR IGNORE INTO defense(cid, layer, level, hp) VALUES(?, ?, ?, ?)",
              (cid, layer, max(15, min(95, lv)), 100))


def level(cid: str, layer: str) -> int:
    ensure(cid)
    r = db.one("SELECT level FROM defense WHERE cid=? AND layer=?", (cid, layer))
    return r["level"] if r else 25


def absorb(cid: str, kind: str, shots: int = 1) -> tuple[float, float, str, int, str]:
    """محاسبه رهگیری و جذب ضربه توسط پدافند:
    خروجی: (شانس رهگیری، ضریب آسیب وارده، نام لایه، سطح لایه، نام سامانه)
    """
    layer = KIND_LAYER.get(kind, "دفاع زمینی")
    lvl = level(cid, layer)
    ew = level(cid, "جنگ الکترونیک")
    sys_name = get_system_name(cid, layer)

    # فرسایش جزئی پدافند در اثر دفاع
    db.ex("""
    UPDATE defense 
    SET level=MAX(10, level - ?), hp=MAX(15, hp - ? * 2) 
    WHERE cid=? AND layer=?
    """, (random.randint(1, 2), shots, cid, layer))

    # محاسبه شانس رهگیری بر اساس سطح پدافند
    chance = min(0.85, max(0.12, lvl / 120.0))

    # بررسی پایگاه‌های پدافندی ساخته‌شده در کشور
    from game import geo
    bases = geo.list_country_bases(cid)
    def_bases = [b for b in bases if "پدافند" in b.get("base_type", "")]
    if def_bases:
        chance = min(0.92, chance + 0.15)

    # بررسی کور شدن رادار در اثر مرحله ۱ عملیات
    radar_blind = int(db.kv_get(f"radar_blinded:{cid}", "0") or 0) > db.now()
    if radar_blind:
        chance = max(0.10, chance * 0.55)

    # بررسی وضعیت آماده‌باش ۲ دقیقه‌ای (اسکرامبل پدافندی)
    is_scrambled = int(db.kv_get(f"defense_scramble:{cid}", "0") or 0) > db.now()
    if is_scrambled:
        chance = min(0.95, chance + 0.25)

    dmg_mult = 1.0 - min(0.45, ew / 250.0)
    return chance, dmg_mult, layer, lvl, sys_name


def activate_scramble(uid: int) -> tuple[str, str]:
    """آماده‌باش اضطراری و اسکرامبل جنگنده‌ها و سامانه‌های پدافند در مهلت ۲ دقیقه‌ای."""
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»", ""
    cid = p["country"]
    c_info = countries.COUNTRIES[cid]
    user_tag = texts.mention(uid, p["name"])
    
    db.kv_set(f"defense_scramble:{cid}", str(db.now() + 120))
    restore(cid, "ضد موشک", 3)
    restore(cid, "ضد هوایی", 3)
    restore(cid, "ضد پهپاد", 3)
    
    msg = f"""🚨 <b>فرمان آماده‌باش رزمی و اسکرامبل پدافند هوایی صادر شد!</b>
{texts.FULL}
🛡️ تمامی سامانه‌های پدافندی و جنگنده‌های رهگیر {c_info['flag']} <b>{c_info['name']}</b> در وضعیت شلیک به هدف قرار گرفتند (+۲۵٪ شانس رهگیری ضربات ورودی)."""
    ann = f"""🛡️ <b>آماده‌باش دفاعی کامل در {c_info['flag']} {c_info['name']}</b>
{texts.FULL}
فرمانده {user_tag} سامانه‌های پدافندی و جنگال کشور را در وضعیت هشدار حداکثری قرار داد!"""
    return msg, ann


def restore(cid: str, layer: str, amount: int = 3):
    db.ex("UPDATE defense SET level=MIN(95, level+?), hp=MIN(100, hp+?*3) WHERE cid=? AND layer=?",
          (amount, amount, cid, layer))


def strengthen(uid: int, layer: str) -> str:
    """تقویت پدافند ملی توسط فرمانده یا شهروندان."""
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    if layer not in LAYERS:
        return "⚠️ لایه دفاعی نامعتبر است."
    cid = p["country"]
    lvl = level(cid, layer)
    cost = 350 + lvl * 8
    if p["money"] < cost:
        return f"⚠️ بودجه ناکافی! هزینه ارتقا: {texts.money(cid, cost)} (موجودی: {texts.money(cid, p['money'])})"
    if lvl >= 95:
        return "🛡️ این سامانه پدافندی در بالاترین سطح آمادگی رزمی (۹۵٪) قرار دارد."
    db.ex("UPDATE users SET money=money-? WHERE uid=?", (cost, uid))
    restore(cid, layer, 4)
    from game import quests
    quests.on_event(uid, "پدافند")
    c = countries.COUNTRIES[cid]
    sys_name = get_system_name(cid, layer)
    return f"""🛡️ <b>ارتقای پدافند ملی {c['flag']} {c['name']}</b>
{texts.FULL}
📡 سامانه: <b>{sys_name}</b> ({LAYERS[layer]} {layer})
📈 سطح پدافند: {texts.fa(lvl)} ➔ <b>{texts.fa(level(cid, layer))}</b>
💵 سرمایه‌گذاری دفاعی: {texts.money(cid, cost)}"""


def status(cid: str) -> str:
    """گزارش وضعیت کامل سپر پدافندی چندلایه کشور."""
    ensure(cid)
    c = countries.COUNTRIES.get(cid)
    if not c:
        return "⚠️ کشور نامعتبر است."
    t = texts
    rows = db.q("SELECT layer, level, hp FROM defense WHERE cid=? ORDER BY layer", (cid,))
    lines = [
        t.hdr(f"سپر پدافند ملی {c['name']} {c['flag']}", "🛡️"),
        f"🎯 دکترین دفاعی: <b>{c.get('mil_name', 'نیروهای مسلح')}</b>",
        ""
    ]
    for r in rows:
        sys_name = get_system_name(cid, r["layer"])
        bar = "▰" * (r["level"] // 10) + "▱" * (10 - (r["level"] // 10))
        lines.append(f"{LAYERS.get(r['layer'], '▫️')} <b>{r['layer']}</b> ({sys_name}):\n   سطح: <b>{texts.fa(r['level'])}٪</b> {bar} | سلامت: {texts.fa(r['hp'])} HP")
    
    lines += [
        "",
        "⚡ <b>جنگ الکترونیک:</b> آسیب موشک‌ها و بمباران‌های ورودی را کاهش می‌دهد.",
        "🔧 <i>فرماندهان و رزمندگان می‌توانند با بودجه شخصی پدافند کشور را تقویت کنند.</i>"
    ]
    return "\n".join(lines)
