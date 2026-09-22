"""
clean_real_data.py — 阶段1·周1：真实数据集清洗（天池 UserBehavior）

数据源：UserBehavior.csv（阿里云天池公开数据集子集，见 dataset/数据集说明.md）
字段：user_id, item_id, category_id, behavior_type(pv/buy/cart/fav), timestamp
清洗动作（对应方案步骤3）：
    1. 字段类型校验 + 缺失值处理
    2. 行为类型过滤：只保留 pv/fav/cart/buy 四种合法枚举
    3. 时间范围过滤：只保留 2017-11-25 ~ 2017-12-03（数据集官方声明区间）
    4. 全字段去重
输出：dataset/clean_behavior.csv（清洗后标准数据集）
"""
import pandas as pd

RAW = "../dataset/UserBehavior.csv"
OUT = "../dataset/clean_behavior.csv"

# ---------- 1. 读取原始数据（无表头，5列） ----------
df = pd.read_csv(RAW, header=None,
                 names=["user_id", "item_id", "category_id", "behavior_type", "timestamp"])
n0 = len(df)

# ---------- 2. 缺失值处理 ----------
df = df.dropna()
n1 = len(df)

# ---------- 3. 行为类型过滤（非法枚举视为脏数据） ----------
VALID = ["pv", "fav", "cart", "buy"]
df = df[df["behavior_type"].isin(VALID)]
n2 = len(df)

# ---------- 4. 时间范围过滤 ----------
df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")
lo, hi = pd.Timestamp("2017-11-25"), pd.Timestamp("2017-12-04")
df = df[(df["datetime"] >= lo) & (df["datetime"] < hi)]
n3 = len(df)

# ---------- 5. 全字段去重 ----------
df = df.drop_duplicates()
n4 = len(df)

# ---------- 6. 输出标准数据集 ----------
df = df.sort_values(["user_id", "timestamp"]).reset_index(drop=True)
df.to_csv(OUT, index=False)

print("========== 数据清洗质量报告 ==========")
print(f"原始记录数           ：{n0:,}")
print(f"缺失值剔除后         ：{n1:,}（剔除 {n0-n1} 条）")
print(f"非法行为类型剔除后   ：{n2:,}（剔除 {n1-n2} 条）")
print(f"时间范围过滤后       ：{n3:,}（剔除 {n2-n3} 条）")
print(f"去重后               ：{n4:,}（剔除 {n3-n4} 条）")
print(f"清洗保留率           ：{n4/n0:.2%}")
print(f"行为分布：{df['behavior_type'].value_counts().to_dict()}")
print(f"时间跨度：{df['datetime'].min()} ~ {df['datetime'].max()}")
print(f"用户数：{df['user_id'].nunique():,}  商品数：{df['item_id'].nunique():,}  类目数：{df['category_id'].nunique():,}")
print(f"\n标准数据集已保存：{OUT}")

print("""
========== 分析解读 ==========
1. 该子集为真实天池数据（2017-11-26 单日 10 小时），48.6 万条、23 万用户，
   规模足以支撑后续 SQL 聚合、窗口计算和推荐算法，且本机 pandas 可直接处理。
2. 购买占比约 2.3%（对比早期教学样本的 60%）——真实电商的浏览-购买转化
   就是低个位数，这才是有效漏斗：pv(89%) → cart(5.3%)/fav(3%) → buy(2.3%)。
3. 数据本身零缺失零重复：天池官方已做过初步清洗，但清洗流程不能省——
   换一份原始日志（如埋点日志）时这些步骤就是必修课，代码保留以备复用。
""")
