"""
run_sql_analysis.py — 执行 sql_analysis.sql 中的全部指标查询

设计要点：SQL 只有一份（sql_analysis.sql），本脚本负责读取并逐条执行，
          避免"脚本里抄一份 SQL、文件里再放一份"的双份维护问题。
输出：stage1_data_analysis/sql_results.txt（UTF-8 结果快照，可直接提交到仓库）

运行：py -3.10 stage1_data_analysis/run_sql_analysis.py
前置：MySQL 已启动，且已执行过 load_to_mysql.py
"""
from pathlib import Path

import pymysql

HERE = Path(__file__).resolve().parent
SQL_FILE = HERE / "sql_analysis.sql"
OUT_FILE = HERE / "sql_results.txt"
DB_NAME = "ecommerce_analysis"

# ---------- 1. 解析 SQL 文件：按 ';' 切分语句，并用语句上方的标题注释命名该段 ----------
# 标题优先级：优先取 "---------- 3. xxx ----------" 这种带序号的段落标记，
# 没有标记时退化为语句上方的第一条普通注释（避免误取段落内的说明文字）
import re

MARKER = re.compile(r"^-{3,}\s*(\d+\.\s*.+?)\s*-{3,}$")
statements, cur_lines, title, first_comment = [], [], None, None
for line in SQL_FILE.read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if s.startswith("--"):
        if not cur_lines:                       # 语句还没开始 → 这条注释属于它
            body = s.lstrip("-").strip()        # 先去掉注释符 "--"，再判断内容
            m = MARKER.match(body)
            if m:
                title = m.group(1)
            elif body and not body.startswith("=") and first_comment is None:
                first_comment = body
        continue
    if not s:
        continue
    cur_lines.append(line)
    if s.endswith(";"):
        sql = "\n".join(cur_lines).rstrip().rstrip(";")
        if not sql.upper().startswith("USE "):  # USE 语句由脚本自己连库代替
            statements.append((title or first_comment or f"查询 {len(statements) + 1}", sql))
        cur_lines, title, first_comment = [], None, None

if not statements:
    raise SystemExit(f"未从 {SQL_FILE} 解析出任何查询语句")

# ---------- 2. 逐条执行 ----------
try:
    conn = pymysql.connect(host="127.0.0.1", port=3306, user="root", password="",
                           database=DB_NAME, charset="utf8mb4")
except Exception as e:
    raise SystemExit(f"连接 MySQL 失败：{e}\n请先启动数据库（scripts/start_mysql.ps1）并执行 load_to_mysql.py")

cursor = conn.cursor()
lines = []
for idx, (t, sql) in enumerate(statements, 1):
    cursor.execute(sql)
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    lines.append("=" * 64)
    lines.append(t)
    lines.append("-" * 64)
    lines.append(" | ".join(cols))
    for r in rows:
        lines.append(" | ".join("" if v is None else str(v) for v in r))
    lines.append("")
    print(f"[{idx}/{len(statements)}] {t} → {len(rows)} 行")
conn.close()

OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
print(f"\n结果已写入：{OUT_FILE}")
print("""
========== 分析解读（拿到结果后重点看三处） ==========
1. 第1段整体指标：购买率 2.57% 是真实电商的量级——简历上写"转化率"必须有分母口径。
2. 第3段漏斗（独立用户口径）：21.6万 浏览用户 → 3.5万 有意向 → 1.06万 购买，
   注意它与"行为次数口径"算出的比率不同，面试常被追问两者区别。
3. 第6段 RFM：一般发展客户占比最高（75% 量级），说明这批样本中"近期活跃但购买力弱"
   的用户是主体，运营动作应该是"提客单"而不是"拉新"。
""")
