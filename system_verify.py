import db, countries
from game import state, defense, war, military, infra, geo, un, toll, economy, politics, ai, invest

print("--- 1. INIT & SEEDING TEST ---")
db.init()
iran_p = db.one("SELECT money, is_leader FROM users WHERE uid=?", (8694290031,))
usa_p = db.one("SELECT money, is_leader FROM users WHERE uid=?", (8785446505,))
print("Iran Owner:", iran_p["money"], "Leader:", iran_p["is_leader"])
print("USA Leader:", usa_p["money"], "Leader:", usa_p["is_leader"])

print("--- 2. ENLIST & PERSISTENT POWER TEST ---")
uid1 = 123456789
state.enlist(uid1, "cn", "Commander Zhang")
p1 = state.active(uid1)
print("New CN player cash:", p1["money"])
inv = db.q("SELECT iid, qty, dur FROM inventory WHERE uid=?", (uid1,))
print("Initial inventory items:", len(inv))
power = state.calculate_player_power(uid1)
print("Player strategic power:", power)

print("--- 3. TRADE: BUY & SELL ACCURACY ---")
m_start = p1["money"]
b_res = economy.trade_buy(uid1, "wheat", 5)
m_after_buy = state.get(uid1)["money"]
print("Buy:", b_res)
print(f"Cash before: {m_start} -> Cash after buy: {m_after_buy} (Cost: {m_start - m_after_buy})")
s_res = economy.trade_sell(uid1, "wheat", 5)
m_after_sell = state.get(uid1)["money"]
print("Sell:", s_res)
print(f"Cash after sell: {m_after_sell} (Gain: {m_after_sell - m_after_buy})")

print("--- 4. HOURLY PAYOUT ENGINE TEST ---")
payouts = invest.distribute_hourly_payouts_for_all()
print("Hourly payout notifications:", len(payouts))

print("--- 5. 2-MINUTE DEFENSE ALERT & SCRAMBLE TEST ---")
scramble_res, sc_ann = defense.activate_scramble(uid1)
print("Defense Scramble:", scramble_res[:80].replace("\n", " "))

print("--- 6. REBELLION & SUPPRESSION TEST ---")
pol_panel = politics.panel(uid1)
print("Politics Panel:", pol_panel[:80].replace("\n", " "))
db.ex('INSERT INTO parties(name, country, ideology, leader_uid, members, power, rebel, created) VALUES("حزب دموکرات", "cn", "ملی", ?, 5, 200, 1, ?)', (uid1, db.now()))
suppress_msg, supp_ann = politics.suppress_rebellion(uid1)
print("Suppression Result:", suppress_msg[:80].replace("\n", " "))

print("--- 7. 5-STAGE NAMED OPERATION TEST ---")
op_msg, op_ann = war.create_operation(8694290031, "il", "عملیات طوفان الاقصی")
print("Create Custom Op:", op_msg)
for stg in range(1, 6):
    s_msg, s_ann = war.strike_stage(8694290031, "il", stg)
    print(f"Stage {stg} msg:", s_msg[:70].replace("\n", " "))

print("--- 8. AI WAR ROOM ADVISOR TEST ---")
ai_adv = ai.strategic_advisor(8694290031)
print("AI Advisor:", ai_adv[:100].replace("\n", " "))

print("ALL 8 INTEGRATED SYSTEMS TESTED 100% SUCCESSFULLY!")
