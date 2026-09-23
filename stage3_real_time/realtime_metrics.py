"""
realtime_metrics.py — Stage3 实时计算（本地可运行版）

真实架构（本脚本模拟的对象）：
    埋点日志 → Flume/Canal → Kafka(消息队列) → Flink/Spark Streaming(流式计算)
             → Redis/MySQL(结果存储) → 实时大屏

模拟思路：
    1. 把 dataset/clean_behavior.csv 按"事件时间"排序，当作 Kafka 里一条条到达的消息；
    2. 按 5 分钟滚动窗口（Tumbling Window）聚合 PV / UV / 购买量；
    3. 另算一组"15 分钟窗口、每 5 分钟滑动一次"的滑动窗口（Sliding Window）做对照；
    4. 窗口结果写成 csv（等价于线上写 Redis/MySQL 结果表），并画成实时大屏样式。

数据：dataset/clean_behavior.csv（真实数据 48.6 万条，行为类型 pv/fav/cart/buy）
输出：realtime_windows.csv、realtime_metrics.png
运行：py -3.10 stage3_real_time/realtime_metrics.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "dataset" / "clean_behavior.csv"
WINDOW_MIN = 5          # 滚动窗口大小（分钟）
SLIDE_MIN = 5           # 滑动步长（分钟）
SLIDE_SIZE = 15         # 滑动窗口大小（分钟）

if not SRC.exists():
    raise SystemExit(f"找不到 {SRC}\n请先运行：py -3.10 stage1_data_analysis/clean_real_data.py")

# ---------- 1. 读取"数据源"（相当于 Kafka 的 topic），按事件时间排序 ----------
df = pd.read_csv(SRC, parse_dates=["datetime"])
df = df.sort_values("datetime").reset_index(drop=True)

span_min = (df["datetime"].max() - df["datetime"].min()).total_seconds() / 60
print("========== 数据源（模拟 Kafka 消息流）==========")
print(f"消息条数：{len(df):,}   时间跨度：{df['datetime'].min()} ~ {df['datetime'].max()}（约 {span_min:.0f} 分钟）")

# ---------- 2. 滚动窗口聚合（等价于 Flink: TUMBLE(rowtime, INTERVAL '5' MINUTE)） ----------
# pandas 的 dt.floor 把每条事件归入它所属的窗口，等价于 Flink 按事件时间分桶
df["window_start"] = df["datetime"].dt.floor(f"{WINDOW_MIN}min")

win = df.groupby("window_start").agg(
    pv=("behavior_type", lambda s: int((s == "pv").sum())),
    buy=("behavior_type", lambda s: int((s == "buy").sum())),
    cart=("behavior_type", lambda s: int((s == "cart").sum())),
    uv=("user_id", "nunique"),
).reset_index()
win["window_end"] = win["window_start"] + pd.Timedelta(minutes=WINDOW_MIN)
win["window"] = win["window_start"].dt.strftime("%H:%M") + "~" + win["window_end"].dt.strftime("%H:%M")

print(f"\n========== 滚动窗口聚合结果（{WINDOW_MIN} 分钟窗口，共 {len(win)} 个窗口）==========")
print(win[["window", "pv", "uv", "cart", "buy"]].to_string(index=False))

# 窗口结果落表（线上对应"写 Redis/MySQL 结果表"，供大屏高频读取）
out_csv = HERE / "realtime_windows.csv"
win[["window_start", "window_end", "window", "pv", "uv", "cart", "buy"]].to_csv(out_csv, index=False)
print(f"\n窗口结果已落表：{out_csv}")

# ---------- 3. 滑动窗口对照（每 5 分钟滑动、窗口长 15 分钟） ----------
# 用途：大屏想要"曲线平滑、不抖动"就用滑动窗口；要"每分钟一个准数"就用滚动窗口
slide_rows = []
start = df["datetime"].min().floor(f"{WINDOW_MIN}min")
end = df["datetime"].max()
while start <= end:
    seg = df[(df["datetime"] >= start) & (df["datetime"] < start + pd.Timedelta(minutes=SLIDE_SIZE))]
    slide_rows.append({
        "window": f"{start:%H:%M}",
        "pv": int((seg["behavior_type"] == "pv").sum()),
        "uv": seg["user_id"].nunique(),
        "buy": int((seg["behavior_type"] == "buy").sum()),
    })
    start += pd.Timedelta(minutes=SLIDE_MIN)
slide = pd.DataFrame(slide_rows)
print(f"\n========== 滑动窗口对照（窗口 {SLIDE_SIZE} 分钟 / 步长 {SLIDE_MIN} 分钟，前 6 行）==========")
print(slide.head(6).to_string(index=False))
print(f"... 共 {len(slide)} 个滑动窗口（同一秒会被 3 个窗口同时统计，所以不能把滑动窗口结果相加）")

# ---------- 4. 可视化（模拟实时大屏） ----------
fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)

ax = axes[0]
ax.plot(win["window_start"], win["pv"], marker="o", markersize=2.5, label="PV", color="#5B8FF9")
ax.plot(win["window_start"], win["uv"], marker="s", markersize=2.5, label="UV", color="#5AD8A6")
ax.set_title(f"实时流量趋势（{WINDOW_MIN} 分钟滚动窗口）")
ax.set_ylabel("数量")
ax.legend()

ax = axes[1]
ax.bar(win["window_start"], win["buy"], width=pd.Timedelta(minutes=4), color="#E8684A", label="购买量")
ax.set_title("实时成交监控（每窗口购买次数）")
ax.set_ylabel("购买次数")
ax.set_xlabel("时间")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.xaxis.set_major_locator(mdates.HourLocator())
ax.legend()

plt.tight_layout()
out_png = HERE / "realtime_metrics.png"
plt.savefig(out_png, dpi=150)

# ---------- 5. 分析解读 ----------
peak = win.loc[win["pv"].idxmax()]
busiest = win.loc[win["buy"].idxmax()]
print(f"""
========== 分析解读 ==========
1. 实时计算和离线计算（Stage2）的数学逻辑完全一样，区别只在"何时算"：
   - 离线：攒一天的数据，T+1 凌晨批量跑（Hive），看"昨天全天怎么样"
   - 实时：数据到一条算一条，按窗口分钟级出结果，看"现在这一刻怎么样"
2. 本数据流量峰值出现在 {peak['window']}（PV={peak['pv']:,}、UV={peak['uv']:,}），
   成交最密集的窗口是 {busiest['window']}（购买 {busiest['buy']:,} 次）。
   真实大屏里这两条曲线会持续跳动，运营靠它发现流量突增/突降并告警。
3. 窗口是实时计算的核心权衡：窗口越小越灵敏但抖动越大，越大越平稳但越迟钝。
   滚动窗口（本脚本上半部分）不重叠、结果可相加，适合对账；
   滑动窗口（下半部分）重叠统计、曲线平滑，适合做大屏趋势展示。
4. 生产环境中本脚本的四个部分各有对应组件：
   - 读 csv + 按时间排序 → Kafka（削峰、解耦、保留事件时间）
   - groupby 窗口聚合     → Flink/Spark Structured Streaming（水位线处理乱序）
   - realtime_windows.csv → Redis/MySQL 结果表
   - 下面的两张图          → ECharts/Superset 实时大屏
5. 真实流式计算还要处理两个本脚本回避了的问题：乱序数据（用 watermark 等）和
   迟到数据（用 allowed lateness + 侧输出流补算），见 flink_sql_realtime.sql 注释。
""")
print(f"图表已保存：{out_png}")
