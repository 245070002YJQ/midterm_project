
# -*- coding: utf-8 -*-
# 只生成宁波、苏州的TOP20 / Metro / Bus
# 复用原来的 split_top20_cities_aoi.py
# 输入改为 cleaned_data/country_citywalk_cleaned.xlsx
# 自动识别AOI的GPKG或GeoJSON
# 不修改其余13个城市的结果

from pathlib import Path
from collections import defaultdict
from importlib import util
from openpyxl import load_workbook
import csv

# ==================================================
# 1. 路径配置
# ==================================================

ROOT = Path(r"D:\大三（上）\大数据原理期中")

DATA = ROOT / "data_file" / "15country_citywalk_data"

# 新版cleaned：不再读取cleaned4
SOURCE = (
    DATA / "cleaned_data"
    / "country_citywalk_cleaned.xlsx"
)

# 最终输出到原来的split目录
OUTPUT = DATA / "split top20 cities data"

# A的城市AOI
A_ROOT = ROOT / "yn_qgis_file_2025"

# 原来已经运行成功的分割代码
ORIGINAL_CODE = OUTPUT / "split_top20_cities_aoi.py"

# 本次只运行两个城市
ONLY = {
    "宁波": "ningbo",
    "苏州": "suzhou"
}


# ==================================================
# 2. 读取原始分割代码
# ==================================================

def load_original():

    if not ORIGINAL_CODE.is_file():
        raise FileNotFoundError(
            "找不到原始分割代码："
            + str(ORIGINAL_CODE)
        )

    spec = util.spec_from_file_location(
        "citywalk_original_split",
        str(ORIGINAL_CODE)
    )

    module = util.module_from_spec(spec)

    spec.loader.exec_module(module)

    return module


def read_count(path):

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        return sum(
            1 for _ in csv.DictReader(f)
        )


# ==================================================
# 3. 主程序
# ==================================================

def main():

    if not SOURCE.is_file():
        raise FileNotFoundError(
            "新版cleaned Excel不存在："
            + str(SOURCE)
        )

    if not A_ROOT.is_dir():
        raise FileNotFoundError(
            "A的AOI根目录不存在："
            + str(A_ROOT)
        )

    m = load_original()

    # 修改原模块的读取来源
    m.SOURCE = SOURCE
    m.A_ROOT = A_ROOT
    m.OUTPUT = OUTPUT
    m.TOP_N = 20

    # ==============================================
    # 4. 修正宁波、苏州AOI文件识别
    # ==============================================

    def find_aoi_geojson(cn, en):

        folder = A_ROOT / cn

        options = [
            folder / f"{en}_aoi_projected.gpkg",
            folder / f"{en}_aoi_4326.geojson"
        ]

        found = next(
            (
                p for p in options
                if p.is_file()
            ),
            None
        )

        if found is None:
            raise FileNotFoundError(
                f"{cn}未找到A提供的AOI："
                + str(options)
            )

        return found

    # 用新的AOI识别函数替换旧函数
    # 其他计算函数保持原样
    m.find_aoi = find_aoi_geojson

    # 先验证两个AOI是否可以读取
    for cn, en in ONLY.items():

        aoi = m.find_aoi(cn, en)

        inside, layer_name, crs, bounds = (
            m.read_aoi(aoi)
        )

        print(
            "AOI检查通过：",
            cn,
            aoi.name,
            "CRS：", crs,
            "范围：", bounds
        )

    # ==============================================
    # 5. 读取新版cleaned Excel
    # ==============================================

    wb = load_workbook(
        SOURCE,
        read_only=True,
        data_only=True
    )

    try:

        if (
            m.SHEET1 not in wb.sheetnames
            or m.SHEET2 not in wb.sheetnames
        ):
            raise ValueError(
                "新版cleaned的Sheet名称不匹配："
                + str(wb.sheetnames)
            )

        ws1 = wb[m.SHEET1]
        ws2 = wb[m.SHEET2]

        h1 = m.headers_of(
            ws1,
            [
                "景点统一编码",
                "城市",
                "CityWalk景点名称",
                "score_numeric",
                "经度(Lon)",
                "纬度(Lat)"
            ]
        )

        h2 = m.headers_of(
            ws2,
            [
                "关联景点编码",
                "城市",
                "交通设施大类",
                "出入口/站点具体名称",
                "设施经度(Lon)",
                "设施纬度(Lat)"
            ]
        )

        # 新版cleaned比cleaned4多两个评分辅助字段
        # 保持以前TOP20输出的列结构
        output_h1 = [
            x for x in h1
            if x not in (
                "score_status",
                "score_rank_city"
            )
        ]

        if "city_position" not in output_h1:
            output_h1.append("city_position")

        # ==========================================
        # 6. 只提取宁波、苏州景点
        # ==========================================

        candidates = defaultdict(list)

        for excel_row, row in m.read_sheet(ws1):

            city = m.norm(row["城市"])

            if city in ONLY:

                candidates[city].append(
                    (excel_row, row)
                )

        # ==========================================
        # 7. 按景点编码读取交通设施
        # 与原来的13城算法相同
        # ==========================================

        transport = defaultdict(list)

        for excel_row, row in m.read_sheet(ws2):

            pid = m.norm(
                row["关联景点编码"]
            )

            if pid:

                transport[pid].append(
                    (excel_row, row)
                )

    finally:
        wb.close()

    print("\n输入Excel：", SOURCE)
    print("输出目录：", OUTPUT)
    print("复用原代码：", ORIGINAL_CODE)

    # ==============================================
    # 8. 仅对两个城市调用原来的run_one
    # ==============================================

    reports = []
    audits = []
    warnings = []

    for cn, en in ONLY.items():

        print("\n==============================")
        print("开始处理：", cn, en)

        print(
            "cleaned中的景点记录：",
            len(candidates[cn])
        )

        try:

            # 使用原代码的完整筛选算法
            result, audit, warn = m.run_one(
                cn,
                en,
                candidates[cn],
                transport,
                output_h1,
                h2
            )

            folder = OUTPUT / en

            files = [
                folder / f"{en}_top20_citywalk_wgs84.csv",
                folder / f"{en}_metro_stop_wgs84.csv",
                folder / f"{en}_bus_stop_wgs84.csv",
                folder / f"{en}_metro_review_wgs84.csv",
                folder / f"{en}_transport_coverage.csv"
            ]

            for f in files:

                if not f.is_file():
                    raise RuntimeError(
                        "输出文件缺失："
                        + str(f)
                    )

            # ======================================
            # 9. 自动验证结果数量
            # ======================================

            if (
                read_count(files[0]) != 20
                or read_count(files[4]) != 20
            ):
                raise RuntimeError(
                    f"{cn} TOP20或覆盖情况不是20行"
                )

            if (
                read_count(files[1])
                != result["metro_candidate"]
            ):
                raise RuntimeError(
                    f"{cn}地铁候选数量不一致"
                )

            if (
                read_count(files[2])
                != result["bus"]
            ):
                raise RuntimeError(
                    f"{cn}公交候选数量不一致"
                )

            reports.append(result)

            audits.extend(audit)

            warnings.extend(warn)

            print(
                f"{cn}成功：",
                "TOP20=20",
                "Metro=", result["metro_candidate"],
                "Bus=", result["bus"],
                "Metro待核查=", result["metro_review"]
            )

        except Exception as exc:

            reports.append({
                "city": cn,
                "folder": en,
                "status": "FAILED: " + str(exc)
            })

            print(
                f"{cn}处理失败：",
                str(exc)
            )

    # ==============================================
    # 10. 保存两个城市独立的统计报告
    # 不覆盖以前13城的summary.csv
    # ==============================================

    report_fields = [
        "city", "folder", "aoi_file",
        "aoi_layer", "aoi_original_crs",
        "raw_candidates", "aoi_eligible",
        "aoi_unique", "top",
        "metro_candidate", "metro_review",
        "bus", "top_without_metro",
        "top_without_bus", "status"
    ]

    m.save_csv(
        OUTPUT / "summary_ningbo_suzhou.csv",
        report_fields,
        reports
    )

    audit_keys = [
        "city", "excel_row",
        "place_id", "place_name", "reason"
    ]

    m.save_csv(
        OUTPUT / "excluded_citywalk_audit_ningbo_suzhou.csv",
        audit_keys,
        [
            dict(zip(audit_keys, row))
            for row in audits
        ]
    )

    warn_keys = [
        "city", "place_id",
        "excel_row", "reason"
    ]

    m.save_csv(
        OUTPUT / "transport_issues_audit_ningbo_suzhou.csv",
        warn_keys,
        [
            dict(zip(warn_keys, row))
            for row in warnings
        ]
    )

    ok = sum(
        r["status"] == "OK"
        for r in reports
    )

    print("\n==============================")
    print(f"完成 {ok}/2 个城市")
    print(
        "检查：",
        OUTPUT / "summary_ningbo_suzhou.csv"
    )

    if ok != 2:
        raise SystemExit(
            "部分城市失败，请检查错误报告"
        )


if __name__ == "__main__":
    main()
