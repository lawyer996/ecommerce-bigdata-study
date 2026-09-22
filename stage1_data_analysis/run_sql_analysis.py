"""
run_sql_analysis.py — 执行 sql_analysis.sql 并将结果写入 UTF-8 文件
用途：绕开终端编码问题，把查询结果落成可读文本
"""
import pymysql

conn = pymysql.connect(host="127.0.0.1", user="root", password="", database="ecommerce_analysis")
cur = conn.cursor()

sections = [
    ("1. 整体核心指标（PV/UV/转化率）", """
        SELECT COUNT(*) total_records, COUNT(DISTINCT user_id) uv,
               SUM(behavior_type='pv') pv, SUM(behavior_type='fav') fav,
               SUM(behavior_type='cart') cart, SUM(behavior_type='buy') buy,
               ROUND(SUM(behavior_type='cart')/SUM(behavior_type='pv'),4) cart_rate,
               ROUND(SUM(behavior_type='buy')/SUM(behavior_type='pv'),4) buy_rate
        FROM user_behavior"""),
    ("2. 小时级流量分布", """
        SELECT HOUR(datetime) h, SUM(behavior_type='pv') pv,
               COUNT(DISTINCT user_id) uv, SUM(behavior_type='buy') buy
        FROM user_behavior GROUP BY h ORDER BY h"""),
    ("3. 转化漏斗（独立用户口径）", """
        SELECT COUNT(DISTINCT CASE WHEN behavior_type='pv' THEN user_id END) pv_users,
               COUNT(DISTINCT CASE WHEN behavior_type IN ('cart','fav') THEN user_id END) intent_users,
               COUNT(DISTINCT CASE WHEN behavior_type='buy' THEN user_id END) buy_users
        FROM user_behavior"""),
    ("4. 品类热度 TOP10", """
        SELECT category_id, SUM(behavior_type='pv') pv, SUM(behavior_type='buy') buy,
               ROUND(SUM(behavior_type='buy')/SUM(behavior_type='pv'),4) buy_rate
        FROM user_behavior GROUP BY category_id HAVING pv > 100
        ORDER BY pv DESC LIMIT 10"""),
    ("5. RFM 用户分层", """
        WITH rfm AS (
            SELECT user_id,
                TIMESTAMPDIFF(HOUR, MAX(CASE WHEN behavior_type='buy' THEN datetime END),
                    (SELECT MAX(datetime) FROM user_behavior)) AS r_hours,
                SUM(behavior_type='buy') AS f_cnt,
                COUNT(DISTINCT CASE WHEN behavior_type='buy' THEN item_id END) AS m_items
            FROM user_behavior GROUP BY user_id HAVING f_cnt > 0),
        scored AS (
            SELECT user_id, r_hours, f_cnt, m_items,
                CASE WHEN r_hours<=1 THEN 5 WHEN r_hours<=3 THEN 4 WHEN r_hours<=6 THEN 3 WHEN r_hours<=9 THEN 2 ELSE 1 END AS r_score,
                CASE WHEN f_cnt>=5 THEN 5 WHEN f_cnt>=3 THEN 4 WHEN f_cnt=2 THEN 3 ELSE 2 END AS f_score,
                CASE WHEN m_items>=5 THEN 5 WHEN m_items>=3 THEN 4 WHEN m_items=2 THEN 3 ELSE 2 END AS m_score
            FROM rfm)
        SELECT CASE
            WHEN r_score>=3 AND f_score>=3 AND m_score>=3 THEN '重要价值客户'
            WHEN r_score>=3 AND f_score<3  AND m_score>=3 THEN '重要发展客户'
            WHEN r_score<3  AND f_score>=3 AND m_score>=3 THEN '重要保持客户'
            WHEN r_score<3  AND f_score<3  AND m_score>=3 THEN '重要挽留客户'
            WHEN r_score>=3 AND f_score>=3 AND m_score<3  THEN '一般价值客户'
            WHEN r_score>=3 AND f_score<3  AND m_score<3  THEN '一般发展客户'
            WHEN r_score<3  AND f_score>=3 AND m_score<3  THEN '一般保持客户'
            ELSE '一般挽留客户' END AS customer_layer,
            COUNT(*) user_cnt,
            ROUND(COUNT(*)*100.0/SUM(COUNT(*)) OVER (),1) pct
        FROM scored GROUP BY customer_layer ORDER BY user_cnt DESC"""),
]

lines = []
for title, sql in sections:
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    lines.append("=" * 60)
    lines.append(title)
    lines.append("-" * 60)
    lines.append(" | ".join(cols))
    for r in rows:
        lines.append(" | ".join(str(v) for v in r))
    lines.append("")

conn.close()
with open("sql_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("done -> sql_results.txt")
