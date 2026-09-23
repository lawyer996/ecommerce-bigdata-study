-- ============================================================
-- 2. DWD 层（Data Warehouse Detail）：明细数据层
-- 核心思想：清洗、转换，产出干净、语义完整的明细表
--   - 清洗：过滤关键字段缺失的脏数据、用窗口函数去重
--   - 转换：字段类型规整（string → bigint）、timestamp → datetime、拆出日期分区 dt
--   - 丰富：增加 behavior_name 行为中文名称，下游不必再维护映射
-- 数据源：ods_user_behavior（behavior_type 是 pv/fav/cart/buy 字符串枚举）
-- 本地等价实现见同目录 run_local_dw.py
-- ============================================================

DROP TABLE IF EXISTS dwd_user_behavior;

CREATE EXTERNAL TABLE dwd_user_behavior (
    user_id       bigint,
    item_id       bigint,
    category_id   bigint,
    behavior_type string,   -- 规范化后的行为枚举 pv/fav/cart/buy
    behavior_name string,   -- 新增：行为中文名（浏览/收藏/加购/购买）
    datetime      string,   -- 新增：完整日期时间 yyyy-MM-dd HH:mm:ss
    dt            string    -- 新增：日期分区字段 yyyy-MM-dd
)
COMMENT 'DWD层：清洗转换后的用户行为明细表，按天分区'
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'
STORED AS TEXTFILE
LOCATION '/warehouse/ecommerce/dwd/dwd_user_behavior';

-- 动态分区写入（dt 由数据自身的日期决定）
SET hive.exec.dynamic.partition = true;
SET hive.exec.dynamic.partition.mode = nonstrict;

INSERT OVERWRITE TABLE dwd_user_behavior PARTITION (dt)
SELECT
    user_id,
    item_id,
    category_id,
    behavior_type,
    CASE behavior_type
        WHEN 'pv'   THEN '浏览'
        WHEN 'fav'  THEN '收藏'
        WHEN 'cart' THEN '加购'
        WHEN 'buy'  THEN '购买'
        ELSE '未知'
    END AS behavior_name,
    from_unixtime(ts, 'yyyy-MM-dd HH:mm:ss') AS datetime,
    from_unixtime(ts, 'yyyy-MM-dd')          AS dt
FROM (
    -- 子查询①：清洗 + 类型转换 + 去重
    SELECT
        CAST(user_id AS bigint)       AS user_id,
        CAST(item_id AS bigint)       AS item_id,
        CAST(category_id AS bigint)   AS category_id,
        behavior_type,
        CAST(timestamp AS bigint)     AS ts,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, item_id, category_id, behavior_type, timestamp
            ORDER BY timestamp          -- 完全重复的行只保留一条
        ) AS rn
    FROM ods_user_behavior
    WHERE user_id      IS NOT NULL AND user_id      != ''   -- 关键字段非空
      AND item_id      IS NOT NULL AND item_id      != ''
      AND category_id  IS NOT NULL AND category_id  != ''
      -- 行为类型必须是合法枚举值（脏数据/爬虫流量在这一步被拦掉）
      AND behavior_type IN ('pv', 'fav', 'cart', 'buy')
      AND timestamp IS NOT NULL AND timestamp != ''
) t
WHERE rn = 1;

-- 校验：DWD 行数应 ≤ ODS 行数
-- SELECT dt, COUNT(*) FROM dwd_user_behavior GROUP BY dt;
