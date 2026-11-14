# -*- coding: utf-8 -*-
"""
CityWalk C组数据一键整理（必须基于 A 的 AOI）
读取 cleaned4 → 高德 GCJ-02 转 WGS84 → A 的 AOI 内筛选 → 每城评分排序+核心名去重取20
→ 以选中景点的编码匹配 Sheet2 → Metro/Bus 分开 → 每城3 XLSX + 3 UTF-8 CSV。

先运行成都： py split_top20_cities_aoi.py --city chengdu
运行全部： py split_top20_cities_aoi.py
依赖：py -m pip install openpyxl geopandas pyogrio shapely pyproj
"""
from pathlib import Path
from collections import defaultdict
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Alignment
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
from shapely.prepared import prep
import argparse
import csv
import math
import re
import unicodedata

# ====== 1. 只改这里的路径（截图中的实际 Windows 路径）======
ROOT = Path(r"D:\大三（上）\大数据原理期中")
DATA_DIR = ROOT / "data_file" / "15country_citywalk_data"
SOURCE = DATA_DIR / "country_citywalk_cleaned4.xlsx"
A_ROOT = ROOT / "yn_qgis_file_2025"
OUTPUT = DATA_DIR / "split top20 cities data"
TOP_N = 20

SHEET1 = "CityWalk核心景点名录"
SHEET2 = "周边地铁出入口与公交配套表"
CITIES = {
    "成都": "chengdu", "重庆": "chongqing", "杭州": "hangzhou",
    "南京": "nanjing", "苏州": "suzhou", "武汉": "wuhan",
    "西安": "xian", "宁波": "ningbo", "长沙": "changsha",
    "郑州": "zhengzhou", "青岛": "qingdao", "天津": "tianjin",
    "合肥": "hefei", "佛山": "foshan", "东莞": "dongguan"
}

# 仅作“名称近似去重”，不把不同的街区自动当成同一地点。
SUFFIXES = sorted({
    "历史文化街区", "特色商业步行街", "特色商业街区", "商业文化街区",
    "文化商业街区", "商业步行街", "商业街区", "历史街区", "文化街区",
    "文旅街区", "特色街区", "旅游景区", "商业街", "步行街", "风景区",
    "景区", "街区", "商圈"
}, key=len, reverse=True)
PI = math.pi
EARTH_A = 6378245.0
EE = 0.006693421622965943


def norm(v):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(v or ""))).strip()


def name_key(name):
    value = norm(name)
    original = value
    if "商圈" in value and re.search(r"[-—–－]", value):
        value = re.split(r"[-—–－]", value, maxsplit=1)[0]
    value = re.sub(r"\([^()]*\)$", "", value)
    while True:
        suffix = next((s for s in SUFFIXES if value.endswith(s) and len(value) - len(s) >= 2), None)
        if suffix is None:
            break
        value = value[:-len(suffix)]
    return (value or original).casefold()


def tlat(x, y):
    r = -100 + 2*x + 3*y + .2*y*y + .1*x*y + .2*math.sqrt(abs(x))
    r += (20*math.sin(6*x*PI) + 20*math.sin(2*x*PI))*2/3
    r += (20*math.sin(y*PI) + 40*math.sin(y*PI/3))*2/3
    r += (160*math.sin(y*PI/12) + 320*math.sin(y*PI/30))*2/3
    return r


def tlon(x, y):
    r = 300 + x + 2*y + .1*x*x + .1*x*y + .1*math.sqrt(abs(x))
    r += (20*math.sin(6*x*PI) + 20*math.sin(2*x*PI))*2/3
    r += (20*math.sin(x*PI) + 40*math.sin(x*PI/3))*2/3
    r += (150*math.sin(x*PI/12) + 300*math.sin(x*PI/30))*2/3
    return r


def wgs_to_gcj(lon, lat):
    x, y = lon - 105, lat - 35
    dlat, dlon = tlat(x, y), tlon(x, y)
    rad = lat*PI/180
    magic = 1 - EE*math.sin(rad)**2
    root = math.sqrt(magic)
    dlat *= 180 / (EARTH_A*(1-EE)/(magic*root)*PI)
    dlon *= 180 / (EARTH_A/root*math.cos(rad)*PI)
    return lon + dlon, lat + dlat


def gcj_to_wgs(lon0, lat0):
    """高德 GCJ-02 近似逆变换；数值回算检查 ≠ 真实 POI 位置核验。"""
    try:
        lon, lat = float(lon0), float(lat0)
    except (ValueError, TypeError):
        raise ValueError("经纬度非数字")
    if not (math.isfinite(lon) and math.isfinite(lat) and 73 <= lon <= 135 and 18 <= lat <= 54):
        raise ValueError("经纬度异常或 X/Y 颠倒")
    x, y = lon, lat
    for _ in range(8):
        gx, gy = wgs_to_gcj(x, y)
        x += lon - gx
        y += lat - gy
    checkx, checky = wgs_to_gcj(x, y)
    error_m = math.hypot((checkx-lon)*111320*math.cos(lat*PI/180), (checky-lat)*111320)
    if error_m > 1:
        raise ValueError(f"坐标转换回算误差 {error_m:.2f} 米")
    return round(x, 8), round(y, 8), round(error_m, 4)


def read_sheet(ws):
    rows = ws.iter_rows(values_only=True)
    header = [str(v).strip() if v is not None else "" for v in next(rows)]
    if len(header) != len(set(header)):
        raise ValueError(f"{ws.title}: 重复的列名")
    for excel_row, vals in enumerate(rows, 2):
        if any(v is not None for v in vals):
            yield excel_row, dict(zip(header, vals))


def headers_of(ws, mandatory):
    header = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(max_row=1))]
    missing = set(mandatory) - set(header)
    if missing:
        raise ValueError(f"{ws.title}: 找不到字段 {sorted(missing)}")
    return header


def find_aoi(cn, en):
    """只允许读取 A 的这一个城市自己的 projected AOI，不使用道路、网格或其他边界代替。"""
    folder = A_ROOT / cn
    if not folder.is_dir():
        raise FileNotFoundError(f"A 的城市文件夹不存在: {folder}")
    path = folder / f"{en}_aoi_projected.gpkg"
    if not path.is_file():
        raise FileNotFoundError(f"AOI 文件不存在: {path}")
    return path


def read_aoi(path):
    # GeoPackage 可能有多个内部图层，必须唯一确定面图层，不能随便取第一个。
    import pyogrio
    layers = pyogrio.list_layers(path)
    polygons = [str(name) for name, geometry_type in layers
                if geometry_type and "Polygon" in str(geometry_type)]
    if len(polygons) != 1:
        raise ValueError(f"AOI 内有 {len(polygons)} 个面图层，无法自动唯一确认: {layers.tolist()}")
    layer_name = polygons[0]
    aoi = gpd.read_file(path, layer=layer_name)
    if aoi.empty or aoi.crs is None:
        raise ValueError("AOI 没有要素或坐标参考系 CRS")
    aoi = aoi[aoi.geometry.notna() & ~aoi.geometry.is_empty]
    if aoi.empty or not all(x in ("Polygon", "MultiPolygon") for x in aoi.geom_type):
        raise ValueError("AOI 不是有效的面图层")
    if not aoi.geometry.is_valid.all():
        raise ValueError("AOI 有无效几何；请让 A 修复后再运行")
    original_crs = str(aoi.crs)
    aoi = aoi.to_crs(epsg=4326)
    merged = unary_union(list(aoi.geometry))
    if merged.is_empty or not merged.is_valid:
        raise ValueError("AOI 面合并失败")
    return prep(merged), layer_name, original_crs, tuple(round(v, 5) for v in merged.bounds)


def metro_label(label):
    """只有名称中确有编号/字母出口的才入首轮路线 CSV。"""
    name = norm(label).upper()
    if re.search(r"(?:[A-Z]\d?|\d+号|[东西南北]\d+(?:[东西南北])?)\s*(?:出入口|出口|口)", name):
        return "named_exit_candidate"
    if "地铁站" in name or name.endswith("站"):
        if "出入口" not in name and "出口" not in name:
            return "station_center_review"
    return "unspecified_exit_review"


def save_xlsx(path, columns, records):
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(columns)
    for record in records:
        ws.append([record.get(key) for key in columns])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.fill = PatternFill("solid", fgColor="24466B")
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(vertical="center")
    for col in "ABCDEFGHIJ":
        ws.column_dimensions[col].width = 22
    ws.column_dimensions["C"].width = 35
    wb.save(path)


def save_csv(path, columns, records):
    # UTF-8-SIG: Windows Excel 可以显示中文；QGIS 选 UTF-8 即可。
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def run_one(cn, en, candidate_rows, transport_by_id, columns1, columns2):
    aoi_file = find_aoi(cn, en)
    inside, layer, crs, bounds = read_aoi(aoi_file)
    print(f"  AOI: {aoi_file.name} | 图层={layer} | CRS={crs} | WGS84范围={bounds}")
    audit = []
    candidates = []
    for excel_row, row in candidate_rows:
        pid, name = norm(row["景点统一编码"]), norm(row["CityWalk景点名称"])
        try:
            if not pid or not name:
                raise ValueError("景点编码/名称为空")
            score = float(row["score_numeric"])
            if not math.isfinite(score) or score <= 0 or score > 5:
                raise ValueError("评分不是 0～5 范围内的有效数值")
            x, y, e = gcj_to_wgs(row["经度(Lon)"], row["纬度(Lat)"])
            if not inside.intersects(Point(x, y)):
                raise ValueError("景点 POI 点不在 A 的 AOI 面内")
            candidate = dict(row)
            candidate.update({"lon_wgs84":x,"lat_wgs84":y,"coordinate_error_m":e,
                              "source_excel_row":excel_row,"name_match_key":name_key(name),
                              "aoi_match":"YES"})
            candidates.append(candidate)
        except (ValueError, TypeError) as exc:
            audit.append((cn, excel_row, pid, name, str(exc)))

    candidates.sort(key=lambda r:(-float(r["score_numeric"]),r["source_excel_row"]))
    uniq, seen_names, seen_ids = [], set(), set()
    for r in candidates:
        pid = norm(r["景点统一编码"])
        key = r["name_match_key"]
        if key in seen_names or pid in seen_ids:
            audit.append((cn, r["source_excel_row"], pid, r["CityWalk景点名称"], "同核心名称或编码重复"))
            continue
        seen_names.add(key); seen_ids.add(pid)
        uniq.append(r)
    if len(uniq) < TOP_N:
        raise ValueError(f"AOI 内有效且去重后的候选只有 {len(uniq)}，不足 {TOP_N}，不会范围外补选")

    top = uniq[:TOP_N]
    for rank, r in enumerate(top, 1):
        r["city_position"] = rank
    for r in uniq[TOP_N:]:
        audit.append((cn,r["source_excel_row"],norm(r["景点统一编码"]),r["CityWalk景点名称"],"AOI 内合格，但排名超过TOP20"))

    metro, bus, transport_warnings = [], [], []
    counts = defaultdict(lambda:{"metro":0,"bus":0})
    for place in top:
        pid = norm(place["景点统一编码"])
        for excel_row, raw in transport_by_id.get(pid, []):
            facility_type = norm(raw["交通设施大类"])
            if norm(raw.get("城市")) != cn:
                transport_warnings.append((cn,pid,excel_row,"设施所属城市与景点不一致"))
                continue
            if facility_type not in ("地铁出入口","公交站点"):
                transport_warnings.append((cn,pid,excel_row,f"交通类型不支持: {facility_type}"))
                continue
            try:
                x,y,e = gcj_to_wgs(raw["设施经度(Lon)"],raw["设施纬度(Lat)"])
            except (ValueError,TypeError) as exc:
                transport_warnings.append((cn,pid,excel_row,f"设施坐标错误: {exc}"))
                continue
            item = dict(raw)
            item.update({"lon_wgs84":x,"lat_wgs84":y,"coordinate_error_m":e,
                         "source_excel_row":excel_row})
            if facility_type == "地铁出入口":
                item["metro_type_check"] = metro_label(raw["出入口/站点具体名称"])
                metro.append(item)
                if item["metro_type_check"] == "named_exit_candidate":
                    counts[pid]["metro"] += 1
            else:
                bus.append(item)
                counts[pid]["bus"] += 1

    metro_good = [r for r in metro if r["metro_type_check"] == "named_exit_candidate"]
    metro_review = [r for r in metro if r["metro_type_check"] != "named_exit_candidate"]
    top_cols = list(columns1) + [x for x in ["lon_wgs84","lat_wgs84","coordinate_error_m",
                              "name_match_key","aoi_match","source_excel_row"] if x not in columns1]
    metro_cols = list(columns2) + ["lon_wgs84","lat_wgs84","coordinate_error_m","metro_type_check","source_excel_row"]
    bus_cols = list(columns2) + ["lon_wgs84","lat_wgs84","coordinate_error_m","source_excel_row"]

    folder = OUTPUT / en
    folder.mkdir(parents=True,exist_ok=True)
    # 三份 Excel 都保留全部相应记录；Metro CSV 只放明确出口候选，待核查另输出。
    save_xlsx(folder/f"{en}_top20_citywalk.xlsx",top_cols,top)
    save_xlsx(folder/f"{en}_metro_stop.xlsx",metro_cols,metro)
    save_xlsx(folder/f"{en}_bus_stop.xlsx",bus_cols,bus)
    save_csv(folder/f"{en}_top20_citywalk_wgs84.csv",top_cols,top)
    save_csv(folder/f"{en}_metro_stop_wgs84.csv",metro_cols,metro_good)
    save_csv(folder/f"{en}_bus_stop_wgs84.csv",bus_cols,bus)
    save_csv(folder/f"{en}_metro_review_wgs84.csv",metro_cols,metro_review)
    coverage = [{"place_id":norm(p["景点统一编码"]),"place_name":p["CityWalk景点名称"],
                 "metro_candidate_count":counts[norm(p["景点统一编码"])]["metro"],
                 "bus_count":counts[norm(p["景点统一编码"])]["bus"]} for p in top]
    save_csv(folder/f"{en}_transport_coverage.csv",
             ["place_id","place_name","metro_candidate_count","bus_count"],coverage)
    print(f"  合格AOI候选={len(candidates)}；去重后={len(uniq)}；TOP={len(top)}；"
          f"地铁候选={len(metro_good)}；地铁待核查={len(metro_review)}；公交关联={len(bus)}")
    return {"city":cn,"folder":en,"aoi_file":str(aoi_file),"aoi_layer":layer,"aoi_original_crs":crs,
            "raw_candidates":len(candidate_rows),"aoi_eligible":len(candidates),"aoi_unique":len(uniq),
            "top":len(top),"metro_candidate":len(metro_good),"metro_review":len(metro_review),
            "bus":len(bus),"top_without_metro":sum(x["metro_candidate_count"]==0 for x in coverage),
            "top_without_bus":sum(x["bus_count"]==0 for x in coverage),"status":"OK"},audit,transport_warnings


def main():
    parser = argparse.ArgumentParser(description="按 A 的 AOI 重排 15 城市 TOP20，匹配公交地铁，输出 WGS84")
    parser.add_argument("--city",choices=list(CITIES.values()),help="只运行某个城市，如 chengdu；省略则处理全部15个")
    args = parser.parse_args()
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Excel 不存在: {SOURCE}")
    if not A_ROOT.is_dir():
        raise FileNotFoundError(f"A 的目录不存在: {A_ROOT}")
    selected = {cn:en for cn,en in CITIES.items() if args.city is None or en==args.city}
    print("Excel:",SOURCE,"\nA 的 AOI:",A_ROOT,"\n输出:",OUTPUT)
    wb = load_workbook(SOURCE,read_only=True,data_only=True)
    if SHEET1 not in wb.sheetnames or SHEET2 not in wb.sheetnames:
        raise ValueError(f"缺少 Sheet；实际为 {wb.sheetnames}")
    ws1, ws2 = wb[SHEET1],wb[SHEET2]
    h1 = headers_of(ws1,["景点统一编码","城市","CityWalk景点名称","score_numeric","经度(Lon)","纬度(Lat)"])
    h2 = headers_of(ws2,["关联景点编码","城市","交通设施大类","出入口/站点具体名称","设施经度(Lon)","设施纬度(Lat)"])
    groups = defaultdict(list)
    for i,r in read_sheet(ws1):
        if norm(r["城市"]) in selected:
            groups[norm(r["城市"])].append((i,r))
    transport = defaultdict(list)
    for i,r in read_sheet(ws2):
        pid = norm(r["关联景点编码"])
        if pid:
            transport[pid].append((i,r))
    wb.close()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    reports,audits,warnings=[],[],[]
    for cn,en in selected.items():
        print(f"\n===== {cn} / {en} =====")
        try:
            result,audit,warn = run_one(cn,en,groups[cn],transport,h1,h2)
            reports.append(result); audits.extend(audit); warnings.extend(warn)
        except Exception as exc:
            reports.append({"city":cn,"folder":en,"status":"FAILED: "+str(exc)})
            print("  FAILED:",exc)
    cols = ["city","folder","aoi_file","aoi_layer","aoi_original_crs","raw_candidates",
            "aoi_eligible","aoi_unique","top","metro_candidate","metro_review","bus",
            "top_without_metro","top_without_bus","status"]
    save_csv(OUTPUT/"summary.csv",cols,reports)
    save_csv(OUTPUT/"excluded_citywalk_audit.csv",["city","excel_row","place_id","place_name","reason"],
             [dict(zip(["city","excel_row","place_id","place_name","reason"],r)) for r in audits])
    save_csv(OUTPUT/"transport_issues_audit.csv",["city","place_id","excel_row","reason"],
             [dict(zip(["city","place_id","excel_row","reason"],r)) for r in warnings])
    ok = sum(r["status"]=="OK" for r in reports)
    print(f"\n完成 {ok}/{len(selected)} 城市。检查: {OUTPUT / 'summary.csv'}")
    print("注意: AOI 的实际年份与研究口径、地铁出口是否开放、POI 是否为实际入口，仍需核查。")
    if ok < len(selected):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
