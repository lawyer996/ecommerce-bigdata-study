"""
run_local_dw.py — 用 DuckDB 在本机跑通"离线数仓四层"（无需 Hadoop/Hive 集群）

为什么有这个东西：
    1_ods / 2_dwd / 3_dws / 4_ads 四个 .sql 是给 Hive 集群写的（生产口径），
    但没有集群时它们只是"能读不能跑"的文档。本脚本用 DuckDB（嵌入式 OLAP，
    语法与 Hive 高度相似）在单机上复刻同样的四层逻辑，让你**先跑通再上集群**：
    本地验证业务逻辑 → 上集群时只改 from_unixtime 这类方言差异。

四层与 Hive 文件的对应关系：
    ODS  原样装载       ← 1_ods_user_behavior.sql
    DWD  清洗去重+转换    ← 2_dwd_user_behavior.sql
    DWS  按天指标宽表     ← 3_dws_user_behavior_metrics.sql
    ADS  面向业务的报表   ← 4_ads_user_behavior_report.sql

数据：dataset/clean_behavior.csv
输出：stage2_offline_dw/out_*.csv（四层结果，可直接提交仓库作为证据）
运行：py -3.10 stage2_offline_dw/run_local_dw.py
"""
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CSV = ROOT / "dataset" / "clean_behavior.csv"

if not CSV.exists():
    raise SystemExit(f"找不到 {CSV}\n请先运行：py -3.10 stage1_data_analysis/clean_real_data.py")

con = duckdb.connect()
csv_path = CSV.as_posix()   # DuckDB 需要正斜杠路径


def show(title, sql, out_name=None, preview=12):
    """执行 SQL、打印结果，并落成 csv"""
    df = con.execute(sql).df()
    print(f"\n---------- {title} ----------")
    print(df.head(preview).to_string(index=False) if len(df) > preview else df.to_string(index=False))
    if len(df) > preview:
        print(f"... 共 {len(df):,} 行")
    if out_name:
        df.to_csv(HERE / out_name, index=False, encoding="utf-8-sig")
        print(f"已落表：{out_name}（{len(df):,} 行）")
    return df


print("=" * 64)
print("离线数仓四层本地跑通（DuckDB 模拟 Hive，口径与 *.sql 完全一致）")
print("=" * 64)

# ---------- ODS：原样装载，字段全部字符串，不做任何处理 ----------
# 对应 1_ods_user_behavior.sql：这一层就是"数据备份"，出问题随时回到这里重算
con.execute(f"""
CREATE OR REPLACE TABLE ods_user_behavior AS
SELECT CAST(user_id AS VARCHAR)       AS user_id,
       CAST(item_id AS VARCHAR)       AS item_id,
       CAST(category_id AS VARCHAR)   AS category_id,
       CAST(behavior_type AS VARCHAR) AS behavior_type,
       CAST(timestamp AS VARCHAR)     AS timestamp
FROM read_csv_auto('{csv_path}', header = true)
""")
ods_cnt = con.execute("SELECT COUNT(*) FROM ods_user_behavior").fetchone()[0]
print(f"\n[ODS] 原始装载完成，行数 {ods_cnt:,}（与源文件一致，未做任何清洗）")

# ---------- DWD：清洗 + 类型规整 + 去重 + 派生字段 ----------
# 对应 2_dwd_user_behavior.sql：窗口函数去重、行为枚举过滤、时间戳转可读时间
con.execute("""
CREATE OR REPLACE TABLE dwd_user_behavior AS
SELECT user_id, item_id, category_id, behavior_type, behavior_name, datetime, dt
FROM (
    SELECT
        CAST(user_id AS BIGINT)     AS user_id,
        CAST(item_id AS BIGINT)     AS item_id,
        CAST(category_id AS BIGINT) AS category_id,
        behavior_type,
        CASE behavior_type
            WHEN 'pv'   THEN '浏览'
            WHEN 'fav'  THEN '收藏'
            WHEN 'cart' THEN '加购'
            WHEN 'buy'  THEN '购买'
            ELSE '未知'
        END AS behavior_name,
        -- 时间转换：DuckDB 用 epoch_ms（毫秒时间戳）得到"本地墙上时间"
        -- 坑：to_timestamp() 返回 TIMESTAMP WITH TIME ZONE，按会话时区渲染，会整体偏移 8 小时；
        --     等价于 Hive 的 from_unixtime(ts, 'yyyy-MM-dd HH:mm:ss')
        strftime(epoch_ms(CAST(timestamp AS BIGINT) * 1000), '%Y-%m-%d %H:%M:%S') AS datetime,
        strftime(epoch_ms(CAST(timestamp AS BIGINT) * 1000), '%Y-%m-%d')          AS dt,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, item_id, category_id, behavior_type, timestamp
            ORDER BY timestamp
        ) AS rn
    FROM ods_user_behavior
    WHERE user_id      IS NOT NULL AND user_id      != ''
      AND item_id      IS NOT NULL AND item_id      != ''
      AND category_id  IS NOT NULL AND category_id  != ''
      AND behavior_type IN ('pv', 'fav', 'cart', 'buy')
      AND timestamp IS NOT NULL AND timestamp != ''
) t
WHERE rn = 1
""")
dwd_cnt = con.execute("SELECT COUNT(*) FROM dwd_user_behavior").fetchone()[0]
print(f"[DWD] 清洗去重完成，行数 {dwd_cnt:,}（剔除 {ods_cnt - dwd_cnt:,} 条脏数据/重复数据）")

# 校验：DWD 派生出来的时间必须与源文件的时间列完全对得上（时区/格式错误在这里暴露）
src_hourly = con.execute(f"""
SELECT EXTRACT(HOUR FROM CAST(datetime AS TIMESTAMP)) AS h, COUNT(*) AS c
FROM read_csv_auto('{csv_path}', header = true) WHERE behavior_type = 'pv' GROUP BY 1 ORDER BY 1
""").df()
dwd_hourly = con.execute("""
SELECT EXTRACT(HOUR FROM CAST(datetime AS TIMESTAMP)) AS h, COUNT(*) AS c
FROM dwd_user_behavior WHERE behavior_type = 'pv' GROUP BY 1 ORDER BY 1
""").df()
print(f"[DWD] 时间转换校验（与源文件逐小时对比）：{'一致 OK' if src_hourly.equals(dwd_hourly) else '不一致，请检查时区处理！'}")

show("DWD 明细样例（前 8 行）", """
SELECT user_id, item_id, category_id, behavior_type, behavior_name, datetime, dt
FROM dwd_user_behavior LIMIT 8
""")

# ---------- DWS：按天聚合的指标宽表 ----------
# 对应 3_dws_user_behavior_metrics.sql：条件聚合一次算出所有指标
show("DWS 指标宽表（按天，一行一天）", """
SELECT
    dt,
    SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv,
    COUNT(DISTINCT user_id)                                 AS uv,
    SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_cnt,
    SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_cnt,
    SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_cnt,
    ROUND(SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END)
        / SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END), 4) AS cart_rate,
    ROUND(SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END)
        / SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END), 4) AS buy_rate,
    ROUND(SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END)
        / SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END), 4) AS cart2buy_rate
FROM dwd_user_behavior
GROUP BY dt
ORDER BY dt
""", "out_dws_metrics.csv")

# ---------- ADS：三张面向业务的报表 ----------
# 对应 4_ads_user_behavior_report.sql
show("ADS-1 小时级流量报表（运营看流量涨跌）", """
SELECT
    EXTRACT(HOUR FROM CAST(datetime AS TIMESTAMP))           AS hour,
    SUM(CASE WHEN behavior_type = 'pv'  THEN 1 ELSE 0 END)   AS pv,
    COUNT(DISTINCT user_id)                                  AS uv,
    SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END)   AS buy_cnt,
    ROUND(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END)
        / SUM(CASE WHEN behavior_type = 'pv'  THEN 1 ELSE 0 END), 4) AS buy_rate
FROM dwd_user_behavior
GROUP BY hour
ORDER BY hour
""", "out_ads_hourly.csv")

show("ADS-2 类目热度 TOP10（选品/招商看哪些类目流量高但成交差）", """
SELECT category_id,
       SUM(CASE WHEN behavior_type = 'pv'  THEN 1 ELSE 0 END) AS pv,
       SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS buy_cnt,
       ROUND(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END)
           / SUM(CASE WHEN behavior_type = 'pv'  THEN 1 ELSE 0 END), 4) AS buy_rate
FROM dwd_user_behavior
GROUP BY category_id
HAVING SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END) > 100
ORDER BY pv DESC
LIMIT 10
""", "out_ads_category_top.csv")

show("ADS-3 转化漏斗（独立用户口径，产品看卡在哪一层）", """
SELECT '1-浏览' AS layer_name, COUNT(DISTINCT user_id) AS user_cnt,
       ROUND(COUNT(DISTINCT user_id) * 100.0
           / (SELECT COUNT(DISTINCT user_id) FROM dwd_user_behavior WHERE behavior_type = 'pv'), 2) AS pct_of_pv
FROM dwd_user_behavior WHERE behavior_type = 'pv'
UNION ALL
SELECT '2-加购或收藏', COUNT(DISTINCT user_id),
       ROUND(COUNT(DISTINCT user_id) * 100.0
           / (SELECT COUNT(DISTINCT user_id) FROM dwd_user_behavior WHERE behavior_type = 'pv'), 2)
FROM dwd_user_behavior WHERE behavior_type IN ('cart', 'fav')
UNION ALL
SELECT '3-购买', COUNT(DISTINCT user_id),
       ROUND(COUNT(DISTINCT user_id) * 100.0
           / (SELECT COUNT(DISTINCT user_id) FROM dwd_user_behavior WHERE behavior_type = 'pv'), 2)
FROM dwd_user_behavior WHERE behavior_type = 'buy'
""", "out_ads_funnel.csv")

print("""
========== 分析解读 ==========
1. 分层的意义在这里非常直观：ODS 一行没动，所有"加工"都发生在 DWD 之后。
   如果发现指标口径有问题，只需重跑 DWS/ADS；发现数据有脏值，只需重跑 DWD；
   原始 csv 永远躺在 ODS 这一层，不用重新采集。
2. DWD 的清洗不是走过场：本例源数据来自天池，已被官方预清洗，所以 DWD 行数
   与 ODS 一致（剔除 0 条）。但换成真实埋点日志，合法枚举过滤和去重通常能截掉
   3%~10% 的脏数据——那部分才是分层清洗的价值所在。
3. DWS 一行一天、ADS 一张表一个场景，这是数仓最核心的"消费友好"设计：
   报表/BI 只连 DWS/ADS，永远不查明细，才不会把集群拖垮。
4. 本脚本用的是 DuckDB（单机 OLAP）。它的 SQL 与 Hive 高度相似，差异主要在
   时间函数（Hive 的 from_unixtime vs DuckDB 的 epoch_ms/strftime）和
   分区语法。先在这里把业务逻辑跑通，再上集群改方言，能省下大量调试时间。
5. 踩坑记录（面试可讲）：时间戳转换处处是时区陷阱。DuckDB 的 to_timestamp() 返回
   TIMESTAMP WITH TIME ZONE，按会话时区渲染，同一批数据算出来的小时分布会整体
   偏移 8 小时；换成 epoch_ms() 得到"本地墙上时间"才与源文件一致。所以本脚本专门
   加了"与源文件逐小时对比"的校验——数仓里任何时间派生字段都该这样验一次，否则
   指标会静默错位，而且错得很像"对的"（量级看着正常，只是时间整体平移了）。
""")
