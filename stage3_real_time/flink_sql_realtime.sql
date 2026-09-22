-- ============================================================
-- Flink SQL 版实时指标（集群版对照，本地无 Flink 时仅供学习阅读）
-- 与 realtime_metrics.py 的模拟逻辑一一对应
--
-- 架构：Kafka(ods_user_behavior topic) → Flink SQL → Redis/MySQL 大屏
-- ============================================================

-- 1. 定义 Kafka 数据源表（对应模拟脚本里的 deque 消息队列）
CREATE TABLE kafka_user_behavior (
    user_id       STRING,
    item_id       STRING,
    category_id   STRING,
    behavior_type INT,
    ts            TIMESTAMP(3),
    -- 行为时间是"事件时间"：以事件实际发生时间为准，而不是数据到达时间
    WATERMARK FOR ts AS ts - INTERVAL '5' SECOND   -- 允许5秒乱序
) WITH (
    'connector' = 'kafka',
    'topic' = 'ods_user_behavior',
    'properties.bootstrap.servers' = 'kafka-1:9092',
    'scan.startup.mode' = 'latest-offset',
    'format' = 'json'
);

-- 2. 5分钟滚动窗口聚合（对应模拟脚本里的 while 循环 + 窗口触发）
-- 窗口表值函数（Windowing TVF）是 Flink 1.13+ 的推荐写法
INSERT INTO redis_realtime_metrics
SELECT
    window_start,
    window_end,
    COUNT(*)                                  AS pv,          -- 浏览量（含所有行为）
    COUNT(DISTINCT user_id)                   AS uv,          -- 独立访客
    SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS buy_cnt,
    -- 实时成交金额可再 JOIN 商品维表得到（维度关联，实时数仓的常见操作）
    SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END)
      / COUNT(*)                              AS buy_rate     -- 实时购买占比
FROM TABLE(
    TUMBLE(TABLE kafka_user_behavior, DESCRIPTOR(ts), INTERVAL '5' MINUTE)
)
GROUP BY window_start, window_end;

-- ============================================================
-- 解读（面试常问）：
-- 1. Watermark（水位线）：窗口要等"水位线越过窗口末端"才触发，用来容忍
--    网络延迟导致的乱序数据。设5秒=宁可结果晚5秒出，也不能漏算晚到的事件。
-- 2. TUMBLE 滚动窗口：窗口不重叠，每5分钟出一次完整结果；
--    若要看"最近30分钟滑动趋势"则改用 HOP(..., INTERVAL '1' MINUTE, INTERVAL '30' MINUTE)。
-- 3. 状态管理：Flink 会在 RocksDB 状态后端里保存窗口内未触发的事件，
--    任务重启可从 checkpoint 恢复——这是它比"自己写个字典计数"强的根本原因。
-- 4. 与 Stage2 的关系：实时链路算"当天累计+当前窗口"，离线链路每天凌晨
--    用全量数据重算修正，两者对账保证数据质量（Lambda 架构思想）。
-- ============================================================
