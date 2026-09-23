"""
read_data.py — 入门演示：pandas 读取 + 转换 + 质量检查 + 基础指标

数据：dataset/sample_behavior.csv（10 条手造教学样本，行为类型为数字 1/2/3/4）
说明：这是阶段1 最初的入门练习，用来跑通"读数据 → 转时间 → 查质量 → 算指标"的套路。
      真实数据分析请用上一级的 clean_real_data.py / real_data_kpi.py。

运行：py -3.10 stage1_data_analysis/sample_demo/read_data.py
"""
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[2]          # 项目根目录
SRC = BASE / "dataset" / "sample_behavior.csv"

df = pd.read_csv(SRC)
print("====原始数据====")
print(df)

# 1. 时间戳转 datetime
df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")
# 2. 行为类型映射为中文名
behavior_map = {1: "浏览", 2: "收藏", 3: "加购", 4: "购买"}
df["behavior_name"] = df["behavior_type"].map(behavior_map)

print("\n==== 转换后数据 ====")
print(df)

print("\n==== 缺失值检查 ====")
print(df.isnull().sum())

print("\n==== 重复行检查 ====")
print("重复行数：", df.duplicated().sum())

print("\n==== 基础统计 ====")
print(df.describe())

# ========== 电商核心指标计算 ==========
print("\n========== 电商核心指标 ==========")
pv = len(df[df["behavior_type"] == 1])       # 浏览量 PV
uv = df["user_id"].nunique()                 # 独立用户 UV
fav_cnt = len(df[df["behavior_type"] == 2])  # 收藏数量
cart_cnt = len(df[df["behavior_type"] == 3]) # 加购数量
buy_cnt = len(df[df["behavior_type"] == 4])  # 购买行为次数

cart_rate = cart_cnt / pv if pv != 0 else 0  # 浏览 → 加购
buy_rate = buy_cnt / pv if pv != 0 else 0    # 浏览 → 购买

print(f"浏览量PV：{pv}")
print(f"独立访客UV：{uv}")
print(f"收藏次数：{fav_cnt}")
print(f"加购次数：{cart_cnt}")
print(f"购买次数：{buy_cnt}")
print(f"浏览-加购转化率：{cart_rate:.2%}")
print(f"浏览-购买转化率：{buy_rate:.2%}")

# 每个用户的行为汇总
print("\n==== 用户行为汇总 ====")
user_behavior = df.groupby(["user_id", "behavior_name"]).size().unstack(fill_value=0)
print(user_behavior)
