"""Secret delivery: get private information to one player inside a group.

The oldest friction point in this bot was that hidden-role modes needed a
DM, so anyone who had not started the bot privately could not be dealt a
role. Bot API (July 2026) added **ephemeral messages**: a group message
visible only to one chosen user. That removes the friction entirely.

Not every deployment can rely on it, so this module degrades in order:

  1. ephemeral message in the group  (nothing to set up, nobody misses out)
  2. private DM                      (works if the user started the bot)
  3. report failure                  (caller warns the group by name)

`deliver()` returns how the message actually got there, so callers can tell
the group who is unreachable instead of silently dealing them out.
"""
from __future__ import annotations

import asyncio
import logging
from enum import Enum

from aiogram import Bot
from aiogram.types import EphemeralMessageParameters, InlineKeyboardMarkup

log = logging.getLogger("vcorp.secret")


class Route(str, Enum):
    EPHEMERAL = "ephemeral"
    DM = "dm"
    FAILED = "failed"


# Chats where ephemeral delivery has already failed. Retrying it for every
# player of every round would add a doomed API call per player, so the first
# failure disables it for that chat.
_no_ephemeral: set[int] = set()


def reset_cache() -> None:
    """Forget which chats rejected ephemeral messages (used by tests)."""
    _no_ephemeral.clear()


def supports_ephemeral(bot: Bot) -> bool:
    """Whether this aiogram build can send ephemeral messages at all."""
    return hasattr(bot, "send_message") and _HAS_EPHEMERAL


try:  # pragma: no cover - trivial capability probe
    import inspect as _inspect

    _HAS_EPHEMERAL = "ephemeral_message_parameters" in _inspect.signature(
        Bot.send_message).parameters
except Exception:  # noqa: BLE001
    _HAS_EPHEMERAL = False


async def deliver(bot: Bot, chat_id: int, user_id: int, text: str,
                  markup: InlineKeyboardMarkup | None = None,
                  callback_query_id: str | None = None) -> Route:
    """Send `text` so that only `user_id` can read it.

    Tries the group-local ephemeral message first, then a DM. Never raises:
    a failed secret must not tear down a running round.
    """
    if _HAS_EPHEMERAL and chat_id not in _no_ephemeral:
        try:
            await bot.send_message(
                chat_id, text, reply_markup=markup,
                ephemeral_message_parameters=EphemeralMessageParameters(
                    receiver_user_id=user_id,
                    callback_query_id=callback_query_id))
            return Route.EPHEMERAL
        except Exception as exc:  # noqa: BLE001
            # Old Bot API server, bot is not an admin, or the chat type does
            # not allow it. Stop trying for this chat and fall back to DM.
            _no_ephemeral.add(chat_id)
            log.info("ephemeral unavailable in %s (%s); using DMs",
                     chat_id, type(exc).__name__)

    try:
        await bot.send_message(user_id, text, reply_markup=markup)
        return Route.DM
    except Exception:  # noqa: BLE001
        log.debug("secret delivery failed for %s", user_id, exc_info=True)
        return Route.FAILED


async def deliver_many(bot: Bot, chat_id: int,
                       items: list[tuple[int, str, InlineKeyboardMarkup | None]],
                       ) -> dict[int, Route]:
    """Deliver several secrets concurrently. Returns user_id -> Route.

    Dealing roles one at a time makes a 20-player lobby feel broken, so the
    sends are issued together.
    """
    if not items:
        return {}

    async def one(uid: int, text: str, markup) -> tuple[int, Route]:
        return uid, await deliver(bot, chat_id, uid, text, markup)

    # The first call decides whether ephemeral works; running it alone avoids
    # every player racing to discover the same failure.
    first = await one(*items[0])
    rest = await asyncio.gather(*(one(*i) for i in items[1:]))
    return dict([first, *rest])


def unreachable(routes: dict[int, Route]) -> list[int]:
    return [uid for uid, r in routes.items() if r is Route.FAILED]
