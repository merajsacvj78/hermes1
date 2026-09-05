"""V-CORP: OUTBREAK — Telegram text-strategy game bot (aiogram 3, async)."""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats

from . import scheduler
from .config import config
from .db import db
from .game.engine import seed
from .handlers import (actions, admin, betrayal, economy, group_core, guide,
                       lockdown, orgs, private, pvp)
from .middlewares import BanMiddleware, ChatTrackMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("vcorp")

GROUP_COMMANDS = [
    ("start", "☣️ ورود به جهان"),
    ("me", "🧬 پروفایل"),
    ("scavenge", "🔦 جست‌وجو"),
    ("mission", "🎯 مأموریت‌ها"),
    ("attack", "⚔️ حمله (ریپلای)"),
    ("duel", "🩸 دوئل PvP (ریپلای)"),
    ("arena", "🏆 رتبه‌بندی گودال"),
    ("lockdown", "☣️ پروتکل قرنطینه (گروهی)"),
    ("power", "🦸 قدرت‌ها"),
    ("mutate", "🧬 درخت جهش"),
    ("shop", "🛒 فروشگاه"),
    ("black", "🕳️ بازار سیاه"),
    ("contract", "🎯 قرارداد مخفی"),
    ("wanted", "🚨 تحت تعقیب"),
    ("orgs", "🏢 سازمان‌ها"),
    ("world", "🌎 وضعیت جهان"),
    ("boss", "👹 تهدید بزرگ"),
    ("top", "🏆 رتبه‌بندی"),
    ("guide", "📚 آموزش گام‌به‌گام"),
    ("help", "📖 راهنما"),
]


async def main() -> None:
    if not config.token:
        log.error("BOT_TOKEN تنظیم نشده است. متغیر محیطی BOT_TOKEN را ست کن.")
        sys.exit(1)

    await db.connect()
    await seed()

    session = None
    if config.api_base:
        # local or self-hosted Bot API server
        session = AiohttpSession(
            api=TelegramAPIServer.from_base(config.api_base.rstrip("/")))
        log.info("using Bot API server at %s", config.api_base)

    bot = Bot(config.token,
              session=session,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML,
                                           link_preview_is_disabled=True))
    me = await bot.get_me()
    if not config.bot_username:
        config.bot_username = me.username or ""
    log.info("V-CORP: OUTBREAK online as @%s", me.username)

    dp = Dispatcher()
    dp.message.middleware(ChatTrackMiddleware())
    dp.message.middleware(BanMiddleware())
    dp.callback_query.middleware(BanMiddleware())

    dp.include_router(admin.router)
    dp.include_router(private.router)
    dp.include_router(group_core.router)
    dp.include_router(actions.router)
    dp.include_router(economy.router)
    dp.include_router(betrayal.router)
    dp.include_router(orgs.router)
    dp.include_router(pvp.router)
    dp.include_router(guide.router)
    dp.include_router(lockdown.router)

    from .handlers import world as world_h
    dp.include_router(world_h.router)

    await bot.set_my_commands(
        [BotCommand(command=c, description=d) for c, d in GROUP_COMMANDS],
        scope=BotCommandScopeAllGroupChats())

    task = scheduler.start(bot)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        from .game.duel import abort_all
        from .handlers.lockdown import abort_all as ld_abort
        refunded = await abort_all()
        if refunded:
            log.info("refunded %s in-flight duel(s)", refunded)
        rounds = await ld_abort()
        if rounds:
            log.info("refunded %s open LOCKDOWN round(s)", rounds)
        await scheduler.stop(task)
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("shutdown")
