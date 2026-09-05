"""Branding and channel posting must be safe, complete and non-fatal."""
from __future__ import annotations

import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vcorp import branding, channel  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Bot:
    """Records identity calls; can be told to fail some of them."""

    def __init__(self, fail: set[str] | None = None):
        self.fail = fail or set()
        self.calls: list[str] = []

    def _maybe(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise RuntimeError(f"{name} rejected")
        return True

    async def set_my_name(self, name=None, **kw):
        return self._maybe("name")

    async def set_my_short_description(self, short_description=None, **kw):
        return self._maybe("short_description")

    async def set_my_description(self, description=None, **kw):
        return self._maybe("description")

    async def set_my_commands(self, commands, scope=None, **kw):
        self.last_commands = commands
        self.last_scope = scope
        return self._maybe("commands:" + type(scope).__name__)

    async def set_chat_menu_button(self, menu_button=None, **kw):
        return self._maybe("menu_button")

    async def set_my_default_administrator_rights(self, rights=None, **kw):
        self.rights = rights
        return self._maybe("admin_rights")


class ChannelBot:
    def __init__(self, ok=True):
        self.ok = ok
        self.posts: list[tuple[str, str]] = []

    async def send_message(self, chat_id, text, **kw):
        if not self.ok:
            raise RuntimeError("chat not found")
        self.posts.append(("text", text))
        return types.SimpleNamespace(message_id=1)

    async def send_photo(self, chat_id, photo, caption=None, **kw):
        if not self.ok:
            raise RuntimeError("chat not found")
        self.posts.append(("photo", caption or ""))
        return types.SimpleNamespace(message_id=2)


async def main() -> None:
    # ── the copy itself must respect Telegram's limits ───────────────────
    assert len(branding.NAME) <= 64
    assert len(branding.SHORT_DESCRIPTION) <= 120, \
        f"short description is {len(branding.SHORT_DESCRIPTION)} chars"
    assert len(branding.DESCRIPTION) <= 512, \
        f"description is {len(branding.DESCRIPTION)} chars"

    for table in (branding.GROUP_COMMANDS, branding.PRIVATE_COMMANDS):
        seen = set()
        for cmd, desc in table:
            assert cmd.islower() and cmd.replace("_", "").isalnum(), \
                f"illegal command name: {cmd}"
            assert 1 <= len(cmd) <= 32, cmd
            assert 1 <= len(desc) <= 256, cmd
            assert cmd not in seen, f"duplicate command: {cmd}"
            seen.add(cmd)

    # private chat is a doorway, not a game surface
    private = {c for c, _ in branding.PRIVATE_COMMANDS}
    assert private == {"start", "help"}, f"private surface too wide: {private}"
    group = {c for c, _ in branding.GROUP_COMMANDS}
    for essential in ("lockdown", "convoy", "duel", "boss", "guide", "modes"):
        assert essential in group, f"{essential} missing from the group menu"

    # every advertised command must actually exist in the code
    import subprocess
    src = subprocess.run(
        ["grep", "-rho", r'Command("[a-z_]*"\|Command("[a-z_]*",',
         os.path.join(ROOT, "vcorp", "handlers")],
        capture_output=True, text=True).stdout
    for cmd in group | private:
        assert f'Command("{cmd}"' in src or f'"{cmd}"' in src, \
            f"/{cmd} is advertised but has no handler"

    # ── a healthy run sets everything ────────────────────────────────────
    bot = Bot()
    done = await branding.apply(bot, set_avatar=False)
    assert all(done.values()), f"something failed on a healthy bot: {done}"
    assert "commands:BotCommandScopeAllGroupChats" in bot.calls
    assert "commands:BotCommandScopeAllPrivateChats" in bot.calls
    # the bot must ask for the rights it actually needs
    assert bot.rights.can_delete_messages and bot.rights.can_manage_chat
    assert not bot.rights.can_promote_members, "must not request promotion"

    # ── partial failure must not stop the rest ───────────────────────────
    bot = Bot(fail={"name", "menu_button"})
    done = await branding.apply(bot, set_avatar=False)
    assert done["name"] is False and done["menu_button"] is False
    assert done["description"] is True and done["group_commands"] is True

    # ── "not modified" counts as success ─────────────────────────────────
    class Unchanged(Bot):
        async def set_my_name(self, name=None, **kw):
            raise RuntimeError("Bad Request: bot name is not modified")

    done = await branding.apply(Unchanged(), set_avatar=False)
    assert done["name"] is True, "an unchanged value is not a failure"

    # ── a totally broken bot must never raise ────────────────────────────
    class Broken:
        def __getattr__(self, _):
            async def boom(*a, **k):
                raise RuntimeError("network down")
            return boom

    done = await branding.apply(Broken(), set_avatar=False)
    assert not any(done.values())

    # ── the avatar referenced by branding exists ─────────────────────────
    assert os.path.exists(branding.AVATAR), "bot avatar is missing"

    # ── channel posting is a no-op until configured ──────────────────────
    channel.CHANNEL = ""
    channel.reset()
    bot = ChannelBot()
    assert not channel.configured()
    assert await channel.boss_defeated(bot, "x", "g", "p", 1, 2) is False
    assert bot.posts == [], "must not post when unconfigured"

    # ── configured: posts, and uses art when present ─────────────────────
    channel.CHANNEL = "@test"
    channel.reset()
    bot = ChannelBot()
    assert await channel.boss_defeated(bot, "👹 آوار", "گروه", "P1", 500,
                                       9000, art="brand/boss_avar.jpg")
    assert bot.posts[0][0] == "photo", "should use the boss portrait"
    assert "آوار" in bot.posts[0][1]

    # a missing art path still posts, as text
    bot = ChannelBot()
    channel.reset()
    assert await channel.boss_defeated(bot, "x", "g", "p", 1, 2,
                                       art="brand/nope.jpg")
    assert bot.posts[0][0] == "text"

    # ── a broken channel disables itself instead of erroring forever ─────
    channel.reset()
    bot = ChannelBot(ok=False)
    assert await channel.round_ended(bot, "convoy", "g", "h", "d") is False
    assert not channel.configured(), "must self-disable after a failure"
    assert await channel.world_event(bot, "t", "b") is False

    channel.CHANNEL = ""
    channel.reset()
    print("✅ branding passed — identity complete, channel safe", flush=True)


if __name__ == "__main__":
    import traceback
    code = 0
    try:
        asyncio.run(main())
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    os._exit(code)
