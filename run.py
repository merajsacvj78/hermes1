"""🚀 جنگ جهانی — اسکریپت اصلی اجرا: polling + اقتصاد زنده + رویدادهای گروهی + ذخیره‌سازی."""
import asyncio
import contextlib
import os
import time
import traceback
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import config
import db
import handlers
from game import ai, economy, events, war, invest, toll, un

NEWS_TMPL = [
    ("📊 خبرگزاری مالی جهانی: شاخص دلار به ×{dollar:.2f} رسید — بازارهای بورس جهانی واکنش نشان دادند.", "dollar"),
    ("🛢️ شوک در بازار انرژی: قیمت نفت برنت به ${oil:.0f} در هر بشکه رسید.", "oil"),
    ("📈 گزارش صندوق بین‌المللی پول: نرخ تورم جهانی به {inf:.1f}٪ افزایش یافت.", "inflation"),
]


def _news(w) -> str | None:
    import random
    if random.random() > 0.04:          # هر تیک ۶۰ ثانیه → تقریباً هر ۴۰ دقیقه یک خبر
        return None
    tpl, key = random.choice(NEWS_TMPL)
    import texts
    return texts.fa(tpl.format(dollar=w["dollar"], oil=w["oil"], inf=w["inflation"] * 100))


_last = {}


def _too_fast(uid: int, gap: float = 0.5) -> bool:
    """ضداسپم فردی — پیام ۰٫۵ ثانیه، دکمه ۰٫۲۵ ثانیه."""
    t = time.time()
    if t - _last.get(uid, 0) < gap:
        return True
    _last[uid] = t
    return False


async def world_loop(bot: Bot):
    """حلقه اقتصاد جهانی، واریز سودهای ساعتی و پردازش خودکار سررسیدها."""
    await asyncio.sleep(15)
    print("🌍 world_loop started successfully", flush=True)
    while True:
        try:
            for g in db.list_games():
                db.GAME.set(g)
                if not events.game_alive(g):
                    continue

                # ۱. واریز درآمدهای ساعتی به وقت ایران
                invest.distribute_hourly_payouts_for_all(g)

                # ۲. تیک اقتصاد، دلار و تورم
                w = economy.tick()
                news = _news(w)
                if news:
                    with contextlib.suppress(Exception):
                        await bot.send_message(g, news, parse_mode="HTML")

                # ۳. حل و فصل جنگ‌های سررسیدشده
                for msg in war.settle():
                    with contextlib.suppress(Exception):
                        await bot.send_message(g, msg, parse_mode="HTML")

            await asyncio.sleep(60)
        except Exception:
            with contextlib.suppress(Exception):
                db.log("error", "world_loop: " + traceback.format_exc()[-300:])
            await asyncio.sleep(60)


async def events_loop(bot: Bot):
    """رویدادهای زنده گروهی و فراخوان‌های نبرد."""
    def _tag_all(text: str) -> str:
        """منشن امن بازیکنان فعال گروه."""
        with contextlib.suppress(Exception):
            rows = db.q("SELECT uid, name FROM users "
                        "WHERE country IS NOT NULL AND last_active > ? "
                        "ORDER BY last_active DESC LIMIT 15",
                        (db.now() - 3 * 86400,))
            if rows:
                import texts as _tx
                tags = " ".join(_tx.mention(r["uid"], (r["name"] or "سرباز")[:16])
                                for r in rows)
                return f"{tags}\n\n{text}"
        return text

    await asyncio.sleep(25)
    print("⚡ events_loop started successfully", flush=True)
    while True:
        try:
            now = db.now()
            for g in db.list_games():
                if not events.game_alive(g):
                    continue
                db.GAME.set(g)

                # خبرنامه هر ۳۰ دقیقه
                if not db.kv_get("bl_off") and now - int(db.kv_get("bl_last", "0")) >= 1800:
                    db.kv_set("bl_last", str(now))
                    bl = _tag_all(events.bulletin())
                    with contextlib.suppress(Exception):
                        await bot.send_message(g, bl, parse_mode="HTML")

                # رویدادهای گروهی
                if not db.kv_get("ev_off"):
                    ev = events.maybe_event(g)
                    if ev:
                        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
                        text, word = ev
                        text = _tag_all(text)
                        kb = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="⚡ شرکت در رویداد و دریافت پاداش", callback_data=f"evc:{word}")
                        ]])
                        with contextlib.suppress(Exception):
                            await bot.send_message(g, text, parse_mode="HTML", reply_markup=kb)
            await asyncio.sleep(45)
        except Exception:
            with contextlib.suppress(Exception):
                db.log("error", "events_loop: " + traceback.format_exc()[-300:])
            await asyncio.sleep(45)


async def main():
    db.init()
    # ریست و تنظیم لیدرهای ویژه و مبالغ آغازین
    db.seed_special_users()

    import countries
    countries.init_items()

    for g in db.list_games():
        db.GAME.set(g)
        countries.init_items()
        db.seed_special_users()
    db.GAME.set(None)

    handlers.bot = bot = Bot(config.TOKEN,
                             default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # ثبت منوی دستورهای اسلش تلگرام
    with contextlib.suppress(Exception):
        from aiogram.types import BotCommand
        await bot.set_my_commands([
            BotCommand(command="menu", description="🏛️ منوی اصلی و داشبورد بازی"),
            BotCommand(command="start", description="🚀 شروع / انتخاب کشور"),
            BotCommand(command="war", description="⚔️ عملیات، حمله و جبهه‌های نبرد"),
            BotCommand(command="military", description="🎖️ ارتش، شاخه‌ها و زرادخانه"),
            BotCommand(command="un", description="🏛️ مجمع عمومی و شورای امنیت سازمان ملل"),
            BotCommand(command="toll", description="🌊 تنگه‌ها و عوارض کشتیرانی"),
            BotCommand(command="bases", description="🏗️ احداث پایگاه‌های نظامی در شهرها"),
            BotCommand(command="invest", description="📈 سرمایه‌گذاری و درآمدهای ساعتی"),
            BotCommand(command="trade", description="🚢 تجارت و بازارهای جهانی"),
            BotCommand(command="infra", description="⚡ زیرساخت‌ها و نیروگاه‌ها"),
            BotCommand(command="defense", description="🛡️ تقویت سپر پدافند ۶ لایه"),
            BotCommand(command="profile", description="👤 اطلاعات ملی و کارت فرمانده"),
            BotCommand(command="world", description="🌍 نقشه و اخبار جهان"),
            BotCommand(command="help", description="📖 راهنمای کامل بازی، دلار و تورم"),
        ])

    dp = Dispatcher()
    dp.include_router(handlers.router)

    from aiogram import BaseMiddleware
    from aiogram.types import Message

    _PM_WORLD: dict = {}

    def _world_of(uid: int):
        hit = _PM_WORLD.get(uid)
        if hit:
            return hit
        for g in db.list_games():
            db.GAME.set(g)
            if db.one("SELECT 1 FROM users WHERE uid=? AND country IS NOT NULL", (uid,)):
                _PM_WORLD[uid] = g
                return g
        return None

    handlers.WORLD_OF = _world_of

    class Guard(BaseMiddleware):
        async def __call__(self, handler, event, data):
            chat = getattr(event, "chat", None)
            if chat is None:
                chat = getattr(getattr(event, "message", None), "chat", None)
            cid = getattr(chat, "id", 0) if chat is not None else 0
            who = getattr(event, "from_user", None)
            if cid < 0:
                db.GAME.set(cid)
            elif who is not None:
                db.GAME.set(_world_of(who.id))
            if who and who.id != config.OWNER_ID and _too_fast(
                    who.id, 0.5 if isinstance(event, Message) else 0.25):
                if not isinstance(event, Message):
                    with contextlib.suppress(Exception):
                        await event.answer()
                return
            return await handler(event, data)

    dp.message.middleware(Guard())
    dp.callback_query.middleware(Guard())

    # ارسال پیام آپدیت و تغییرات به تمام گروه‌های بازی
    for g in db.list_games():
        with contextlib.suppress(Exception):
            await bot.send_message(g, texts.UPDATE_BROADCAST_TEXT, parse_mode="HTML")

    print("🚀 DarkZone Bot v40 is now active!", flush=True)
    t1 = asyncio.create_task(world_loop(bot))
    t2 = asyncio.create_task(events_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        t1.cancel()
        t2.cancel()


if __name__ == "__main__":
    asyncio.run(main())
