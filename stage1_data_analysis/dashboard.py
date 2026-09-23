"""
dashboard.py — 阶段1·周3：Streamlit 交互式电商数据大屏

设计要点：
    1. 双数据源：优先读 MySQL（阶段1周2 已入库的表），连不上就自动回退到
       dataset/clean_behavior.csv —— 别人 clone 仓库后没装 MySQL 也能直接看大屏。
    2. 指标口径与 sql_analysis.sql 完全一致（次数口径 + 独立用户漏斗口径），
       同一套定义在 SQL 和大屏两处结果可互相校验。
    3. 侧边栏筛选（时段 / 行为类型 / 类目 TOP N）实时联动所有图表，
       指标卡带"对比全量"的 delta，一眼看出当前切片是否偏离整体。

运行：
    py -3.10 -m streamlit run stage1_data_analysis/dashboard.py
    （在仓库根目录执行；浏览器打开 http://localhost:8501）
"""
from __future__ import annotations

import warnings
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CLEAN_CSV = ROOT / "dataset" / "clean_behavior.csv"

# 与 load_to_mysql.py 保持一致，换环境只改这一处
DB_CONFIG = dict(host="127.0.0.1", port=3306, user="root", password="", charset="utf8mb4")
DB_NAME = "ecommerce_analysis"
DB_TABLE = "user_behavior"

BEHAVIOR_NAME = {"pv": "浏览", "fav": "收藏", "cart": "加购", "buy": "购买"}
BEHAVIOR_ORDER = ["pv", "fav", "cart", "buy"]
BEHAVIOR_COLOR = {"pv": "#4C78A8", "fav": "#F2A93B", "cart": "#54A24B", "buy": "#E45756"}

# RFM 八分层展示顺序（与 sql_analysis.sql 第 6 段的命名口径一致：
# "重要/一般" 按 M 划分，"价值/保持/发展/挽留" 按 R、F 组合）
RFM_ORDER = [
    "重要价值客户", "重要发展客户", "重要保持客户", "重要挽留客户",
    "一般价值客户", "一般发展客户", "一般保持客户", "一般挽留客户",
]


# ==================== 数据层 ====================
@st.cache_data(show_spinner="正在加载数据…")
def load_data() -> tuple[pd.DataFrame, str]:
    """优先 MySQL，失败回退 CSV。返回 (DataFrame, 数据源描述)。"""
    err = ""
    try:
        import pymysql

        conn = pymysql.connect(**DB_CONFIG)
        sql = (
            f"SELECT user_id, item_id, category_id, behavior_type, datetime "
            f"FROM {DB_NAME}.{DB_TABLE}"
        )
        with warnings.catch_warnings():
            # pd.read_sql 对 DBAPI2 原生连接会发 SQLAlchemy 提示，这里用原生连接足够
            warnings.simplefilter("ignore", UserWarning)
            df = pd.read_sql(sql, conn)
        conn.close()
        if len(df):
            return prepare(df), f"MySQL · {DB_NAME}.{DB_TABLE}"
        err = "表中没有数据"
    except Exception as e:  # 连不上/没建表都走回退分支
        err = f"{type(e).__name__}: {e}"

    if not CLEAN_CSV.exists():
        raise SystemExit(
            f"无法读取数据：{err}\n且本地不存在 {CLEAN_CSV}\n"
            f"请先运行：py -3.10 stage1_data_analysis/clean_real_data.py"
        )
    df = pd.read_csv(CLEAN_CSV)
    prepare(df, inplace=True)
    return df, f"CSV 回退 · dataset/clean_behavior.csv（MySQL 不可用：{err[:60]}）"


def prepare(df: pd.DataFrame, inplace: bool = False) -> pd.DataFrame:
    """统一字段类型：datetime 转时间戳、补 hour / behavior_name 两列。"""
    out = df if inplace else df.copy()
    out["datetime"] = pd.to_datetime(out["datetime"])
    out["hour"] = out["datetime"].dt.hour
    out["behavior_name"] = out["behavior_type"].map(BEHAVIOR_NAME)
    return out


# ==================== 指标层（口径与 sql_analysis.sql 对齐） ====================
def core_metrics(df: pd.DataFrame) -> dict:
    """整体核心指标：PV / UV / 加购率 / 购买率 / 人均行为次数。"""
    pv = int((df["behavior_type"] == "pv").sum())
    uv = int(df["user_id"].nunique())
    cart = int((df["behavior_type"] == "cart").sum())
    buy = int((df["behavior_type"] == "buy").sum())
    fav = int((df["behavior_type"] == "fav").sum())
    return {
        "pv": pv,
        "uv": uv,
        "fav": fav,
        "cart": cart,
        "buy": buy,
        "cart_rate": cart / pv if pv else 0.0,
        "buy_rate": buy / pv if pv else 0.0,
        "actions_per_user": len(df) / uv if uv else 0.0,
    }


def funnel(df: pd.DataFrame) -> pd.DataFrame:
    """转化漏斗（独立用户口径）：浏览用户 → 有加购/收藏的意向用户 → 购买用户。"""
    d = df
    pv_users = d.loc[d.behavior_type == "pv", "user_id"].nunique()
    intent_users = d.loc[d.behavior_type.isin(["cart", "fav"]), "user_id"].nunique()
    buy_users = d.loc[d.behavior_type == "buy", "user_id"].nunique()
    return pd.DataFrame(
        {
            "stage": ["1. 浏览用户", "2. 意向用户（加购/收藏）", "3. 购买用户"],
            "users": [pv_users, intent_users, buy_users],
            "rate": [1.0, intent_users / pv_users if pv_users else 0, buy_users / pv_users if pv_users else 0],
        }
    )


def compute_rfm(df: pd.DataFrame) -> pd.DataFrame:
    """RFM 八分层，打分边界与 sql_analysis.sql 第 6 段完全一致。

    R：距数据窗口结束的小时数（越小越新鲜）
    F：购买次数      M：购买的不同商品数（无金额字段的替代口径）
    """
    buy = df[df.behavior_type == "buy"]
    if buy.empty:
        return pd.DataFrame(columns=["customer_layer", "user_cnt", "pct"])

    window_end = df["datetime"].max()
    # 注意：这里对小时数取整（截断），与 sql_analysis.sql 的 TIMESTAMPDIFF(HOUR, ...) 语义一致。
    # 用小数小时会让边界用户（如 6.5 小时）落进更低的分档，导致大屏与 SQL 结果不一致。
    r_hours = (
        (window_end - buy.groupby("user_id")["datetime"].max()).dt.total_seconds() / 3600
    ).clip(lower=0).astype(int)
    agg = pd.DataFrame(
        {
            "r_hours": r_hours,
            "f_cnt": buy.groupby("user_id").size(),
            "m_items": buy.groupby("user_id")["item_id"].nunique(),
        }
    )

    def score_r(x):  # noqa: E704
        return 5 if x <= 1 else 4 if x <= 3 else 3 if x <= 6 else 2 if x <= 9 else 1

    def score_f(x):
        return 5 if x >= 5 else 4 if x >= 3 else 3 if x == 2 else 2

    agg["r_score"] = agg["r_hours"].map(score_r)
    agg["f_score"] = agg["f_cnt"].map(score_f)
    agg["m_score"] = agg["m_items"].map(score_f)  # 同一套分档阈值

    def layer(r: int, f: int, m: int) -> str:
        hi_r, hi_f, hi_m = r >= 3, f >= 3, m >= 3
        if hi_m:
            return "重要价值客户" if hi_r and hi_f else "重要发展客户" if hi_r else "重要保持客户" if hi_f else "重要挽留客户"
        return "一般价值客户" if hi_r and hi_f else "一般发展客户" if hi_r else "一般保持客户" if hi_f else "一般挽留客户"

    agg["customer_layer"] = [layer(r, f, m) for r, f, m in zip(agg.r_score, agg.f_score, agg.m_score)]
    out = agg.groupby("customer_layer").size().rename("user_cnt").reset_index()
    out["pct"] = out["user_cnt"] / out["user_cnt"].sum()
    out["order"] = out["customer_layer"].map({n: i for i, n in enumerate(RFM_ORDER)})
    return out.sort_values("order").drop(columns="order")


# ==================== 视图层 ====================
def kpi_row(cur: dict, base: dict) -> None:
    """一行指标卡，delta 展示"当前筛选 vs 全量"的差异。

    转化的分母是 PV：筛选掉浏览行为时 PV=0，此时比率没有意义，显示 —— 而不是误导性的 0%。
    """
    cols = st.columns(6)
    cols[0].metric("浏览量 PV", f"{cur['pv']:,}", border=True)
    cols[1].metric("独立访客 UV", f"{cur['uv']:,}", border=True)
    cols[2].metric("加购次数", f"{cur['cart']:,}", border=True)
    cols[3].metric("购买次数", f"{cur['buy']:,}", border=True)
    no_denom = cur["pv"] == 0
    for col, label, key in ((cols[4], "浏览→加购率", "cart_rate"), (cols[5], "浏览→购买率", "buy_rate")):
        col.metric(
            label,
            "—" if no_denom else f"{cur[key]:.2%}",
            delta=None if no_denom else f"{(cur[key] - base[key]) * 100:+.2f}pct",
            delta_color="off",
            border=True,
            help="当前筛选未包含「浏览」行为，转化率分母为 0，无法计算" if no_denom else "分母 = 当前筛选下的 PV 次数",
        )


def hourly_chart(df: pd.DataFrame) -> alt.Chart:
    """小时级流量趋势：PV 与 UV 双线（长表 + color 编码）。"""
    g = df.groupby("hour").agg(pv=("behavior_type", lambda s: (s == "pv").sum()), uv=("user_id", "nunique")).reset_index()
    long = g.melt("hour", ["pv", "uv"], var_name="metric", value_name="value")
    long["metric"] = long["metric"].map({"pv": "PV 浏览量", "uv": "UV 独立访客"})
    return (
        alt.Chart(long)
        .mark_line(point=alt.OverlayMarkDef(size=45), strokeWidth=2.5)
        .encode(
            x=alt.X("hour:O", title="小时（数据窗口 01:00~10:00）"),
            y=alt.Y("value:Q", title="数量"),
            color=alt.Color("metric:N", title="", scale=alt.Scale(range=["#4C78A8", "#E45756"])),
            tooltip=["hour:O", "metric:N", alt.Tooltip("value:Q", format=",")],
        )
        .properties(height=300, title="① 小时级流量趋势")
    )


def behavior_pie(df: pd.DataFrame) -> alt.Chart:
    """行为类型占比：环形图，按业务顺序固定配色。"""
    g = df.groupby("behavior_type").size().rename("cnt").reset_index()
    g["name"] = g.behavior_type.map(BEHAVIOR_NAME)
    g["order"] = g.behavior_type.map({b: i for i, b in enumerate(BEHAVIOR_ORDER)})
    g = g.sort_values("order")
    return (
        alt.Chart(g)
        .mark_arc(innerRadius=65, stroke="#fff", strokeWidth=2)
        .encode(
            theta=alt.Theta("cnt:Q"),
            color=alt.Color(
                "name:N",
                title="行为类型",
                sort=list(BEHAVIOR_NAME.values()),
                scale=alt.Scale(range=[BEHAVIOR_COLOR[b] for b in BEHAVIOR_ORDER]),
            ),
            tooltip=[alt.Tooltip("name:N", title="行为"), alt.Tooltip("cnt:Q", title="次数", format=",")],
        )
        .properties(height=300, title="② 用户行为分布（次数口径）")
    )


def funnel_chart(f: pd.DataFrame) -> alt.Chart:
    """转化漏斗：横向条形 + 相对首层的留存率标注（独立用户口径）。"""
    bars = (
        alt.Chart(f)
        .mark_bar(size=38, cornerRadiusEnd=4)
        .encode(
            y=alt.Y("stage:N", title="", sort=None),
            x=alt.X("users:Q", title="用户数"),
            color=alt.Color("stage:N", legend=None, scale=alt.Scale(range=["#B3CDE3", "#7EA6E0", "#2E5EAA"])),
            tooltip=[alt.Tooltip("stage:N", title="阶段"), alt.Tooltip("users:Q", title="用户数", format=",")],
        )
    )
    text = (
        alt.Chart(f)
        .mark_text(align="left", dx=4, fontWeight="bold")
        .encode(
            y=alt.Y("stage:N", sort=None),
            x="users:Q",
            text=alt.Text("label:N"),
        )
    )
    f = f.assign(
        label=[
            f"{u:,} 人" if i == 0 else f"{u:,} 人（{r:.1%}）"
            for i, (u, r) in enumerate(zip(f.users, f.rate))
        ]
    )
    text = text.encode(text=alt.Text("label:N"))
    return (bars + text).properties(height=230, title="③ 转化漏斗（独立用户口径）")


def hour_behavior_chart(df: pd.DataFrame) -> alt.Chart:
    """小时 × 行为类型 堆积柱：看不同时段的行为构成。"""
    g = df.groupby(["hour", "behavior_name"]).size().rename("cnt").reset_index()
    g["order"] = g.behavior_name.map({v: i for i, v in enumerate(BEHAVIOR_NAME.values())})
    g = g.sort_values("order")
    return (
        alt.Chart(g)
        .mark_bar()
        .encode(
            x=alt.X("hour:O", title="小时"),
            y=alt.Y("cnt:Q", title="行为次数", stack="zero"),
            color=alt.Color(
                "behavior_name:N",
                title="行为类型",
                sort=list(BEHAVIOR_NAME.values()),
                scale=alt.Scale(range=[BEHAVIOR_COLOR[b] for b in BEHAVIOR_ORDER]),
            ),
            tooltip=["hour:O", "behavior_name:N", alt.Tooltip("cnt:Q", format=",")],
        )
        .properties(height=300, title="④ 小时 × 行为类型构成")
    )


def category_chart(df: pd.DataFrame, topn: int) -> alt.Chart:
    """类目热度 TOP N：以 PV 排序，用颜色深浅表示购买率。"""
    g = (
        df.groupby("category_id")
        .agg(pv=("behavior_type", lambda s: (s == "pv").sum()), buy=("behavior_type", lambda s: (s == "buy").sum()))
        .reset_index()
    )
    g = g[g.pv > 100]  # 与 SQL 一致：浏览量过百的类目才有统计意义
    g["buy_rate"] = g.buy / g.pv
    g = g.sort_values("pv", ascending=False).head(topn)
    return (
        alt.Chart(g)
        .mark_bar()
        .encode(
            y=alt.Y("category_id:N", title="类目 ID", sort="-x"),
            x=alt.X("pv:Q", title="浏览量 PV"),
            color=alt.Color("buy_rate:Q", title="购买率", scale=alt.Scale(scheme="reds"), legend=alt.Legend(format=".1%")),
            tooltip=[
                alt.Tooltip("category_id:N", title="类目"),
                alt.Tooltip("pv:Q", title="PV", format=","),
                alt.Tooltip("buy:Q", title="购买", format=","),
                alt.Tooltip("buy_rate:Q", title="购买率", format=".2%"),
            ],
        )
        .properties(height=max(240, 26 * topn), title=f"⑤ 类目热度 TOP {topn}（颜色越深 = 购买率越高）")
    )


def rfm_chart(r: pd.DataFrame) -> alt.Chart:
    """RFM 八分层人数分布：重要层用实色、一般层用浅色区分。"""
    d = r.assign(is_key=r.customer_layer.str.startswith("重要"))
    d["label"] = d.apply(lambda x: f"{x.user_cnt:,} 人（{x.pct:.1%}）", axis=1)
    bars = (
        alt.Chart(d)
        .mark_bar(size=26, cornerRadiusEnd=4)
        .encode(
            y=alt.Y("customer_layer:N", title="", sort=RFM_ORDER),
            x=alt.X("user_cnt:Q", title="用户数"),
            color=alt.Color("is_key:N", legend=None, scale=alt.Scale(domain=[True, False], range=["#E45756", "#A8C5E5"])),
            tooltip=[alt.Tooltip("customer_layer:N", title="分层"), alt.Tooltip("user_cnt:Q", format=","), alt.Tooltip("pct:Q", format=".1%")],
        )
    )
    text = alt.Chart(d).mark_text(align="left", dx=4, fontSize=11).encode(
        y=alt.Y("customer_layer:N", sort=RFM_ORDER), x="user_cnt:Q", text="label:N"
    )
    return (bars + text).properties(height=300, title="⑥ RFM 用户分层（红色 = 重要客户）")


# ==================== 主流程 ====================
def main() -> None:
    st.set_page_config(page_title="电商用户行为分析大屏", page_icon="📊", layout="wide")
    st.title("📊 电商用户行为分析大屏")
    st.caption("数据源：天池《淘宝用户行为数据集》子集 · 2017-11-26 01:00~10:00 · 48.6 万条真实行为")

    df, source = load_data()
    base = core_metrics(df)

    # ---- 侧边栏：筛选（所有图表联动） ----
    with st.sidebar:
        st.header("🎛 筛选条件")
        hours = st.slider("时段范围（小时）", 0, 23, (int(df.hour.min()), int(df.hour.max())))
        behaviors = st.multiselect(
            "行为类型",
            options=BEHAVIOR_ORDER,
            default=BEHAVIOR_ORDER,
            format_func=lambda b: f"{BEHAVIOR_NAME[b]}（{b}）",
        )
        topn = st.slider("类目 TOP N", 5, 20, 10)
        st.divider()
        st.caption("**数据源**")
        st.write(source)
        st.caption(f"总行数 {len(df):,} · 独立用户 {base['uv']:,}")
        st.divider()
        st.caption(
            "口径说明：转化率 = 行为次数 / PV 次数；漏斗为独立用户口径；"
            "RFM 的 M 用「购买商品数」替代（数据集无金额字段）。"
        )

    cur = df[(df.hour >= hours[0]) & (df.hour <= hours[1])]
    if behaviors:
        cur = cur[cur.behavior_type.isin(behaviors)]
    if cur.empty:
        st.warning("当前筛选条件下没有数据，请放宽筛选范围。")
        return
    if "pv" not in behaviors:
        st.info("当前筛选未包含「浏览(pv)」行为，转化率类指标的分母为 0，已显示为 —。想看转化率请勾选浏览。")

    # ---- 指标卡 ----
    kpi_row(core_metrics(cur), base)
    st.caption(
        f"当前筛选：{hours[0]}:00~{hours[1]}:59 · {len(behaviors)} 类行为 · "
        f"命中 {len(cur):,} 行（占全量 {len(cur) / len(df):.1%}）"
    )

    # ---- 图表 ----
    c1, c2 = st.columns([3, 2])
    c1.altair_chart(hourly_chart(cur), width="stretch")
    c2.altair_chart(behavior_pie(cur), width="stretch")

    c3, c4 = st.columns([2, 3])
    c3.altair_chart(funnel_chart(funnel(cur)), width="stretch")
    c4.altair_chart(hour_behavior_chart(cur), width="stretch")

    c5, c6 = st.columns([3, 2])
    c5.altair_chart(category_chart(cur, topn), width="stretch")
    c6.altair_chart(rfm_chart(compute_rfm(cur)), width="stretch")

    # ---- 明细与导出 ----
    with st.expander(f"📄 查看筛选后明细（{len(cur):,} 行，最多显示 1000 行）"):
        st.dataframe(
            cur[["user_id", "item_id", "category_id", "behavior_name", "datetime"]].head(1000),
            width="stretch",
            hide_index=True,
        )
        st.download_button(
            "⬇ 导出筛选结果 CSV",
            data=cur[["user_id", "item_id", "category_id", "behavior_type", "datetime"]]
            .to_csv(index=False)
            .encode("utf-8-sig"),
            file_name="behavior_filtered.csv",
            mime="text/csv",
        )

    st.caption(
        "运行命令：`py -3.10 -m streamlit run stage1_data_analysis/dashboard.py` · "
        "指标口径与 `sql_analysis.sql` 一致，可与 `sql_results.txt` 交叉校验。"
    )


if __name__ == "__main__":
    main()
