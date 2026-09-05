"""Self-configuring bot identity.

Everything that would otherwise be typed into BotFather by hand — name,
about text, description, command lists, group admin rights, the menu
button — is applied by the bot itself on startup. The operator only ever
supplies a token.

Rules this follows:
  * Nothing here may abort startup. A failed cosmetic call is logged and
    skipped; the game must still come up.
  * Telegram rejects an edit that changes nothing ("… is not modified"),
    which is a success for our purposes, so it is treated as one.
  * Command scopes matter: the group list and the private list are
    different, because private chat is only a doorway to a group.
"""
from __future__ import annotations

import logging
import os

from aiogram import Bot
from aiogram.types import (BotCommand, BotCommandScopeAllGroupChats,
                           BotCommandScopeAllPrivateChats,
                           ChatAdministratorRights, FSInputFile,
                           MenuButtonCommands)

log = logging.getLogger("vcorp.branding")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AVATAR = os.path.join(ROOT, "brand", "bot_avatar.jpg")

NAME = "V-CORP: OUTBREAK"

# 120 char limit — shown in the chat list and in search results.
SHORT_DESCRIPTION = (
    "بازی متنی گروهی بقا، آلودگی و خیانت. مرا به گروه اضافه کن."
)

# 512 char limit — shown on the bot's profile before the user starts it.
DESCRIPTION = (
    "☣️ شهر سقوط کرده. ویروس VX-13 مرز انسان و سلاح را پاک کرده.\n\n"
    "🧬 آلوده شو و قدرت بگیر — با شمارش معکوس\n"
    "🦸 قدرت‌های V-SERUM، هرکدام با ضعف مشخص\n"
    "🏢 سازمان بساز، بجنگ، خیانت کن\n\n"
    "⚔️ گودال (PvP) · ☣️ قرنطینه · 🚚 کاروان · 👹 باس جهانی\n\n"
    "بازی کامل داخل گروه انجام می‌شود."
)

GROUP_COMMANDS: list[tuple[str, str]] = [
    ("start", "☣️ ورود به جهان"),
    ("me", "🧬 پروفایل"),
    ("guide", "📚 آموزش گام‌به‌گام"),
    ("modes", "🎮 حالت‌های گروهی"),
    ("duel", "⚔️ دعوت به گودال"),
    ("arena", "🏆 رتبه‌بندی گودال"),
    ("lockdown", "☣️ پروتکل قرنطینه"),
    ("convoy", "🚚 کاروان — فرار گروهی"),
    ("boss", "👹 تهدید بزرگ"),
    ("scavenge", "🎒 جست‌وجو"),
    ("mission", "🎯 مأموریت"),
    ("power", "🦸 قدرت‌ها"),
    ("shop", "💰 فروشگاه"),
    ("world", "🌎 وضعیت جهان"),
    ("top", "🏅 رتبه‌بندی"),
    ("help", "📖 فهرست کامل"),
]

# Private chat is deliberately a doorway, not a game surface.
PRIVATE_COMMANDS: list[tuple[str, str]] = [
    ("start", "☣️ معرفی و افزودن به گروه"),
    ("help", "📖 راهنمای کوتاه"),
]


async def _try(label: str, coro) -> bool:
    """Await a cosmetic call, swallowing failures. True if it took effect."""
    try:
        await coro
        log.info("branding: %s ✓", label)
        return True
    except Exception as exc:  # noqa: BLE001
        text = str(exc)
        if "not modified" in text or "NOT_MODIFIED" in text.upper():
            log.info("branding: %s (already set)", label)
            return True
        log.warning("branding: %s skipped — %s", label, text[:160])
        return False


async def apply(bot: Bot, *, set_avatar: bool = True) -> dict[str, bool]:
    """Push the whole identity to Telegram. Never raises."""
    done: dict[str, bool] = {}

    done["name"] = await _try("name", bot.set_my_name(name=NAME))
    done["short_description"] = await _try(
        "short description", bot.set_my_short_description(
            short_description=SHORT_DESCRIPTION))
    done["description"] = await _try(
        "description", bot.set_my_description(description=DESCRIPTION))

    done["group_commands"] = await _try("group commands", bot.set_my_commands(
        [BotCommand(command=c, description=d) for c, d in GROUP_COMMANDS],
        scope=BotCommandScopeAllGroupChats()))
    done["private_commands"] = await _try(
        "private commands", bot.set_my_commands(
            [BotCommand(command=c, description=d) for c, d in PRIVATE_COMMANDS],
            scope=BotCommandScopeAllPrivateChats()))

    done["menu_button"] = await _try("menu button", bot.set_chat_menu_button(
        menu_button=MenuButtonCommands()))

    # Asking for exactly the rights the game needs, so an admin who promotes
    # the bot gets a sensible pre-filled dialog instead of a blank one.
    # Ephemeral role delivery works best when the bot is an administrator.
    done["admin_rights"] = await _try(
        "default admin rights", bot.set_my_default_administrator_rights(
            rights=ChatAdministratorRights(
                is_anonymous=False,
                can_manage_chat=True,
                can_delete_messages=True,
                can_manage_video_chats=False,
                can_restrict_members=True,
                can_promote_members=False,
                can_change_info=False,
                can_invite_users=True,
                can_send_welcome_messages=False,
                can_post_stories=False,
                can_edit_stories=False,
                can_delete_stories=False,
                can_pin_messages=True,
            ),
            for_channels=False))

    if set_avatar and hasattr(bot, "set_bot_profile_photo"):
        # Only available on newer Bot API versions; skipped silently below.
        if os.path.exists(AVATAR):
            from aiogram.types import InputProfilePhotoStatic
            done["avatar"] = await _try("avatar", bot.set_bot_profile_photo(
                photo=InputProfilePhotoStatic(photo=FSInputFile(AVATAR))))
    return done
