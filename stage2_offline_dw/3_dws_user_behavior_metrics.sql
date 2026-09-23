-- ============================================================
-- 3. DWS 层（Data Warehouse Summary）：汇总数据层
-- 核心思想：聚合计算 PV/UV/转化率，生成指标宽表，供报表/BI 直接取数
-- 一行 = 一个日期（dt）的指标快照，报表层无需再碰明细数据
-- 数据源：dwd_user_behavior
-- 本地等价实现见同目录 run_local_dw.py
-- ============================================================

DROP TABLE IF EXISTS dws_user_behavior_metrics;

CREATE EXTERNAL TABLE dws_user_behavior_metrics (
    dt            string,         -- 日期
    pv            bigint,         -- 浏览量（Page View）
    uv            bigint,         -- 独立访客数（Unique Visitor）
    fav_cnt       bigint,         -- 收藏次数
    cart_cnt      bigint,         -- 加购次数
    buy_cnt       bigint,         -- 购买次数
    buy_users     bigint,         -- 购买用户数（独立用户口径）
    cart_rate     decimal(10,4),  -- 浏览→加购转化率（次数口径）
    buy_rate      decimal(10,4),  -- 浏览→购买转化率（次数口径）
    cart2buy_rate decimal(10,4)   -- 加购→购买转化率（分母是加购数）
)
COMMENT 'DWS层：按天聚合的用户行为指标宽表'
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'
STORED AS TEXTFILE
LOCATION '/warehouse/ecommerce/dws/dws_user_behavior_metrics';

INSERT OVERWRITE TABLE dws_user_behavior_metrics
SELECT
    dt,
    -- 条件聚合：一条SQL同时算出各行为次数，避免多次扫表
    SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv,
    COUNT(DISTINCT user_id)                                 AS uv,
    SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_cnt,
    SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_cnt,
    SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_cnt,
    COUNT(DISTINCT CASE WHEN behavior_type = 'buy' THEN user_id END) AS buy_users,
    -- 转化率：口径统一为"次数/次数"，便于跨天对比
    CAST(SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END)
       / SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS decimal(10,4)) AS cart_rate,
    CAST(SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END)
       / SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS decimal(10,4)) AS buy_rate,
    CAST(SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END)
       / SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS decimal(10,4)) AS cart2buy_rate
FROM dwd_user_behavior
GROUP BY dt;

-- 校验口径：购买率量级应在个位数百分比（真实电商 1%~5%），
-- 若算出几十个百分比，通常是分母口径错了（比如用了"用户数"而非"次数"）
-- SELECT * FROM dws_user_behavior_metrics ORDER BY dt;
