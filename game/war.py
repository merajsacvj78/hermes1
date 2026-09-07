"""⚔️ جنگ جهانی — سیستم جامع جنگ، عملیات‌های نامدار، حملات ۵ مرحله‌ای، پدافند هوایی پیشرفته، محاصره شهری و تسلیم."""
import json
import random
import db
import texts
import countries
from game import state, geo, defense, infra

PENDING_BBC: list = []
MISSILE_FLIGHT = 20  # زمان پرواز موشک بر حسب ثانیه

EMOJI_KIND = {
    "🚀": "موشکی", "✈️": "هوایی", "✈": "هوایی", "🚁": "پهپادی",
    "⚓": "دریایی", "🛡️": "پدافندی", "🛡": "پدافندی", "🎖️": "زمینی",
}


def bbc_pop() -> str | None:
    if PENDING_BBC:
        return PENDING_BBC.pop(0)
    return None


def kind_of(iid: str) -> str:
    item = countries.ITEMS.get(iid)
    if not item:
        return "زمینی"
    em = item[1]
    return EMOJI_KIND.get(em, "زمینی")


def _enemy(cid: str, w: dict) -> str:
    return w["b"] if w["a"] == cid else w["a"]


def war_of(cid: str) -> dict | None:
    """یافتن جنگ فعال کشوری."""
    r = db.one("SELECT * FROM wars WHERE status='active' AND (a=? OR b=?) LIMIT 1", (cid, cid))
    return dict(r) if r else None


def can_strike_kind(attacker_cid: str, defender_cid: str, kind: str) -> tuple[bool, str]:
    """بررسی امکان حمله بر اساس جغرافیا و مرزها."""
    if kind == "زمینی":
        if not (geo.is_neighbor(attacker_cid, defender_cid) or (geo.coastal(attacker_cid) and geo.coastal(defender_cid))):
            return False, "مرز زمینی یا ساحلی مشترک وجود ندارد"
    elif kind == "دریایی":
        if not (geo.coastal(attacker_cid) and geo.coastal(defender_cid)):
            return False, "یکی از دو کشور به آب‌های آزاد دسترسی ندارد"
    return True, "مجاز"


# ═══════════ عملیات‌های نظامی با نام دلخواه ═══════════

def create_operation(uid: int, target_cid: str, op_name: str) -> tuple[str, str]:
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا با دستور «شروع» کشورتان را مشخص کنید.", ""

    cid = p["country"]
    if cid == target_cid:
        return "⚠️ نمی‌توانید علیه خاک خودتان عملیات آغاز کنید!", ""

    if target_cid not in countries.COUNTRIES:
        return "⚠️ کشور هدف نامعتبر است.", ""

    clean_name = op_name.strip()
    if len(clean_name) < 3 or len(clean_name) > 50:
        clean_name = f"عملیات تهاجمی علیه {countries.COUNTRIES[target_cid]['name']}"

    cost = 2500
    if p["money"] < cost:
        return f"⚠️ برای راه‌اندازی ستاد عملیات به {texts.money(cid, cost)} نیاز دارید (موجودی: {texts.money(cid, p['money'])}).", ""

    w = war_of(cid)
    if not w:
        db.ex("""
        INSERT INTO wars(a, b, status, score_a, score_b, started, ends)
        VALUES(?, ?, 'active', 0, 0, ?, ?)
        """, (cid, target_cid, db.now(), db.now() + 86400))

    db.ex("UPDATE users SET money=money-? WHERE uid=?", (cost, uid))
    db.ex("""
    INSERT INTO operations(name, cid, target_cid, stage, power_boost, strikes_done, created, status)
    VALUES(?, ?, ?, 1, 30, 0, ?, 'active')
    """, (clean_name, cid, target_cid, db.now()))

    op_id = db.one("SELECT last_insert_rowid() id")["id"]
    db.ex("UPDATE users SET operation_id=? WHERE uid=?", (op_id, uid))

    c_info = countries.COUNTRIES[cid]
    t_info = countries.COUNTRIES[target_cid]
    user_tag = texts.mention(uid, p["name"])

    target_leader = db.one("SELECT uid, name FROM users WHERE country=? AND is_leader=1", (target_cid,))
    t_tag = texts.mention(target_leader["uid"], target_leader["name"]) if target_leader else t_info["name"]

    ann = f"""🚩 <b>فرمان آماده‌باش — آغاز «{clean_name}»</b>
{texts.FULL}
⚔️ فرمانده {c_info['flag']} <b>{c_info['name']}</b> ({user_tag}) رسماً ستاد فرماندهی عملیات ویژه را علیه {t_info['flag']} <b>{t_info['name']}</b> تأسیس کرد!

🎯 کشور هدف: {t_info['flag']} <b>{t_info['name']}</b> (فرمانده: {t_tag})
⚡ مزیت ستاد عملیات: <b>+۳۰٪ قدرت تخریب به تمامی امواج تهاجمی</b>"""

    msg = f"✅ ستاد عملیات تشکیل شد و عملیات <b>«{clean_name}»</b> علیه {t_info['name']} کلید خورد."
    return msg, ann


def get_active_operation(cid: str) -> dict | None:
    row = db.one("SELECT * FROM operations WHERE cid=? AND status='active' ORDER BY id DESC LIMIT 1", (cid,))
    return dict(row) if row else None


# ═══════════ حملات ۵ مرحله‌ای استراتژیک ═══════════

def strike_stage(uid: int, target_cid: str, stage: int, item_id: str = None) -> tuple[str, str]:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»", ""

    cid = p["country"]
    if cid == target_cid:
        return "⚠️ نمی‌توانید به خاک خودتان حمله کنید!", ""

    t_info = countries.COUNTRIES.get(target_cid)
    if not t_info:
        return "⚠️ کشور هدف یافت نشد.", ""

    c_info = countries.COUNTRIES[cid]
    user_tag = texts.mention(uid, p["name"])

    # بررسی مصونیت سازمان ملل
    pk_until = int(db.kv_get(f"peacekeeping:{target_cid}", "0") or 0)
    if db.now() < pk_until:
        return "🛡️ <b>مصونیت سازمان ملل!</b> نیروهای کلاه آبی در این کشور مستقرند و تا پایان مهلت صلح‌بانی حمله به آن ممنوع است.", ""

    # بررسی تجهیزات: اگر موجود بود با بکارگیری و کسر جزئی استهلاک، در غیر این صورت با تسلیحات استاندارد ستاد کل
    inv_row = db.one("SELECT iid, qty, dur FROM inventory WHERE uid=? AND dur > 5 ORDER BY qty DESC LIMIT 1", (uid,))
    weapon_desc = "تسلیحات استاندارد ستاد کل نیروهای مسلح"
    bonus_power = 0
    if inv_row:
        item_data = countries.ITEMS.get(inv_row["iid"])
        if item_data:
            weapon_desc = f"{item_data[1]} {item_data[0]}"
            bonus_power = item_data[3] // 4
        # استهلاک ۲٪
        db.ex("UPDATE inventory SET dur=MAX(5, dur-2) WHERE uid=? AND iid=?", (uid, inv_row["iid"]))

    target_leader = db.one("SELECT uid, name FROM users WHERE country=? AND is_leader=1", (target_cid,))
    target_troops = db.q("SELECT uid, name FROM users WHERE country=? LIMIT 6", (target_cid,))
    target_tags = " ".join(texts.mention(t["uid"], t["name"]) for t in target_troops) if target_troops else (texts.mention(target_leader["uid"], target_leader["name"]) if target_leader else t_info["name"])

    # فعال‌سازی هشدار آماده‌باش دفاعی ۲ دقیقه‌ای
    alert_exp = int(db.kv_get(f"defense_alert:{target_cid}", "0") or 0)
    alert_line = ""
    if db.now() > alert_exp:
        db.kv_set(f"defense_alert:{target_cid}", str(db.now() + 120))
        alert_line = f"\n🚨 <b>هشدار پدافند هوایی:</b> {target_tags} (۲ دقیقه مهلت واکنش سریع و اسکرامبل دفاعی)"

    active_op = get_active_operation(cid)
    boost = (active_op["power_boost"] if (active_op and active_op["target_cid"] == target_cid) else 0) + bonus_power

    defense.ensure(target_cid)

    if stage == 1:
        # فاز ۱: انهدام C4ISR، رادارها و نیروگاه‌های برق
        ab_chance, dmg_mult, layer, lvl, sys_name = defense.absorb(target_cid, "پدافندی", 2)
        success = random.random() > (ab_chance * 0.7)

        if success:
            infra.damage(target_cid, "power", 35)
            db.kv_set(f"radar_blinded:{target_cid}", str(db.now() + 1200))  # کور شدن رادار برای ۲۰ دقیقه
            _add_war_score(cid, target_cid, 25)
            msg = f"""⚡ <b>پیروزی در فاز ۱ عملیات — خاموشی سراسری C4ISR!</b>
{texts.FULL}
📡 شبکه رادارهای پیش‌اخطار و پست‌های برق {t_info['flag']} <b>{t_info['name']}</b> با جنگ الکترونیک و موشک‌های ضدرادار منهدم شد!
⚠️ <b>اثر تاکتیکی:</b> پدافند هوایی دشمن تا ۲۰ دقیقه آینده ۴۰٪ کارایی خود را از دست داد."""
            ann = f"🚨 <b>خبر فوری جنگی — کور شدن رادارهای {t_info['name']}</b>\n{user_tag} از {c_info['flag']} <b>{c_info['name']}</b> شبکه راداری و برق {t_info['name']} را مختل و از کار انداخت!"
        else:
            _add_war_score(cid, target_cid, 5)
            msg = f"""🛡️ <b>دفع حمله سایبری و الکترونیک</b>
{texts.FULL}
📡 <b>{sys_name}</b> کشور {t_info['name']} موفق شد هجوم الکترونیکی شما را خنثی کند."""
            ann = f"🛡️ پدافند جنگال {t_info['name']} حمله سایبری ارتش {c_info['name']} را دفع کرد."

        if alert_line:
            ann += alert_line
        return msg, ann

    elif stage == 2:
        # فاز ۲: بمباران پایگاه‌های نظامی و آشیانه‌های دشمن
        bases = geo.list_country_bases(target_cid)
        if bases:
            target_base = random.choice(bases)
            dmg = random.randint(35, 65) + int(boost * 0.5)
            new_hp = max(0, target_base["hp"] - dmg)
            if new_hp == 0:
                db.ex("DELETE FROM bases WHERE id=?", (target_base["id"],))
                b_stat = f"💥 <b>پایگاه راهبردی {target_base['base_type']} در شهر {target_base['city']} کاملاً منهدم شد!</b>"
            else:
                db.ex("UPDATE bases SET hp=? WHERE id=?", (new_hp, target_base["id"]))
                b_stat = f"🔥 پایگاه {target_base['base_type']} در {target_base['city']} دچار آسیب سنگین شد (سلامت: {new_hp} HP)."
        else:
            infra.damage(target_cid, "airport", 35)
            b_stat = f"🛫 باند فرودگاه‌ها، آشیانه‌های پروازی و سیلوهای موشکی {t_info['name']} درهم کوبیده شد."

        _add_war_score(cid, target_cid, 30)
        msg = f"""🛫 <b>موفقیت در فاز ۲ — بمباران مراکز فرماندهی و پایگاه‌ها</b>
{texts.FULL}
🎯 سلاح به‌کاررفته: <b>{weapon_desc}</b>
{b_stat}
📈 امتیاز عملیات: <b>+۳۰ امتیاز جنگی</b> ثبت شد."""
        ann = f"💣 <b>بمباران سنگین پایگاه‌های نظامی در {t_info['name']}</b>\n{user_tag} از {c_info['flag']} <b>{c_info['name']}</b> پایگاه‌های استراتژیک دشمن را هدف قرار داد!\n{b_stat}"
        if alert_line:
            ann += alert_line
        return msg, ann

    elif stage == 3:
        # فاز ۳: سرکوب سامانه‌های پدافند هوایی (SEAD)
        ab_chance, dmg_mult, layer, lvl, sys_name = defense.absorb(target_cid, "هوایی", 3)
        defense.absorb(target_cid, "موشکی", 3)
        _add_war_score(cid, target_cid, 35)
        msg = f"""🚀 <b>فاز ۳ عملیات — سرکوب پدافند هوایی (SEAD)</b>
{texts.FULL}
🎯 آتشبارهای پدافندی و سایت‌های موشکی <b>{sys_name}</b> هدف موشک‌های ضدرادار قرار گرفتند.
📉 سطح سپر هوایی و موشکی {t_info['name']} فرسوده و ضعیف‌تر شد (+۳۵ امتیاز)."""
        ann = f"🚀 <b>عملیات SEAD علیه سامانه‌های پدافندی {t_info['name']}</b>\n{user_tag} مواضع آتشبارهای پدافندی {t_info['name']} را درهم کوبید."
        if alert_line:
            ann += alert_line
        return msg, ann

    elif stage == 4:
        # فاز ۴: تهاجم سنگین موشک‌های بالستیک و برتری هوایی
        ab_chance, dmg_mult, layer, lvl, sys_name = defense.absorb(target_cid, "موشکی", 2)
        intercepted = random.random() < ab_chance

        if intercepted:
            msg = f"""🛡️ <b>رهگیری در آسمان!</b>
{texts.FULL}
سامانه پدافند <b>{sys_name}</b> متعلق به {t_info['flag']} {t_info['name']} موشک‌های بالستیک شلیک‌شده را در آسمان منهدم کرد!"""
            ann = f"🛡️ <b>پدافند هوایی {t_info['name']}</b> ({sys_name}) موشک‌های بالستیک مهاجم از سمت {c_info['name']} را رهگیری و نابود کرد."
            _add_war_score(cid, target_cid, 10)
        else:
            dmg_score = int((70 + boost) * dmg_mult)
            _add_war_score(cid, target_cid, dmg_score)
            infra.damage(target_cid, "industry", 40)
            msg = f"""💥 <b>اصابت سهمگین موشک‌های بالستیک و راهبردی به {t_info['name']}!</b>
{texts.FULL}
🎯 تسلیحات: <b>{weapon_desc}</b>
🏭 مجتمع‌های صنعتی و زرادخانه‌های نظامی دشمن منهدم شد (+{dmg_score} امتیاز جنگی)."""
            ann = f"🔥 <b>فوری — اصابت مستقیم موشک‌های راهبردی به خاک {t_info['name']}</b>\nموشک‌های سنگین ارتش {c_info['name']} با عبور از پدافند، مراکز نظامی {t_info['name']} را ویران ساختند!"

        if alert_line:
            ann += alert_line
        return msg, ann

    elif stage == 5:
        # فاز ۵: نبرد شهری، محاصره و پیشروی لشکرهای زرهی
        has_border = geo.is_neighbor(cid, target_cid)
        is_coastal_inv = geo.coastal(cid) and geo.coastal(target_cid)
        if not (has_border or is_coastal_inv):
            return f"🚫 <b>عدم امکان نبرد زمینی!</b> کشور شما مرز زمینی یا ساحلی مشترک با <b>{t_info['name']}</b> ندارد (از بمباران موشکی یا هوایی استفاده کنید).", ""

        target_cities = geo.get_cities(target_cid)
        already_occ = geo.occupied(target_cid)
        free_cities = [c for c in target_cities if c not in already_occ]

        if not free_cities:
            geo.set_colony(target_cid, cid)
            _add_war_score(cid, target_cid, 200)
            msg = f"""👑 <b>فتح کامل و تسلیم سراسری!</b>
{texts.FULL}
تمام شهرهای {t_info['flag']} <b>{t_info['name']}</b> فتح شدند و کشور رسماً به مستعمره {c_info['flag']} <b>{c_info['name']}</b> تبدیل شد!"""
            ann = f"🏆 <b>پیروزی نهایی — سقوط کامل {t_info['name']}</b>\nلشکرهای {c_info['flag']} <b>{c_info['name']}</b> ({user_tag}) تمام پایتخت و شهرهای {t_info['name']} را فتح کردند و کنترل کشور را در دست گرفتند!"
            return msg, ann

        chosen_city = random.choice(free_cities)
        city_hp = int(db.kv_get(f"city_hp:{target_cid}:{chosen_city}", "160"))
        strike_power = random.randint(45, 80) + int(boost * 0.7)
        new_city_hp = max(0, city_hp - strike_power)
        db.kv_set(f"city_hp:{target_cid}:{chosen_city}", str(new_city_hp))

        if new_city_hp == 0:
            geo.occupy_city(target_cid, chosen_city, cid)
            _add_war_score(cid, target_cid, 90)
            msg = f"""🚩 <b>سقوط شهر {chosen_city}!</b>
{texts.FULL}
استحکامات پادگان شهر <b>{chosen_city}</b> فروریخت و پرچم {c_info['flag']} <b>{c_info['name']}</b> بر فراز ساختمان‌های اصلی برافراشته شد!"""
            ann = f"🚨 <b>خبر فوری نبرد — شهر {chosen_city} سقوط کرد!</b>\nلشکرهای زرهی {c_info['flag']} <b>{c_info['name']}</b> شهر استراتژیک <b>{chosen_city}</b> متعلق به {t_info['name']} را فتح و آزاد کردند."
        else:
            _add_war_score(cid, target_cid, 35)
            msg = f"""⚔️ <b>نبرد سنگین شهری در {chosen_city}</b>
{texts.FULL}
سنگرهای مدافعان شهر <b>{chosen_city}</b> زیر آتش قرار گرفت ({strike_power} آسیب وارده).\n🛡️ استقامت پادگان شهر: <b>{new_city_hp} HP باقی‌مانده</b>."""
            ann = f"⚔️ <b>درگیری‌های کوچه به کوچه در {chosen_city}</b>\nنیروهای ارتش {c_info['name']} خطوط دفاعی پادگان <b>{chosen_city}</b> ({t_info['name']}) را زیر آتش گرفتند."

        if alert_line:
            ann += alert_line
        return msg, ann

    return "⚠️ فاز عملیاتی نامعتبر است.", ""


def _add_war_score(a_cid: str, b_cid: str, points: int):
    w = db.one("SELECT * FROM wars WHERE status='active' AND ((a=? AND b=?) OR (a=? AND b=?))", (a_cid, b_cid, b_cid, a_cid))
    if w:
        if w["a"] == a_cid:
            db.ex("UPDATE wars SET score_a=score_a+? WHERE id=?", (points, w["id"]))
        else:
            db.ex("UPDATE wars SET score_b=score_b+? WHERE id=?", (points, w["id"]))


# ═══════════ ضربات مستقیم و نبردهای فوری ═══════════

def strike(uid: int, kind: str, count: int = 1, target: str = None) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    w = war_of(p["country"])
    if not w:
        return "⚠️ کشورت در حال حاضر در جنگ نیست — از بخش دیپلماسی اعلان جنگ کن."

    ecid = _enemy(p["country"], w)
    ec = countries.COUNTRIES.get(ecid, {})
    my_c = countries.COUNTRIES.get(p["country"], {})
    user_tag = texts.mention(uid, p["name"])

    # بررسی مرز
    ok, reason = can_strike_kind(p["country"], ecid, kind)
    if not ok:
        return f"🚫 <b>حمله ناممکن:</b> {reason}."

    # بررسی پدافند دشمن
    ab_chance, dmg_mult, layer, lvl, sys_name = defense.absorb(ecid, kind, count)
    intercepted = random.random() < ab_chance

    # انتخاب تجهیزات
    inv_row = db.one("SELECT iid, qty, dur FROM inventory WHERE uid=? AND dur > 5 ORDER BY qty DESC LIMIT 1", (uid,))
    weapon_name = "تسلیحات استاندارد ملی"
    if inv_row:
        item_data = countries.ITEMS.get(inv_row["iid"])
        if item_data:
            weapon_name = f"{item_data[1]} {item_data[0]}"
        db.ex("UPDATE inventory SET dur=MAX(5, dur - ? * 2) WHERE uid=? AND iid=?", (count, uid, inv_row["iid"]))

    target_troops = db.q("SELECT uid, name FROM users WHERE country=? LIMIT 6", (ecid,))
    target_tags = " ".join(texts.mention(t["uid"], t["name"]) for t in target_troops) if target_troops else ec.get('name','')
    alert_exp = int(db.kv_get(f"defense_alert:{ecid}", "0") or 0)
    alert_line = ""
    if db.now() > alert_exp:
        db.kv_set(f"defense_alert:{ecid}", str(db.now() + 120))
        alert_line = f"\n🚨 <b>هشدار پدافند هوایی:</b> {target_tags} (۲ دقیقه مهلت واکنش سریع و اسکرامبل دفاعی)"

    if intercepted:
        _add_war_score(p["country"], ecid, 5 * count)
        ann = f"🛡️ <b>دفاع هوایی موفق {ec.get('name','')}</b>\n{sys_name} کشور {ec.get('name','')} موج حملات {kind} ارتش {my_c.get('name','')} را در آسمان خنثی کرد." + alert_line
        PENDING_BBC.append(ann)
        return f"""🛡️ <b>حمله توسط پدافند دشمن رهگیری شد!</b>
{texts.FULL}
سامانه پدافند <b>{sys_name}</b> متعلق به {ec.get('flag','')} {ec.get('name','')} موفق به رهگیری ضربت {kind} شد.
💡 <i>برای افزایش شانس نفوذ، با عملیات‌های موشکی و C4ISR پدافند دشمن را تضعیف کنید.</i>"""
    
    # ضربه موفق
    score = int((20 + count * 15) * dmg_mult)
    _add_war_score(p["country"], ecid, score)
    infra.damage(ecid, "industry", 5 * count)

    ann = f"💥 <b>اصابت موج ضربتی {kind} به {ec.get('name','')}</b>\n{user_tag} از {my_c.get('flag','')} <b>{my_c.get('name','')}</b> با {weapon_name} مواضع دشمن را هدف قرار داد (+{score} امتیاز)!" + alert_line
    PENDING_BBC.append(ann)

    return f"""💥 <b>اصابت موفقیت‌آمیز ضربت {kind}!</b>
{texts.FULL}
🎯 سلاح به‌کاررفته: <b>{weapon_name}</b>
📈 امتیاز نبرد: <b>+{score} امتیاز</b> برای کشور شما ثبت شد.
🔥 خسارات وارده به تأسیسات {ec.get('flag','')} {ec.get('name','')} ثبت گردید."""


def launch_missile(uid: int, count: int = 1, target: str = None) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    w = war_of(p["country"])
    if not w:
        return "⚠️ کشورت در حال حاضر در جنگ نیست."
    ecid = _enemy(p["country"], w)
    ec = countries.COUNTRIES.get(ecid, {})
    db.kv_set(f"mstrike:{uid}", json.dumps({"war": w["id"], "ts": db.now(), "ecid": ecid, "count": count}))
    
    return f"""🚀 <b>موج موشک‌های بالستیک پرتاب شد و در راه است!</b>
{texts.FULL}
🎯 مقصد: {ec.get('flag','')} <b>{ec.get('name','')}</b>
⏱️ زمان پرواز موشک تا برخورد: <b>{MISSILE_FLIGHT} ثانیه</b>
🚨 آژیر خطر و وضعیت قرمز در شهرهای دشمن به صدا درآمد!"""


def resolve_missile(uid: int) -> str:
    raw = db.kv_get(f"mstrike:{uid}")
    if not raw:
        return ""
    db.kv_del(f"mstrike:{uid}")
    d = db.jload(raw, {})
    ecid = d.get("ecid")
    if not ecid:
        return ""
    msg, ann = strike_stage(uid, ecid, 4)
    if ann:
        PENDING_BBC.append(ann)
    return msg


def declare(leader_uid: int, target_cid: str) -> str:
    msg, ann = declare_war(leader_uid, target_cid)
    if ann:
        PENDING_BBC.append(ann)
    return msg


def declare_war(leader_uid: int, target_cid: str) -> tuple[str, str]:
    p = state.active(leader_uid)
    if not p:
        return "⚠️ اول «شروع»", ""
    cid = p["country"]
    if cid == target_cid:
        return "⚠️ نمی‌توانید علیه خودتان اعلان جنگ کنید!", ""
    if target_cid not in countries.COUNTRIES:
        return "⚠️ کشور هدف یافت نشد.", ""
    existing = db.one("SELECT * FROM wars WHERE status='active' AND ((a=? AND b=?) OR (a=? AND b=?))", (cid, target_cid, target_cid, cid))
    if existing:
        return "⚠️ جنگ با این کشور از قبل فعال است.", ""
    db.ex("INSERT INTO wars(a, b, status, score_a, score_b, started, ends) VALUES(?, ?, 'active', 0, 0, ?, ?)", (cid, target_cid, db.now(), db.now() + 86400))
    c_info = countries.COUNTRIES[cid]
    t_info = countries.COUNTRIES[target_cid]
    user_tag = texts.mention(leader_uid, p["name"])
    t_leader = db.one("SELECT uid, name FROM users WHERE country=? AND is_leader=1", (target_cid,))
    t_tag = texts.mention(t_leader["uid"], t_leader["name"]) if t_leader else t_info["name"]
    ann = f"""🚨 <b>اعلان رسمی جنگ (Declaration of War)</b>
{texts.FULL}
کشور {c_info['flag']} <b>{c_info['name']}</b> به رهبری {user_tag} رسماً علیه {t_info['flag']} <b>{t_info['name']}</b> (فرمانده: {t_tag}) <b>اعلان جنگ</b> کرد!"""
    msg = f"⚔️ وضعیت جنگی با {t_info['name']} برقرار شد."
    return msg, ann


def surrender(uid: int) -> str:
    msg, ann = surrender_country(uid)
    if ann:
        PENDING_BBC.append(ann)
    return msg


def surrender_country(uid: int) -> tuple[str, str]:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»", ""
    cid = p["country"]
    w = db.one("SELECT * FROM wars WHERE status='active' AND (a=? OR b=?)", (cid, cid))
    if not w:
        return "⚠️ در هیچ جنگ فعالی نیستید.", ""
    winner_cid = w["b"] if w["a"] == cid else w["a"]
    db.ex("UPDATE wars SET status='won', winner=? WHERE id=?", (winner_cid, w["id"]))
    geo.set_colony(cid, winner_cid)
    c_info = countries.COUNTRIES[cid]
    win_info = countries.COUNTRIES[winner_cid]
    user_tag = texts.mention(uid, p["name"])
    ann = f"""🏳️ <b>تسلیم رسمی و پایان مخاصمه</b>
{texts.FULL}
رهبر {c_info['flag']} <b>{c_info['name']}</b> ({user_tag}) به دلیل شدت خسارات، <b>تسلیم کامل</b> را امضا کرد.
👑 کشور {win_info['flag']} <b>{win_info['name']}</b> پیروز میدان شد و {c_info['name']} مستعمره آن گردید."""
    msg = "🏳️ پیمان تسلیم امضا شد."
    return msg, ann


def front(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    w = war_of(p["country"])
    if not w:
        return "🕊️ کشورتان در حال حاضر در صلح کامل است."
    ecid = _enemy(p["country"], w)
    ec = countries.COUNTRIES.get(ecid, {})
    my_score = w["score_a"] if w["a"] == p["country"] else w["score_b"]
    en_score = w["score_b"] if w["a"] == p["country"] else w["score_a"]
    active_op = get_active_operation(p["country"])
    op_line = f"\n🚩 عملیات فعال: <b>{active_op['name']}</b> (فاز {texts.fa(active_op['stage'])})" if active_op else ""
    
    lines = [
        texts.hdr(f"جبهه نبرد با {ec.get('name','')} {ec.get('flag','')}", "⚔️"),
        f"▫️ امتیاز شما: <b>{texts.fa(my_score)}</b> | امتیاز دشمن: <b>{texts.fa(en_score)}</b>",
        op_line,
        "",
        "🎯 آماده شلیک و انجام عملیات تهاجمی:"
    ]
    return "\n".join(lines)


def world_status() -> str:
    wars = db.q("SELECT * FROM wars WHERE status='active'")
    t = texts
    lines = [t.hdr("وضعیت ژئوپلیتیک جهان", "🌍"), ""]
    if not wars:
        lines.append("🕊️ هیچ جنگ فعالی در جهان در جریان نیست.")
    else:
        for w in wars:
            ca = countries.COUNTRIES.get(w["a"], {})
            cb = countries.COUNTRIES.get(w["b"], {})
            lines.append(f"⚔️ {ca.get('flag','')} <b>{ca.get('name','')}</b> ({t.fa(w['score_a'])}) ⟷ {cb.get('flag','')} <b>{cb.get('name','')}</b> ({t.fa(w['score_b'])})")
    return "\n".join(lines)


def power_rank() -> str:
    c_list = list(countries.COUNTRIES.items())
    c_list.sort(key=lambda x: x[1]["mil"] * 2 + x[1]["tech"] + x[1].get("eco", 10) * 4, reverse=True)
    t = texts
    lines = [t.hdr("رده‌بندی ابرقدرت‌های جهان", "🏆"), ""]
    for i, (cid, c) in enumerate(c_list[:10], 1):
        lines.append(f"{t.fa(i)}. {c['flag']} <b>{c['name']}</b> — قدرت نظامی: {t.fa(c['mil'])} | فناوری: {t.fa(c['tech'])}")
    return "\n".join(lines)


def colonies() -> str:
    cols = geo.all_colonies()
    t = texts
    lines = [t.hdr("نقشه مستعمرات جهان", "👑"), ""]
    if not cols:
        lines.append("🌐 در حال حاضر تمام کشورها مستقل هستند.")
    else:
        for col, master in cols.items():
            cc = countries.COUNTRIES.get(col, {})
            cm = countries.COUNTRIES.get(master, {})
            lines.append(f"▫️ {cc.get('flag','')} {cc.get('name','')} ➔ تحت استعمار {cm.get('flag','')} <b>{cm.get('name','')}</b>")
    return "\n".join(lines)


def leaderboard() -> str:
    top = db.q("SELECT name, country, level, xp, kills, money FROM users WHERE country IS NOT NULL ORDER BY kills DESC, level DESC LIMIT 10")
    t = texts
    lines = [t.hdr("برترین فرماندهان جهان", "🎖️"), ""]
    for i, r in enumerate(top, 1):
        c = countries.COUNTRIES.get(r["country"], {})
        lines.append(f"{t.fa(i)}. {c.get('flag','')} <b>{r['name']}</b> — سطح {t.fa(r['level'])} | ⚔️ {t.fa(r['kills'])} انهدام | 💵 {t.money(r['country'], r['money'])}")
    return "\n".join(lines)


def army(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    cid = p["country"]
    c = countries.COUNTRIES[cid]
    troops = db.q("SELECT uid, name, rank, level, kills FROM users WHERE country=? ORDER BY level DESC", (cid,))
    t = texts
    lines = [t.hdr(f"لشکر ملی {c['name']} {c['flag']}", "🪖"), f"تعداد کل پرسنل: <b>{t.fa(len(troops))} نفر</b>", ""]
    for tr in troops[:15]:
        user_mention = texts.mention(tr["uid"], tr["name"])
        lines.append(f"▫️ {user_mention} — درجه: {countries.rank_name(tr['level'])} | ⚔️ {t.fa(tr['kills'])}")
    return "\n".join(lines)


def peace_request(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    w = war_of(p["country"])
    if not w:
        return "⚠️ در جنگ نیستید."
    ecid = _enemy(p["country"], w)
    db.kv_set(f"peace_req:{p['country']}:{ecid}", "1")
    return "🕊️ پیشنهاد آتش‌بس به فرماندهی دشمن ارسال شد."


def peace_accept(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    w = war_of(p["country"])
    if not w:
        return "⚠️ در جنگ نیستید."
    ecid = _enemy(p["country"], w)
    if db.kv_get(f"peace_req:{ecid}:{p['country']}"):
        db.ex("UPDATE wars SET status='peace' WHERE id=?", (w["id"],))
        db.kv_del(f"peace_req:{ecid}:{p['country']}")
        return "🕊️ پیمان صلح دوجانبه امضا شد و جنگ خاتمه یافت."
    return "⚠️ پیشنهاد صلحی از طرف دشمن در انتظار نیست."


def alliance_request(leader_uid: int, target_cid: str) -> str:
    p = state.active(leader_uid)
    if not p:
        return "⚠️ اول «شروع»"
    db.kv_set(f"ally_req:{p['country']}:{target_cid}", "1")
    return "🤝 درخواست اتحاد نظامی به رهبر کشور ارسال شد."


def alliance_accept(leader_uid: int, from_cid: str) -> str:
    p = state.active(leader_uid)
    if not p:
        return "⚠️ اول «شروع»"
    if db.kv_get(f"ally_req:{from_cid}:{p['country']}"):
        db.ex("INSERT INTO alliances(a, b, created) VALUES(?, ?, ?)", (from_cid, p["country"], db.now()))
        db.kv_del(f"ally_req:{from_cid}:{p['country']}")
        return "🤝 پیمان اتحاد راهبردی با موفقیت منعقد گردید."
    return "⚠️ درخواست اتحادی از طرف این کشور وجود ندارد."


def call_help(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    return "📢 پیام فراخوان عمومی و آماده‌باش نظامی به تمام رزمندگان مخابره شد!"


def duel_request(uid: int, target_name: str, target_uid: int) -> str:
    return "⚔️ درخواست دوئل تن‌به‌تن برای فرمانده مقابل ارسال شد."


def duel_accept(uid: int) -> str:
    return "⚔️ نبرد تن‌به‌تن آغاز شد!"


def settle():
    pass
