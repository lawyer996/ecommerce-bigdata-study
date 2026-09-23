-- ============================================================
-- 4. ADS 层（Application Data Service）：应用报表层
-- 核心思想：把 DWS/DWD 的指标整理成"业务方拿来就能看"的报表，
--           一张表/一个查询对应一个具体的业务看板或运营决策场景
-- 数据源：dwd_user_behavior（明细）+ dws_user_behavior_metrics（指标）
-- 本地等价实现见同目录 run_local_dw.py（会把这些结果落成 csv）
-- ============================================================

-- ---------- 4.1 小时级流量报表：运营用来看"今天几点流量掉下来了" ----------
DROP TABLE IF EXISTS ads_hourly_traffic;
CREATE EXTERNAL TABLE ads_hourly_traffic (
    dt        string,
    hour      int,
    pv        bigint,
    uv        bigint,
    buy_cnt   bigint,
    buy_rate  decimal(10,4)
)
COMMENT 'ADS层：小时级流量报表'
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'
STORED AS TEXTFILE
LOCATION '/warehouse/ecommerce/ads/ads_hourly_traffic';

INSERT OVERWRITE TABLE ads_hourly_traffic
SELECT
    dt,
    HOUR(datetime)                                          AS hour,
    SUM(CASE WHEN behavior_type = 'pv'  THEN 1 ELSE 0 END)   AS pv,
    COUNT(DISTINCT user_id)                                  AS uv,
    SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END)   AS buy_cnt,
    CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END)
       / SUM(CASE WHEN behavior_type = 'pv'  THEN 1 ELSE 0 END) AS decimal(10,4)) AS buy_rate
FROM dwd_user_behavior
GROUP BY dt, HOUR(datetime);

-- ---------- 4.2 类目热度报表：选品/招商看"哪些类目流量高但成交差" ----------
DROP TABLE IF EXISTS ads_category_rank;
CREATE EXTERNAL TABLE ads_category_rank (
    category_id bigint,
    pv          bigint,
    buy_cnt     bigint,
    buy_rate    decimal(10,4)
)
COMMENT 'ADS层：类目热度TOP排行（浏览量>100的类目才有统计意义）'
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'
STORED AS TEXTFILE
LOCATION '/warehouse/ecommerce/ads/ads_category_rank';

INSERT OVERWRITE TABLE ads_category_rank
SELECT category_id,
       SUM(CASE WHEN behavior_type = 'pv'  THEN 1 ELSE 0 END) AS pv,
       SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS buy_cnt,
       CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END)
          / SUM(CASE WHEN behavior_type = 'pv'  THEN 1 ELSE 0 END) AS decimal(10,4)) AS buy_rate
FROM dwd_user_behavior
GROUP BY category_id
HAVING SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END) > 100
ORDER BY pv DESC
LIMIT 20;

-- ---------- 4.3 转化漏斗报表：产品/运营定位"卡在哪一层" ----------
-- 注意：这是"独立用户"口径（有多少人走到这一层），与 DWS 的"次数"口径不同，
-- 汇报时两个口径都要给，否则容易被质疑数字对不上。
DROP TABLE IF EXISTS ads_conversion_funnel;
CREATE EXTERNAL TABLE ads_conversion_funnel (
    layer_name  string,
    user_cnt    bigint
)
COMMENT 'ADS层：用户转化漏斗（独立用户口径）'
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'
STORED AS TEXTFILE
LOCATION '/warehouse/ecommerce/ads/ads_conversion_funnel';

INSERT OVERWRITE TABLE ads_conversion_funnel
SELECT '1-浏览' AS layer_name, COUNT(DISTINCT user_id) AS user_cnt
FROM dwd_user_behavior WHERE behavior_type = 'pv'
UNION ALL
SELECT '2-加购或收藏', COUNT(DISTINCT user_id)
FROM dwd_user_behavior WHERE behavior_type IN ('cart', 'fav')
UNION ALL
SELECT '3-购买', COUNT(DISTINCT user_id)
FROM dwd_user_behavior WHERE behavior_type = 'buy';
