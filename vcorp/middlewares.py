"""Middlewares: chat registration and ban/mute enforcement."""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from .db import db


class ChatTrackMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, dict], Awaitable[Any]],
                       event: TelegramObject, data: dict) -> Any:
        if isinstance(event, Message) and event.chat.type in ("group", "supergroup"):
            await db.execute(
                "INSERT INTO chats(chat_id,title,active,added_at) VALUES(?,?,1,?) "
                "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, active=1",
                (event.chat.id, event.chat.title or "", int(time.time())))
        return await handler(event, data)


class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, dict], Awaitable[Any]],
                       event: TelegramObject, data: dict) -> Any:
        user = getattr(event, "from_user", None)
        if user:
            banned = await db.scalar(
                "SELECT banned FROM players WHERE user_id=?", (user.id,), 0)
            if banned:
                if isinstance(event, CallbackQuery):
                    await event.answer("🚫 دسترسی تو مسدود است.", show_alert=True)
                return None
            until = await db.scalar(
                "SELECT until FROM mutes WHERE user_id=?", (user.id,), 0)
            if until and int(until) > int(time.time()):
                return None
        return await handler(event, data)
