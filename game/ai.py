"""🤖 جنگ جهانی — سامانه هوش مصنوعی، اتاق فرماندهی راهبردی و تحلیلگر ژئوپلیتیک."""
import random
import countries
import db
import texts
from game import economy, defense, infra, geo


def tick() -> list:
    """حلقه زمانی هوش مصنوعی — پایش وضعیت بدون ایجاد اسپم."""
    return []


def respond_to_strike(attacker_cid: str, defender_cid: str, kind: str, score: int) -> list:
    """پاسخ تاکتیکی خودکار سامانه‌های پدافند کشوری."""
    return []


def _has_leader(cid: str) -> bool:
    row = db.one("SELECT 1 FROM users WHERE country=? AND is_leader=1 LIMIT 1", (cid,))
    return bool(row)


def news_feed() -> str:
    """بولتن خبری و گزارش تحلیل راهبردی ژئوپلیتیک جهان."""
    lines = [texts.hdr("بولتن تحلیل استراتژیک هوش مصنوعی", "🤖"), ""]
    wars = db.q("SELECT * FROM wars WHERE status='active'")
    if wars:
        lines.append(f"⚔️ <b>گزارش اتاق جنگ:</b> تعداد <b>{texts.fa(len(wars))} نبرد فعال</b> در جبهه‌های مختلف رصد می‌شود.")
        for w in wars[:3]:
            ca = countries.COUNTRIES.get(w["a"], {})
            cb = countries.COUNTRIES.get(w["b"], {})
            lines.append(f"   ▫️ {ca.get('flag','')} {ca.get('name','')} ⚔️ {cb.get('flag','')} {cb.get('name','')}")
    else:
        lines.append("🕊️ <b>وضعیت بین‌الملل:</b> ثبات نسبی در خطوط مرزی حاکم است.")
        
    w_econ = economy.world()
    lines.append(f"\n📊 <b>شاخص‌های اقتصادی:</b> شاخص دلار ×{texts.fa(round(w_econ['dollar'], 2))} | نفت: ${texts.fa(round(w_econ['oil'], 1))} | تورم: {texts.fa(round(w_econ['inflation']*100, 1))}٪")
    return "\n".join(lines)


def strategic_advisor(uid: int) -> str:
    """دستیار راهبردی هوشمند: ارزیابی وضعیت کشور، سپر پدافندی، زیرساخت و ارائه توصیه‌های تاکتیکی."""
    from game import state
    p = state.active(uid)
    if not p:
        return "⚠️ ابتدا با دستور «شروع» کشور خود را مشخص کنید."
    cid = p["country"]
    c = countries.COUNTRIES.get(cid, {})
    
    defense.ensure(cid)
    ew_lvl = defense.level(cid, "جنگ الکترونیک")
    abm_lvl = defense.level(cid, "ضد موشک")
    air_lvl = defense.level(cid, "ضد هوایی")
    
    infr = infra.state_of(cid)
    power_hp = infr.get("power", 100)
    
    recomms = []
    if ew_lvl < 50:
        recomms.append("⚠️ <b>جنگ الکترونیک ضعیف است:</b> برای کاهش خسارات ضربات دشمن، لایه جنگال را تقویت کنید.")
    if abm_lvl < 60:
        recomms.append("🛡️ <b>آسیب‌پذیری در برابر موشک‌های بالستیک:</b> ارتقای سامانه ضد موشک ضروری است.")
    if power_hp < 60:
        recomms.append("⚡ <b>آسیب شبکه برق:</b> جهت جلوگیری از اختلال در خریدهای نظامی، زیرساخت برق را بازسازی کنید.")
    if not recomms:
        recomms.append("✅ <b>آمادگی رزمی کامل:</b> زیرساخت‌ها و سامانه‌های پدافند در شرایط ایده‌آل قرار دارند.")
        
    t = texts
    lines = [
        t.hdr(f"تحلیل اتاق جنگ هوش مصنوعی — {c.get('name','')} {c.get('flag','')}", "🧠"),
        f"🎯 تخصص دکترین: <b>{c.get('spec', 'تهاجمی')}</b>",
        f"🛡️ میانگین آمادگی پدافند هوایی: <b>{t.fa((abm_lvl + air_lvl + ew_lvl) // 3)}٪</b>",
        f"🏭 سلامت زیرساخت‌های استراتژیک: <b>{t.fa(sum(infr.values()) // len(infr))}٪</b>",
        "",
        "📋 <b>توصیه‌های تاکتیکی هوش مصنوعی:</b>",
        *recomms,
        "",
        "💡 <i>پیشنهاد عملیاتی: با آغاز عملیات‌های ۵ مرحله‌ای نامدار، زیرساخت‌های C4ISR دشمن را هدف قرار دهید.</i>"
    ]
    return "\n".join(lines)
