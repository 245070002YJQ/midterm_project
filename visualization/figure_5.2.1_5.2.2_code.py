
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import MaxNLocator
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

# =====================================================
# FIGURE 1 - CITYWALK TRANSPORT ACCESSIBILITY
# 15 Cities | Metro & Bus | Average Walking Distance
#
# Supports different column names used by Changsha
# Outputs to: figure1_avg_distance
# Existing output files will be replaced automatically
# =====================================================

# 1. PATHS
BASE = Path(__file__).resolve().parent

ROOT_OPTIONS = [
    BASE.parent / "final result",
    BASE / "final result"
]

ROOT = next((p for p in ROOT_OPTIONS if p.is_dir()), None)

if ROOT is None:
    raise FileNotFoundError(
        "找不到 final result 文件夹，"
        "请确认它与 citywalk_visualization 同级。"
    )

OUTPUT = BASE / "figure1_avg_distance"

CITIES = {
    "changsha": "长沙",
    "chengdu": "成都",
    "chongqing": "重庆",
    "dongguan": "东莞",
    "foshan": "佛山",
    "hangzhou": "杭州",
    "hefei": "合肥",
    "nanjing": "南京",
    "ningbo": "宁波",
    "qingdao": "青岛",
    "suzhou": "苏州",
    "tianjin": "天津",
    "wuhan": "武汉",
    "xian": "西安",
    "zhengzhou": "郑州"
}

# Unify different CSV column names
ALIASES = {
    "success": [
        "候选成功路网数",
        "路网成功数"
    ],
    "distance": [
        "最近站点估算总距_米",
        "最近总估算距离_米"
    ],
    "time": [
        "估算步行分钟"
    ]
}

NAVY = "#172B4D"
BLUE = "#477EBB"
TEAL = "#229D91"
GREY = "#64748B"

# 2. FONT SETTINGS
available_fonts = {
    f.name for f in font_manager.fontManager.ttflist
}

FONT = next(
    (
        f for f in [
            "Microsoft YaHei",
            "SimHei",
            "Noto Sans CJK SC",
            "PingFang SC"
        ]
        if f in available_fonts
    ),
    "DejaVu Sans"
)

plt.rcParams["font.sans-serif"] = [FONT]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42


# 3. READ CSV
def read_csv_safe(path):
    for encoding in ["utf-8-sig", "utf-8", "gb18030"]:
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError(f"无法识别文件编码: {path}")


def find_summary(city, mode):
    folder = ROOT / city / mode

    expected = folder / f"{city}_{mode}_top20_summary.csv"

    if expected.is_file():
        return expected

    files = list(folder.glob("*top20_summary.csv"))

    if len(files) == 1:
        return files[0]

    raise FileNotFoundError(
        f"{city}/{mode} 找到 {len(files)} 个Top20文件"
    )


def get_column(df, possible_names):
    for name in possible_names:
        if name in df.columns:
            return name

    raise ValueError(
        "缺少字段，尝试过: " + " / ".join(possible_names)
    )


# 4. COLLECT ALL 30 DATASETS
records = []
details = []
errors = []

print("\n开始读取15城市Metro和Bus数据")
print("数据目录:", ROOT)
print("-" * 55)

for city, cn_name in CITIES.items():

    for mode in ["metro", "bus"]:

        try:
            path = find_summary(city, mode)
            df = read_csv_safe(path)

            df.columns = (
                df.columns.astype(str).str.strip()
            )

            # Automatically recognize column aliases
            success_col = get_column(
                df, ALIASES["success"]
            )
            distance_col = get_column(
                df, ALIASES["distance"]
            )
            time_col = get_column(
                df, ALIASES["time"]
            )

            for col in ["景点编码", "景点名称"]:
                if col not in df.columns:
                    raise ValueError(f"缺少字段: {col}")

            if len(df) != 20:
                raise ValueError(
                    f"应有20个景点，实际只有{len(df)}行"
                )

            if df["景点编码"].isna().any():
                raise ValueError("存在空景点编码")

            if df["景点编码"].duplicated().any():
                raise ValueError("景点编码重复")

            # Unify to common columns
            df["路网成功数_统一"] = pd.to_numeric(
                df[success_col], errors="coerce"
            )

            df["估算总距离_米_统一"] = pd.to_numeric(
                df[distance_col], errors="coerce"
            )

            df["估算时间_分钟_统一"] = pd.to_numeric(
                df[time_col], errors="coerce"
            )

            success = df["路网成功数_统一"]
            dist = df["估算总距离_米_统一"]
            mins = df["估算时间_分钟_统一"]

            # Check values only where a route is reported
            invalid = (
                (success > 0)
                & (
                    dist.isna()
                    | mins.isna()
                    | (dist < 0)
                    | (mins < 0)
                )
            )

            if invalid.any():
                raise ValueError(
                    f"{invalid.sum()}条成功路线缺少有效距离或时间"
                )

            # Only count POIs with valid network routes
            valid = (
                (success > 0)
                & dist.notna()
                & mins.notna()
                & (dist >= 0)
                & (mins >= 0)
            )

            df["城市名称_统一"] = cn_name
            df["交通方式_统一"] = mode
            df["有效路网结果_统一"] = valid

            details.append(df)

            good = df.loc[valid]

            total = len(df)
            count = len(good)

            records.append({
                "城市": cn_name,
                "城市英文": city,
                "交通方式": mode,
                "景点总数": total,
                "有效景点数": count,
                "有效覆盖率_%": round(
                    count / total * 100, 2
                ),
                "平均距离_米": (
                    round(
                        good["估算总距离_米_统一"].mean(), 2
                    ) if count else np.nan
                ),
                "距离中位数_米": (
                    round(
                        good["估算总距离_米_统一"].median(), 2
                    ) if count else np.nan
                ),
                "平均时间_分钟": (
                    round(
                        good["估算时间_分钟_统一"].mean(), 2
                    ) if count else np.nan
                )
            })

            print(
                f"OK: {cn_name} {mode} "
                f"{count}/{total} | "
                f"距离字段: {distance_col}"
            )

        except Exception as e:
            errors.append({
                "城市": cn_name,
                "交通方式": mode,
                "错误": str(e)
            })

            print(
                f"ERROR: {cn_name} {mode}: {e}"
            )


# 5. VALIDATE BEFORE REPLACING EXISTING FILES
OUTPUT.mkdir(parents=True, exist_ok=True)

if errors:
    error_df = pd.DataFrame(errors)

    error_df.to_csv(
        OUTPUT / "figure1_read_errors.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\n数据检查未通过！")
    print(f"成功: {len(records)}/30")
    print("已保存错误报告，旧图片和Excel不会被覆盖。")

    raise SystemExit(1)

if len(records) != 30:
    raise RuntimeError(
        f"数据组数不正确: {len(records)}/30"
    )

summary = pd.DataFrame(records)
details_df = pd.concat(details, ignore_index=True)

# Ensure the same POI IDs in Metro and Bus of each city
for city_cn in CITIES.values():

    city_df = details_df[
        details_df["城市名称_统一"] == city_cn
    ]

    metro_ids = set(
        city_df.loc[
            city_df["交通方式_统一"] == "metro",
            "景点编码"
        ]
    )

    bus_ids = set(
        city_df.loc[
            city_df["交通方式_统一"] == "bus",
            "景点编码"
        ]
    )

    if metro_ids != bus_ids:
        raise RuntimeError(
            f"{city_cn} 的Metro与Bus景点编码不一致，"
            "请检查原始数据；旧图表不会覆盖。"
        )

# Remove outdated error report on success
old_error = OUTPUT / "figure1_read_errors.csv"

if old_error.exists():
    old_error.unlink()

# 6. SAVE DATA TABLES
summary.to_csv(
    OUTPUT / "figure1_city_summary.csv",
    index=False,
    encoding="utf-8-sig"
)

details_df.to_csv(
    OUTPUT / "figure1_poi_details.csv",
    index=False,
    encoding="utf-8-sig"
)

with pd.ExcelWriter(
    OUTPUT / "figure1_transport_analysis.xlsx",
    engine="xlsxwriter"
) as writer:

    for sheet_name, frame in [
        ("City Summary", summary),
        ("POI Details", details_df)
    ]:

        frame.to_excel(
            writer, sheet_name=sheet_name, index=False
        )

        worksheet = writer.sheets[sheet_name]

        worksheet.freeze_panes(1, 0)

        worksheet.set_column(
            0, len(frame.columns) - 1, 20
        )

        worksheet.autofilter(
            0, 0,
            len(frame),
            len(frame.columns) - 1
        )


# 7. PREPARE CHART DATA
def get_mode_data(mode):

    data = summary[
        (summary["交通方式"] == mode)
        & summary["平均距离_米"].notna()
    ].copy()

    return data.sort_values(
        "平均距离_米"
    ).reset_index(drop=True)


# 8. CREATE HIGH-RESOLUTION FIGURES
def make_chart(mode, title, color, filename):

    data = get_mode_data(mode)

    if data.empty:
        raise RuntimeError(f"{mode} 无有效数据")

    fig, ax = plt.subplots(figsize=(13.5, 10.5))

    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    y = np.arange(len(data))

    values = data["平均距离_米"].values

    bars = ax.barh(
        y,
        values,
        color=color,
        height=0.62,
        edgecolor="none",
        zorder=3
    )

    bars[0].set_color(NAVY)

    labels = [
        f'{r["城市"]}  '
        f'({int(r["有效景点数"])}/'
        f'{int(r["景点总数"])})'
        for _, r in data.iterrows()
    ]

    ax.set_yticks(y)
    ax.set_yticklabels(
        labels, fontsize=11, color=NAVY
    )

    ax.invert_yaxis()

    maximum = float(max(values))
    limit = maximum * 1.55 if maximum > 0 else 1

    ax.set_xlim(0, limit)

    for i, row in data.iterrows():

        distance = row["平均距离_米"]
        minutes = row["平均时间_分钟"]

        ax.text(
            distance + maximum * 0.025,
            i,
            f"{distance:,.1f} m  |  {minutes:.1f} min",
            fontsize=10,
            va="center",
            color=NAVY
        )

    ax.set_title(
        title,
        fontsize=20,
        weight="bold",
        color=NAVY,
        loc="left",
        pad=36
    )

    ax.text(
        0, 1.02,
        "CITYWALK  /  WALKING ACCESSIBILITY  /  15 CITIES",
        transform=ax.transAxes,
        fontsize=10,
        color=GREY
    )

    ax.set_xlabel(
        "平均估算步行距离（米）",
        fontsize=12,
        color=GREY,
        labelpad=14
    )

    ax.xaxis.set_major_locator(
        MaxNLocator(nbins=6)
    )

    ax.grid(
        axis="x",
        color="#E6EBF2",
        linewidth=0.8,
        zorder=0
    )

    ax.set_axisbelow(True)
    ax.tick_params(
        axis="both", length=0, pad=8
    )

    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.text(
        0.17, 0.075,
        "括号为有效景点数/总景点数；平均距离只计算有效路网路线。",
        fontsize=9.5,
        color=GREY
    )

    fig.text(
        0.17, 0.050,
        "OSM + Dijkstra；包括未完全核验的接入段，"
        "不等于真实导航步行距离。",
        fontsize=9.5,
        color=GREY
    )

    fig.subplots_adjust(
        left=0.19,
        right=0.96,
        top=0.86,
        bottom=0.15
    )

    for ext in ["png", "svg", "pdf"]:

        fig.savefig(
            OUTPUT / f"{filename}.{ext}",
            dpi=300,
            facecolor="white"
        )

    plt.close(fig)


make_chart(
    "metro",
    "15城市地铁—景点平均步行接驳距离",
    BLUE,
    "01_metro_avg_distance"
)

make_chart(
    "bus",
    "15城市公交—景点平均步行接驳距离",
    TEAL,
    "02_bus_avg_distance"
)


# 9. EDITABLE POWERPOINT
prs = Presentation()

prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)


def rgb(color):
    return RGBColor.from_string(
        color.replace("#", "")
    )


def add_text(
    slide, x, y, w, h, content,
    size=11, color=NAVY, bold=False
):

    shape = slide.shapes.add_textbox(
        Inches(x),
        Inches(y),
        Inches(w),
        Inches(h)
    )

    tf = shape.text_frame
    tf.word_wrap = False

    tf.margin_left = 0
    tf.margin_top = 0

    p = tf.paragraphs[0]
    p.text = str(content)

    p.font.name = "Microsoft YaHei"
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = rgb(color)

    return shape


def add_editable_slide(mode, title, color):

    data = get_mode_data(mode)

    if data.empty:
        return

    slide = prs.slides.add_slide(
        prs.slide_layouts[6]
    )

    add_text(
        slide, 0.7, 0.35, 12, 0.5,
        title, size=22, bold=True
    )

    add_text(
        slide, 0.72, 0.95, 12, 0.25,
        "CITYWALK / AVERAGE WALKING ACCESS DISTANCE",
        size=10, color=GREY
    )

    maximum = data["平均距离_米"].max()

    chart_x = 3.15
    chart_width = 6.50

    top = 1.43
    row_height = 0.32

    for i, row in data.iterrows():

        y = top + i * row_height

        distance = row["平均距离_米"]
        minutes = row["平均时间_分钟"]

        sample = (
            f'{int(row["有效景点数"])}/'
            f'{int(row["景点总数"])}'
        )

        add_text(
            slide, 0.72, y, 2.30, 0.27,
            f'{row["城市"]} ({sample})',
            size=10
        )

        bar_width = (
            chart_width * distance / maximum
            if maximum > 0 else 0
        )

        rectangle = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(chart_x),
            Inches(y),
            Inches(max(bar_width, 0.005)),
            Inches(0.21)
        )

        rectangle.fill.solid()

        rectangle.fill.fore_color.rgb = rgb(
            NAVY if i == 0 else color
        )

        rectangle.line.fill.background()

        add_text(
            slide, 9.95, y, 3.0, 0.25,
            f"{distance:,.1f} m | {minutes:.1f} min",
            size=10
        )

    add_text(
        slide, 0.72, 6.55, 12, 0.25,
        "注：城市后为有效景点数/总景点数，"
        "仅统计有效路网估算距离。",
        size=9,
        color=GREY
    )

    add_text(
        slide, 0.72, 6.87, 12, 0.25,
        "OSM + Dijkstra；接入段未完全核验。",
        size=9,
        color=GREY
    )


add_editable_slide(
    "metro",
    "15城市地铁—景点平均步行接驳距离",
    BLUE
)

add_editable_slide(
    "bus",
    "15城市公交—景点平均步行接驳距离",
    TEAL
)

prs.save(
    OUTPUT / "figure1_editable_charts.pptx"
)


# 10. FINAL REPORT
print("\n" + "=" * 60)
print("FIGURE 1 GENERATION FINISHED")
print("=" * 60)

print("读取成功：30/30 组")
print("长沙Metro、Bus字段已自动统一")
print("输出位置：", OUTPUT)

print("\n已覆盖生成：")
print("01_metro_avg_distance.png / svg / pdf")
print("02_bus_avg_distance.png / svg / pdf")
print("figure1_editable_charts.pptx")
print("figure1_transport_analysis.xlsx")
print("figure1_city_summary.csv")
print("figure1_poi_details.csv")

print("\n请检查15城平均距离、有效覆盖率和样本数。")
