"""
calculate_kpi.py — 入门演示：电商核心 KPI 指标计算（小样本版）

输入：dataset/sample_behavior.csv
输出：PV / UV / 收藏 / 加购 / 购买次数、三级转化率、人均指标、用户行为汇总、购买明细
说明：真实数据版 KPI 见上一级 real_data_kpi.py（口径相同，行为类型换成 pv/fav/cart/buy）

运行：py -3.10 stage1_data_analysis/sample_demo/calculate_kpi.py
"""
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[2]
df = pd.read_csv(BASE / "dataset" / "sample_behavior.csv")

# 行为类型映射：1浏览 2收藏 3加购 4购买
behavior_map = {1: "浏览", 2: "收藏", 3: "加购", 4: "购买"}
df["behavior_name"] = df["behavior_type"].map(behavior_map)

# ========== 核心流量指标 ==========
pv = len(df[df["behavior_type"] == 1])       # 浏览量 PV（Page View）
uv = df["user_id"].nunique()                 # 独立访客 UV（Unique Visitor）
fav_cnt = len(df[df["behavior_type"] == 2])  # 收藏次数
cart_cnt = len(df[df["behavior_type"] == 3]) # 加购次数
buy_cnt = len(df[df["behavior_type"] == 4])  # 购买次数

# ========== 转化率 ==========
cart_rate = cart_cnt / pv if pv else 0       # 浏览 → 加购
buy_rate = buy_cnt / pv if pv else 0         # 浏览 → 购买
cart2buy_rate = buy_cnt / cart_cnt if cart_cnt else 0   # 加购 → 购买（分母是加购数）

# ========== 人均指标 ==========
behavior_per_user = len(df) / uv if uv else 0    # 人均行为次数
pv_per_user = pv / uv if uv else 0               # 人均浏览次数

# ========== 输出 ==========
print("========== 电商核心 KPI ==========")
print(f"浏览量 PV        ：{pv}")
print(f"独立访客 UV      ：{uv}")
print(f"收藏次数         ：{fav_cnt}")
print(f"加购次数         ：{cart_cnt}")
print(f"购买次数         ：{buy_cnt}")
print("-" * 34)
print(f"浏览 → 加购转化率：{cart_rate:.2%}")
print(f"浏览 → 购买转化率：{buy_rate:.2%}")
print(f"加购 → 购买转化率：{cart2buy_rate:.2%}")
print("-" * 34)
print(f"人均行为次数     ：{behavior_per_user:.2f}")
print(f"人均浏览次数     ：{pv_per_user:.2f}")

print("\n========== 用户行为汇总 ==========")
user_behavior = df.groupby(["user_id", "behavior_name"]).size().unstack(fill_value=0)
order = [c for c in ["浏览", "收藏", "加购", "购买"] if c in user_behavior.columns]
print(user_behavior[order])

print("\n========== 购买用户明细 ==========")
buy_users = df[df["behavior_type"] == 4][["user_id", "item_id", "category_id", "datetime"]]
print(buy_users.to_string(index=False))

print("""
========== 一个数据提醒 ==========
样本里 10 条记录、5 次浏览对应 3 次购买，加购 → 购买转化率会超过 100%：
因为手造数据里购买行为没有前置加购记录。真实数据集（见 real_data_kpi.py）
购买率只有 2.57%，这个指标才有漏斗意义。
""")
