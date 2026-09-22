"""
load_to_mysql.py — 阶段1·周2：清洗后的数据导入 MySQL
前置：MySQL 已启动（本机 3306，root 空密码），库 ecommerce_analysis 已建
运行：py -3.10 load_to_mysql.py
"""
import pymysql

CONN = dict(host="127.0.0.1", user="root", password="", database="ecommerce_analysis", local_infile=True)

conn = pymysql.connect(**CONN)
cur = conn.cursor()

# 1. 建表（字段与 clean_behavior.csv 一一对应）
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

# 2. 清空旧数据（脚本可重复执行）
cur.execute("TRUNCATE TABLE user_behavior")

# 3. LOAD DATA 本地批量导入（48万条约几秒，比逐条 INSERT 快百倍）
cur.execute("""
LOAD DATA LOCAL INFILE '../dataset/clean_behavior.csv'
INTO TABLE user_behavior
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\\n'
IGNORE 1 LINES
(user_id, item_id, category_id, behavior_type, timestamp, datetime)
""")
conn.commit()  # LOAD DATA 在 InnoDB 中是事务性的，必须提交，否则连接关闭时回滚！

# 4. 验证
cur.execute("SELECT COUNT(*) FROM user_behavior")
total = cur.fetchone()[0]
cur.execute("SELECT behavior_type, COUNT(*) AS cnt FROM user_behavior GROUP BY behavior_type ORDER BY cnt DESC")
dist = cur.fetchall()
print(f"导入完成：共 {total:,} 条")
print("行为分布：")
for bt, c in dist:
    print(f"  {bt:<6}{c:>9,}")

conn.close()
