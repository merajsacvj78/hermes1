"""Living-world background loop: infection progression, events, decay."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import random

from aiogram import Bot

from .config import config
from .db import db
from .game import engine as E
from .ui import card

log = logging.getLogger("vcorp.tick")


async def tick_once(bot: Bot) -> None:
    # energy & passive regen
    await db.execute("UPDATE players SET energy=MIN(100, energy+10)")
    await db.execute("UPDATE players SET hp=MIN(max_hp, hp+3) WHERE hp>0")
    # heat cools down
    await db.execute("UPDATE players SET heat=MAX(0, heat-1) WHERE heat>0")
    # unhide expired
    rows = await db.fetchall("SELECT user_id FROM players WHERE hidden=1")
    for r in rows:
        if not await E.cooldown_left(r["user_id"], "hidden"):
            await db.execute("UPDATE players SET hidden=0 WHERE user_id=?", (r["user_id"],))

    # infection creeps up with world threat
    threat = int(await db.world_get("threat", 10))
    if threat >= 30:
        await db.execute(
            "UPDATE players SET infection=MIN(100, infection+1) WHERE infection>0")
        for r in await db.fetchall("SELECT user_id, infection FROM players WHERE infection>0"):
            await E.apply_infection(r["user_id"], 0)
    cure = int(await db.world_get("cure_progress", 0))
    if cure >= 100:
        await db.execute("UPDATE players SET infection=MAX(0, infection-15)")
        await db.world_set("cure_progress", 0)
        await db.world_set("threat", max(0, threat - 25))
        await broadcast(bot, card("🔬 <b>درمان منتشر شد</b>", [
            "پادتن پایدار تولید انبوه شد. آلودگی همه ۱۵ واحد کاهش یافت.",
            "اما نمونه‌های VX-13 هنوز جایی هستند...",
        ]))
    # random world event
    if random.randint(1, 100) <= 18:
        from .handlers.world import spawn_event
        chats = await db.fetchall("SELECT chat_id FROM chats WHERE active=1")
        if chats:
            chat = random.choice(chats)["chat_id"]
            e = await spawn_event(bot, chat)
            await broadcast(bot, card(f"{e['icon']} <b>{e['title']}</b>", [
                e["body"], "", "واکنش گروه: <code>/respond</code>"], "رویداد جهانی"))
    else:
        await db.world_set("threat", max(0, threat - 1))


async def broadcast(bot: Bot, text: str) -> None:
    rows = await db.fetchall("SELECT chat_id FROM chats WHERE active=1")
    for r in rows:
        try:
            await bot.send_message(r["chat_id"], text)
        except Exception:  # noqa: BLE001
            await db.execute("UPDATE chats SET active=0 WHERE chat_id=?", (r["chat_id"],))


async def world_loop(bot: Bot) -> None:
    while True:
        try:
            await asyncio.sleep(config.tick_seconds)
            await tick_once(bot)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("world tick failed")


def start(bot: Bot) -> asyncio.Task:
    return asyncio.create_task(world_loop(bot))


async def stop(task: asyncio.Task) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
