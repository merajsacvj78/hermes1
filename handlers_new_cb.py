# ═══════════ سیستم‌های پیشرفته نسخه ۴۰ (سازمان ملل، تنگه‌ها، پایگاه‌ها، حملات ۵ مرحله‌ای) ═══════════

@router.callback_query(F.data.startswith("unp:"))
async def cb_un_propose(c: CallbackQuery):
    res_type = c.data.split(":")[1]
    prompt_text = "🏛️ <b>سازمان ملل متحد — ثبت قطعنامه</b>\nنوع: <b>" + str(un.RESOLUTION_TYPES.get(res_type, res_type)) + "</b>\n\nکشور هدف را از فهرست زیر انتخاب کنید:"
    await _edit(c, prompt_text, kb_targets(c.from_user.id, "unsub:" + res_type))
    await c.answer()

@router.callback_query(F.data.startswith("unsub:"))
async def cb_un_submit(c: CallbackQuery):
    parts = c.data.split(":")
    res_type = parts[1]
    target_cid = parts[2]
    msg, ann = un.propose_resolution(c.from_user.id, res_type, target_cid)
    await _edit(c, msg, kb_un(c.from_user.id))
    if ann:
        with contextlib.suppress(Exception):
            await c.message.answer(ann, parse_mode="HTML")
    await c.answer()

@router.callback_query(F.data == "unv:")
async def cb_un_vote_list(c: CallbackQuery):
    rows = db.q("SELECT * FROM un_resolutions WHERE status='voting' ORDER BY id DESC LIMIT 5")
    if not rows:
        await _edit(c, "🏛️ در حال حاضر قطعنامه‌ای در جریان رأی‌گیری نیست.", kb_un(c.from_user.id))
        return await c.answer()
    p = state.active(c.from_user.id)
    is_p5 = un.is_p5(p["country"]) if p else False
    btn_rows = []
    for r in rows:
        btn_rows.append([InlineKeyboardButton(text="🗳️ رأی به قطعنامه #" + str(r['id']), callback_data="unpick:" + str(r['id']))])
    btn_rows.append([InlineKeyboardButton(text="🔙 بازگشت به سازمان ملل", callback_data="mn:un")])
    await _edit(c, un.list_active_resolutions(), InlineKeyboardMarkup(inline_keyboard=btn_rows))
    await c.answer()

@router.callback_query(F.data.startswith("unpick:"))
async def cb_un_pick(c: CallbackQuery):
    res_id = int(c.data.split(":")[1])
    p = state.active(c.from_user.id)
    is_p5 = un.is_p5(p["country"]) if p else False
    res = db.one("SELECT * FROM un_resolutions WHERE id=?", (res_id,))
    if not res:
        return await c.answer("قطعنامه یافت نشد.", show_alert=True)
    body = "🏛️ <b>رأی‌گیری قطعنامه #" + str(res['id']) + "</b>\nعنوان: <b>" + str(res['title']) + "</b>\n\nآرای ثبت‌شده:\n🟢 موافق: " + str(res['votes_yes']) + " | 🔴 مخالف: " + str(res['votes_no']) + "\n\nرأی خود را انتخاب کنید:"
    await _edit(c, body, kb_un_vote(res_id, is_p5))
    await c.answer()

@router.callback_query(F.data.startswith("unv:"))
async def cb_un_cast_vote(c: CallbackQuery):
    parts = c.data.split(":")
    if len(parts) >= 3:
        vote = parts[1]
        res_id = int(parts[2])
        msg, ann = un.vote_resolution(c.from_user.id, res_id, vote)
        await _edit(c, msg, kb_un(c.from_user.id))
        if ann:
            with contextlib.suppress(Exception):
                await c.message.answer(ann, parse_mode="HTML")
        await c.answer()

@router.callback_query(F.data.startswith("strv40:"))
async def cb_strait_view(c: CallbackQuery):
    key = c.data.split(":")[1]
    s = toll.STRAITS.get(key)
    if not s:
        return await c.answer("تنگه نامعتبر است.", show_alert=True)
    owner_str = " / ".join(countries.COUNTRIES.get(o,{}).get('name',o) for o in s["owners"])
    closed = toll.is_closed(key)
    toll_amt = toll.get_toll(key)
    st_status = "⛔ مسدود" if closed else "🟢 آزاد و باز"
    desc = "🌊 <b>آبراه " + s['name'] + "</b> (" + s['flag'] + ")\n" + texts.FULL + "\n▫️ حاکمیت قانونی: <b>" + owner_str + "</b>\n▫️ وضعیت: <b>" + st_status + "</b>\n▫️ نرخ عوارض: <b>" + texts.money('us', toll_amt) + "</b>\n▫️ صندوق: <b>" + texts.money('us', toll.get_pot(key)) + "</b>\n\n" + s['desc']
    await _edit(c, desc, kb_strait_manage(c.from_user.id, key))
    await c.answer()

@router.callback_query(F.data.startswith("strop:"))
async def cb_strait_op(c: CallbackQuery):
    parts = c.data.split(":")
    op = parts[1]
    key = parts[2]
    if op == "toggle_close":
        msg, ann = toll.toggle_closure(c.from_user.id, key)
    elif op == "toggle_toll":
        msg, ann = toll.toggle_toll(c.from_user.id, key)
    elif op == "collect":
        msg = toll.collect_pot(c.from_user.id, key)
        ann = ""
    elif op == "pay":
        msg = toll.pay_user_toll(c.from_user.id, key)
        ann = ""
    else:
        msg, ann = "⚠️ عملیات نامعتبر است.", ""
    await _edit(c, msg, kb_straits_v40(c.from_user.id))
    if ann:
        with contextlib.suppress(Exception):
            await c.message.answer(ann, parse_mode="HTML")
    await c.answer()

@router.callback_query(F.data.startswith("bldbase:"))
async def cb_build_base(c: CallbackQuery):
    parts = c.data.split(":")
    btype = parts[1]
    city = parts[2]
    msg = geo.build_base(c.from_user.id, city, btype)
    await _edit(c, msg, kb_bases(c.from_user.id))
    await c.answer()

@router.callback_query(F.data.startswith("opstg:"))
async def cb_operation_stage(c: CallbackQuery):
    parts = c.data.split(":")
    stage = int(parts[1])
    target_cid = parts[2]
    msg, ann = war.strike_stage(c.from_user.id, target_cid, stage)
    await _edit(c, msg, kb_operation_stages(c.from_user.id, target_cid))
    if ann:
        with contextlib.suppress(Exception):
            await c.message.answer(ann, parse_mode="HTML")
    await c.answer()

@router.callback_query(F.data.startswith("newop:"))
async def cb_new_operation(c: CallbackQuery):
    target_cid = c.data.split(":")[1]
    _pend_set(c.from_user.id, c.message.chat.id, "opname:" + target_cid)
    t_info = countries.COUNTRIES.get(target_cid, {})
    await _edit(c, "🚩 <b>طراحی عملیات نظامی جدید علیه " + str(t_info.get('name','')) + "</b>\n\n✍️ لطفاً <b>نام عملیات دلخواه خود</b> را در گروه بفرستید:\n(مثال: <code>عملیات وعده صادق</code> یا <code>Operation Overlord</code>)\n\nبرای لغو بنویسید: <b>لغو</b>", kb_cancel_pol())
    await c.answer()
