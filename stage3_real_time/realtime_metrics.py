"""
realtime_metrics.py — Stage3 实时计算模拟（本地可运行版）

真实架构（本脚本模拟的对象）：
    埋点日志 → Flume/Canal → Kafka(消息队列) → Flink(流式计算) → Redis/MySQL(结果存储) → 报表大屏

模拟思路：
    把 csv 按 timestamp 排序后逐条"喂"进窗口（相当于 Kafka 逐条消费），
    按 5 分钟滚动窗口聚合 PV / UV / 购买量 —— 等价于 Flink 的 TumblingWindow 聚合。
"""
from collections import deque

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

# ---------- 1. 读取"数据源"（相当于 Kafka 的 topic） ----------
df = pd.read_csv("../dataset/sample_behavior.csv")
df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")
df = df.sort_values("datetime")  # 流式数据必须按事件时间排序

# ---------- 2. 滚动窗口流式聚合（模拟 Flink TumblingWindow） ----------
WINDOW_MIN = 5  # 窗口大小：5 分钟
events = deque(df.to_dict("records"))          # 内存版"消息队列"
windows = []                                   # 每个窗口的聚合结果

current_start = df["datetime"].min().floor(f"{WINDOW_MIN}min")
buf = []
while events:
    ev = events.popleft()
    if ev["datetime"] < current_start + pd.Timedelta(minutes=WINDOW_MIN):
        buf.append(ev)                          # 事件落入当前窗口
    else:
        # 窗口关闭 → 触发计算并输出（对应 Flink 的窗口触发器）
        b = pd.DataFrame(buf)
        windows.append({
            "窗口": f"{current_start:%H:%M}~{(current_start + pd.Timedelta(minutes=WINDOW_MIN)):%H:%M}",
            "PV": int((b["behavior_type"] == 1).sum()),
            "UV": b["user_id"].nunique(),
            "购买": int((b["behavior_type"] == 4).sum()),
        })
        current_start += pd.Timedelta(minutes=WINDOW_MIN)
        buf = [ev]
# 收尾：处理最后一个窗口
if buf:
    b = pd.DataFrame(buf)
    windows.append({
        "窗口": f"{current_start:%H:%M}~{(current_start + pd.Timedelta(minutes=WINDOW_MIN)):%H:%M}",
        "PV": int((b["behavior_type"] == 1).sum()),
        "UV": b["user_id"].nunique(),
        "购买": int((b["behavior_type"] == 4).sum()),
    })

win_df = pd.DataFrame(windows)

print("========== 实时窗口聚合结果（5分钟滚动窗口）==========")
print(win_df.to_string(index=False))

# ---------- 3. 可视化 ----------
fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
x = range(len(win_df))

ax = axes[0]
ax.plot(x, win_df["PV"], marker="o", label="PV", color="#5B8FF9")
ax.plot(x, win_df["UV"], marker="s", label="UV", color="#5AD8A6")
ax.set_xticks(x, win_df["窗口"])
ax.set_title("各窗口流量趋势（模拟实时大屏折线）")
ax.set_ylabel("数量")
ax.legend()

ax = axes[1]
bars = ax.bar(x, win_df["购买"], color="#E8684A", width=0.5)
ax.bar_label(bars)
ax.set_xticks(x, win_df["窗口"])
ax.set_title("各窗口购买量（模拟实时成交监控）")
ax.set_ylabel("购买次数")

plt.tight_layout()
plt.savefig("realtime_metrics.png", dpi=150)

# ---------- 4. 分析解读 ----------
peak = win_df.loc[win_df["PV"].idxmax()]
print("""
========== 分析解读 ==========
1. 实时计算和离线计算（Stage2）的数学逻辑完全一样，区别只在"何时算"：
   - 离线：攒一天的数据，T+1 凌晨批量跑（Hive），看的是"昨天全天怎么样"
   - 实时：数据到一条算一条，按窗口秒级/分钟级出结果，看的是"现在这一刻怎么样"
2. 本数据 17 分钟内只有一个流量小高峰（窗口 {}，PV={}），
   真实大屏里这一列会持续跳动，运营靠它发现流量突增/突降并告警。
3. 窗口选择是实时计算的核心权衡：窗口越小越灵敏但抖动越大，越大越平稳但越迟钝。
   电商大屏常用 1~5 分钟窗口 + 滑动更新。
4. 生产环境中本脚本的三样东西各有对应组件：
   - deque 消息队列  → Kafka（削峰、解耦）
   - 逐条喂入+窗口触发 → Flink（事件时间、水位线处理乱序）
   - win_df 结果表   → Redis/MySQL，供大屏高频读取
""".format(peak["窗口"], peak["PV"]))
