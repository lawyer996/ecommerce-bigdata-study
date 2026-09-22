-- ============================================================
-- 2. DWD 层（Data Warehouse Detail）：明细数据层
-- 核心思想：清洗、转换，产出干净、语义完整的明细表
--   - 清洗：过滤关键字段缺失的脏数据、用窗口函数去重
--   - 转换：timestamp → datetime 日期时间、拆出日期分区字段 dt
--   - 丰富：增加 behavior_name 行为中文名称，方便下游直接使用
-- ============================================================

DROP TABLE IF EXISTS dwd_user_behavior;

CREATE EXTERNAL TABLE dwd_user_behavior (
    user_id       string,
    item_id       string,
    category_id   string,
    behavior_type int,
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
        WHEN 1 THEN '浏览'
        WHEN 2 THEN '收藏'
        WHEN 3 THEN '加购'
        WHEN 4 THEN '购买'
        ELSE '未知'
    END AS behavior_name,
    from_unixtime(timestamp, 'yyyy-MM-dd HH:mm:ss') AS datetime,
    from_unixtime(timestamp, 'yyyy-MM-dd')          AS dt
FROM (
    -- 子查询①：清洗 + 去重
    SELECT
        user_id, item_id, category_id, CAST(behavior_type AS int) AS behavior_type,
        CAST(timestamp AS bigint) AS timestamp,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, item_id, category_id, behavior_type, timestamp
            ORDER BY timestamp          -- 完全重复的行只保留一条
        ) AS rn
    FROM ods_user_behavior
    WHERE user_id  IS NOT NULL AND user_id  != ''   -- 关键字段非空
      AND item_id  IS NOT NULL AND item_id  != ''
      AND behavior_type IN ('1', '2', '3', '4')     -- 行为类型必须是合法枚举值
      AND timestamp IS NOT NULL AND timestamp != ''
) t
WHERE rn = 1;
