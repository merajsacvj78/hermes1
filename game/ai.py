"""🤖 جنگ جهانی — هوش مصنوعی و گزارشگر بازار.
طبق دکترین ۲۰۲۶ و دستورات سیستم:
• هیچ ربات یا NPC به صورت خودکار اعلام جنگ یا اسپم نمی‌کند
• تمام تصمیمات و جنگ‌ها صد در صد توسط بازیکنان واقعی رهبری می‌شود
"""
import random
import countries
import db
import texts
from game import economy


def tick() -> list:
    """حلقه زمانی AI — بدون ارسال اسپم یا جنگ خودکار."""
    return []


def respond_to_strike(attacker_cid: str, defender_cid: str, kind: str, score: int) -> list:
    """پاسخ دفاعی خودکار پایگاه‌های کشوری که بازیکن ندارد (بدون پیام اسپم)."""
    return []
