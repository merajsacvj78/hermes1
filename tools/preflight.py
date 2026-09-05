"""Pre-launch check: is this deployment actually ready to run?

    python tools/preflight.py

Verifies the token, the database, the art, and Telegram reachability, then
prints exactly what remains to be done. Exits non-zero if the bot cannot
start, so it can gate a deploy script.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OK, WARN, BAD = "  ✅", "  ⚠️ ", "  ❌"


async def main() -> int:
    from vcorp import branding, channel
    from vcorp.config import config
    from vcorp.game import bestiary as B

    fatal = 0
    warn = 0
    print("V-CORP: OUTBREAK — preflight\n")

    # ── token ────────────────────────────────────────────────────────────
    print("token")
    if not config.token:
        print(BAD, "BOT_TOKEN is empty. Put it in .env")
        fatal += 1
    elif ":" not in config.token:
        print(BAD, "BOT_TOKEN is malformed")
        fatal += 1
    else:
        print(OK, f"present ({config.token.split(':')[0]})")

    # ── admins ───────────────────────────────────────────────────────────
    print("\nadmins")
    if config.admins:
        print(OK, f"{len(config.admins)} configured")
    else:
        print(WARN, "ADMIN_IDS empty — /admin will be unreachable.")
        print("      Send /whoami to the bot, then put the id in .env")
        warn += 1

    # ── artwork ──────────────────────────────────────────────────────────
    print("\nartwork")
    missing = [k.key for k in B.BESTIARY
               if not os.path.exists(os.path.join(ROOT, k.art))]
    if missing:
        print(WARN, f"missing boss art: {', '.join(missing)} (text fallback)")
        warn += 1
    else:
        print(OK, f"all {len(B.BESTIARY)} boss portraits present")
    if os.path.exists(branding.AVATAR):
        print(OK, "bot avatar present")
    else:
        print(WARN, "brand/bot_avatar.jpg missing")
        warn += 1

    # ── database ─────────────────────────────────────────────────────────
    print("\ndatabase")
    try:
        from vcorp.db import db
        db.path = config.db_path
        await db.connect()
        from vcorp.game import engine as E
        await E.seed()
        players = await db.scalar("SELECT COUNT(*) FROM players")
        print(OK, f"{config.db_path} ready ({players} players)")
        await db.close()
    except Exception as exc:  # noqa: BLE001
        print(BAD, f"database error: {exc}")
        fatal += 1

    # ── channel ──────────────────────────────────────────────────────────
    print("\nchannel")
    if channel.configured():
        print(OK, f"announcements -> {channel.CHANNEL}")
    else:
        print(WARN, "CHANNEL_ID unset — no auto announcements (optional)")
        warn += 1

    # ── telegram reachability ────────────────────────────────────────────
    print("\ntelegram")
    if not config.token:
        print(WARN, "skipped (no token)")
    else:
        try:
            from aiogram import Bot
            from aiogram.client.default import DefaultBotProperties
            kw = {}
            if config.api_base:
                from aiogram.client.session.aiohttp import AiohttpSession
                from aiogram.client.telegram import TelegramAPIServer
                kw["session"] = AiohttpSession(
                    api=TelegramAPIServer.from_base(config.api_base))
            bot = Bot(config.token,
                      default=DefaultBotProperties(parse_mode="HTML"), **kw)
            me = await bot.get_me()
            print(OK, f"connected as @{me.username} ({me.id})")
            if not me.can_join_groups:
                print(BAD, "this bot cannot join groups — enable in BotFather")
                fatal += 1
            if me.can_read_all_group_messages:
                print(OK, "privacy mode off (sees group commands)")
            else:
                print(WARN, "privacy mode ON — BotFather /setprivacy -> Disable")
                warn += 1
            await bot.session.close()
        except Exception as exc:  # noqa: BLE001
            print(WARN, f"could not reach Telegram: {type(exc).__name__}")
            print("      (blocked network? the bot itself may still be fine)")
            warn += 1

    print("\n" + "─" * 46)
    if fatal:
        print(f"❌ {fatal} blocking problem(s) — the bot will not start")
        return 1
    print(f"✅ ready to launch" + (f"  ({warn} optional item(s))" if warn else ""))
    print("\n   .venv/bin/python -m vcorp")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except BaseException:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    os._exit(code)
