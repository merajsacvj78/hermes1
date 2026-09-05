"""Static game content: powers, mutations, items, orgs, missions, characters.

Everything here is original to V-CORP: OUTBREAK. Inspirations are homage only —
no names, art or lore are copied from existing franchises.
"""
from __future__ import annotations

# ── Paths ────────────────────────────────────────────────────────────────
PATHS = {
    "survivor":  ("🧑", "بازمانده",       "انسان معمولی، آزاد در انتخاب مسیر."),
    "ubc":       ("🪖", "مأمور U.B.C",    "سرکوب تهدید زیستی، دفاع بالا."),
    "scientist": ("🧪", "دانشمند",        "تحقیق، درمان، ساخت سرم."),
    "merc":      ("💰", "مزدور",          "قرارداد، پول، شکار جایزه."),
    "vhero":     ("🦸", "ابرقدرت V-CORP", "حامل V-SERUM با قدرت فعال."),
    "double":    ("🕵️", "مأمور دوطرفه",   "دسترسی به اطلاعات دو سازمان."),
    "infected":  ("☣️", "آلوده",          "VX-13 در خون، قدرت با بهای جان."),
    "mutant":    ("🧬", "جهش‌یافته",       "بدن بازنویسی‌شده توسط ویروس."),
    "bioweapon": ("👹", "سلاح زیستی",     "دیگر انسان نیست. هدف متحرکِ همه."),
    "leader":    ("👑", "رهبر سازمان",    "فرمانده منابع و مأموریت‌ها."),
    "traitor":   ("🗡️", "خائن",           "وفاداری‌اش فقط به قیمت بعدی است."),
}

# ── VX-13 infection stages ───────────────────────────────────────────────
STAGES = [
    ("human",     0,   "🧑", "انسان"),
    ("infected",  20,  "☣️", "آلوده"),
    ("mutant",    45,  "🧬", "جهش‌یافته"),
    ("advanced",  70,  "🩸", "جهش پیشرفته"),
    ("bioweapon", 92,  "👹", "Bio-Weapon"),
]

STAGE_BONUS = {
    "human":     {"attack": 0,  "defense": 0,  "stealth": 0,  "risk": 0},
    "infected":  {"attack": 4,  "defense": 2,  "stealth": -1, "risk": 5},
    "mutant":    {"attack": 10, "defense": 6,  "stealth": -3, "risk": 12},
    "advanced":  {"attack": 20, "defense": 12, "stealth": -6, "risk": 22},
    "bioweapon": {"attack": 38, "defense": 22, "stealth": -12, "risk": 35},
}


def stage_for(infection: int) -> tuple[str, str, str]:
    cur = STAGES[0]
    for st in STAGES:
        if infection >= st[1]:
            cur = st
    return cur[0], cur[2], cur[3]


# ── V-SERUM powers ───────────────────────────────────────────────────────
# power_type: offense | control | stealth | support | utility
POWERS: list[dict] = [
    dict(code="kinetic_lash", name="شلاق جنبشی", icon="🌀", power_type="offense",
         description="انرژی جنبشی متراکم را در یک قوس آزاد می‌کند.",
         cooldown=900, risk=12, magnitude=34, counter="سپر ثقلی / دفاع بالای ۲۵"),
    dict(code="hemo_drain", name="زهکش خونی", icon="🩸", power_type="offense",
         description="خون هدف را می‌کشد و بخشی را به HP خودت تبدیل می‌کند.",
         cooldown=1200, risk=20, magnitude=26, counter="اهداف Bio-Weapon خون سالم ندارند"),
    dict(code="static_veil", name="پرده ایستا", icon="🫥", power_type="stealth",
         description="۳۰ دقیقه مخفی‌سازی آلودگی و مصونیت از ردیابی.",
         cooldown=2700, risk=8, magnitude=30, counter="اسکن U.B.C"),
    dict(code="mind_thread", name="نخ ذهنی", icon="🧠", power_type="control",
         description="هدف را وادار به فاش‌کردن یک راز (Evidence) می‌کند.",
         cooldown=3600, risk=25, magnitude=1, counter="Intellect بالای ۳۰"),
    dict(code="carapace", name="زره کیتینی", icon="🛡️", power_type="support",
         description="دفاعت را تا پایان نبرد بعدی دو برابر می‌کند.",
         cooldown=1800, risk=10, magnitude=100, counter="اسید / آتش"),
    dict(code="viral_burst", name="انفجار ویروسی", icon="☣️", power_type="offense",
         description="موج VX-13؛ به هدف آسیب می‌زند و آلوده‌اش می‌کند.",
         cooldown=2400, risk=35, magnitude=30, counter="واکسن پایه / پادتن"),
    dict(code="phase_step", name="گام فاز", icon="💠", power_type="stealth",
         description="فرار تضمینی از یک نبرد یا کمین.",
         cooldown=1500, risk=15, magnitude=100, counter="میدان مهارکننده"),
    dict(code="overclock", name="اورکلاک عصبی", icon="⚡", power_type="support",
         description="Attack +۵۰٪ برای ۳ اقدام، اما ۱۰ HP می‌سوزاند.",
         cooldown=1800, risk=22, magnitude=50, counter="خستگی، انرژی زیر ۲۰"),
    dict(code="pathogen_read", name="خوانش بیماری‌زا", icon="🔬", power_type="utility",
         description="آلودگی واقعی و مسیر پنهان یک بازیکن را آشکار می‌کند.",
         cooldown=1200, risk=5, magnitude=1, counter="پرده ایستا"),
    dict(code="dead_switch", name="کلید مرده", icon="💣", power_type="control",
         description="اگر در ۱ ساعت آینده کشته شوی، قاتلت نصف پولش را می‌بازد.",
         cooldown=5400, risk=18, magnitude=50, counter="ندارد — فقط بازدارنده است"),
]

# ── Mutation tree ────────────────────────────────────────────────────────
# node: (icon, name, requires, min_infection, effect dict, description)
MUTATIONS: dict[str, dict] = {
    "claw":     dict(icon="🦴", name="پنجه استخوانی", req=None, inf=20,
                     effect={"attack": 6}, desc="ساعد به تیغه تبدیل می‌شود."),
    "hide":     dict(icon="🧱", name="پوست ضخیم", req=None, inf=20,
                     effect={"defense": 6}, desc="لایه‌های کراتینی زیرپوستی."),
    "nerve":    dict(icon="⚡", name="شبکه عصبی سریع", req=None, inf=25,
                     effect={"stealth": 5}, desc="زمان واکنش نیمه‌ثانیه‌ای."),
    "ripper":   dict(icon="🗡️", name="دریدن", req="claw", inf=45,
                     effect={"attack": 12}, desc="ضربه‌های زنجیره‌ای."),
    "regen":    dict(icon="♻️", name="بازسازی بافت", req="hide", inf=45,
                     effect={"max_hp": 25}, desc="زخم‌ها خودشان بسته می‌شوند."),
    "mimic":    dict(icon="🫥", name="هم‌رنگی", req="nerve", inf=45,
                     effect={"stealth": 10}, desc="پوست الگوی محیط را می‌گیرد."),
    "hive":     dict(icon="🧠", name="ذهن کندویی", req="mimic", inf=70,
                     effect={"intellect": 12}, desc="پردازش موازی اطلاعات."),
    "acid":     dict(icon="🧪", name="غدد اسیدی", req="ripper", inf=70,
                     effect={"attack": 16}, desc="بافت و فلز را حل می‌کند."),
    "titan":    dict(icon="🦾", name="اسکلت تیتان", req="regen", inf=70,
                     effect={"max_hp": 40, "defense": 10}, desc="استخوان‌های بازآرایی‌شده."),
    "apex":     dict(icon="👹", name="فرم اوج", req="acid", inf=92,
                     effect={"attack": 25, "defense": 15, "max_hp": 50},
                     desc="پایان مسیر VX-13. راه بازگشتی نیست."),
}

# ── Items ────────────────────────────────────────────────────────────────
ITEMS: dict[str, dict] = {
    "medkit":     dict(icon="🩹", name="کیت درمان", price=350, legal=True,
                       desc="۴۰ HP بازیابی."),
    "antiviral":  dict(icon="💊", name="پادتن پایه", price=900, legal=True,
                       desc="۱۰ واحد آلودگی کم می‌کند."),
    "suppressor": dict(icon="🫥", name="مهارکننده", price=1400, legal=True,
                       desc="۶ ساعت آلودگی را از اسکن پنهان می‌کند."),
    "ammo":       dict(icon="🔫", name="مهمات سنگین", price=500, legal=True,
                       desc="+۱۲ Attack در نبرد بعدی."),
    "armor":      dict(icon="🦺", name="جلیقه تاکتیکی", price=1200, legal=True,
                       desc="+۱۰ Defense دائمی (یک‌بار مصرف)."),
    "vsample":    dict(icon="🧫", name="نمونه VX-13", price=2500, legal=False,
                       desc="ماده خام تحقیق و ساخت سرم."),
    "vserum":     dict(icon="🧬", name="V-SERUM", price=6000, legal=False,
                       desc="یک قدرت تصادفی می‌دهد؛ ریسک آلودگی دارد."),
    "cure_proto": dict(icon="🔬", name="نمونه درمان", price=9000, legal=False,
                       desc="آلودگی را ۴۰ واحد پایین می‌آورد."),
    "tracker":    dict(icon="📡", name="ردیاب", price=800, legal=False,
                       desc="مکان و وضعیت یک بازیکن را لو می‌دهد."),
    "forged_id":  dict(icon="🪪", name="هویت جعلی", price=2000, legal=False,
                       desc="Heat را صفر می‌کند."),
}

BLACK_MARKET = ["vsample", "vserum", "cure_proto", "tracker", "forged_id"]

# ── Organizations ────────────────────────────────────────────────────────
SYSTEM_ORGS = [
    dict(code="vcorp", name="V-CORP", icon="🏢",
         desc="شرکت مهندسی ابرقدرت‌ها. سود بالاتر از اخلاق."),
    dict(code="ubc", name="U.B.C.", icon="🪖",
         desc="اداره مهار زیستی. قانون را با گلوله می‌نویسد."),
    dict(code="umbra", name="UMBRA", icon="🕷️",
         desc="سازمانی که رسماً وجود ندارد."),
]

ORG_RANKS = ["recruit", "operative", "handler", "director", "leader"]

# ── Missions ─────────────────────────────────────────────────────────────
BASE_MISSIONS = [
    dict(code="quarantine", title="🚧 پاکسازی قرنطینه", org="ubc", difficulty=3,
         reward=1200, infection=6, rep=6,
         description="بلوک D را از آلوده‌ها خالی کن."),
    dict(code="sample_run", title="🧫 سرقت نمونه", org="umbra", difficulty=5,
         reward=2600, infection=10, rep=8,
         description="یک نمونه VX-13 از سردخانه V-CORP بیرون بکش."),
    dict(code="lab_trial", title="🧪 آزمایش سرم", org="vcorp", difficulty=4,
         reward=1800, infection=14, rep=7,
         description="روی خودت یا داوطلب، دوز جدید را تست کن."),
    dict(code="escort", title="🚐 اسکورت شاهد", org="any", difficulty=3,
         reward=1100, infection=2, rep=4,
         description="شاهدی را از منطقه سرخ خارج کن."),
    dict(code="blackout", title="🔌 خاموشی", org="umbra", difficulty=6,
         reward=3400, infection=4, rep=10,
         description="برق مرکز داده U.B.C را قطع کن."),
    dict(code="hunt_bio", title="👹 شکار سلاح زیستی", org="ubc", difficulty=7,
         reward=4200, infection=18, rep=12,
         description="موجودی که از سکتور ۹ فرار کرده را متوقف کن."),
    dict(code="cure_research", title="🔬 پژوهش درمان", org="any", difficulty=5,
         reward=2000, infection=-8, rep=9,
         description="داده‌های پادتن را تحلیل کن."),
    dict(code="extort", title="💼 اخاذی شرکتی", org="any", difficulty=4,
         reward=2200, infection=0, rep=-4,
         description="از یک مدیر V-CORP باج بگیر."),
]

# ── Signature characters (original) ──────────────────────────────────────
LEGENDS = [
    dict(code="wexler", icon="🕶️", name="آدریان وکسلر",
         title="مدیر سابق بخش تطبیق V-CORP",
         desc="اولین کسی که VX-13 را کنترل کرد بدون اینکه انسان بماند. "
              "سرد، دقیق، و مطمئن که تکامل یک تصمیم مدیریتی است.",
         power="phase_step", bounty=250000),
    dict(code="mother", icon="🕷️", name="مادرِ سکتور ۹",
         title="کندوی زنده UMBRA",
         desc="یک ذهن، ده‌ها بدن. با هرکسی که بکشد بزرگ‌تر می‌شود.",
         power="mind_thread", bounty=400000),
    dict(code="ronan", icon="🪖", name="سرگرد رونان کالد",
         title="فرمانده تیم مهار U.B.C",
         desc="هفت شهر را سوزاند تا هشتمی زنده بماند. پشیمان نیست.",
         power="carapace", bounty=180000),
    dict(code="halcyon", icon="🦸", name="هَلسیون",
         title="محصول پرچمدار V-CORP",
         desc="چهره تبلیغاتی شرکت. هر لبخندش قراردادی است که کسی نخوانده.",
         power="kinetic_lash", bounty=320000),
]

EVENT_TYPES = {
    "outbreak":   ("☣️", "شیوع ویروس", "VX-13 در {zone} منتشر شد."),
    "escape":     ("🚨", "فرار Bio-Weapon", "یک سلاح زیستی از {zone} گریخت."),
    "theft":      ("🧪", "سرقت نمونه", "نمونه‌ای از آزمایشگاه {zone} ناپدید شد."),
    "revolt":     ("🦸", "شورش ابرقدرت‌ها", "حاملان سرم علیه V-CORP بلند شدند."),
    "collapse":   ("🏢", "سقوط V-CORP", "سهام V-CORP فرو ریخت. منابع بلوکه شد."),
    "globalmut":  ("🩸", "جهش جهانی", "موج جهش همه آلوده‌ها را پیش برد."),
    "cure":       ("🔬", "کشف درمان", "پادتن پایدار ساخته شد. آلودگی کاهش یافت."),
    "orgwar":     ("⚔️", "جنگ سازمان‌ها", "{a} به {b} اعلام جنگ داد."),
}

ZONES = ["سکتور ۹", "بندر شرقی", "بلوک D", "مرکز داده آرک",
         "بیمارستان مرکزی", "معدن متروک", "برج V-CORP", "حومه شمالی"]
