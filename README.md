# ☣️ V-CORP: OUTBREAK

بازی متنی تلگرامی، گروه‌محور، در دنیایی که ویروس **VX-13** مرز انسان و سلاح را پاک کرده است.
ترکیبی از فضای بقا/بیوهارور و سیاست ابرقدرت‌های شرکتی — با هویت، نام‌ها و داستان کاملاً مستقل.

> Chat خصوصی فقط راهنما + دکمه «➕ مرا به گروه اضافه کنید». کل Gameplay داخل گروه است.

## راه‌اندازی

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env      # BOT_TOKEN و ADMIN_IDS را پر کن
export BOT_TOKEN=...      # یا از .env استفاده کن
export ADMIN_IDS=123456789

.venv/bin/python -m vcorp
```

تست آفلاین موتور بازی (بدون تلگرام):

```bash
.venv/bin/python tests/test_engine.py
```

### systemd (VPS)

```ini
[Unit]
Description=V-CORP OUTBREAK bot
After=network-online.target

[Service]
WorkingDirectory=/opt/hermes1
Environment=BOT_TOKEN=xxx
Environment=ADMIN_IDS=123456789
ExecStart=/opt/hermes1/.venv/bin/python -m vcorp
Restart=always

[Install]
WantedBy=multi-user.target
```

## معماری

```
vcorp/
  __main__.py      bootstrap، Dispatcher، ثبت روترها و دستورهای گروه
  config.py        پیکربندی از ENV
  db.py            لایه SQLite async + اسکیمای کامل
  middlewares.py   ثبت گروه‌ها، Ban/Mute
  scheduler.py     تیک جهان زنده (رویداد، آلودگی، انرژی، Heat)
  ui.py            کارت‌های Embedگونه، Progress bar، کیبورد Inline
  game/
    content.py     مسیرها، مراحل VX-13، قدرت‌ها، جهش‌ها، آیتم‌ها، سازمان‌ها، شخصیت‌ها
    engine.py      قوانین بازی: آمار، آلودگی، نبرد، اقتصاد، شهرت، Legacy
  handlers/
    private.py     راهنمای کوتاه + Add to group
    group_core.py  ورود، پروفایل، اسکن، کوله، رتبه‌بندی، لاگ، شخصیت‌ها
    actions.py     جست‌وجو، نبرد، قدرت، جهش، سرم، مأموریت
    economy.py     فروشگاه، بازار سیاه، بازار بازیکنان، مدارک، پرداخت
    betrayal.py    قرارداد مخفی، Wanted، خیانت به سازمان
    orgs.py        عضویت، تأسیس، خزانه، تحقیق، ارتقا، جنگ
    world.py       رویدادهای جهانی، وضعیت جهان، World Boss
    admin.py       پنل مدیریت کامل
```

## سیستم‌ها

| سیستم | توضیح |
|---|---|
| مسیرها | بازمانده، U.B.C، دانشمند، مزدور، ابرقدرت، دوطرفه، آلوده، جهش‌یافته، سلاح زیستی، رهبر، خائن — با تصمیم‌ها تغییر می‌کنند |
| VX-13 | انسان → آلوده → جهش‌یافته → جهش پیشرفته → Bio-Weapon؛ هر مرحله بونوس + ریسک |
| V-SERUM | ۱۰ قدرت متمایز با Cooldown، ریسک عوارض، Counter مشخص و اثر واقعی (نه فقط Attack) |
| Mutation Tree | ۱۰ گره شاخه‌ای با پیش‌نیاز و آستانه آلودگی، برگشت‌ناپذیر |
| سازمان‌ها | V-CORP / U.B.C / UMBRA + سازمان‌های ساخته بازیکن؛ رتبه، خزانه، تحقیق، جنگ |
| Reputation | شهرت مستقل نزد هر سازمان، شرط عضویت و ارتقا |
| خیانت | قرارداد مخفی روی سر بازیکنان + فروش اسناد سازمان خودی |
| Wanted | مجموع قراردادها + Heat به‌عنوان فهرست تحت تعقیب |
| اقتصاد پویا | قیمت‌ها با خرید/فروش واقعی بازیکنان بالا و پایین می‌رود |
| Evidence | مدارک قابل کشف، سرقت (نخ ذهنی) و فروش در بازار |
| بازار سیاه | نمونه ویروس، سرم، درمان، ردیاب، هویت جعلی — با Heat و ریسک لو رفتن |
| دنیای زنده | ۸ نوع رویداد جهانی که تهدید، آلودگی همه و ثبات V-CORP را جابه‌جا می‌کند |
| World Boss | باس گروهی با HP مقیاس‌شونده و تقسیم جایزه بر اساس آسیب |
| Legacy | مرگ = نسل جدید؛ بخشی از دستاورد به‌صورت Legacy منتقل می‌شود |

## دستورهای گروه

`/start` `/me` `/scan` `/scavenge` `/attack` `/heal` `/mission` `/power` `/use`
`/mutate` `/inject` `/hide` `/cure` `/shop` `/black` `/inv` `/pay` `/sell` `/market`
`/evidence` `/contract` `/contracts` `/wanted` `/betray` `/orgs` `/found` `/org` `/war`
`/world` `/event` `/respond` `/boss` `/hit` `/top` `/log` `/legends` `/help`

## پنل ادمین — `/admin`

آمار · گروه‌ها · Ban/Mute · Give (پول/آیتم) · تغییر Infection · ساخت و اعطای قدرت ·
ساخت Event · ساخت Mission · مدیریت سازمان‌ها · تنظیم Economy · Broadcast · Logs ·
Backup/Restore فایل دیتابیس · اجرای مستقیم SQL.
