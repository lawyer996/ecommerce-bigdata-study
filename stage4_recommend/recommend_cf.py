"""
recommend_cf.py — Stage4 推荐系统：协同过滤（本地可运行版）

真实架构（本脚本模拟的对象）：
    行为数据 → 召回（Candidate Generation）→ 排序（Ranking）→ Top-N 推荐

本脚本实现两个最经典的召回算法：
    1. UserCF（基于用户协同过滤）：和我相似的人喜欢什么，就推荐什么
    2. ItemCF（基于物品协同过滤）：和我买过的东西相似的东西，就推荐什么
评分权重：浏览=1，收藏=2，加购=3，购买=4（行为越重，兴趣越强）
"""
import numpy as np
import pandas as pd

BEHAVIOR_WEIGHT = {1: 1, 2: 2, 3: 3, 4: 4}

df = pd.read_csv("../dataset/sample_behavior.csv")
df["weight"] = df["behavior_type"].map(BEHAVIOR_WEIGHT)

# ---------- 1. 构建用户-商品评分矩阵 R[user, item] ----------
R = df.pivot_table(index="user_id", columns="item_id",
                   values="weight", aggfunc="sum", fill_value=0)
R = R.reindex(sorted(R.columns), axis=1)
print("========== 用户-商品评分矩阵（行=用户，列=商品，值=兴趣权重）==========")
print(R.to_string())

def cosine_sim(M, axis):
    """余弦相似度。axis=1 算用户间相似度，axis=0 管商品间相似度"""
    norm = np.linalg.norm(M, axis=axis, keepdims=True)
    norm[norm == 0] = 1e-9
    Mn = M / norm
    return Mn @ Mn.T if axis == 1 else Mn.T @ Mn

Rm = R.values.astype(float)

# ---------- 2. UserCF：用户相似度 + 相似用户的兴趣加权 ----------
user_sim = cosine_sim(Rm, axis=1)               # (n_users, n_users)
np.fill_diagonal(user_sim, 0)                   # 排除自己
user_names, item_names = list(R.index), list(R.columns)

# 预测分数 = 相似度加权平均（只对"没交互过的商品"做推荐）
user_scores = user_sim @ Rm
seen = Rm > 0

def top_n(scores, user_idx, names, n=3):
    """取该用户未交互过的商品中分数最高的 Top-N"""
    row = scores[user_idx].copy()
    row[seen[user_idx]] = -1                    # 已交互过的不再推荐
    order = np.argsort(row)[::-1][:n]
    return [(names[i], row[i]) for i in order if row[i] > 0]

print("\n========== UserCF 推荐（和你相似的人还喜欢什么）==========")
print("用户间余弦相似度矩阵：")
print(pd.DataFrame(user_sim.round(3), index=user_names, columns=user_names).to_string())
for u_idx, u in enumerate(user_names):
    rec = top_n(user_scores, u_idx, item_names)
    rec_str = ", ".join(f"{it}(分数{float(s):.2f})" for it, s in rec) if rec else "无（兴趣已被覆盖/无相似用户）"
    print(f"用户 {u} 的推荐：{rec_str}")

# ---------- 3. ItemCF：商品相似度 + 已交互商品的相似商品 ----------
item_sim = cosine_sim(Rm, axis=0)               # (n_items, n_items)
np.fill_diagonal(item_sim, 0)
item_scores = Rm @ item_sim                     # 已喜欢商品 × 商品相似度 → 推荐分

print("\n========== ItemCF 推荐（买过A的人大多也买了B）==========")
print("商品间余弦相似度矩阵：")
print(pd.DataFrame(item_sim.round(3), index=item_names, columns=item_names).to_string())
for u_idx, u in enumerate(user_names):
    rec = top_n(item_scores, u_idx, item_names)
    rec_str = ", ".join(f"{it}(分数{float(s):.2f})" for it, s in rec) if rec else "无"
    print(f"用户 {u} 的推荐：{rec_str}")

# ---------- 4. 落地推荐结果表（模拟线上召回结果写入 Redis） ----------
rows = []
for u_idx, u in enumerate(user_names):
    for algo, scores in [("UserCF", user_scores), ("ItemCF", item_scores)]:
        for rank, (it, s) in enumerate(top_n(scores, u_idx, item_names, n=3), 1):
            rows.append({"user_id": u, "algorithm": algo, "rank": rank, "item_id": it, "score": round(float(s), 3)})
pd.DataFrame(rows).to_csv("recommendations.csv", index=False, encoding="utf-8-sig")

# ---------- 5. 分析解读 ----------
print("""
========== 分析解读 ==========
1. UserCF vs ItemCF 的适用场景（面试高频题）：
   - UserCF：适合用户少、兴趣发散的场景（新闻、资讯），推荐"同人群热点"
   - ItemCF：适合商品多、兴趣稳定的场景（电商、视频），可解释性强
     ——"因为你买过203，猜你喜欢206"，客服和运营都能讲清楚理由
2. 本样本只有 10 条记录、6 个商品，相似度矩阵非常稀疏，很多用户拿不到
   推荐（无共同交互 = 余弦相似度为 0）。真实场景会引入：
   - 更多行为数据（百万级），相似度才有区分度
   - 热门兜底策略（排行榜）填充无结果用户 —— 冷启动方案
3. 评分权重 1/2/3/4 是最朴素的行为建模。工业界还会考虑：
   时间衰减（上周的浏览不如今天的浏览值钱）、行为类型分开建模、负反馈（点了不买）。
4. 生产链路中本脚本的定位是"召回层"：先从百万商品里快速捞出几百个候选，
   再交给排序模型（LR → GBDT → 深度学习 DNN）精排，最后按业务规则重排
   （去重、打散、广告位插入）后才展示给用户。
5. 推荐结果已保存 recommendations.csv（user_id, algorithm, rank, item_id, score），
   对应线上"离线召回 → 写入 Redis → 线上秒级读取"的落地方式。
""")
