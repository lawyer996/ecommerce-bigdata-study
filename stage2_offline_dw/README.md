# Stage2 · Hadoop + Hive 离线数仓

离线数仓的分层建模实现：**ODS → DWD → DWS → ADS** 四层。
提供两套等价实现：**Hive SQL（生产口径）** 与 **DuckDB 脚本（本机可跑）**。

---

## 项目简介

把原始行为日志加工成"消费友好"的指标体系，核心是**分层**：
每一层只依赖上一层，改口径只重跑对应层，原始数据永远是干净的备份。

| 层 | 定位 | 关键动作 |
|---|---|---|
| ODS | 原始数据层（Operational Data Store） | 原样装载，字段全字符串，不做任何清洗 = 数据备份 |
| DWD | 明细数据层（Data Warehouse Detail） | 类型规整、非法枚举过滤、窗口函数去重、派生时间与中文行为名 |
| DWS | 汇总数据层（Data Warehouse Summary） | 按天一行指标宽表：PV/UV/收藏/加购/购买 + 三级转化率 |
| ADS | 应用数据服务层（Application Data Service） | 三张业务报表：小时流量、类目热度、转化漏斗 |

## 技术栈

| 用途 | 技术 |
|---|---|
| 数仓 SQL（生产） | Hive SQL（动态分区、窗口函数、`from_unixtime`） |
| 本地执行 | DuckDB 1.5（嵌入式 OLAP，语法与 Hive 高度相似） |
| 调度（规划中） | Azkaban（每日凌晨跑 T+1 全链路） |

## 环境要求

- 仅跑本地版：`py -3.10 -m pip install duckdb -i https://mirrors.aliyun.com/pypi/simple/`
- 跑 Hive 版：需 Hadoop + Hive 集群（JDK8 / Hadoop 3.x / Hive 3.x），非必需

## 数据集来源

`../dataset/UserBehavior.csv`（485,730 条真实行为），经 `../stage1_data_analysis/clean_real_data.py`
清洗后为 `../dataset/clean_behavior.csv`——本地数仓脚本以它为输入。

## 部署运行步骤

```powershell
# 前置：先生成清洗后的数据集
py -3.10 ..\stage1_data_analysis\clean_real_data.py

# 本地跑通四层（无需集群，约 1 秒）→ out_dws_metrics.csv / out_ads_*.csv
py -3.10 run_local_dw.py
```

**上 Hive 集群时**（生产路径）：按 1→2→3→4 顺序执行 SQL 文件，
`1_ods` 中取消注释 `load data local inpath` 装载数据，其余依赖上一层结果。

## 核心功能

| 文件 | 层级 | 说明 |
|---|---|---|
| `1_ods_user_behavior.sql` | ODS | 外部表 + 全 string 字段，与 csv 列结构一一对应，仅"装载"不"加工" |
| `2_dwd_user_behavior.sql` | DWD | `ROW_NUMBER()` 全字段去重、合法枚举过滤、`from_unixtime` 派生 `datetime`/`dt`、`CASE` 映射中文行为名 |
| `3_dws_user_behavior_metrics.sql` | DWS | `SUM(CASE WHEN ...)` 条件聚合，一次扫表算完所有指标 + 三级转化率 |
| `4_ads_user_behavior_report.sql` | ADS | 小时流量报表 / 类目热度 TOP20 / 漏斗各层人数（独立用户口径） |
| `run_local_dw.py` | 本地 | 用 DuckDB 复刻同样四层逻辑，并**自动校验**派生时间与源文件是否一致 |

## 运行结果

```
[ODS] 原始装载完成，行数 485,730（与源文件一致，未做任何清洗）
[DWD] 清洗去重完成，行数 485,730（剔除 0 条脏数据/重复数据）
[DWD] 时间转换校验（与源文件逐小时对比）：一致 OK
[DWS] dt=2017-11-26  pv=434,349  uv=231,912  cart_rate=0.0595  buy_rate=0.0257  cart2buy_rate=0.4322
[ADS] out_ads_hourly.csv(10 行) / out_ads_category_top.csv(10 行) / out_ads_funnel.csv(3 行)
```

> DWD 剔除 0 条是因为天池数据已被官方预清洗；换成真实埋点日志，合法枚举过滤和去重
> 通常能截掉 3%~10% 的脏数据——那部分才是分层清洗的价值。

## 技术亮点

1. **两套实现、一套口径**：Hive SQL 用于生产（面对集群），DuckDB 脚本用于本地验证
   （零集群跑通），两者逻辑一一对应，上集群时只需替换方言函数。
2. **可加校验的派生字段**：`run_local_dw.py` 会把 DWD 派生出的时间与源文件逐小时比对，
   时区/格式错误在启动阶段就暴露（详见下方踩坑）。
3. **DWS 条件聚合**：一条 SQL 一次扫表算出全部指标，避免多次扫表——这是数仓最常见的性能优化点。
4. **口径分层明确**：DWS 用"次数口径"（适合跨天对比），ADS 漏斗用"独立用户口径"（适合定位问题），
   两个口径同时给出，避免汇报时被质疑数字对不上。

## 踩坑记录（面试可讲）

- **时区陷阱**：DuckDB 的 `to_timestamp()` 返回带时区的时间戳，按会话时区渲染，
  同一批数据的小时分布会整体偏移 8 小时；改用 `epoch_ms(ts*1000)` 得到本地墙上时间才与源文件一致。
  这类错误的特征是**量级正常、只是整体平移**，比直接报错更难发现，所以脚本里加了自动校验。
- **Hive 动态分区**：写入分区表前必须 `SET hive.exec.dynamic.partition.mode=nonstrict`，
  否则 `INSERT OVERWRITE ... PARTITION (dt)` 会因为分区字段来自数据本身而报错。
- **去重要用窗口函数**：`DISTINCT` 无法保留"重复中的哪一条"，用 `ROW_NUMBER() ... WHERE rn=1`
  才能稳定保留第一条，这也是面试高频考点。
