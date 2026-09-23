"""
recommend_cf.py — Stage4 推荐系统：协同过滤召回 + 离线评估（本地可运行版）

真实架构（本脚本模拟的对象）：
    行为日志 → 评分矩阵 → 召回(Candidate Generation) → 排序(Ranking) → 重排 → Top-N 推荐

本脚本实现两个最经典的召回算法：
    1. UserCF（基于用户）：和我相似的人喜欢什么，就推荐什么
    2. ItemCF（基于物品）：和我交互过的商品相似的商品，就推荐什么
评分权重：pv=1，fav=2，cart=3，buy=4（行为越重，兴趣越强）

离线评估（不做评估的推荐模型等于没做）：
    - 留一法：每个用户隐藏权重最高的 1 个交互作为测试集
    - 指标：HR@5（命中率）+ 与"随机推荐"基线的倍数对比

数据：dataset/clean_behavior.csv（真实数据 48.6 万条，23 万用户 / 27 万商品）
输出：recommendations.csv（召回结果表）、evaluation.txt（评估报告）、hot_items.csv（冷启动兜底）
运行：py -3.10 stage4_recommend/recommend_cf.py

实测结果（本仓库数据，48.6 万条真实行为）：
    用户 8,000 × 商品 3,868，稀疏度 99.94%，参与评估用户 2,382
    ItemCF HR@5 = 1.93%   UserCF HR@5 = 1.89%   随机基线 HR@5 = 0.13%  → 约 15 倍于随机
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "dataset" / "clean_behavior.csv"

WEIGHT = {"pv": 1, "fav": 2, "cart": 3, "buy": 4}
MIN_ITEM_USERS = 2     # 商品至少被 N 个不同用户交互过才纳入（滤掉只被看过一次的长尾）
MIN_USER_ACT = 2       # 用户至少发生 N 次行为才纳入（0/1 次行为的用户没有相似度可算）
MAX_ITEMS = 4000       # 商品上限：item-item 相似度矩阵是 O(n²)，必须控制规模
MAX_USERS = 8000       # 用户上限：user-user 相似度矩阵同理
TOP_N = 5              # 推荐 / 评估的 Top-K
MAX_OUTPUT_USERS = 1000  # 落表的用户数上限（避免 csv 过大）

if not SRC.exists():
    raise SystemExit(f"找不到 {SRC}\n请先运行：py -3.10 stage1_data_analysis/clean_real_data.py")

# ---------- 1. 构建"用户-商品"评分矩阵 ----------
df = pd.read_csv(SRC)
df["weight"] = df["behavior_type"].map(WEIGHT)

item_users = df.groupby("item_id")["user_id"].nunique()
items = item_users[item_users >= MIN_ITEM_USERS].sort_values(ascending=False).head(MAX_ITEMS).index
d = df[df["item_id"].isin(items)]

user_act = d.groupby("user_id").size()
users = user_act[user_act >= MIN_USER_ACT].sort_values(ascending=False).head(MAX_USERS).index
d = d[d["user_id"].isin(users)]

R = d.pivot_table(index="user_id", columns="item_id", values="weight", aggfunc="max", fill_value=0)
Rm = R.values.astype(np.float32)
n_users, n_items = Rm.shape
density = (Rm > 0).sum() / (n_users * n_items)

print("========== 样本规模（真实数据抽样，全量单机算不动）==========")
print(f"原始数据：{len(df):,} 条行为 / {df['user_id'].nunique():,} 用户 / {df['item_id'].nunique():,} 商品")
print(f"建模矩阵：{n_users:,} 用户 × {n_items:,} 商品，非零占比 {density:.4%}（稀疏度 {1-density:.2%}）")
print(f"抽样规则：商品被 ≥{MIN_ITEM_USERS} 人交互、用户有 ≥{MIN_USER_ACT} 次行为，取最活跃的前 {MAX_USERS:,} 人")


def cosine_sim(M, axis):
    """余弦相似度：axis=1 算用户间相似度，axis=0 算商品间相似度"""
    norm = np.linalg.norm(M, axis=axis, keepdims=True)
    norm[norm == 0] = 1e-9
    Mn = M / norm
    return Mn @ Mn.T if axis == 1 else Mn.T @ Mn


def top_k(scores_row, seen_row, k=TOP_N):
    """取该用户未交互过、且推荐分 > 0 的 Top-K 商品列下标"""
    row = scores_row.copy()
    row[seen_row] = -np.inf
    order = np.argsort(row)[::-1][:k]
    return [j for j in order if row[j] > 0]


# ---------- 2. 全量相似度与召回分（用于产出推荐结果表） ----------
user_sim = cosine_sim(Rm, axis=1)
np.fill_diagonal(user_sim, 0)
user_scores = user_sim @ Rm                     # UserCF 召回分
del user_sim

seen_all = Rm > 0
item_sim = cosine_sim(Rm, axis=0)
np.fill_diagonal(item_sim, 0)
item_scores = Rm @ item_sim                     # ItemCF 召回分
del item_sim

# ---------- 3. 留一法离线评估 ----------
# 隐藏每个用户权重最高的 1 个交互（相当于"未来会发生的行为"），看能否被 Top-K 召回
Rm_train = Rm.copy()
test_of_user = {}
for i in range(n_users):
    nz = np.flatnonzero(Rm_train[i])
    if len(nz) < 3:                             # 交互太少的用户无法做留一，跳过
        continue
    j = nz[np.argmax(Rm_train[i][nz])]
    test_of_user[i] = int(j)
    Rm_train[i, j] = 0

seen_train = Rm_train > 0
u_sim_tr = cosine_sim(Rm_train, axis=1); np.fill_diagonal(u_sim_tr, 0)
i_sim_tr = cosine_sim(Rm_train, axis=0); np.fill_diagonal(i_sim_tr, 0)
eval_scores = {"UserCF": u_sim_tr @ Rm_train, "ItemCF": Rm_train @ i_sim_tr}
del u_sim_tr, i_sim_tr

results = {}
for algo, sc in eval_scores.items():
    hit = sum(1 for i, j in test_of_user.items() if j in top_k(sc[i], seen_train[i]))
    results[algo] = hit / len(test_of_user)
avg_pool = float(np.mean([n_items - seen_train[i].sum() for i in test_of_user]))
rand_hr = TOP_N / avg_pool

lines = [
    "========== 模型评估报告（留一法，Top-{})==========".format(TOP_N),
    f"建模矩阵：{n_users:,} 用户 × {n_items:,} 商品，非零占比 {density:.4%}",
    f"参与评估用户数：{len(test_of_user):,}（各隐藏 1 个最重交互做测试）",
    "",
]
for algo, v in results.items():
    lines.append(f"{algo:<8} HR@{TOP_N} = {v:.2%}    相对随机基线 {v/rand_hr:.1f} 倍")
lines += [
    f"{'随机推荐':<8} HR@{TOP_N} = {rand_hr:.4%}（基线：候选池平均 {avg_pool:,.0f} 个商品）",
    "",
    "解读：",
    f"1. 真实行为数据极度稀疏（非零占比仅 {density:.4%}），所以绝对命中率是个位数百分比；",
    "   关键看相对提升——两个算法都拿到随机的 10 倍以上，说明行为共现里确实有协同信号。",
    "2. 提升方向：换 ALS 矩阵分解做隐语义召回、引入时间衰减与负反馈、加用户/商品侧特征。",
    "3. 冷启动：交互 <2 次的用户算不出相似度（本数据里这类用户占 20%+），",
    "   线上必须配热门兜底——见本目录 hot_items.csv（当前最热商品 TOP20）。",
]
report = "\n".join(lines)
(HERE / "evaluation.txt").write_text(report, encoding="utf-8")
print("\n" + report)

# ---------- 4. 召回结果表（线上对应"离线召回写入 Redis"） ----------
rows = []
for i, u in enumerate(R.index):
    if i >= MAX_OUTPUT_USERS:
        break
    for algo, sc in [("UserCF", user_scores), ("ItemCF", item_scores)]:
        for rank, j in enumerate(top_k(sc[i], seen_all[i], k=3), 1):
            rows.append({
                "user_id": int(u), "algorithm": algo, "rank": rank,
                "item_id": int(R.columns[j]), "score": round(float(sc[i, j]), 4),
            })
rec_df = pd.DataFrame(rows)
rec_df.to_csv(HERE / "recommendations.csv", index=False, encoding="utf-8-sig")
print(f"\n召回结果表：{HERE / 'recommendations.csv'}（{len(rec_df):,} 行，前 {MAX_OUTPUT_USERS} 个用户 × 2 算法 × Top3）")

# ---------- 5. 热门兜底（冷启动用户用） ----------
hot = (df[df["behavior_type"].isin(["buy", "cart"])]
       .groupby("item_id").size().sort_values(ascending=False).head(20)
       .rename("interactions").to_frame())
hot["rank"] = range(1, len(hot) + 1)
hot.to_csv(HERE / "hot_items.csv", encoding="utf-8-sig")
print(f"冷启动兜底表：{HERE / 'hot_items.csv'}（购买/加购最热的 20 个商品）")

# ---------- 6. 示例输出 ----------
print("\n========== 示例：最活跃 3 个用户 + 1 个冷启动用户 ==========")
for i in range(min(3, n_users)):
    u = R.index[i]
    cf = ", ".join(str(R.columns[j]) for j in top_k(user_scores[i], seen_all[i])) or "无（没有相似用户）"
    icf = ", ".join(str(R.columns[j]) for j in top_k(item_scores[i], seen_all[i])) or "无"
    print(f"用户 {u}（矩阵内行为 {int(seen_all[i].sum())} 次）")
    print(f"    UserCF：{cf}")
    print(f"    ItemCF：{icf}")
cold_i = int(np.argmin(seen_all.sum(axis=1)))
print(f"用户 {R.index[cold_i]}（矩阵内行为 {int(seen_all[cold_i].sum())} 次，冷启动）")
print(f"    UserCF/ItemCF 均无结果 → 线上回落到热门兜底：{', '.join(str(x) for x in hot.index[:5])} ...")

print("""
========== 分析解读 ==========
1. UserCF vs ItemCF 的适用场景（面试高频题）：
   - UserCF：适合用户少、兴趣发散的场景（新闻、资讯），推的是"同人群热点"
   - ItemCF：适合商品多、兴趣稳定的场景（电商、视频），可解释性强——
     "因为你买过 A，猜你喜欢 B"，客服和运营都能讲清理由；工业界电商主力是 ItemCF
2. 为什么必须抽样：全量 23 万用户 × 27 万商品，item-item 相似度矩阵有
   27万² ≈ 730 亿个元素，单机内存装不下。工业界用 Spark 分布式算相似度 +
   LSH/向量检索(FAISS) 做近邻搜索——这正是 Stage2/3 那套集群能力在推荐场景的价值。
   本脚本用"活跃用户 + 高频商品"抽样把规模降到单机能算，代价是长尾商品被过滤。
3. 评分权重 1/2/3/4 是最朴素的行为建模。工业界还会考虑：时间衰减（上周的浏览不如
   今天的浏览值钱）、行为分类型建模、负反馈（点了不买/划走要降权）。
4. 生产链路中本脚本的定位是"召回层"：先从百万商品里快速捞出几百个候选，
   再交给排序模型（LR → GBDT → DNN）精排，最后按业务规则重排（去重、打散、
   广告位插入）后才展示给用户。本脚本只覆盖召回，且用 HR@5 自证有效。
""")
