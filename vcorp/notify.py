"""Smart notifications: private DMs for things a player must not miss.

Rules (deliberately conservative — no spam):
  • only high-signal events (contract on your head, betrayal, death, boss loot)
  • silently skipped if the player never opened the bot in private
  • rate-limited per user per kind
"""
from __future__ import annotations

import logging

from aiogram import Bot

from .db import db
from .game import engine as E
from .ui import card

log = logging.getLogger("vcorp.notify")

RATE_LIMIT = {
    "hunted": 600,
    "death": 0,
    "betrayed": 300,
    "loot": 0,
    "stage": 900,
    "org": 300,
}


async def dm(bot: Bot, user_id: int, kind: str, title: str,
             lines: list[str], footer: str | None = None,
             silent: bool = False) -> bool:
    """Send a private notification. Returns False if blocked/unreachable."""
    cd = RATE_LIMIT.get(kind, 300)
    if cd and await E.cooldown_left(user_id, f"nt:{kind}"):
        return False
    try:
        await bot.send_message(user_id, card(title, lines, footer),
                               disable_notification=silent)
        if cd:
            await E.set_cooldown(user_id, f"nt:{kind}", cd)
        return True
    except Exception:  # noqa: BLE001
        # user never started the bot privately, or blocked it — never fatal
        log.debug("dm to %s failed", user_id, exc_info=True)
        return False


async def hunted(bot: Bot, target_id: int, reward: int) -> None:
    """The target learns there is a price on their head — but NOT by whom."""
    await dm(bot, target_id, "hunted", "🎯 <b>هشدار امنیتی</b>", [
        "منبعی ناشناس به تو خبر داد:",
        f"<b>قراردادی روی سر تو گذاشته شده.</b>",
        f"💰 مبلغ تقریبی: <b>${reward:,}</b>",
        "",
        "سفارش‌دهنده معلوم نیست. مجری هم می‌تواند هرکسی باشد.",
    ], "پنهان شو، قیمت را بالا بخر، یا اول تو بزن.")


async def killed(bot: Bot, victim_id: int, killer_name: str, legacy: int,
                 generation: int) -> None:
    await dm(bot, victim_id, "death", "💀 <b>پایان یک نسل</b>", [
        f"<b>{killer_name}</b> تو را از پا درآورد.",
        "",
        f"🏅 Legacy منتقل‌شده: <b>{legacy}</b>",
        f"🧬 نسل جدید: <b>{generation}</b>",
        "جهش‌ها و قدرت‌هایت از بین رفتند؛ بدنت قوی‌تر برگشت.",
    ], "انتقام یک تصمیم است، نه یک وظیفه.")


async def betrayed(bot: Bot, member_id: int, traitor_name: str, org_name: str) -> None:
    await dm(bot, member_id, "betrayed", "🗡️ <b>نشت داخلی</b>", [
        f"<b>{traitor_name}</b> اسناد <b>{org_name}</b> را فروخت.",
        "خزانه و قدرت سازمان کاهش یافت.",
    ], "او دیگر عضو نیست. اسناد اما بیرون است.")


async def betrayed_all(bot: Bot, org_id: int, traitor_name: str, org_name: str) -> None:
    """Every remaining member of the organization is warned."""
    rows = await db.fetchall("SELECT user_id FROM players WHERE org_id=?", (org_id,))
    for r in rows:
        await betrayed(bot, r["user_id"], traitor_name, org_name)


async def loot(bot: Bot, user_id: int, boss_name: str, damage: int, share: int) -> None:
    await dm(bot, user_id, "loot", "👹 <b>سهم غنیمت</b>", [
        f"<b>{boss_name}</b> از پا درآمد.",
        f"⚔️ آسیب تو: <b>{damage}</b>",
        f"💵 سهم: <b>${share:,}</b>",
    ], silent=True)


async def stage_up(bot: Bot, user_id: int, stage_label: str, infection: int) -> None:
    await dm(bot, user_id, "stage", "🧬 <b>پیشروی VX-13</b>", [
        f"بدنت وارد مرحله <b>{stage_label}</b> شد.",
        f"☣️ آلودگی: <b>{infection}٪</b>",
        "",
        "قدرت بیشتر. کنترل کمتر. هر دو واقعی‌اند.",
    ], "پنهان کن یا درمان کن — انتخاب با توست.")


async def org_event(bot: Bot, org_id: int, title: str, lines: list[str]) -> None:
    """Notify every member of an organization."""
    rows = await db.fetchall("SELECT user_id FROM players WHERE org_id=?", (org_id,))
    for r in rows:
        await dm(bot, r["user_id"], "org", title, lines)
