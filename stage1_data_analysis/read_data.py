import pandas as pd
# 相对路径读取csv
df = pd.read_csv("../dataset/sample_behavior.csv")
print("====原始数据====")
print(df)

# 1. 时间戳转datetime
df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
# 2. 行为类型映射注释
behavior_map = {
    1: "浏览",
    2: "收藏",
    3: "加购",
    4: "购买"
}
df['behavior_name'] = df['behavior_type'].map(behavior_map)

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
pv = len(df[df["behavior_type"] == 1])      # 浏览量PV
uv = df["user_id"].nunique()                # 独立用户UV
fav_cnt = len(df[df["behavior_type"] == 2]) # 收藏数量
cart_cnt = len(df[df["behavior_type"] == 3])# 加购数量
buy_cnt = len(df[df["behavior_type"] == 4]) # 购买行为次数

# 转化率
cart_rate = cart_cnt / pv if pv != 0 else 0
buy_rate = buy_cnt / pv if pv != 0 else 0

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
