-- ============================================================
-- 1. ODS 层（Operational Data Store）：原始数据层
-- 核心思想：原样存放原始 csv，不做任何处理，相当于数据备份
-- 建表语句照搬 csv 的列结构，字段全部用 string，保留最原始的形态
-- ============================================================

-- 如果存在先删掉（学习环境方便重复跑；生产环境慎用 DROP）
DROP TABLE IF EXISTS ods_user_behavior;

CREATE EXTERNAL TABLE ods_user_behavior (
    user_id       string,   -- 用户ID
    item_id       string,   -- 商品ID
    category_id   string,   -- 商品类目ID
    behavior_type string,   -- 行为类型：1浏览 2收藏 3加购 4购买
    timestamp     string    -- 行为时间戳（Unix秒）
)
COMMENT 'ODS层：用户行为原始数据，与csv字段一一对应，不做任何清洗'
ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','       -- csv 逗号分隔
    LINES TERMINATED BY '\n'
STORED AS TEXTFILE
LOCATION '/warehouse/ecommerce/ods/ods_user_behavior';

-- 加载本地 csv 到 ODS 表（原样灌入，不加工）
-- load data local inpath '/opt/data/sample_behavior.csv' into table ods_user_behavior;
