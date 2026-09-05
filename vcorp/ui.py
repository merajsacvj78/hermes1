"""Presentation helpers: embed-like cards, bars, keyboards."""
from __future__ import annotations

from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

LINE = "─" * 18


def bar(value: int, maximum: int, width: int = 10, full: str = "█", empty: str = "░") -> str:
    maximum = max(1, maximum)
    filled = max(0, min(width, round(value / maximum * width)))
    return full * filled + empty * (width - filled)


def card(title: str, lines: list[str], footer: str | None = None) -> str:
    body = "\n".join(lines)
    out = f"<b>{title}</b>\n<code>{LINE}</code>\n{body}"
    if footer:
        out += f"\n<code>{LINE}</code>\n<i>{footer}</i>"
    return out


def money(n: int) -> str:
    return f"${n:,}"


def esc(s: str) -> str:
    return escape(str(s), quote=False)


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows
    ])


def builder() -> InlineKeyboardBuilder:
    return InlineKeyboardBuilder()


def mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{esc(name)}</a>'
