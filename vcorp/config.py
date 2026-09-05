from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_env_file() -> None:
    """Read a local .env into the environment if present.

    Keeps the operator's workflow to "put the token in .env and run", with
    no export dance. Real environment variables always win, so a systemd
    unit or container can still override the file. .env is gitignored.
    """
    path = Path(__file__).resolve().parent.parent / ".env"
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file()


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
    # override to use a local/self-hosted Bot API server (also used by tests)
    api_base: str = field(default_factory=lambda: os.getenv("TELEGRAM_API_BASE", "").strip())

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admins


config = Config()
