# 周记 · Week2（阶段1：SQL 指标统计）（进行中）

## 本周做了什么
- 安装 MySQL 8.4.9（winget），手动初始化数据目录 + 启动服务（未注册系统服务，见 scripts/start_mysql.ps1）
- 编写 `load_to_mysql.py`：建表 user_behavior（含三列索引），LOAD DATA LOCAL INFILE 导入 485,730 条
- 编写 `sql_analysis.sql`：整体指标 / 小时流量 / 转化漏斗 / 品类 TOP10 / 高频买家 / RFM 八分层
- 指标结论：UV 231,912，浏览→加购 5.95%，浏览→购买 2.57%；RFM 中"一般发展客户"占 75.7%（单日数据 R 维度失真所致）

## 踩了什么坑
- **pymysql 默认 autocommit=0**：LOAD DATA 后没 commit，连接关闭时全部回滚，下一连接查表是空的。
  教训：InnoDB 里 LOAD DATA 是事务性的；验证数据要用"新连接"查，不能只信本会话的结果
- RFM 分层命名第一版把"重要/一般"按 R 划分了，标准阿里口径应按 M 划分（重要层 = M 高），已修正
- mysqld 用 Start-Process 启动会随终端会话结束被杀，改用后台常驻任务；注册 Windows 服务需要管理员权限

## 口径备注（面试可讲）
- UserBehavior 无金额字段：GMV/客单价不可算，RFM 的 M 用"购买商品数"替代
- 单日数据 R(Recency) 用"距窗口结束的小时数"，只能区分当日活跃早晚；完整 9 天数据才有真正 R

## 下周计划
- Streamlit 四模块大屏（总览/GMV趋势→小时流量趋势/RFM分布/品类排行）
- stage1 README + 提交规范整理，打 tag v0.1
