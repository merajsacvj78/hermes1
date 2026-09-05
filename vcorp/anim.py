"""Telegram-native animations used only where they carry gameplay meaning.

- animated emoji dice: the actual combat/mission roll is *shown*, not described
- GIF/sticker: reserved for irreversible or group-wide moments
Every helper fails silently: an animation must never break a game action.
"""
from __future__ import annotations

import logging
import random

from aiogram import Bot
from aiogram.enums import DiceEmoji

log = logging.getLogger("vcorp.anim")

# Animated-emoji rolls. The value returned by Telegram IS the game roll.
ROLL_COMBAT = DiceEmoji.DART        # 🎯 accuracy
ROLL_LUCK = DiceEmoji.DICE          # 🎲 scavenge luck
ROLL_JACKPOT = DiceEmoji.SLOT_MACHINE  # 🎰 black-market gamble
ROLL_STRIKE = DiceEmoji.BOWLING     # 🎳 boss strike

# Public animation URLs are avoided (they rot). We use Telegram's own
# animated emoji + optional file_ids configured by admins at runtime.
STAGE_EMOJI = {
    "infected": "☣️",
    "mutant": "🧬",
    "advanced": "🩸",
    "bioweapon": "👹",
}


async def roll(bot: Bot, chat_id: int, emoji: str = ROLL_COMBAT) -> int:
    """Send an animated dice and return its value (1-6, or 1-64 for slots)."""
    try:
        msg = await bot.send_dice(chat_id, emoji=emoji)
        return msg.dice.value if msg.dice else random.randint(1, 6)
    except Exception:  # noqa: BLE001
        log.debug("dice failed", exc_info=True)
        return random.randint(1, 6)


async def big_emoji(bot: Bot, chat_id: int, emoji: str) -> None:
    """Single large animated emoji — used for stage jumps and boss deaths."""
    try:
        await bot.send_message(chat_id, emoji)
    except Exception:  # noqa: BLE001
        pass


async def stage_animation(bot: Bot, chat_id: int, stage: str) -> None:
    em = STAGE_EMOJI.get(stage)
    if em:
        await big_emoji(bot, chat_id, em * 3)


async def send_effect(bot: Bot, chat_id: int, file_key: str) -> bool:
    """Send an admin-configured GIF/sticker (set via /aanim <key> reply-to-file)."""
    from .db import db
    fid = await db.world_get(f"anim:{file_key}")
    if not fid:
        return False
    kind, file_id = fid.get("kind"), fid.get("id")
    try:
        if kind == "sticker":
            await bot.send_sticker(chat_id, file_id)
        else:
            await bot.send_animation(chat_id, file_id)
        return True
    except Exception:  # noqa: BLE001
        return False
