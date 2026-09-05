"""Automatic channel announcements.

If the operator sets CHANNEL_ID and makes the bot an admin of that channel,
the world starts publishing itself: bosses that fall, rounds that end, and
weekly standings. Without CHANNEL_ID every call here is a cheap no-op, so
the feature costs nothing when unused.

Announcements are intentionally rare. A channel that fires on every dice
roll gets muted, so only irreversible or group-wide moments are posted.
"""
from __future__ import annotations

import logging
import os

from aiogram import Bot

from .ui import card, money

log = logging.getLogger("vcorp.channel")

CHANNEL = os.getenv("CHANNEL_ID", "").strip()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Set to False by the first failure so a misconfigured channel does not
# generate an error for every future event.
_enabled = bool(CHANNEL)


def configured() -> bool:
    return _enabled and bool(CHANNEL)


def reset() -> None:
    """Re-enable posting (tests)."""
    global _enabled
    _enabled = bool(CHANNEL)


async def _post(bot: Bot, text: str, photo: str | None = None) -> bool:
    global _enabled
    if not configured():
        return False
    try:
        if photo:
            path = os.path.join(ROOT, photo)
            if os.path.exists(path):
                from aiogram.types import FSInputFile
                await bot.send_photo(CHANNEL, FSInputFile(path), caption=text)
                return True
        await bot.send_message(CHANNEL, text, disable_web_page_preview=True)
        return True
    except Exception as exc:  # noqa: BLE001
        _enabled = False
        log.warning("channel posting disabled — %s: %s",
                    type(exc).__name__, str(exc)[:160])
        return False


async def boss_defeated(bot: Bot, boss_name: str, chat_title: str,
                        top_name: str, top_damage: int, reward: int,
                        art: str | None = None) -> bool:
    return await _post(bot, card("🏆 <b>یک تهدید بزرگ از پا درآمد</b>", [
        f"👹 <b>{boss_name}</b>",
        f"🏟️ گروه: {chat_title}",
        "",
        f"🥇 بیشترین آسیب: <b>{top_name}</b> — {top_damage}",
        f"💰 غنیمت کل: {money(reward)}",
    ], "گروه خودت را جمع کن: /boss"), photo=art)


async def round_ended(bot: Bot, mode: str, chat_title: str,
                      headline: str, detail: str) -> bool:
    icon = {"lockdown": "☣️", "convoy": "🚚", "duel": "⚔️"}.get(mode, "🎮")
    return await _post(bot, card(f"{icon} <b>{headline}</b>", [
        f"🏟️ گروه: {chat_title}",
        "",
        detail,
    ], "حالت‌های گروهی: /modes"))


async def world_event(bot: Bot, title: str, body: str) -> bool:
    return await _post(bot, card("🌎 <b>رویداد جهانی</b>", [
        f"<b>{title}</b>",
        "",
        body,
    ], "واکنش نشان بده: /event"))
