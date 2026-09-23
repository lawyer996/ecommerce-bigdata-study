"""
run_pipeline.py — 一键跑通全链路（4 个阶段 7 个步骤）

用途：新人 clone 仓库后不需要逐个目录去翻脚本，一条命令看到全部产出。
      每步都会打印自己的运行日志，最后给出汇总表（成功/失败/耗时）。

步骤（按依赖顺序）：
    1. 数据清洗            stage1_data_analysis/clean_real_data.py
    2. KPI 与可视化        stage1_data_analysis/real_data_kpi.py
    3. 离线数仓四层(DuckDB) stage2_offline_dw/run_local_dw.py
    4. 导入 MySQL          stage1_data_analysis/load_to_mysql.py      [需 MySQL]
    5. SQL 指标分析        stage1_data_analysis/run_sql_analysis.py   [需 MySQL]
    6. 实时窗口计算        stage3_real_time/realtime_metrics.py
    7. 推荐召回与评估      stage4_recommend/recommend_cf.py

用法：
    py -3.10 run_pipeline.py                 # 全部跑
    py -3.10 run_pipeline.py --skip-mysql     # 跳过需要 MySQL 的两步
    py -3.10 run_pipeline.py --only 6         # 只跑第 6 步
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEPS = [
    ("数据清洗",             "stage1_data_analysis/clean_real_data.py",   False),
    ("KPI 与可视化",         "stage1_data_analysis/real_data_kpi.py",     False),
    ("离线数仓四层 (DuckDB)", "stage2_offline_dw/run_local_dw.py",         False),
    ("导入 MySQL",           "stage1_data_analysis/load_to_mysql.py",     True),
    ("SQL 指标分析",          "stage1_data_analysis/run_sql_analysis.py",  True),
    ("实时窗口计算",          "stage3_real_time/realtime_metrics.py",      False),
    ("推荐召回与评估",        "stage4_recommend/recommend_cf.py",          False),
]

parser = argparse.ArgumentParser(description="一键跑通电商大数据全链路")
parser.add_argument("--skip-mysql", action="store_true", help="跳过需要 MySQL 的步骤")
parser.add_argument("--only", type=int, help="只运行指定步骤序号（1-7）")
parser.add_argument("--keep-going", action="store_true", help="某步失败后继续执行后续步骤")
args = parser.parse_args()

env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")


def run(step_no, name, rel_path, needs_mysql):
    script = ROOT / rel_path
    if not script.exists():
        print(f"  跳过：脚本不存在 {rel_path}")
        return False, 0.0
    t0 = time.time()
    proc = subprocess.Popen(
        [sys.executable, "-u", str(script)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", env=env,
    )
    tail = []
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            print("  " + line)
            tail.append(line)
    code = proc.wait()
    cost = time.time() - t0
    if code != 0:
        print(f"  !! 第 {step_no} 步失败（exit={code}），末尾输出：")
        for l in tail[-8:]:
            print("     " + l)
    return code == 0, cost


print("=" * 70)
print("电商大数据全链路一键运行")
print("=" * 70)

summary = []
for i, (name, rel, needs_mysql) in enumerate(STEPS, 1):
    if args.only and i != args.only:
        continue
    if needs_mysql and args.skip_mysql:
        print(f"\n[{i}/{len(STEPS)}] {name} —— 已按 --skip-mysql 跳过")
        summary.append((i, name, "跳过", "-"))
        continue
    print(f"\n[{i}/{len(STEPS)}] {name}")
    print("-" * 70)
    ok, cost = run(i, name, rel, needs_mysql)
    summary.append((i, name, "成功" if ok else "失败", f"{cost:.1f}s"))
    if not ok and not args.keep_going:
        print("\n出现失败，已中断。加 --keep-going 可继续跑后续步骤。")
        break

print("\n" + "=" * 70)
print("运行汇总")
print("=" * 70)
print(f"{'步骤':<4}{'内容':<24}{'结果':<8}{'耗时':<8}")
for i, name, status, cost in summary:
    print(f"{i:<6}{name:<24}{status:<10}{cost:<8}")
print("""
产出文件一览：
    stage1_data_analysis/real_behavior_analysis.png   真实数据 KPI 图表
    stage1_data_analysis/sql_results.txt               SQL 指标结果快照
    stage2_offline_dw/out_dws_metrics.csv              数仓 DWS 指标宽表
    stage2_offline_dw/out_ads_*.csv                    ADS 报表（小时/类目/漏斗）
    stage3_real_time/realtime_windows.csv              实时窗口聚合结果
    stage3_real_time/realtime_metrics.png              实时大屏样式图表
    stage4_recommend/evaluation.txt                    推荐模型评估报告
    stage4_recommend/recommendations.csv               召回结果表
    stage4_recommend/hot_items.csv                     冷启动热门兜底
""")
