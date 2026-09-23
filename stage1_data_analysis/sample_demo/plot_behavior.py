"""
plot_behavior.py — 入门演示：电商用户行为可视化（小样本版）

三张图：行为类型分布 / 转化漏斗 / 各用户行为构成
输出：stage1_data_analysis/sample_demo/behavior_analysis.png

运行：py -3.10 stage1_data_analysis/sample_demo/plot_behavior.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]

df = pd.read_csv(BASE / "dataset" / "sample_behavior.csv")
behavior_map = {1: "浏览", 2: "收藏", 3: "加购", 4: "购买"}
df["behavior_name"] = df["behavior_type"].map(behavior_map)

# ---- 统计各行为次数 ----
counts = df["behavior_name"].value_counts().reindex(["浏览", "收藏", "加购", "购买"], fill_value=0)
pv, fav, cart, buy = counts["浏览"], counts["收藏"], counts["加购"], counts["购买"]

fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))

# 图1：行为类型分布
ax = axes[0]
bars = ax.bar(counts.index, counts.values, color=["#5B8FF9", "#F6BD16", "#5AD8A6", "#E8684A"])
ax.bar_label(bars)
ax.set_title("用户行为类型分布", fontsize=13)
ax.set_ylabel("次数")

# 图2：转化漏斗（浏览 → 加购+收藏 → 购买）
ax = axes[1]
stages = ["浏览", "收藏+加购", "购买"]
values = [pv, fav + cart, buy]
colors = ["#5B8FF9", "#F6BD16", "#E8684A"]
bars = ax.barh(stages[::-1], values[::-1], color=colors[::-1], height=0.55)
ax.bar_label(bars)
ax.set_title(f"转化漏斗（购买率 {buy/pv:.1%}）", fontsize=13)
ax.set_xlabel("次数")

# 图3：各用户行为堆积柱状图
ax = axes[2]
user_behavior = df.groupby(["user_id", "behavior_name"]).size().unstack(fill_value=0)
order = [c for c in ["浏览", "收藏", "加购", "购买"] if c in user_behavior.columns]
bottom = pd.Series(0, index=user_behavior.index, dtype=float)
for c in order:
    ax.bar(user_behavior.index.astype(str), user_behavior[c], bottom=bottom, label=c, width=0.6)
    bottom += user_behavior[c]
ax.legend(title="行为", fontsize=9)
ax.set_title("各用户行为构成", fontsize=13)
ax.set_ylabel("次数")

plt.tight_layout()
out = HERE / "behavior_analysis.png"
plt.savefig(out, dpi=150)
print(f"图表已保存：{out}")
