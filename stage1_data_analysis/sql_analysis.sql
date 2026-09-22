-- ============================================================
-- sql_analysis.sql — 阶段1·周2：电商核心指标 SQL 统计
-- 库：ecommerce_analysis  表：user_behavior（48.6万条，2017-11-26 单日）
--
-- 口径说明（重要）：
-- UserBehavior 数据集没有订单金额字段，因此：
--   - GMV / 客单价 无法计算（需要订单金额），本脚本用"购买用户人均购买件数"近似客单量
--   - RFM 的 M(金额) 用"购买商品数"替代，业务含义为"购买广度"
-- 换成含金额的订单数据集时，只需把 m_items 换成 SUM(amount) 即可
-- ============================================================

USE ecommerce_analysis;

-- ---------- 1. 整体核心指标：PV / UV / 各行为量 / 转化率 ----------
SELECT
    COUNT(*)                                                        AS total_records,
    COUNT(DISTINCT user_id)                                         AS uv,
    SUM(behavior_type = 'pv')                                       AS pv,
    SUM(behavior_type = 'fav')                                      AS fav_cnt,
    SUM(behavior_type = 'cart')                                     AS cart_cnt,
    SUM(behavior_type = 'buy')                                      AS buy_cnt,
    ROUND(SUM(behavior_type = 'cart') / SUM(behavior_type = 'pv'), 4) AS cart_rate,
    ROUND(SUM(behavior_type = 'buy')  / SUM(behavior_type = 'pv'), 4) AS buy_rate
FROM user_behavior;

-- ---------- 2. 小时级流量分布（单日数据，按小时替代按天） ----------
SELECT
    HOUR(datetime)                                                  AS hour_of_day,
    SUM(behavior_type = 'pv')                                       AS pv,
    COUNT(DISTINCT user_id)                                         AS uv,
    SUM(behavior_type = 'buy')                                      AS buy_cnt
FROM user_behavior
GROUP BY hour_of_day
ORDER BY hour_of_day;

-- ---------- 3. 转化漏斗：浏览 → 加购+收藏 → 购买（独立用户口径） ----------
SELECT
    COUNT(DISTINCT CASE WHEN behavior_type = 'pv'   THEN user_id END) AS pv_users,
    COUNT(DISTINCT CASE WHEN behavior_type IN ('cart','fav') THEN user_id END) AS intent_users,
    COUNT(DISTINCT CASE WHEN behavior_type = 'buy'  THEN user_id END) AS buy_users
FROM user_behavior;

-- ---------- 4. 品类热度 TOP10（浏览量过百的类目才有统计意义） ----------
SELECT
    category_id,
    SUM(behavior_type = 'pv')                                         AS pv,
    SUM(behavior_type = 'buy')                                        AS buy_cnt,
    ROUND(SUM(behavior_type = 'buy') / SUM(behavior_type = 'pv'), 4)  AS buy_rate
FROM user_behavior
GROUP BY category_id
HAVING pv > 100
ORDER BY pv DESC
LIMIT 10;

-- ---------- 5. 购买力 TOP10 用户（高频买家画像） ----------
SELECT
    user_id,
    COUNT(*) AS total_actions,
    SUM(behavior_type = 'buy') AS buy_cnt
FROM user_behavior
GROUP BY user_id
ORDER BY buy_cnt DESC, total_actions DESC
LIMIT 10;

-- ---------- 6. RFM 用户分层（购买用户） ----------
-- R(Recency)：距离数据窗口结束的小时数，越小越"新鲜"
-- F(Frequency)：当日购买次数
-- M(Monetary 替代)：购买的不同商品数（无金额字段的近似口径）
-- 评分 1~5 分，3 分为界划分高/低，组合出经典 8 类客户
WITH rfm AS (
    SELECT
        user_id,
        TIMESTAMPDIFF(HOUR,
            MAX(CASE WHEN behavior_type = 'buy' THEN datetime END),
            (SELECT MAX(datetime) FROM user_behavior))                    AS r_hours,
        SUM(behavior_type = 'buy')                                        AS f_cnt,
        COUNT(DISTINCT CASE WHEN behavior_type = 'buy' THEN item_id END)  AS m_items
    FROM user_behavior
    GROUP BY user_id
    HAVING f_cnt > 0
),
scored AS (
    SELECT
        user_id, r_hours, f_cnt, m_items,
        CASE WHEN r_hours <= 1 THEN 5 WHEN r_hours <= 3 THEN 4
             WHEN r_hours <= 6 THEN 3 WHEN r_hours <= 9 THEN 2 ELSE 1 END AS r_score,
        CASE WHEN f_cnt >= 5 THEN 5 WHEN f_cnt >= 3 THEN 4
             WHEN f_cnt = 2  THEN 3 ELSE 2 END                            AS f_score,
        CASE WHEN m_items >= 5 THEN 5 WHEN m_items >= 3 THEN 4
             WHEN m_items = 2  THEN 3 ELSE 2 END                          AS m_score
    FROM rfm
)
SELECT
    CASE
        WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN '重要价值客户'
        WHEN r_score >= 3 AND f_score <  3 AND m_score >= 3 THEN '重要发展客户'
        WHEN r_score <  3 AND f_score >= 3 AND m_score >= 3 THEN '重要保持客户'
        WHEN r_score <  3 AND f_score <  3 AND m_score >= 3 THEN '重要挽留客户'
        WHEN r_score >= 3 AND f_score >= 3 AND m_score <  3 THEN '一般价值客户'
        WHEN r_score >= 3 AND f_score <  3 AND m_score <  3 THEN '一般发展客户'
        WHEN r_score <  3 AND f_score >= 3 AND m_score <  3 THEN '一般保持客户'
        ELSE '一般挽留客户'
    END AS customer_layer,
    COUNT(*) AS user_cnt,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
FROM scored
GROUP BY customer_layer
ORDER BY user_cnt DESC;

-- ---------- 7. 附：有金额数据时的 GMV / 客单价模板（换数据集即用） ----------
-- SELECT DATE(datetime) AS dt,
--        SUM(amount)                                   AS gmv,
--        COUNT(DISTINCT order_id)                      AS order_cnt,
--        COUNT(DISTINCT user_id)                       AS pay_users,
--        ROUND(SUM(amount) / COUNT(DISTINCT user_id),2) AS avg_order_value
-- FROM orders WHERE status = 'paid' GROUP BY dt;
