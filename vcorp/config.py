from __future__ import annotations

import os
from dataclasses import dataclass, field


def _ids(raw: str) -> set[int]:
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


@dataclass(slots=True)
class Config:
    token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", "").strip())
    admins: set[int] = field(default_factory=lambda: _ids(os.getenv("ADMIN_IDS", "")))
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "vcorp.sqlite3"))
    bot_username: str = field(default_factory=lambda: os.getenv("BOT_USERNAME", "").lstrip("@"))
    # world tick (seconds) for the living-world engine
    tick_seconds: int = field(default_factory=lambda: int(os.getenv("TICK_SECONDS", "300")))

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admins


config = Config()
