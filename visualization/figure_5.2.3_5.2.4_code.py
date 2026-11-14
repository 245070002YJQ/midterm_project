
# -*- coding: utf-8 -*-
"""
15城CityWalk交通 × 商业可视化升级版

直接读取已生成的：
figure2_transport_commercial/figure2_merged_analysis.xlsx

自动覆盖：
1. figure2A_scatter.png
2. figure2B_city_ranking.png
3. figure2_editable.pptx
4. figure2_merged_analysis.xlsx

保留300景点原始合并明细。
"""

from pathlib import Path
import math
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE


# ==========================================
# 1. 文件路径
# ==========================================

ROOT = Path(__file__).resolve().parent

OUT = ROOT / "figure2_transport_commercial"

EXCEL = OUT / "figure2_merged_analysis.xlsx"

if not EXCEL.exists():
    raise FileNotFoundError(
        f"未找到上次的合并数据：{EXCEL}"
    )


# ==========================================
# 2. 读取300景点合并数据
# ==========================================

df = pd.read_excel(
    EXCEL,
    sheet_name="300景点合并数据",
    engine="openpyxl"
)

need = {
    "城市",
    "景点编码",
    "景点名称",
    "metro_valid",
    "metro_distance_m",
    "500米商业总数"
}

missing = need - set(df.columns)

if missing:
    raise ValueError(
        f"缺少必要字段：{sorted(missing)}"
    )

df["城市"] = df["城市"].astype(str).str.strip()

df["metro_valid"] = (
    df["metro_valid"]
    .astype(str)
    .str.strip()
    .str.lower()
    .isin(["true", "1", "yes"])
)

df["metro_distance_m"] = pd.to_numeric(
    df["metro_distance_m"],
    errors="coerce"
)

df["500米商业总数"] = pd.to_numeric(
    df["500米商业总数"],
    errors="coerce"
)

if (
    len(df) != 300
    or df["城市"].nunique() != 15
    or not (df.groupby("城市").size() == 20).all()
):
    raise ValueError(
        "必须是15城、每城20个景点，共300行。"
    )

if df.duplicated(["城市", "景点编码"]).any():
    raise ValueError("城市+景点编码出现重复。")

if (
    df["500米商业总数"].isna().any()
    or (df["500米商业总数"] < 0).any()
):
    raise ValueError("商业POI数量有缺失或负值。")

bad_distance = (
    df.loc[df.metro_valid, "metro_distance_m"].isna()
    | (
        df.loc[df.metro_valid, "metro_distance_m"] < 0
    )
)

if bad_distance.any():
    raise ValueError(
        "存在有效地铁结果但没有有效距离。"
    )

df.loc[
    ~df.metro_valid,
    "metro_distance_m"
] = np.nan

valid = df.loc[df.metro_valid].copy()

if valid["城市"].nunique() != 15:
    raise ValueError(
        "部分城市没有有效地铁景点，"
        "需要单独处理缺失城市。"
    )


# ==========================================
# 3. 计算城市平均值及双优指标
# ==========================================

# 景点级双优分类阈值
poi_limit = 500

poi_cutoff = float(
    df["500米商业总数"].median()
)

df["双优_暂定"] = (
    df.metro_valid
    & (df.metro_distance_m <= poi_limit)
    & (df["500米商业总数"] >= poi_cutoff)
)

# 城市X和Y使用同一批有效地铁景点
city = (
    valid.groupby("城市", as_index=False)
    .agg(
        平均地铁距离米=("metro_distance_m", "mean"),
        平均商业POI条=("500米商业总数", "mean"),
        地铁有效数=("metro_valid", "sum")
    )
)

count = (
    df.groupby("城市", as_index=False)
    .agg(
        景点数=("景点编码", "size"),
        双优景点数=("双优_暂定", "sum")
    )
)

city = city.merge(
    count,
    on="城市",
    validate="one_to_one"
)

city["双优景点占比%"] = (
    city["双优景点数"] / 20 * 100
)

# 城市四象限分界：城市平均值的中位数
mx = float(
    city["平均地铁距离米"].median()
)

my = float(
    city["平均商业POI条"].median()
)


def region(x, y):

    if x <= mx and y >= my:
        return "接驳较短／商业较多"

    if x > mx and y >= my:
        return "接驳较长／商业较多"

    if x <= mx and y < my:
        return "接驳较短／商业较少"

    return "接驳较长／商业较少"


city["相对类型"] = [
    region(x, y)
    for x, y in zip(
        city["平均地铁距离米"],
        city["平均商业POI条"]
    )
]

city = city.sort_values(
    "平均地铁距离米"
).reset_index(drop=True)

rank = city.sort_values(
    ["双优景点数", "地铁有效数"],
    ascending=[False, False]
).reset_index(drop=True)


# ==========================================
# 4. 学术风配色及中文字体
# ==========================================

PALETTE = [
    "#8AA069",
    "#866CC1",
    "#AB7C98",
    "#70849E",
    "#967C63",
    "#5F7FB5",
    "#447E98",
    "#B86E6E",
    "#438F7A",
    "#C68B60",
    "#429C9A",
    "#6B78B4",
    "#9C78A7",
    "#248A92",
    "#B29A59"
]

COLORS = dict(
    zip(
        sorted(city["城市"].tolist()),
        PALETTE
    )
)

NAVY = "#243650"
MUTED = "#63748C"
GRID = "#E3E9F0"
TEAL = "#679C92"

fontset = {
    f.name
    for f in font_manager.fontManager.ttflist
}

for font in [
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "SimHei"
]:

    if font in fontset:

        plt.rcParams["font.sans-serif"] = [font]
        break

plt.rcParams["axes.unicode_minus"] = False


# ==========================================
# 5. 设置坐标轴范围和数值刻度
# ==========================================

xmin = max(
    0,
    math.floor(
        (
            city["平均地铁距离米"].min() - 80
        ) / 100
    ) * 100
)

xmax = math.ceil(
    (
        city["平均地铁距离米"].max() + 85
    ) / 100
) * 100

ymin = 0

ymax = math.ceil(
    city["平均商业POI条"].max() * 1.18 / 50
) * 50

# 横轴每100米标一个数字
xticks = list(
    range(int(xmin), int(xmax) + 1, 100)
)

# 纵轴每50条商业POI标一个数字
yticks = list(
    range(0, int(ymax) + 1, 50)
)


# ==========================================
# 6. 城市标签位置
# ==========================================

# 手动微调拥挤城市，避免文字重叠
OFFSETS = {
    "长沙": (8, 16),
    "青岛": (8, 11),
    "重庆": (-50, -18),
    "成都": (-22, -22),
    "苏州": (10, -25),
    "西安": (8, 13),
    "武汉": (-55, 17),
    "宁波": (10, 12),
    "天津": (9, 13),
    "东莞": (9, 12),
    "杭州": (-38, 15),
    "南京": (8, -20),
    "合肥": (12, -12),
    "佛山": (-49, -20),
    "郑州": (11, 12)
}

# 重点城市额外显示数字
HIGHLIGHT = {
    "青岛", "长沙", "天津", "杭州"
}


def name_label(r):

    name = r["城市"]

    if name in HIGHLIGHT:

        return (
            f"{name}  "
            f"{r['平均地铁距离米']:.0f}m / "
            f"{r['平均商业POI条']:.0f}条"
        )

    return name


OUT.mkdir(
    parents=True,
    exist_ok=True
)


# ==========================================
# 7. PNG图A：15城市四象限散点图
# ==========================================

fig = plt.figure(
    figsize=(15.0, 8.8),
    facecolor="white"
)

gs = fig.add_gridspec(
    1, 2,
    width_ratios=[2.15, 1.0],
    left=0.075,
    right=0.965,
    top=0.79,
    bottom=0.19,
    wspace=0.19
)

ax = fig.add_subplot(gs[0, 0])

side = fig.add_subplot(gs[0, 1])

side.axis("off")

ax.set_facecolor("#FBFCFE")

# 四象限背景
ax.axvspan(
    xmin, mx,
    ymin=my / ymax,
    ymax=1,
    color="#E7F3EC",
    alpha=0.85,
    zorder=0
)

ax.axvspan(
    mx, xmax,
    ymin=my / ymax,
    ymax=1,
    color="#FFF3E3",
    alpha=0.85,
    zorder=0
)

ax.axvspan(
    xmin, mx,
    ymin=0,
    ymax=my / ymax,
    color="#F2F7F9",
    alpha=0.7,
    zorder=0
)

ax.axvspan(
    mx, xmax,
    ymin=0,
    ymax=my / ymax,
    color="#F4F6F8",
    alpha=0.7,
    zorder=0
)

# 显示真实数字刻度
ax.set_xlim(xmin, xmax)
ax.set_ylim(0, ymax)

ax.set_xticks(xticks)
ax.set_yticks(yticks)

ax.tick_params(
    labelsize=10,
    colors=MUTED,
    length=0,
    pad=7
)

ax.grid(
    which="major",
    color=GRID,
    linewidth=0.8,
    zorder=1
)

# 中位数虚线
ax.axvline(
    mx,
    color=TEAL,
    linewidth=1.5,
    linestyle="--",
    zorder=2
)

ax.axhline(
    my,
    color=TEAL,
    linewidth=1.5,
    linestyle="--",
    zorder=2
)

for spine in ax.spines.values():
    spine.set_visible(False)

# X / Y轴标题
ax.set_xlabel(
    "X轴：该城市有效地铁景点的平均估算步行距离（米）",
    fontsize=11,
    color=NAVY,
    labelpad=13
)

ax.set_ylabel(
    "Y轴：同批景点周边500米平均商业POI数量（条）",
    fontsize=11,
    color=NAVY,
    labelpad=11
)

# 15个城市散点
for r in city.to_dict("records"):

    x = r["平均地铁距离米"]
    y = r["平均商业POI条"]

    name = r["城市"]

    ax.scatter(
        x, y,
        s=155,
        color=COLORS[name],
        edgecolors="white",
        linewidths=1.8,
        zorder=5
    )

    dx, dy = OFFSETS.get(
        name, (9, 9)
    )

    ax.annotate(
        name_label(r),
        (x, y),
        xytext=(dx, dy),
        textcoords="offset points",
        fontsize=(
            9 if name in HIGHLIGHT else 9.5
        ),
        color=NAVY,
        fontweight="semibold",
        ha="left",
        va="center",
        bbox=dict(
            boxstyle="round,pad=0.18",
            fc="white",
            ec="none",
            alpha=0.92
        ),
        arrowprops=dict(
            arrowstyle="-",
            color="#B0BEC8",
            linewidth=0.6
        ),
        zorder=6
    )

# 四象限说明
ax.text(
    0.015, 0.975,
    "接驳较短 / 商业较多",
    va="top",
    color="#467E70",
    fontweight="bold",
    fontsize=10,
    transform=ax.transAxes
)

ax.text(
    0.985, 0.975,
    "接驳较长 / 商业较多",
    va="top",
    ha="right",
    color="#927142",
    fontweight="bold",
    fontsize=10,
    transform=ax.transAxes
)

ax.text(
    0.015, 0.025,
    "接驳较短 / 商业较少",
    va="bottom",
    color=MUTED,
    fontsize=10,
    transform=ax.transAxes
)

ax.text(
    0.985, 0.025,
    "接驳较长 / 商业较少",
    va="bottom",
    ha="right",
    color=MUTED,
    fontsize=10,
    transform=ax.transAxes
)

# 标出两条线的具体数值
ax.text(
    0.02, 0.90,
    f"横线中位数：{my:.1f}条",
    fontsize=9,
    color="#467E70",
    transform=ax.transAxes
)

ax.text(
    0.52, 0.075,
    f"竖线中位数：{mx:.1f}米",
    fontsize=9,
    color="#467E70",
    transform=ax.transAxes
)

fig.text(
    0.075, 0.926,
    "15城CityWalk地铁接驳距离 × 周边商业丰富度",
    fontsize=21,
    weight="bold",
    color=NAVY
)

fig.text(
    0.075, 0.865,
    "每点=1座城市｜15种颜色对应右侧城市表｜"
    "虚线=15城指标中位数",
    fontsize=11,
    color=MUTED
)

# 右侧精确数值表
side.text(
    0.02, 0.985,
    "15城市具体数值",
    va="top",
    fontsize=14,
    weight="bold",
    color=NAVY,
    transform=side.transAxes
)

headers = [
    (0.09, "城市", "left"),
    (0.54, "距离(米)", "right"),
    (0.81, "商业(条)", "right"),
    (0.995, "有效", "right")
]

for x, text_, ha in headers:

    side.text(
        x, 0.910,
        text_,
        ha=ha,
        fontsize=9,
        weight="bold",
        color=MUTED,
        transform=side.transAxes
    )

for i, r in city.iterrows():

    yy = 0.868 - i * 0.052

    side.scatter(
        [0.045],
        [yy],
        s=50,
        c=COLORS[r["城市"]],
        transform=side.transAxes
    )

    values = [
        (0.09, r["城市"], "left"),
        (
            0.54,
            f"{r['平均地铁距离米']:.0f}",
            "right"
        ),
        (
            0.81,
            f"{r['平均商业POI条']:.1f}",
            "right"
        ),
        (
            0.995,
            f"{int(r['地铁有效数'])}/20",
            "right"
        )
    ]

    for xx, value, ha in values:

        side.text(
            xx, yy,
            value,
            ha=ha,
            va="center",
            fontsize=9,
            color=NAVY,
            transform=side.transAxes
        )

fig.text(
    0.075, 0.095,
    "口径：X与Y均基于同一城市有有效地铁结果的景点；"
    "商业为景点周边500米POI数量，并非全市商业数量。",
    fontsize=9,
    color=MUTED
)

fig.text(
    0.075, 0.064,
    "探索版：B组商业POI有重复计数风险；"
    "地铁有效景点较少的城市（如东莞4/20）不宜直接排名。",
    fontsize=9,
    color="#AC7854"
)

fig.savefig(
    OUT / "figure2A_scatter.png",
    dpi=220,
    facecolor="white"
)

plt.close(fig)


# ==========================================
# 8. PNG图B：双优景点占比排名
# ==========================================

fig, ax = plt.subplots(
    figsize=(13.4, 8.6),
    facecolor="white"
)

fig.subplots_adjust(
    left=0.135,
    right=0.95,
    top=0.83,
    bottom=0.15
)

pos = np.arange(15)

ax.barh(
    pos,
    rank["双优景点占比%"],
    color=[
        COLORS[n]
        for n in rank["城市"]
    ],
    height=0.62,
    zorder=3
)

ax.set_yticks(
    pos,
    rank["城市"]
)

ax.invert_yaxis()
ax.set_xlim(0, 138)

ax.set_xticks(
    [0, 20, 40, 60, 80, 100],
    ["0%", "20%", "40%", "60%", "80%", "100%"]
)

ax.set_xlabel(
    "双优景点占该城市20个景点的比例（%）",
    color=NAVY,
    fontsize=11,
    labelpad=12
)

ax.tick_params(
    length=0,
    pad=8,
    labelsize=10,
    colors=NAVY
)

ax.grid(
    axis="x",
    color=GRID,
    zorder=0
)

for spine in ax.spines.values():
    spine.set_visible(False)

# 直接写每个城市的百分比
for i, r in rank.iterrows():

    v = float(
        r["双优景点占比%"]
    )

    if v > 0:

        ax.text(
            v + 1, i,
            f"{v:.0f}%",
            va="center",
            fontsize=10,
            weight="bold",
            color=NAVY
        )

    ax.text(
        103, i,
        f"{int(r['双优景点数'])}/20"
        f"  ·  地铁有效"
        f"{int(r['地铁有效数'])}/20",
        va="center",
        fontsize=9.2,
        color=NAVY
    )

fig.text(
    0.135, 0.928,
    "15城交通—商业双优景点占比",
    fontsize=21,
    color=NAVY,
    weight="bold"
)

fig.text(
    0.135, 0.874,
    f"景点级阈值：地铁估算距离≤500米，"
    f"周边500米商业POI≥{poi_cutoff:g}条",
    fontsize=10.5,
    color=MUTED
)

fig.text(
    0.135, 0.072,
    "分母固定20个景点；"
    "无有效地铁结果不等于现实中不可达。",
    fontsize=9,
    color=MUTED
)

fig.text(
    0.135, 0.048,
    "探索版：B组商业POI统计仍待核验，"
    "双优比例并非城市综合适宜性排名。",
    fontsize=9,
    color="#AC7854"
)

fig.savefig(
    OUT / "figure2B_city_ranking.png",
    dpi=220,
    facecolor="white"
)

plt.close(fig)


# ==========================================
# 9. PowerPoint可编辑工具函数
# ==========================================

prs = Presentation()

prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)


def RGB(s):
    return RGBColor.from_string(
        s.lstrip("#")
    )


def txt(
    sl, x, y, w, h, s,
    fs=10, color=NAVY, bold=False
):

    sh = sl.shapes.add_textbox(
        Inches(x),
        Inches(y),
        Inches(w),
        Inches(h)
    )

    tf = sh.text_frame
    tf.word_wrap = False
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0

    pp = tf.paragraphs[0]
    pp.text = str(s)

    pp.font.name = "Microsoft YaHei"
    pp.font.size = Pt(fs)
    pp.font.bold = bold
    pp.font.color.rgb = RGB(color)

    return sh


def rect(sl, x, y, w, h, color):

    sh = sl.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(x),
        Inches(y),
        Inches(max(w, 0.001)),
        Inches(max(h, 0.001))
    )

    sh.fill.solid()
    sh.fill.fore_color.rgb = RGB(color)
    sh.line.fill.background()

    return sh


def dot(sl, x, y, d, color):

    sh = sl.shapes.add_shape(
        MSO_SHAPE.OVAL,
        Inches(x - d / 2),
        Inches(y - d / 2),
        Inches(d),
        Inches(d)
    )

    sh.fill.solid()
    sh.fill.fore_color.rgb = RGB(color)
    sh.line.fill.background()

    return sh


# ==========================================
# 10. PPT第一页：15城散点图
# ==========================================

sl = prs.slides.add_slide(
    prs.slide_layouts[6]
)

txt(
    sl, 0.61, 0.29, 12, 0.45,
    "15城CityWalk地铁接驳距离 × 周边商业丰富度",
    21, bold=True
)

txt(
    sl, 0.62, 0.85, 12, 0.30,
    f"每点=1座城市｜四象限分界线："
    f"{mx:.1f}米、{my:.1f}条（15城中位数）",
    10, color=MUTED
)

# 图形在PPT中的位置和大小
X = 1.03
Y = 1.85
W = 7.55
H = 4.25

cx = X + (
    (mx - xmin) / (xmax - xmin)
) * W

cy = Y + (
    (ymax - my) / (ymax - ymin)
) * H

# 四象限背景
rect(
    sl, X, Y,
    cx - X,
    cy - Y,
    "#EDF6F1"
)

rect(
    sl, cx, Y,
    X + W - cx,
    cy - Y,
    "#FFF5E9"
)

rect(
    sl, X, cy,
    cx - X,
    Y + H - cy,
    "#F4F8FA"
)

rect(
    sl, cx, cy,
    X + W - cx,
    Y + H - cy,
    "#F5F7F9"
)

# X轴数字刻度 + 纵向网格线
for v in xticks:

    xx = X + (
        (v - xmin) / (xmax - xmin)
    ) * W

    rect(
        sl, xx, Y,
        0.009, H,
        GRID
    )

    txt(
        sl,
        xx - 0.21,
        Y + H + 0.11,
        0.52,
        0.21,
        str(v),
        8,
        color=MUTED
    )

# Y轴数字刻度 + 水平网格线
for v in yticks:

    yy = Y + H - (
        v / ymax
    ) * H

    rect(
        sl, X, yy,
        W, 0.009,
        GRID
    )

    txt(
        sl,
        0.54,
        yy - 0.09,
        0.40,
        0.20,
        str(v),
        8,
        color=MUTED
    )

# 中位数虚线
for k in range(23):

    rect(
        sl,
        cx,
        Y + k * H / 23,
        0.016,
        H / 45,
        TEAL
    )

    rect(
        sl,
        X + k * W / 23,
        cy,
        W / 45,
        0.016,
        TEAL
    )

# PPT中的X、Y轴必须明确标注
txt(
    sl, 1.03, 1.51, 7.60, 0.24,
    "Y轴：同批景点周边500米平均商业POI数量（条）",
    9,
    color=NAVY,
    bold=True
)

txt(
    sl, 1.25, 6.41, 7.60, 0.25,
    "X轴：有效景点平均地铁估算步行距离（米）",
    10,
    color=NAVY,
    bold=True
)

# 四象限标题
txt(
    sl, X + 0.10, Y + 0.10,
    2.38, 0.20,
    "接驳较短 · 商业较多",
    9, color="#47816D", bold=True
)

txt(
    sl, cx + 0.13, Y + 0.10,
    2.45, 0.20,
    "接驳较长 · 商业较多",
    9, color="#987342", bold=True
)

txt(
    sl, X + 0.10, Y + H - 0.26,
    2.38, 0.20,
    "接驳较短 · 商业较少",
    9, color=MUTED
)

txt(
    sl, cx + 0.13, Y + H - 0.26,
    2.45, 0.20,
    "接驳较长 · 商业较少",
    9, color=MUTED
)

# 15个可编辑城市圆点
for r in city.to_dict("records"):

    px = X + (
        (r["平均地铁距离米"] - xmin)
        / (xmax - xmin)
    ) * W

    py = Y + H - (
        r["平均商业POI条"] / ymax
    ) * H

    dot(
        sl,
        px,
        py,
        0.125,
        COLORS[r["城市"]]
    )

    dx, dy = OFFSETS.get(
        r["城市"],
        (9, 9)
    )

    label = r["城市"]

    if r["城市"] in HIGHLIGHT:

        label = (
            r["城市"]
            + " "
            + f"{r['平均地铁距离米']:.0f}m"
        )

    xx = px + dx / 80
    yy = py - dy / 70 - 0.07

    txt(
        sl,
        xx,
        yy,
        1.38,
        0.21,
        label,
        8.5,
        bold=True
    )

# 右侧15城市精确统计
rx = 9.06

txt(
    sl,
    rx, 1.40, 3.80, 0.30,
    "15城市具体数值",
    13,
    bold=True
)

txt(
    sl,
    rx, 1.87, 3.80, 0.20,
    "城市        地铁(m)    商业(条)    有效",
    8,
    color=MUTED
)

for i, r in city.iterrows():

    yy = 2.14 + i * 0.268

    dot(
        sl,
        rx + 0.085,
        yy + 0.087,
        0.082,
        COLORS[r["城市"]]
    )

    txt(
        sl,
        rx + 0.22, yy,
        0.85, 0.21,
        r["城市"], 9
    )

    txt(
        sl,
        rx + 1.16, yy,
        0.66, 0.21,
        f"{r['平均地铁距离米']:.0f}", 9
    )

    txt(
        sl,
        rx + 2.04, yy,
        0.67, 0.21,
        f"{r['平均商业POI条']:.1f}", 9
    )

    txt(
        sl,
        rx + 2.97, yy,
        0.73, 0.21,
        f"{int(r['地铁有效数'])}/20", 9
    )

txt(
    sl,
    0.62, 7.06, 12, 0.19,
    "探索版：B商业POI数据仍可能重复计数；"
    "低有效景点城市的平均数不代表该城全部20个景点。",
    8.5,
    color="#A9754C"
)


# ==========================================
# 11. PPT第二页：双优占比排名图
# ==========================================

sl = prs.slides.add_slide(
    prs.slide_layouts[6]
)

txt(
    sl,
    0.62, 0.30, 12, 0.48,
    "15城交通—商业双优景点占比",
    21,
    bold=True
)

txt(
    sl,
    0.63, 0.86, 12, 0.30,
    f"双优标准：地铁估算距离≤500米，"
    f"周边500米商业POI≥{poi_cutoff:g}条；"
    "每城20景点",
    10,
    color=MUTED
)

BX = 1.95
BW = 8.10
BTOP = 1.62
STEP = 0.309

# 横轴百分比刻度
for t in [0, 20, 40, 60, 80, 100]:

    xx = BX + t / 100 * BW

    rect(
        sl,
        xx, 1.50,
        0.010, 4.95,
        GRID
    )

    txt(
        sl,
        xx - 0.12,
        6.50,
        0.50,
        0.22,
        f"{t}%",
        8,
        color=MUTED
    )

# 可编辑条形和百分比
for i, r in rank.iterrows():

    yy = BTOP + i * STEP

    txt(
        sl,
        0.68,
        yy,
        1.00,
        0.22,
        r["城市"],
        9,
        bold=True
    )

    pct = float(
        r["双优景点占比%"]
    )

    if pct > 0:

        rect(
            sl,
            BX,
            yy + 0.02,
            pct / 100 * BW,
            0.19,
            COLORS[r["城市"]]
        )

    txt(
        sl,
        BX + pct / 100 * BW + 0.08,
        yy,
        0.58,
        0.23,
        f"{pct:.0f}%",
        9,
        color=NAVY,
        bold=True
    )

    txt(
        sl,
        10.44,
        yy,
        2.75,
        0.23,
        f"{int(r['双优景点数'])}/20"
        f" · 地铁有效"
        f"{int(r['地铁有效数'])}/20",
        9
    )

txt(
    sl,
    3.65, 6.83,
    7, 0.22,
    "双优景点占本城市20个候选景点的比例（%）",
    9,
    color=NAVY
)

txt(
    sl,
    0.62, 7.07,
    12, 0.18,
    "探索版：商业数据待核验；"
    "无有效地铁路网结果不等于现实不可达。",
    8.5,
    color="#A9754C"
)

prs.save(
    OUT / "figure2_editable.pptx"
)


# ==========================================
# 12. 更新Excel
# ==========================================

notes = pd.DataFrame(
    [
        [
            "城市散点X轴",
            "各城市有效地铁景点的平均估算步行距离（米）",
            "平均值不包括无有效地铁路网结果的景点"
        ],
        [
            "城市散点Y轴",
            "与X轴完全同一批景点的500米周边商业POI平均数量（条）",
            "不是全市商业POI总量"
        ],
        [
            "城市四象限X线",
            f"15城市平均地铁距离中位数：{mx:.1f}米",
            "城市相对比较指标"
        ],
        [
            "城市四象限Y线",
            f"15城市平均商业数量中位数：{my:.1f}条",
            "城市相对比较指标"
        ],
        [
            "景点双优",
            f"有效地铁距离≤500米，且商业POI≥{poi_cutoff:g}条",
            "不同于城市四象限中位数"
        ],
        [
            "双优占比",
            "每城双优景点数量÷20×100%",
            "不是城市综合CityWalk适宜性排名"
        ],
        [
            "数据提醒",
            "B组商业POI可能存在重复计数",
            "现阶段只作探索，不应用作定稿结论"
        ]
    ],
    columns=[
        "指标",
        "计算定义",
        "注意事项"
    ]
)

# 写入临时Excel，完成后再替换
temp = (
    OUT / "figure2_merged_analysis_TEMP.xlsx"
)

with pd.ExcelWriter(
    temp,
    engine="xlsxwriter"
) as writer:

    df.to_excel(
        writer,
        sheet_name="300景点合并数据",
        index=False
    )

    city.to_excel(
        writer,
        sheet_name="15城城市散点统计",
        index=False
    )

    rank.to_excel(
        writer,
        sheet_name="15城双优占比",
        index=False
    )

    notes.to_excel(
        writer,
        sheet_name="统计口径",
        index=False
    )

    for sh in writer.sheets.values():

        sh.freeze_panes(1, 0)
        sh.set_column(0, 25, 18)

    writer.sheets[
        "300景点合并数据"
    ].set_column(2, 2, 32)

    writer.sheets[
        "统计口径"
    ].set_column(1, 2, 72)

try:
    os.replace(temp, EXCEL)

except PermissionError as e:
    raise PermissionError(
        "请先关闭Excel中的"
        "figure2_merged_analysis.xlsx，再重新运行。"
    ) from e


# ==========================================
# 13. 完成提示
# ==========================================

print("\n" + "=" * 55)
print("FIGURE 2 UPDATED SUCCESSFULLY")
print("=" * 55)

print("城市数量：", len(city))
print("景点数量：", len(df))
print("有效地铁景点：", len(valid))

print(
    "城市四象限中位线：",
    round(mx, 1), "米 /",
    round(my, 1), "条"
)

print(
    "景点双优阈值：",
    poi_limit, "米 /",
    poi_cutoff, "条"
)

print("\n生成目录：", OUT)

for name in [
    "figure2A_scatter.png",
    "figure2B_city_ranking.png",
    "figure2_editable.pptx",
    "figure2_merged_analysis.xlsx"
]:
    print(" -", name)
