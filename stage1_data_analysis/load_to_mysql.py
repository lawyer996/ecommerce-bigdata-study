"""
load_to_mysql.py — 阶段1·周2：清洗后的数据导入 MySQL

流程：建库（不存在则创建）→ 建表 → 清空 → LOAD DATA 批量导入 → 新连接验证
前置：MySQL 已启动（scripts/start_mysql.ps1，本机 3306，root 空密码）
运行：py -3.10 stage1_data_analysis/load_to_mysql.py

踩坑备忘（面试可讲）：
    pymysql 默认 autocommit=0，LOAD DATA 在 InnoDB 中是事务性的，
    不 commit 的话连接一关数据全部回滚——所以本脚本显式 commit，
    并且用"另开一个连接"的方式验证，避免被同一个事务的未提交数据骗到。
"""
from pathlib import Path

import pymysql

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CSV = ROOT / "dataset" / "clean_behavior.csv"

DB_NAME = "ecommerce_analysis"
# 连接参数集中在这里，换环境只改这一处
DB_CONFIG = dict(host="127.0.0.1", port=3306, user="root", password="", charset="utf8mb4")

if not CSV.exists():
    raise SystemExit(f"找不到 {CSV}\n请先运行：py -3.10 stage1_data_analysis/clean_real_data.py")

try:
    conn = pymysql.connect(**DB_CONFIG, local_infile=True)
except Exception as e:
    raise SystemExit(
        f"连接 MySQL 失败：{e}\n"
        f"请先启动数据库（Windows 下执行 scripts/start_mysql.ps1）"
    )

cur = conn.cursor()

# ---------- 1. 建库 + 建表 ----------
cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} DEFAULT CHARACTER SET utf8mb4")
conn.select_db(DB_NAME)

cur.execute("""
CREATE TABLE IF NOT EXISTS user_behavior (
    user_id       BIGINT       NOT NULL,
    item_id       BIGINT       NOT NULL,
    category_id   BIGINT       NOT NULL,
    behavior_type VARCHAR(10)  NOT NULL COMMENT 'pv浏览/fav收藏/cart加购/buy购买',
    timestamp     BIGINT       NOT NULL,
    datetime      DATETIME     NOT NULL,
    KEY idx_behavior (behavior_type),
    KEY idx_user (user_id),
    KEY idx_datetime (datetime)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")
conn.commit()

# ---------- 2. 清空旧数据（脚本可重复执行） ----------
cur.execute("TRUNCATE TABLE user_behavior")

# ---------- 3. LOAD DATA 本地批量导入（48万条约几秒，比逐条 INSERT 快百倍） ----------
# 路径用绝对路径 + 正斜杠，MySQL 在 Windows 下同样识别
csv_path = CSV.as_posix()
cur.execute(f"""
LOAD DATA LOCAL INFILE '{csv_path}'
INTO TABLE user_behavior
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\\n'
IGNORE 1 LINES
(user_id, item_id, category_id, behavior_type, timestamp, datetime)
""")
conn.commit()   # 关键：LOAD DATA 是事务性的，不提交等于白导
cur.close()
conn.close()

# ---------- 4. 另开新连接验证（避免被未提交事务骗到） ----------
check = pymysql.connect(**DB_CONFIG)
cc = check.cursor()
cc.execute(f"SELECT COUNT(*) FROM {DB_NAME}.user_behavior")
total = cc.fetchone()[0]
cc.execute(f"""SELECT behavior_type, COUNT(*) FROM {DB_NAME}.user_behavior
               GROUP BY behavior_type ORDER BY 2 DESC""")
dist = cc.fetchall()
check.close()

print(f"========== 导入结果（库 {DB_NAME} / 表 user_behavior）==========")
print(f"新连接验证行数：{total:,}")
print("行为分布：")
for bt, c in dist:
    print(f"  {bt:<6}{c:>9,}")
if total == 0:
    raise SystemExit("导入 0 条，请检查 MySQL 的 local_infile 是否开启")
print("\n下一步：py -3.10 stage1_data_analysis/run_sql_analysis.py")
