"""In-game tutorial: short, paged, and only teaches things that matter."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..game import engine as E
from ..ui import card, kb

router = Router(name="guide")

PAGES: list[tuple[str, str, list[str], str]] = [
    ("start", "☣️ <b>۱/۶ — تو کی هستی</b>", [
        "یک انسان معمولی در شهری که ویروس <b>VX-13</b> آن را بلعیده.",
        "",
        "هیچ کلاسی انتخاب نمی‌کنی. مسیرت را <b>کارهایت</b> می‌سازند:",
        "🧪 آزمایش کنی → دانشمند · 💰 قرارداد بگیری → مزدور",
        "☣️ آلوده شوی → جهش‌یافته · 🗡️ لو بدهی → خائن",
        "",
        "شروع: <code>/start</code> بعد <code>/me</code>",
    ], "هیچ مسیری قفل نیست. هیچ‌کدام هم برگشت‌پذیر نیست."),

    ("loop", "🔦 <b>۲/۶ — حلقه بازی</b>", [
        "<code>/scavenge</code> — پول، آیتم و مدرک پیدا کن (Cooldown ۴ دقیقه)",
        "<code>/mission</code> — کار واقعی با ریسک و پاداش بزرگ‌تر",
        "<code>/heal</code> — HP و انرژی برگردان",
        "",
        "هر اقدام <b>انرژی</b> می‌خورد و <b>Cooldown</b> دارد.",
        "انرژی خودش پر می‌شود — بازی برای مارتن‌دویدن ساخته شده، نه اسپم.",
    ], "پول بی‌مصرف است اگر نخری. /shop"),

    ("vx13", "🧬 <b>۳/۶ — ویروس</b>", [
        "<code>انسان ← آلوده ← جهش‌یافته ← جهش پیشرفته ← Bio-Weapon</code>",
        "",
        "آلودگی <b>هم قدرت است هم شمارش معکوس</b>:",
        "↗️ هر مرحله Attack و Defense بیشتر می‌دهد",
        "↘️ و تو را به از دست دادن کامل شخصیت نزدیک‌تر می‌کند",
        "",
        "🧬 <code>/mutate</code> جهش شاخه‌ای (برگشت‌ناپذیر)",
        "💊 <code>/cure</code> عقب بکش · 🫥 <code>/hide</code> از اسکن پنهان شو",
    ], "👹 Bio-Weapon شدی؟ راه برگشتی نیست."),

    ("power", "🦸 <b>۴/۶ — قدرت</b>", [
        "💉 <code>/inject</code> با V-SERUM یک قدرت واقعی می‌گیری.",
        "",
        "هیچ قدرتی فقط «+آسیب» نیست. هرکدام:",
        "⏱ Cooldown · ⚠️ ریسک عوارض · 🛡 یک Counter مشخص دارد",
        "",
        "مثلاً 🧠 نخ ذهنی مدرک حریف را <b>می‌دزدد</b>،",
        "💠 گام فاز از نبرد <b>فرار</b> می‌دهد.",
        "",
        "<code>/power</code> ببین · <code>/use کد</code> (ریپلای روی هدف)",
    ], "قدرت رایگان نیست — سرم آلودگی می‌آورد."),

    ("pvp", "⚔️ <b>۵/۶ — گودال (PvP)</b>", [
        "روی حریف ریپلای کن: <code>/duel</code> یا <code>/duel 5000</code>",
        "",
        "هر دو <b>همزمان و مخفی</b> حرکت انتخاب می‌کنید:",
        "⚔️ ضربه ← 🛡️ گارد ← 🩸 توحش ← ⚔️ ضربه",
        "👁️ خوانش ضربه و توحش را می‌خواند · 🛡️ گارد حدسِ خوانش را تنبیه می‌کند",
        "",
        "⚡ آدرنالین نمی‌گذارد یک حرکت را تکرار کنی.",
        "📉 تکرار = لو رفتن الگو = ضربه ضعیف‌تر.",
        "",
        "🩸 توحش قوی‌ترین است ولی <b>آلودگی می‌آورد</b>.",
    ], "در گودال کسی نمی‌میرد. برای کشتن /attack هست."),

    ("trust", "🗡️ <b>۶/۶ — به هیچ‌کس اعتماد نکن</b>", [
        "🎯 <code>/contract نام مبلغ</code> — قرارداد <b>مخفی</b> روی سر یک بازیکن.",
        "هدف فقط می‌فهمد قیمتی روی سرش هست، نه اینکه <b>کی</b> گذاشته.",
        "",
        "🗂️ مدارک قابل دزدیدن و فروختن‌اند.",
        "🏢 عضو سازمان شو، بالا برو، بعد <code>/betray</code> کن.",
        "🚨 <code>/wanted</code> ببین چه کسی قیمت دارد.",
        "",
        "☠️ مرگ پایان نیست: بخشی از دستاوردت به‌عنوان <b>Legacy</b>",
        "به نسل بعدی‌ات می‌رسد و قوی‌تر برمی‌گردی.",
    ], "حالا برو. کسی برایت داستان نمی‌نویسد."),
]

INDEX = {p[0]: i for i, p in enumerate(PAGES)}


def render(i: int) -> tuple[str, object]:
    i = max(0, min(len(PAGES) - 1, i))
    _, title, lines, foot = PAGES[i]
    rows = []
    nav = []
    if i > 0:
        nav.append(("◀️ قبلی", f"gd:{i-1}"))
    if i < len(PAGES) - 1:
        nav.append(("بعدی ▶️", f"gd:{i+1}"))
    if nav:
        rows.append(nav)
    rows.append([("🎯 مأموریت", "ui:missions"), ("🧬 پروفایل", "ui:me")])
    return card(title, lines, foot), kb(rows)


@router.message(Command("guide", "tutorial", "learn"))
async def guide(message: Message) -> None:
    await E.ensure_player(message.from_user.id, message.from_user.full_name)
    text, markup = render(0)
    await message.reply(text, reply_markup=markup)


@router.callback_query(F.data.startswith("gd:"))
async def page(cq: CallbackQuery) -> None:
    try:
        i = int(cq.data.split(":", 1)[1])
    except ValueError:
        return await cq.answer()
    text, markup = render(i)
    try:
        await cq.message.edit_text(text, reply_markup=markup)
    except Exception:  # noqa: BLE001
        pass
    await cq.answer()
