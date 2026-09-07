"""⚔️ جنگ جهانی — سیستم جامع جنگ، عملیات‌های نامدار، حملات ۵ مرحله‌ای، پدافند هوایی، نبرد تن‌به‌تن و صلح."""
import json
import random
import db
import texts
import countries
from game import state, geo, defense, infra

PENDING_BBC: list = []
MISSILE_FLIGHT = 25  # زمان پرواز موشک بر حسب ثانیه

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
            return False, "یکی از دو کشور به دریا دسترسی ندارد"
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
    if len(clean_name) < 3 or len(clean_name) > 40:
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
    VALUES(?, ?, ?, 1, 25, 0, ?, 'active')
    """, (clean_name, cid, target_cid, db.now()))

    op_id = db.one("SELECT last_insert_rowid() id")["id"]
    db.ex("UPDATE users SET operation_id=? WHERE uid=?", (op_id, uid))

    c_info = countries.COUNTRIES[cid]
    t_info = countries.COUNTRIES[target_cid]
    user_tag = texts.mention(uid, p["name"])

    target_leader = db.one("SELECT uid, name FROM users WHERE country=? AND is_leader=1", (target_cid,))
    t_tag = texts.mention(target_leader["uid"], target_leader["name"]) if target_leader else t_info["name"]

    ann = f"""🚩 <b>فرمان آماده‌باش — آغاز {clean_name}</b>
{texts.FULL}
⚔️ فرمانده کل {c_info['flag']} <b>{c_info['name']}</b> ({user_tag}) رسماً دستور آغاز عملیات استراتژیک را صادر کرد!

🎯 کشور هدف: {t_info['flag']} <b>{t_info['name']}</b> (فرمانده: {t_tag})
⚡ مزیت ستاد عملیات: <b>+۲۵٪ قدرت تخریب به تمامی امواج ضربتی</b>"""

    msg = f"✅ ستاد عملیات تشکیل شد و عملیات <b>«{clean_name}»</b> کلید خورد."
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
        return "🛡️ <b>مصونیت سازمان ملل!</b> نیروهای کلاه آبی در این کشور مستقرند و حمله تا پایان مهلت ممنوع است.", ""

    # بررسی سلاح
    inv_rows = db.q("SELECT * FROM inventory WHERE uid=? AND dur > 5", (uid,))
    if not inv_rows:
        return "⚠️ هیچ جنگ‌افزار سالمی ندارید! ابتدا از زرادخانه خرید یا تعمیر کنید.", ""

    active_op = get_active_operation(cid)
    boost = active_op["power_boost"] if (active_op and active_op["target_cid"] == target_cid) else 0

    defense.ensure(target_cid)

    if stage == 1:
        # مرحله ۱: رادار و برق
        layer_level = defense.level(target_cid, "جنگ الکترونیک")
        intercept_chance = max(0.10, min(0.65, layer_level / 160.0))
        success = random.random() > intercept_chance

        if success:
            infra.damage(target_cid, "برق", 35)
            defense.absorb(target_cid, "پدافندی", 2)
            db.kv_set(f"radar_blinded:{target_cid}", str(db.now() + 1200))
            msg = f"⚡ <b>موفقیت مرحله ۱ — خاموشی C4ISR!</b>\nشبکه راداری و نیروگاه‌های برق {t_info['name']} منهدم شد (-۲۵٪ افت پدافند دشمن)."
            ann = f"🚨 <b>حمله الکترونیکی و موشکی به رادارهای {t_info['name']}</b>\n{user_tag} از {c_info['name']} شبکه راداری {t_info['name']} را کور کرد!"
        else:
            msg = f"🛡️ پدافند جنگ الکترونیک {t_info['name']} حمله شما را مهار کرد."
            ann = f"🛡️ پدافند {t_info['name']} حمله سایبری {c_info['name']} را خنثی نمود."

        _add_war_score(cid, target_cid, 15 if success else 3)
        return msg, ann

    elif stage == 2:
        # مرحله ۲: بمباران پایگاه‌ها
        bases = geo.list_country_bases(target_cid)
        if bases:
            target_base = random.choice(bases)
            dmg = random.randint(35, 75) + int(boost * 0.5)
            new_hp = max(0, target_base["hp"] - dmg)
            if new_hp == 0:
                db.ex("DELETE FROM bases WHERE id=?", (target_base["id"],))
                b_stat = f"💥 <b>پایگاه {target_base['base_type']} در شهر {target_base['city']} منهدم شد!</b>"
            else:
                db.ex("UPDATE bases SET hp=? WHERE id=?", (new_hp, target_base["id"]))
                b_stat = f"🔥 پایگاه {target_base['base_type']} در {target_base['city']} آسیب دید ({new_hp} HP باقی‌مانده)."
        else:
            infra.damage(target_cid, "فرودگاه", 30)
            b_stat = f"🛫 باند فرودگاه‌ها و آشیانه‌های {t_info['name']} بمباران شد."

        _add_war_score(cid, target_cid, 25)
        msg = f"🎯 <b>مرحله ۲ — بمباران پایگاه‌های دشمن:</b>\n{b_stat}"
        ann = f"💣 <b>بمباران سنگین هوایی در {t_info['name']}</b>\n{user_tag} از {c_info['name']} پایگاه‌های دشمن را درهم کوبید!\n{b_stat}"
        return msg, ann

    elif stage == 3:
        # مرحله ۳: سرکوب پدافند (SEAD)
        defense.absorb(target_cid, "هوایی", 3)
        defense.absorb(target_cid, "ضدموشک", 3)
        _add_war_score(cid, target_cid, 30)
        msg = f"🚀 <b>مرحله ۳ — سرکوب پدافند (SEAD):</b>\nآتشبارهای پدافندی {t_info['name']} مورد اصابت قرار گرفت و سپر هوایی تضعیف شد."
        ann = f"🚀 <b>تهاجم ضدرادار علیه سامانه‌های پدافند {t_info['name']}</b>\n{user_tag} سامانه‌های پدافندی {t_info['name']} را درهم شکست."
        return msg, ann

    elif stage == 4:
        # مرحله ۴: موشک‌های بالستیک دوربرد
        radar_blind = int(db.kv_get(f"radar_blinded:{target_cid}", "0") or 0) > db.now()
        ab_chance, dmg_mult, layer, lvl = defense.absorb(target_cid, "موشکی", 2)
        if radar_blind:
            ab_chance *= 0.60
        intercepted = random.random() < ab_chance
        if intercepted:
            msg = f"🛡️ پدافند {t_info['name']} موشک بالستیک شما را رهگیری کرد!"
            ann = f"🛡️ پدافند {t_info['name']} موشک بالستیک شلیک‌شده از {c_info['name']} را در آسمان منهدم ساخت."
            _add_war_score(cid, target_cid, 5)
        else:
            dmg_score = int((65 + boost) * dmg_mult)
            _add_war_score(cid, target_cid, dmg_score)
            infra.damage(target_cid, "صنعت", 35)
            msg = f"💥 <b>اصابت سهمگین موشک بالستیک به {t_info['name']}!</b> (+{dmg_score} امتیاز نبرد)"
            ann = f"🔥 <b>فوری — اصابت مستقیم موشک بالستیک به {t_info['name']}</b>\nموشک بالستیک {c_info['name']} با عبور از سپر پدافند به هدف اصابت کرد!"
        return msg, ann

    elif stage == 5:
        # مرحله ۵: نبرد شهری
        has_border = geo.is_neighbor(cid, target_cid)
        is_coastal_inv = geo.coastal(cid) and geo.coastal(target_cid)
        if not (has_border or is_coastal_inv):
            return f"🚫 <b>عدم امکان پیشروی زمینی!</b> کشور شما مرز زمینی یا ساحلی مشترک با <b>{t_info['name']}</b> ندارد.", ""

        target_cities = geo.get_cities(target_cid)
        already_occ = geo.occupied(target_cid)
        free_cities = [c for c in target_cities if c not in already_occ]

        if not free_cities:
            geo.set_colony(target_cid, cid)
            msg = f"👑 <b>فتح کامل و تسلیم نهایی!</b> تمام شهرهای {t_info['name']} فتح شد و مستعمره {c_info['name']} گردید."
            ann = f"🏆 <b>پیروزی نهایی و سقوط کامل {t_info['name']}</b>\nلشکرهای {c_info['name']} ({user_tag}) تمام خاک {t_info['name']} را تسخیر کردند!"
            return msg, ann

        chosen_city = random.choice(free_cities)
        city_hp = int(db.kv_get(f"city_hp:{target_cid}:{chosen_city}", "150"))
        strike_power = random.randint(45, 80) + int(boost * 0.8)
        new_city_hp = max(0, city_hp - strike_power)
        db.kv_set(f"city_hp:{target_cid}:{chosen_city}", str(new_city_hp))

        if new_city_hp == 0:
            geo.occupy_city(target_cid, chosen_city, cid)
            _add_war_score(cid, target_cid, 80)
            msg = f"🚩 <b>سقوط شهر {chosen_city}!</b> پرچم {c_info['name']} بر فراز شهر برافراشته شد."
            ann = f"🚨 <b>خبر فوری جنگی — شهر {chosen_city} سقوط کرد!</b>\nنیروهای {c_info['name']} شهر <b>{chosen_city}</b> را از تصرف {t_info['name']} خارج کردند."
        else:
            _add_war_score(cid, target_cid, 30)
            msg = f"⚔️ <b>نبرد شهری در {chosen_city}:</b> استقامت مدافعان شهر به <b>{new_city_hp} HP</b> کاهش یافت."
            ann = f"⚔️ نبردهای سنگین در خیابان‌های <b>{chosen_city}</b> بین نیروهای {c_info['name']} و {t_info['name']} ادامه دارد."

        return msg, ann

    return "⚠️ مرحله نامعتبر است.", ""


def _add_war_score(a_cid: str, b_cid: str, points: int):
    w = db.one("SELECT * FROM wars WHERE status='active' AND ((a=? AND b=?) OR (a=? AND b=?))", (a_cid, b_cid, b_cid, a_cid))
    if w:
        if w["a"] == a_cid:
            db.ex("UPDATE wars SET score_a=score_a+? WHERE id=?", (points, w["id"]))
        else:
            db.ex("UPDATE wars SET score_b=score_b+? WHERE id=?", (points, w["id"]))


# ═══════════ توابع کمکی و نبردهای فوری ═══════════

def strike(uid: int, kind: str, count: int = 1, target: str = None) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    w = war_of(p["country"])
    if not w:
        return "⚠️ کشورت در جنگ نیست — از منو یک کشور را برای اعلان جنگ انتخاب کن."
    ecid = _enemy(p["country"], w)
    stage_map = {"پدافندی": 1, "هوایی": 2, "موشکی": 3, "پهپادی": 4, "زمینی": 5, "دریایی": 5}
    stage = stage_map.get(kind, 2)
    msg, ann = strike_stage(uid, ecid, stage)
    if ann:
        PENDING_BBC.append(ann)
    return msg


def launch_missile(uid: int, count: int = 1, target: str = None) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    w = war_of(p["country"])
    if not w:
        return "⚠️ کشورت در حال حاضر در جنگ نیست."
    ecid = _enemy(p["country"], w)
    ec = countries.COUNTRIES.get(ecid, {})
    db.kv_set(f"mstrike:{uid}", json.dumps({"war": w["id"], "ts": db.now(), "ecid": ecid}))
    return f"""🚀 <b>موج موشک‌های بالستیک پرتاب شد!</b>
{texts.FULL}
🎯 مقصد: {ec.get('flag','')} <b>{ec.get('name','')}</b>
⏱️ زمان پرواز موشک: <b>{MISSILE_FLIGHT} ثانیه</b>
🛡️ سامانه پدافندی دشمن در وضعیت هشدار قرمز قرار گرفت."""


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
    lines = [
        texts.hdr(f"جبهه نبرد با {ec.get('name','')}", "⚔️"),
        f"▫️ امتیاز شما: <b>{texts.fa(my_score)}</b> | امتیاز دشمن: <b>{texts.fa(en_score)}</b>",
        f"▫️ شهرهای تسخیرشده دشمن: {', '.join(geo.occupied(ecid)) or 'هنوز شهری فتح نشده'}",
        texts.DASH,
        "برای اجرای مراحل حمله از دکمه‌های زیر استفاده کنید:"
    ]
    return "\n".join(lines)


def world_status() -> str:
    counts = {r["country"]: r["n"] for r in db.q("SELECT country, COUNT(*) n FROM users WHERE country IS NOT NULL GROUP BY country")}
    lines = [texts.hdr("وضعیت ژئوپلیتیک جهان", "🌍"), "فهرست قدرت‌ها و لیدرهای مستقر:\n"]
    for cid, c in list(countries.COUNTRIES.items())[:12]:
        n = counts.get(cid, 0)
        lines.append(f"{c['flag']} <b>{c['name']}</b>: {texts.fa(n)} فرمانده")
    wars = db.q("SELECT * FROM wars WHERE status='active'")
    lines += ["", "⚔️ <b>جنگ‌های فعال:</b>"]
    if not wars:
        lines.append("🕊️ صلح بر سراسر جهان حاکم است.")
    for w in wars:
        c1 = countries.COUNTRIES.get(w['a'], {})
        c2 = countries.COUNTRIES.get(w['b'], {})
        lines.append(f"▫️ {c1.get('flag','')} {c1.get('name','')} VS {c2.get('flag','')} {c2.get('name','')} (امتیاز: {texts.fa(w['score_a'])} — {texts.fa(w['score_b'])})")
    return "\n".join(lines)


def power_rank() -> str:
    rows = db.q("SELECT country, SUM(level) total_lvl FROM users WHERE country IS NOT NULL GROUP BY country ORDER BY total_lvl DESC LIMIT 10")
    lines = [texts.hdr("رتبه‌بندی ابرقدرت‌های جهان", "🏆")]
    for i, r in enumerate(rows, 1):
        c = countries.COUNTRIES.get(r["country"], {})
        lines.append(f"{texts.fa(i)}. {c.get('flag','')} <b>{c.get('name','')}</b> — قدرت کل: <b>{texts.fa(r['total_lvl'])}</b>")
    return "\n".join(lines)


def colonies() -> str:
    lines = [texts.hdr("قلمروهای مستعمره و تحت قیمومیت", "👑")]
    has_any = False
    for cid in countries.COUNTRIES:
        overlord = geo.colony_of(cid)
        if overlord and overlord in countries.COUNTRIES:
            c = countries.COUNTRIES[cid]
            o = countries.COUNTRIES[overlord]
            lines.append(f"▫️ {c['flag']} {c['name']} ⬅️ تحت اشغال {o['flag']} <b>{o['name']}</b>")
            has_any = True
    if not has_any:
        lines.append("در حال حاضر هیچ کشوری مستعمره نشده است.")
    return "\n".join(lines)


def leaderboard() -> str:
    rows = db.q("SELECT uid, name, country, level, kills, money FROM users WHERE country IS NOT NULL ORDER BY level DESC, kills DESC LIMIT 10")
    lines = [texts.hdr("فرماندهان برتر جهان", "🎖️")]
    for i, r in enumerate(rows, 1):
        c = countries.COUNTRIES.get(r["country"], {})
        lines.append(f"{texts.fa(i)}. {c.get('flag','')} <b>{r['name']}</b> — سطح {texts.fa(r['level'])} | ⚔️ {texts.fa(r['kills'])} پیروزی")
    return "\n".join(lines)


def army(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    rows = db.q("SELECT * FROM inventory WHERE uid=?", (uid,))
    lines = [texts.hdr("لشکر و تجهیزات رزمی شما", "🎖️")]
    if not rows:
        lines.append("زرادخانه شما خالی است.")
    for r in rows:
        it = countries.ITEMS.get(r["iid"])
        if it:
            lines.append(f"▫️ {it[1]} <b>{it[0]}</b>: تعداد <b>{texts.fa(r['qty'])}</b> (استقامت: {texts.fa(r['dur'])}٪)")
    return "\n".join(lines)


def peace_request(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    w = war_of(p["country"])
    if not w:
        return "⚠️ در هیچ جنگی نیستید."
    ecid = _enemy(p["country"], w)
    ec = countries.COUNTRIES.get(ecid, {})
    db.kv_set(f"peace_req:{w['id']}", p["country"])
    return f"🕊️ پیشنهاد صلح و آتش‌بس به فرمانده {ec.get('flag','')} <b>{ec.get('name','')}</b> ارسال شد."


def peace_accept(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    w = war_of(p["country"])
    if not w:
        return "⚠️ در جنگی نیستید."
    req_by = db.kv_get(f"peace_req:{w['id']}")
    if not req_by or req_by == p["country"]:
        return "⚠️ هنوز پیشنهادی دریافت نشده است."
    db.ex("UPDATE wars SET status='peace' WHERE id=?", (w["id"],))
    db.kv_del(f"peace_req:{w['id']}")
    return "🕊️ پیمان صلح دوجانبه امضا شد و آتش‌بس برقرار گردید."


def alliance_request(leader_uid: int, target_cid: str) -> str:
    p = state.active(leader_uid)
    if not p:
        return "⚠️ اول «شروع»"
    t_info = countries.COUNTRIES.get(target_cid, {})
    db.kv_set(f"ally_req:{p['country']}:{target_cid}", str(leader_uid))
    return f"🤝 پیمان اتحاد نظامی به رهبر {t_info.get('flag','')} <b>{t_info.get('name','')}</b> پیشنهاد شد."


def alliance_accept(leader_uid: int, from_cid: str) -> str:
    p = state.active(leader_uid)
    if not p:
        return "⚠️ اول «شروع»"
    db.ex("INSERT INTO alliances(a, b, created) VALUES(?, ?, ?)", (p["country"], from_cid, db.now()))
    c = countries.COUNTRIES.get(from_cid, {})
    return f"🤝 پیمان اتحاد رسمی با {c.get('flag','')} <b>{c.get('name','')}</b> امضا گردید."


def call_help(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    return f"📢 فراخوان عمومی کمک نظامی به تمام متحدین {p['country']} ابلاغ شد."


def duel_request(uid: int, target_name: str, target_uid: int = None) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    db.kv_set(f"duel_from:{uid}", str(db.now()))
    return "⚔️ درخواست نبرد تن‌به‌تن برای حریف فرستاده شد (۵ دقیقه مهلت پاسخ)."


def duel_accept(uid: int) -> str:
    p = state.active(uid)
    if not p:
        return "⚠️ اول «شروع»"
    win = random.choice([True, False])
    if win:
        prize = 600
        db.ex("UPDATE users SET money=money+?, kills=kills+1 WHERE uid=?", (prize, uid))
        return f"🏆 <b>شما در دوئل تن‌به‌تن پیروز شدید!</b>\nپاداش غنیمت: <b>{texts.money(p['country'], prize)}</b>"
    else:
        db.ex("UPDATE users SET hp=MAX(10, hp-30) WHERE uid=?", (uid,))
        return "💥 در دوئل مغلوب شدید و ۳۰ واحد جان از دست دادید."


def settle() -> list[str]:
    """پایان جنگ‌های سررسیده‌شده (۲۴ ساعت)."""
    out = []
    rows = db.q("SELECT * FROM wars WHERE status='active' AND ends<=?", (db.now(),))
    for w in rows:
        if w["score_a"] == w["score_b"]:
            db.ex("UPDATE wars SET status='draw' WHERE id=?", (w["id"],))
            out.append("🕊️ جنگ سررسید شد و با نتیجه مساوی خاتمه یافت.")
        else:
            win = w["a"] if w["score_a"] > w["score_b"] else w["b"]
            lose = w["b"] if win == w["a"] else w["a"]
            db.ex("UPDATE wars SET status='won', winner=? WHERE id=?", (win, w["id"]))
            wc = countries.COUNTRIES.get(win, {})
            out.append(f"🏆 نبرد به پایان رسید! کشور {wc.get('flag','')} <b>{wc.get('name','')}</b> با پیروزی میدان را ترک کرد.")
    return out
