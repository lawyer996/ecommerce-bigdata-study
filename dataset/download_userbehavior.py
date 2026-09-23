"""
download_userbehavior.py — 下载真实数据集（天池 UserBehavior 子集）

来源：阿里云天池《淘宝用户行为数据集》公开子集，Flink 官方教程镜像
      https://raw.githubusercontent.com/wuchong/my-flink-project/master/src/main/resources/UserBehavior.csv
规模：约 17.8 MB / 485,730 条真实行为（2017-11-26 单日 10 小时）
说明：完整版 1 亿条数据需在天池官网 dataset/649 登录后申请，本子集足够学习使用

用法：
    py -3.10 dataset/download_userbehavior.py            # 已存在则跳过
    py -3.10 dataset/download_userbehavior.py --force    # 强制重新下载
"""
import argparse
import urllib.request
from pathlib import Path

URL = ("https://raw.githubusercontent.com/wuchong/my-flink-project/"
       "master/src/main/resources/UserBehavior.csv")
HERE = Path(__file__).resolve().parent
DEST = HERE / "UserBehavior.csv"
MIN_SIZE = 15_000_000          # 小于 15MB 视为下载不完整

parser = argparse.ArgumentParser(description="下载天池 UserBehavior 数据集子集")
parser.add_argument("--force", action="store_true", help="已存在也重新下载")
args = parser.parse_args()

if DEST.exists() and not args.force:
    size = DEST.stat().st_size
    print(f"已存在，跳过下载：{DEST}（{size/1024/1024:.1f} MB）")
    print("如需重新下载请加 --force")
    raise SystemExit(0)

print(f"开始下载：{URL}")
print(f"保存到：{DEST}")

with urllib.request.urlopen(URL, timeout=60) as resp, open(DEST, "wb") as f:
    total = int(resp.headers.get("Content-Length") or 0)
    done = 0
    mark = 0
    while True:
        chunk = resp.read(1024 * 256)
        if not chunk:
            break
        f.write(chunk)
        done += len(chunk)
        if done // (1024 * 1024 * 5) > mark:      # 每 5MB 报一次进度
            mark = done // (1024 * 1024 * 5)
            pct = f"{done/total:.0%}" if total else "?"
            print(f"  已下载 {done/1024/1024:.1f} MB（{pct}）")

size = DEST.stat().st_size
print(f"\n下载完成：{size/1024/1024:.1f} MB")
if size < MIN_SIZE:
    raise SystemExit("文件过小，可能下载不完整，请重试或手动下载")

# 快速校验：行数与行为分布
n = 0
kinds = {}
with open(DEST, encoding="utf-8") as f:
    for line in f:
        parts = line.rstrip("\n").split(",")
        if len(parts) != 5:
            continue
        n += 1
        kinds[parts[3]] = kinds.get(parts[3], 0) + 1
print(f"数据校验：{n:,} 条，行为分布 {kinds}")
print("\n下一步：py -3.10 stage1_data_analysis/clean_real_data.py")
