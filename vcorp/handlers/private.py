"""Private chat: short guide + add-to-group button only."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import config
from ..game.engine import ensure_player
from ..ui import card

router = Router(name="private")
router.message.filter(F.chat.type == "private")

GUIDE = card(
    "☣️ <b>V-CORP: OUTBREAK</b>",
    [
        "دنیایی که در آن ویروس <b>VX-13</b> مرز انسان و سلاح را پاک کرده است.",
        "",
        "🧑 از یک انسان معمولی شروع می‌کنی.",
        "🧬 آلوده می‌شوی، جهش می‌کنی یا درمان می‌سازی.",
        "🦸 با V-SERUM قدرت می‌گیری — با ریسک و ضعف واقعی.",
        "🏢 وارد V-CORP / U.B.C / UMBRA می‌شوی یا سازمان خودت را می‌سازی.",
        "🎯 قرارداد مخفی می‌بندی، خیانت می‌کنی، اطلاعات می‌فروشی.",
        "",
        "⚔️ <b>کل بازی داخل گروه انجام می‌شود.</b>",
        "ربات را به گروه اضافه کن و <code>/start</code> بزن.",
    ],
    "داخل گروه: /guide آموزش · /help فهرست دستورها",
)


def add_kb() -> InlineKeyboardMarkup:
    uname = config.bot_username or "your_bot"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="➕ مرا به گروه اضافه کنید",
            url=f"https://t.me/{uname}?startgroup=outbreak")],
        [InlineKeyboardButton(text="📜 قوانین بقا", callback_data="pv:rules")],
    ])


@router.message(CommandStart())
@router.message(Command("help"))
async def start(message: Message) -> None:
    u = message.from_user
    await ensure_player(u.id, u.full_name)
    await message.answer(GUIDE, reply_markup=add_kb())


@router.callback_query(F.data == "pv:rules")
async def rules(cq: CallbackQuery) -> None:
    await cq.message.edit_text(
        card("📜 <b>قوانین بقا</b>", [
            "1️⃣ هر اقدام Cooldown و انرژی مصرف می‌کند.",
            "2️⃣ آلودگی هم قدرت است هم شمارش معکوس.",
            "3️⃣ مرگ پایان نیست: <b>Legacy</b> به نسل بعد می‌رسد.",
            "4️⃣ Heat بالا یعنی U.B.C دنبالت است.",
            "5️⃣ هیچ‌کس متحد دائمی نیست — قراردادها مخفی‌اند.",
        ], "برای بازی، ربات را به گروه اضافه کن."),
        reply_markup=add_kb())
    await cq.answer()


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(GUIDE, reply_markup=add_kb())
