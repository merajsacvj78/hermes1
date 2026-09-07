"""🇺🇳 جنگ جهانی — سازمان ملل متحد و شورای امنیت (United Nations).
شامل مجمع عمومی، شورای امنیت، ۵ عضو دائم دارای حق وتو و رأی‌گیری قطعنامه‌ها.
"""
import db
import texts
import countries

# ۵ عضو دائم شورای امنیت با حق وتو
P5_MEMBERS = {"us", "ru", "cn", "gb", "fr"}

RESOLUTION_TYPES = {
    "ceasefire": "🕊️ قطعنامه برقراری آتش‌بس فوری",
    "sanctions": "🚫 قطعنامه تحریم‌های جامع اقتصادی و تسلیحاتی",
    "lift_sanctions": "🟢 قطعنامه لغو تحریم‌های بین‌المللی",
    "peacekeeping": "🛡️ قطعنامه استقرار نیروهای حافظ صلح (کلاه آبی‌ها)",
    "aid": "💵 قطعنامه کمک‌های بلاعوض اقتصادی و بشردوستانه",
}


def is_p5(cid: str) -> bool:
    return cid in P5_MEMBERS


def propose_resolution(uid: int, res_type: str, target_cid: str, title: str = "") -> tuple[str, str]:
    """ثبت یک قطعنامه جدید در شورای امنیت / مجمع عمومی سازمان ملل."""
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا با دستور «شروع» کشورتان را انتخاب کنید.", ""

    if res_type not in RESOLUTION_TYPES:
        return "⚠️ نوع قطعنامه نامعتبر است.", ""

    if target_cid not in countries.COUNTRIES:
        return "⚠️ کشور هدف نامعتبر است.", ""

    cid = p["country"]
    c_info = countries.COUNTRIES[cid]
    t_info = countries.COUNTRIES[target_cid]

    # چک کردن اینکه آیا قطعنامه باز مشابهی وجود دارد یا خیر
    active_res = db.one("SELECT id FROM un_resolutions WHERE res_type=? AND target_cid=? AND status='voting'", (res_type, target_cid))
    if active_res:
        return "⚠️ در حال حاضر رأی‌گیری درباره این قطعنامه در جریان است.", ""

    cost = 1500
    if p["money"] < cost:
        return f"⚠️ برای طرح قطعنامه به {texts.money(cid, cost)} نیاز دارید (موجودی: {texts.money(cid, p['money'])}).", ""

    db.ex("UPDATE users SET money=money-? WHERE uid=?", (cost, uid))

    res_title = title or f"{RESOLUTION_TYPES[res_type]} علیه/برای {t_info['name']}"
    ends = db.now() + 1800  # ۳۰ دقیقه فرصت رأی‌گیری

    db.ex("""
    INSERT INTO un_resolutions(title, res_type, target_cid, proposer_uid, proposer_cid, votes_yes, votes_no, votes_veto, voters_json, status, created, ends)
    VALUES(?, ?, ?, ?, ?, 1, 0, 0, ?, 'voting', ?, ?)
    """, (res_title, res_type, target_cid, uid, cid, db.json.dumps({str(uid): "yes"}), db.now(), ends))

    user_tag = texts.mention(uid, p["name"])
    proposer_str = f"{c_info['flag']} <b>{c_info['name']}</b>"
    target_str = f"{t_info['flag']} <b>{t_info['name']}</b>"

    ann = f"""🏛️ <b>سازمان ملل متحد — ثبت قطعنامه جدید</b>
{texts.FULL}
📜 <b>{res_title}</b>
▫️ پیشنهاددهنده: {user_tag} ({proposer_str})
▫️ کشور هدف: {target_str}
▫️ نوع اقدام: <b>{RESOLUTION_TYPES[res_type]}</b>

🗳️ تمام رهبران کشورها می‌توانند با مراجعه به <b>منو → سازمان ملل</b> رأی خود را ثبت کنند!
⚠️ اعضای دائم شورای امنیت (🇺🇸 آمریکا، 🇷🇺 روسیه، 🇨🇳 چین، 🇬🇧 بریتانیا، 🇫🇷 فرانسه) دارای <b>حق وتو</b> هستند."""

    msg = f"✅ قطعنامه شما با شماره ثبت شد و در صحن علنی مجمع عمومی قرار گرفت.\n{texts.DASH}\nاعلام عمومی در گروه انجام شد."
    return msg, ann


def vote_resolution(uid: int, res_id: int, vote: str) -> tuple[str, str]:
    """ثبت رأی رهبر (موافق، مخالف، یا وتو)."""
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا با دستور «شروع» کشورتان را ثبت کنید.", ""

    res = db.one("SELECT * FROM un_resolutions WHERE id=?", (res_id,))
    if not res:
        return "⚠️ قطعنامه یافت نشد.", ""

    if res["status"] != "voting":
        return "⚠️ مهلت رأی‌گیری این قطعنامه به پایان رسیده است.", ""

    cid = p["country"]
    c_info = countries.COUNTRIES.get(cid, {})
    voters = db.jload(res["voters_json"], {})

    if str(uid) in voters:
        return "⚠️ شما قبلاً رأی خود را برای این قطعنامه ثبت کرده‌اید.", ""

    if vote == "veto":
        if not is_p5(cid):
            return "🚫 <b>حق وتو ندارید!</b> تنها ۵ عضو دائم شورای امنیت (آمریکا، روسیه، چین، انگلیس، فرانسه) دارای حق وتو هستند.", ""
        # اعمال وتو و رد فوری قطعنامه
        voters[str(uid)] = "veto"
        db.ex("UPDATE un_resolutions SET votes_veto=votes_veto+1, voters_json=?, status='vetoed' WHERE id=?", (db.json.dumps(voters), res_id))
        user_tag = texts.mention(uid, p["name"])
        ann = f"""⛔ <b>شورای امنیت سازمان ملل — وتوی قطعنامه!</b>
{texts.FULL}
کشور {c_info.get('flag','')} <b>{c_info.get('name','')}</b> توسط {user_tag} از <b>حق وتو</b> استفاده کرد.
📜 قطعنامه <i>«{res['title']}»</i> رسماً <b>باطل و رد شد</b>."""
        return "✅ حق وتو اعمال شد و قطعنامه رد گردید.", ann

    if vote == "yes":
        voters[str(uid)] = "yes"
        db.ex("UPDATE un_resolutions SET votes_yes=votes_yes+1, voters_json=? WHERE id=?", (db.json.dumps(voters), res_id))
        msg = f"✅ رأی <b>موافق</b> شما از طرف {c_info.get('name','')} ثبت شد."
    else:
        voters[str(uid)] = "no"
        db.ex("UPDATE un_resolutions SET votes_no=votes_no+1, voters_json=? WHERE id=?", (db.json.dumps(voters), res_id))
        msg = f"❌ رأی <b>مخالف</b> شما از طرف {c_info.get('name','')} ثبت شد."

    # چک کردن حد نصاب برای تصویب خودکار
    updated_res = db.one("SELECT * FROM un_resolutions WHERE id=?", (res_id,))
    ann = ""
    if updated_res["votes_yes"] >= 3 and updated_res["votes_yes"] > updated_res["votes_no"] * 2:
        # تصویب قطعنامه
        ann = _execute_resolution(res_id)

    return msg, ann


def _execute_resolution(res_id: int) -> str:
    """اجرای مفاد قطعنامه تصویب‌شده."""
    res = db.one("SELECT * FROM un_resolutions WHERE id=?", (res_id,))
    if not res or res["status"] != "voting":
        return ""

    db.ex("UPDATE un_resolutions SET status='passed' WHERE id=?", (res_id,))
    res_type = res["res_type"]
    target_cid = res["target_cid"]
    t_info = countries.COUNTRIES.get(target_cid, {})

    effect_desc = ""
    if res_type == "ceasefire":
        # توقف جنگ‌های جاری کشور هدف
        db.ex("UPDATE wars SET status='ceasefire' WHERE (a=? OR b=?) AND status='active'", (target_cid, target_cid))
        effect_desc = f"🕊️ تمام جنگ‌های فعال پیرامون {t_info.get('flag','')} <b>{t_info.get('name','')}</b> متوقف شد و آتش‌بس حاکم گردید."

    elif res_type == "sanctions":
        db.kv_set(f"sanctioned:{target_cid}", "1")
        effect_desc = f"🚫 تحریم‌های همه‌جانبه تجاری و نظامی علیه {t_info.get('flag','')} <b>{t_info.get('name','')}</b> وضع شد."

    elif res_type == "lift_sanctions":
        db.kv_set(f"sanctioned:{target_cid}", "0")
        effect_desc = f"🟢 کلیه تحریم‌های بین‌المللی {t_info.get('flag','')} <b>{t_info.get('name','')}</b> برداشته شد و تجارت آزاد بازگشت."

    elif res_type == "peacekeeping":
        db.kv_set(f"peacekeeping:{target_cid}", str(db.now() + 86400))
        effect_desc = f"🛡️ نیروهای کلاه آبی سازمان ملل در {t_info.get('flag','')} <b>{t_info.get('name','')}</b> مستقر شدند. این کشور تا ۲۴ ساعت مصونیت کامل دارد."

    elif res_type == "aid":
        aid_pot = 25000
        # واریز به خزانه‌ی لیدر هدف
        db.ex("UPDATE users SET money=money+? WHERE country=? AND is_leader=1", (aid_pot, target_cid))
        effect_desc = f"💵 مبلغ <b>{texts.money('us', aid_pot)}</b> کمک بلاعوض اقتصادی از صندوق جهانی به خزانه‌ی {t_info.get('flag','')} <b>{t_info.get('name','')}</b> واریز شد."

    return f"""🎉 <b>سازمان ملل متحد — تصویب قطعی قطعنامه</b>
{texts.FULL}
📜 <b>{res['title']}</b>
▫️ نتایج آرا: <b>{res['votes_yes']} موافق</b> | <b>{res['votes_no']} مخالف</b> | <b>بدون وتو</b>
{texts.DASH}
{effect_desc}"""


def list_active_resolutions() -> str:
    """فهرست قطعنامه‌های در جریان رأی‌گیری."""
    rows = db.q("SELECT * FROM un_resolutions WHERE status='voting' ORDER BY id DESC LIMIT 5")
    if not rows:
        return f"""🏛️ <b>سازمان ملل متحد — صحن علنی</b>
{texts.FULL}
در حال حاضر هیچ قطعنامه‌ی بازی در جریان رأی‌گیری نیست.
رهبران کشورها می‌توانند از طریق دکمه‌ی زیر قطعنامه‌ی جدید پیشنهاد دهند."""

    lines = [
        texts.hdr("سازمان ملل متحد — قطعنامه‌های جاری", "🏛️"),
        "شورای امنیت و مجمع عمومی:\n"
    ]
    for r in rows:
        p_c = countries.COUNTRIES.get(r["proposer_cid"], {})
        t_c = countries.COUNTRIES.get(r["target_cid"], {})
        lines.append(f"📜 <b>شماره #{r['id']}: {r['title']}</b>")
        lines.append(f"   ▫️ طراح: {p_c.get('flag','')} {p_c.get('name','')} | هدف: {t_c.get('flag','')} {t_c.get('name','')}")
        lines.append(f"   ▫️ آرا: 🟢 {texts.fa(r['votes_yes'])} موافق | 🔴 {texts.fa(r['votes_no'])} مخالف")
        lines.append(f"   🗳️ برای رأی‌گیری از دکمه‌های زیر استفاده کنید.\n")

    return "\n".join(lines)
