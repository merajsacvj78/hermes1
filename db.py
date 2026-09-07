"""🏛️ جنگ جهانی — دیتابیس (SQLite WAL + thread-local)."""
import json
import contextlib
import sqlite3
import time
from datetime import datetime, timezone, timedelta
import contextvars
import os
import config

TZ = timezone(timedelta(hours=3, minutes=30), "Tehran")
GAME = contextvars.ContextVar("game", default=None)   # شناسه‌ی گروهِ جاری
GAMES_DIR = "games"
_conns = {}                                            # مسیر → اتصال

TZ_OFFSET = 3 * 3600 + 1800          # تهران UTC+3:30


def now() -> int:
    return int(time.time())


def day_index() -> int:
    """شماره‌ی روز تقویمی تهران — مرز دقیق نیمه‌شب محلی."""
    return (now() + TZ_OFFSET) // 86400


def game_path(chat_id) -> str:
    return f"{GAMES_DIR}/{chat_id}.db"


def list_games():
    """همه‌ی دنیاهای موجود (شناسه‌ی گروه‌ها)."""
    if not os.path.isdir(GAMES_DIR):
        os.makedirs(GAMES_DIR, exist_ok=True)
    games = set(int(f[:-3]) for f in os.listdir(GAMES_DIR) if f.endswith(".db"))
    if getattr(config, "MAIN_GROUP_ID", None):
        games.add(config.MAIN_GROUP_ID)
    return sorted(games)


def con():
    g = GAME.get()
    p = game_path(g) if g is not None else config.DB_PATH
    c = _conns.get(p)
    if c is None:
        if g is not None:
            os.makedirs(GAMES_DIR, exist_ok=True)
        c = sqlite3.connect(p, 30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=8000")
        c.execute("PRAGMA temp_store=MEMORY")
        _open_db(c)
        _conns[p] = c
    return c


def _open_db(c):
    """اسکیما + مهاجرت + ایندکس — روی هر دیتابیس."""
    c.executescript(SCHEMA)
    with contextlib.suppress(Exception):
        c.execute("ALTER TABLE users ADD COLUMN username TEXT")
    with contextlib.suppress(Exception):
        c.execute("ALTER TABLE users ADD COLUMN operation_id INTEGER DEFAULT NULL")
    c.executescript("""
CREATE INDEX IF NOT EXISTS ix_users_country ON users(country);
CREATE INDEX IF NOT EXISTS ix_users_active ON users(last_active);
CREATE INDEX IF NOT EXISTS ix_users_level ON users(level DESC);
CREATE INDEX IF NOT EXISTS ix_wars_status ON wars(status);
CREATE INDEX IF NOT EXISTS ix_inv_uid ON inventory(uid);
CREATE INDEX IF NOT EXISTS ix_bases_cid ON bases(cid);
CREATE INDEX IF NOT EXISTS ix_un_status ON un_resolutions(status);
""")
    c.commit()


def con_for(chat_id):
    """اتصال به دنیای مشخص — برای حلقه‌ها و ذخیره‌سازی."""
    os.makedirs(GAMES_DIR, exist_ok=True)
    p = game_path(chat_id)
    c = _conns.get(p)
    if c is None:
        c = sqlite3.connect(p, 30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=8000")
        c.execute("PRAGMA temp_store=MEMORY")
        _open_db(c)
        _conns[p] = c
    return c


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    uid INTEGER PRIMARY KEY,
    name TEXT, country TEXT, branch TEXT,
    rank INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
    money INTEGER DEFAULT 30000,
    hp INTEGER DEFAULT 100, max_hp INTEGER DEFAULT 100,
    kills INTEGER DEFAULT 0, spy_ops INTEGER DEFAULT 0,
    party_id INTEGER, is_leader INTEGER DEFAULT 0,
    joined INTEGER, last_active INTEGER, chat_id INTEGER, username TEXT,
    operation_id INTEGER DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS items (
    iid TEXT PRIMARY KEY, name TEXT, emoji TEXT, country TEXT,
    atk INTEGER, guard INTEGER, price INTEGER,
    max_dur INTEGER DEFAULT 100, img TEXT
);
CREATE TABLE IF NOT EXISTS inventory (
    uid INTEGER, iid TEXT, qty INTEGER DEFAULT 1, dur INTEGER,
    PRIMARY KEY(uid, iid)
);
CREATE TABLE IF NOT EXISTS parties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, country TEXT, ideology TEXT, leader_uid INTEGER,
    members INTEGER DEFAULT 1, power INTEGER DEFAULT 10,
    rebel INTEGER DEFAULT 0, created INTEGER
);
CREATE TABLE IF NOT EXISTS statements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    party_id INTEGER, uid INTEGER, title TEXT, body TEXT, ts INTEGER
);
CREATE TABLE IF NOT EXISTS wars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    a TEXT, b TEXT, status TEXT DEFAULT 'active',
    score_a INTEGER DEFAULT 0, score_b INTEGER DEFAULT 0,
    started INTEGER, ends INTEGER, winner TEXT
);
CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, cid TEXT, target_cid TEXT, stage INTEGER DEFAULT 1,
    power_boost INTEGER DEFAULT 25, strikes_done INTEGER DEFAULT 0,
    created INTEGER, status TEXT DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS bases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cid TEXT, city TEXT, base_type TEXT, level INTEGER DEFAULT 1,
    hp INTEGER DEFAULT 100, created INTEGER,
    UNIQUE(cid, city, base_type)
);
CREATE TABLE IF NOT EXISTS un_resolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT, res_type TEXT, target_cid TEXT,
    proposer_uid INTEGER, proposer_cid TEXT,
    votes_yes INTEGER DEFAULT 0, votes_no INTEGER DEFAULT 0, votes_veto INTEGER DEFAULT 0,
    voters_json TEXT DEFAULT '{}', status TEXT DEFAULT 'voting',
    created INTEGER, ends INTEGER
);
CREATE TABLE IF NOT EXISTS trade_agreements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    a TEXT, b TEXT, created INTEGER, UNIQUE(a, b)
);
CREATE TABLE IF NOT EXISTS straits (
    strait_id TEXT PRIMARY KEY,
    name TEXT, owner_cids TEXT, is_closed INTEGER DEFAULT 0,
    toll_amount INTEGER DEFAULT 200, pot INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS spyops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER, target TEXT, success INTEGER, info TEXT, ts INTEGER
);
CREATE TABLE IF NOT EXISTS alliances (
    a TEXT, b TEXT, created INTEGER
);
CREATE TABLE IF NOT EXISTS defense (
    cid TEXT, layer TEXT, level INTEGER DEFAULT 30, hp INTEGER DEFAULT 100,
    PRIMARY KEY(cid, layer)
);
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT, ts INTEGER
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT, text TEXT, ts INTEGER
);
"""


def ex(sql, args=()):
    con().execute(sql, args)
    con().commit()


def one(sql, args=()):
    return con().execute(sql, args).fetchone()


def q(sql, args=()):
    return con().execute(sql, args).fetchall()


def kv_set(k, v):
    ex("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


def kv_del(k):
    ex("DELETE FROM kv WHERE k=?", (k,))


def kv_get(k, d=None):
    r = one("SELECT v FROM kv WHERE k=?", (k,))
    return r["v"] if r else d


def jload(s, d=None):
    if not s:
        return d
    try:
        return json.loads(s)
    except Exception:
        return d


def log(level, text):
    try:
        ex("INSERT INTO logs(level,text,ts) VALUES(?,?,?)", (level, text[:500], now()))
    except Exception:
        pass


def tehran_date(ts: int) -> str:
    return datetime.fromtimestamp(ts, TZ).strftime("%Y-%m-%d %H:%M")


def seed_special_users():
    """اعطای هدایای ویژه و تنظیم لیدرهای اصلی در دیتابیس جاری:
    ۱. مالک بازی و رهبر ایران (8694290031): ۱٬۰۹۰٬۰۰۰ دلار + ۱۰ ست تجهیزات و پدافند باور
    ۲. رهبر آمریکا (8785446505): ۸۰٬۰۰۰ دلار + ۵ ست تجهیزات و پدافند پاتریوت
    ۳. تمام رزمندگان و بازیکنان: حداقل ۳۰٬۰۰۰ دلار + تسلیحات سازمانی کامل
    """
    import countries
    from game import defense
    iran_uid = config.OWNER_ID  # 8694290031
    usa_uid = getattr(config, "USA_LEADER_ID", 8785446505)

    # 1. تنظیم رهبر ایران
    ex("""
    INSERT INTO users(uid, name, country, branch, rank, money, is_leader, joined, last_active)
    VALUES(?, 'فرمانده کل ایران (مالک)', 'ir', 'ارتش جمهوری اسلامی', 10, 1090000, 1, ?, ?)
    ON CONFLICT(uid) DO UPDATE SET
        country='ir',
        money=MAX(users.money, 1090000),
        is_leader=1,
        branch=COALESCE(users.branch, 'ارتش جمهوری اسلامی'),
        last_active=?
    """, (iran_uid, now(), now(), now()))

    # ۱۰ تا تجهیزات برتر ایران
    iran_top_items = ["sejjil", "shahed", "emad", "khorramshahr", "bavar", "dhow"]
    for iid in iran_top_items:
        ex("""
        INSERT INTO inventory(uid, iid, qty, dur)
        VALUES(?, ?, 10, 100)
        ON CONFLICT(uid, iid) DO UPDATE SET qty=MAX(inventory.qty, 10), dur=100
        """, (iran_uid, iid))

    # سپر پدافندی ماکسیمم ایران
    from game import defense
    defense.ensure("ir")
    for layer in defense.LAYERS:
        ex("UPDATE defense SET level=95, hp=100 WHERE cid='ir' AND layer=?", (layer,))

    # 2. تنظیم رهبر آمریکا
    ex("""
    INSERT INTO users(uid, name, country, branch, rank, money, is_leader, joined, last_active)
    VALUES(?, 'Commander in Chief (USA)', 'us', 'ارتش آمریکا', 8, 80000, 1, ?, ?)
    ON CONFLICT(uid) DO UPDATE SET
        country='us',
        money=MAX(users.money, 80000),
        is_leader=1,
        branch=COALESCE(users.branch, 'ارتش آمریکا'),
        last_active=?
    """, (usa_uid, now(), now(), now()))

    # ۵ تا تجهیزات برتر آمریکا
    usa_top_items = ["f35", "abrams", "carrier", "humvee", "burke", "f22"]
    for iid in usa_top_items:
        ex("""
        INSERT INTO inventory(uid, iid, qty, dur)
        VALUES(?, ?, 5, 100)
        ON CONFLICT(uid, iid) DO UPDATE SET qty=MAX(inventory.qty, 5), dur=100
        """, (usa_uid, iid))

    # سپر پدافندی ماکسیمم آمریکا
    defense.ensure("us")
    for layer in defense.LAYERS:
        ex("UPDATE defense SET level=95, hp=100 WHERE cid='us' AND layer=?", (layer,))

    # 3. تنظیم موجودی و تسلیحات سازمانی برای تمامی رزمندگان و بازیکنان دیگر
    ex("UPDATE users SET money=30000 WHERE money < 30000")
    all_users = q("SELECT uid, country FROM users WHERE country IS NOT NULL AND uid NOT IN (?, ?)", (iran_uid, usa_uid))
    for u in all_users:
        defense.ensure(u["country"])
        c_items = countries.COUNTRIES.get(u["country"], {}).get("items", [])
        for iid in c_items:
            ex("""
            INSERT INTO inventory(uid, iid, qty, dur)
            VALUES(?, ?, 2, 100)
            ON CONFLICT(uid, iid) DO UPDATE SET qty=MAX(inventory.qty, 2), dur=100
            """, (u["uid"], iid))


def reset_and_clean_all():
    """ریست کامل بازی‌ها برای شروع از اول با هدایا."""
    ex("DELETE FROM wars")
    ex("DELETE FROM operations")
    ex("DELETE FROM un_resolutions")
    ex("DELETE FROM statements")
    ex("DELETE FROM alliances")
    ex("DELETE FROM trade_agreements")
    # ریست بازیکنان عادی (به جز دو لیدر اصلی)
    ex("""
    UPDATE users SET country=NULL, branch=NULL, is_leader=0, operation_id=NULL, money=30000
    WHERE uid NOT IN (?, ?)
    """, (config.OWNER_ID, getattr(config, "USA_LEADER_ID", 8785446505)))
    seed_special_users()


def init(path: str = None):
    if path:
        for p, c in list(_conns.items()):
            with contextlib.suppress(Exception):
                c.close()
        _conns.clear()
        config.DB_PATH = path
    else:
        for g in list_games():
            with contextlib.suppress(Exception):
                _open_db(con_for(g))
    _open_db(con())
    seed_special_users()
