"""
real_data_kpi.py — 阶段1：真实数据集核心 KPI + 可视化

数据：dataset/clean_behavior.csv（clean_real_data.py 的输出）
输出：stage1_data_analysis/real_behavior_analysis.png

运行方式（任意目录下都可以执行）：
    py -3.10 stage1_data_analysis/real_data_kpi.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "dataset" / "clean_behavior.csv"

if not SRC.exists():
    raise SystemExit(f"找不到 {SRC}\n请先运行：py -3.10 stage1_data_analysis/clean_real_data.py")

df = pd.read_csv(SRC, parse_dates=["datetime"])

# ---------- 核心 KPI（与 calculate_kpi.py 同口径，行为类型为字符串枚举） ----------
cnt = df["behavior_type"].value_counts()
pv, fav, cart, buy = cnt.get("pv", 0), cnt.get("fav", 0), cnt.get("cart", 0), cnt.get("buy", 0)
uv = df["user_id"].nunique()

print("========== 真实数据核心 KPI（2017-11-26 单日）==========")
print(f"浏览量 PV        ：{pv:,}")
print(f"独立访客 UV      ：{uv:,}")
print(f"收藏次数         ：{fav:,}")
print(f"加购次数         ：{cart:,}")
print(f"购买次数         ：{buy:,}")
print("-" * 34)
print(f"浏览 → 加购转化率：{cart/pv:.2%}")
print(f"浏览 → 收藏转化率：{fav/pv:.2%}")
print(f"浏览 → 购买转化率：{buy/pv:.2%}")
print(f"人均浏览次数     ：{pv/uv:.2f}")

# ---------- 可视化：小时流量 + 真实漏斗 ----------
fig, axes = plt.subplots(1, 2, figsize=(14, 4.8))

ax = axes[0]
hourly = df[df["behavior_type"] == "pv"].groupby(df["datetime"].dt.hour).size()
uv_hourly = df.groupby(df["datetime"].dt.hour)["user_id"].nunique()
ax.plot(hourly.index, hourly.values, marker="o", label="PV", color="#5B8FF9")
ax.plot(uv_hourly.index, uv_hourly.values, marker="s", label="UV", color="#5AD8A6")
ax.set_xticks(range(1, 11), [f"{h}点" for h in range(1, 11)])
ax.set_title("每小时 PV / UV 趋势（真实数据）")
ax.set_ylabel("数量")
ax.legend()

ax = axes[1]
stages = ["浏览 pv", "加购 cart", "收藏 fav", "购买 buy"]
values = [pv, cart, fav, buy]
bars = ax.barh(stages[::-1], values[::-1], color=["#E8684A", "#F6BD16", "#5AD8A6", "#5B8FF9"], height=0.55)
ax.bar_label(bars, fmt=lambda v: f"{v:,.0f}")
ax.set_title(f"真实行为漏斗（购买率 {buy/pv:.2%}）")
ax.set_xlabel("次数")

plt.tight_layout()
out_png = HERE / "real_behavior_analysis.png"
plt.savefig(out_png, dpi=150)
print(f"\n图表已保存：{out_png}")

print("""
========== 分析解读 ==========
1. 时段曲线：凌晨1点后流量持续下滑，9~10点开始抬头——符合"深夜低谷、
   早高峰启动"的日常规律。完整数据集(12月1~3日)还会出现晚间20~22点大高峰。
2. 真实漏斗呈典型金字塔：浏览 43 万 → 加购+收藏 4 万 → 购买 1.1 万，
   每层衰减 8~10 倍。业务上提升"加购→购买"一步的转化，收益最大。
3. 人均浏览约 1.9 次/10小时——样本覆盖 23 万用户但只截取了一天部分时段，
   完整数据集人均 PV 会显著更高。写简历时注明数据窗口，避免指标误读。
""")
