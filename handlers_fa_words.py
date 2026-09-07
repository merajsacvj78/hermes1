# ═══════════ پردازشگر دستورهای متنی و ورودی‌های منتظر ═══════════

def _find_country(txt: str):
    """جستجوی دقیق نام کشور با اصلاح حروف فارسی/عربی."""
    def _n(s):
        return (s or "").replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک").strip()
    t = _n(txt)
    if not t:
        return None
    for cid, c in countries.COUNTRIES.items():
        if t in (c["name"], cid) or _n(c["name"]) == t:
            return cid
    for cid, c in countries.COUNTRIES.items():
        cn = _n(c["name"])
        if cn and (t in cn or cn in t):
            return cid
    return None

@router.message()
async def fa_words(m: Message):
    t = (m.text or "").strip()
    if not t:
        return
    # پاکسازی منشن ربات
    if "@REDarkZoneBot" in t:
        t = t.replace("@REDarkZoneBot", "").strip()
        if not t:
            t = "منو"
        elif not t.isdigit():
            t = next((w for w in t.split() if w in TEXT_ALLOWED), "منو")
    parts = t.split(maxsplit=1)
    w = parts[0]
    if w in ("/menu", "منو"):
        w = "منو"
    arg = parts[1] if len(parts) > 1 else ""
    uid = m.from_user.id

    if m.chat.type == "private":
        if WORLD_OF is None or not WORLD_OF(uid):
            return await m.answer(texts.PM_GUIDE, parse_mode="HTML")

    state.ensure(uid, m.from_user.first_name,
                 None if m.chat.type == "private" else m.chat.id,
                 getattr(m.from_user, "username", None))

    # بررسی ورودی‌های در انتظار (Pending inputs)
    pend = _pend_pop(uid, m.chat.id)
    if pend:
        if w == "لغو":
            return await m.answer("✅ عملیات جاری لغو شد. می‌توانید از «منو» مجدداً اقدام کنید.", parse_mode="HTML")

        if pend.startswith("opname:"):
            target_cid = pend.split(":", 1)[1]
            msg, ann = war.create_operation(uid, target_cid, t)
            sent = await m.answer(msg, parse_mode="HTML", reply_markup=kb_operation_stages(uid, target_cid))
            _own(m, sent, uid)
            if ann:
                with contextlib.suppress(Exception):
                    await m.answer(ann, parse_mode="HTML")
            return sent

        if pend.startswith("pay:"):
            to = int(pend.split(":", 1)[1])
            amt = texts.to_int(w)
            me = db.one("SELECT country, money FROM users WHERE uid=?", (uid,))
            dst = db.one("SELECT name FROM users WHERE uid=?", (to,))
            if not dst or not me:
                return await m.answer("⚠️ گیرنده یافت نشد.", parse_mode="HTML")
            if not amt or amt < 1:
                return await m.answer("⚠️ لطفاً فقط مبلغ عددی بنویسید (مثال: <code>5000</code>).", parse_mode="HTML")
            if amt > me["money"]:
                return await m.answer(f"⚠️ موجودی کافی نیست. موجودی شما: {texts.money(me['country'], me['money'])}", parse_mode="HTML")
            db.ex("UPDATE users SET money=money-? WHERE uid=?", (amt, uid))
            db.ex("UPDATE users SET money=money+? WHERE uid=?", (amt, to))
            sender_tag = texts.mention(uid, m.from_user.first_name)
            receiver_tag = texts.mention(to, dst["name"])
            return await m.answer(f"💸 <b>انتقال موفقیت‌آمیز وجه</b>\n\nمبلغ <b>{texts.money(me['country'], amt)}</b> از طرف {sender_tag} به حساب {receiver_tag} واریز شد.", parse_mode="HTML")

        if pend == "stmt":
            sent = await m.answer(politics.statement(uid, t), parse_mode="HTML", reply_markup=kb_pol())
            _own(m, sent, uid)
            return sent

        if pend == "alead":
            sent = await m.answer(_admin_leader(t), parse_mode="HTML", reply_markup=kb_admin())
            _own(m, sent, uid)
            return sent

        if pend in ("areg", "achg"):
            parts2 = t.split()
            if len(parts2) >= 2 and parts2[0].isdigit():
                fn = _admin_register if pend == "areg" else _admin_change
                sent = await m.answer(fn(int(parts2[0]), " ".join(parts2[1:])), parse_mode="HTML", reply_markup=kb_admin())
                _own(m, sent, uid)
                return sent
            _pend_set(uid, m.chat.id, pend)
            sent = await m.answer("⚠️ الگو: <code>آیدی‌عددی نام‌کشور</code> — مثال: <code>8694290031 ایران</code>", parse_mode="HTML", reply_markup=kb_admin())
            _own(m, sent, uid)
            return sent

        if pend == "party":
            nm, _, ideo = t.partition("|")
            sent = await m.answer(politics.found(uid, nm.strip(), ideo.strip() or "ملی"), parse_mode="HTML", reply_markup=kb_pol())
            _own(m, sent, uid)
            return sent

    # دستورهای متنی
    if w in ("دستورها", "دستور", "دستورات", "کمک", "/commands"):
        sent = await m.answer(texts.COMMANDS, parse_mode="HTML", reply_markup=kb_help(1))
        _own(m, sent, uid)
        return sent

    if w in ("/help", "راهنما"):
        sent = await m.answer(texts.HELP_PAGES[0], parse_mode="HTML", reply_markup=kb_help(1))
        _own(m, sent, uid)
        return sent

    if w in ("منو", "/menu"):
        sent = await m.answer(state.card(uid), parse_mode="HTML", reply_markup=kb_main(uid))
        _own(m, sent, uid)
        return sent

    if w in ("نظامی", "/military", "ارتش"):
        sent = await m.answer(texts.hdr("فرماندهی نظامی", "🎖️") + "\n\nیکی را انتخاب کن:", parse_mode="HTML", reply_markup=kb_mil())
        _own(m, sent, uid)
        return sent

    if w in ("خرید", "زرادخانه", "تجهیزات", "/buy"):
        sent = await m.answer(military.arsenal(uid), parse_mode="HTML", reply_markup=kb_arsenal(uid))
        _own(m, sent, uid)
        return sent

    if w in ("حمله", "جنگ", "/war", "/attack"):
        p = state.active(uid)
        if p and war.war_of(p["country"]):
            sent = await m.answer(war.front(uid), parse_mode="HTML", reply_markup=kb_strikes(uid))
        else:
            sent = await m.answer(texts.hdr("فرماندهی جنگ و عملیات", "⚔️") + "\n\nکشور هدف را برای اعلان جنگ یا آغاز عملیات انتخاب کنید:", parse_mode="HTML", reply_markup=kb_declare(uid))
        _own(m, sent, uid)
        return sent

    if w in ("سازمان ملل", "/un"):
        sent = await m.answer(un.list_active_resolutions(), parse_mode="HTML", reply_markup=kb_un(uid))
        _own(m, sent, uid)
        return sent

    if w in ("تنگه", "تنگه‌ها", "عوارض", "/toll"):
        sent = await m.answer(toll.straits_overview(uid), parse_mode="HTML", reply_markup=kb_straits_v40(uid))
        _own(m, sent, uid)
        return sent

    if w in ("پایگاه", "پایگاه‌ها", "/bases"):
        p = state.active(uid)
        if p:
            sent = await m.answer(texts.hdr("احداث پایگاه‌های نظامی در شهرها", "🏗️"), parse_mode="HTML", reply_markup=kb_bases(uid))
            _own(m, sent, uid)
            return sent

    if w in ("سرمایه", "سرمایه‌گذاری", "معدن", "/invest"):
        sent = await m.answer(invest.view(uid), parse_mode="HTML", reply_markup=kb_invest(uid))
        _own(m, sent, uid)
        return sent

    if w in ("پروفایل", "/profile", "کارت"):
        sent = await m.answer(state.card(uid), parse_mode="HTML", reply_markup=kb_main(uid))
        _own(m, sent, uid)
        return sent

    if w in ("جهان", "/world"):
        sent = await m.answer(war.world_status(), parse_mode="HTML", reply_markup=kb_world())
        _own(m, sent, uid)
        return sent

    # ابزارهای مالک
    if w == "رهبر":
        if uid != config.OWNER_ID:
            return await m.answer("🚫 این دستور فقط برای مالک ربات مجاز است.", parse_mode="HTML")
        parts_l = arg.split() if arg else []
        ru = getattr(m.reply_to_message, "from_user", None) if m.reply_to_message else None
        if ru and parts_l and parts_l[0] not in ("خالی", "-"):
            return await m.answer(_set_leader(ru.id, " ".join(parts_l)), parse_mode="HTML", reply_markup=kb_admin())
        if parts_l and parts_l[0].startswith("@") and parts_l[0][1:]:
            r = db.one("SELECT uid FROM users WHERE username=? COLLATE NOCASE", (parts_l[0][1:],))
            if r:
                return await m.answer(_set_leader(r["uid"], " ".join(parts_l[1:])), parse_mode="HTML", reply_markup=kb_admin())
        sent = await m.answer(_admin_leader(arg), parse_mode="HTML", reply_markup=kb_admin())
        _own(m, sent, uid)
        return sent
