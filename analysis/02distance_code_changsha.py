
# -*- coding: utf-8 -*-
# 长沙 CityWalk TOP20 -> Metro / Bus
# QGIS Python Console -> Show Editor
# 直接覆盖 final result/changsha 的旧结果
# 使用2025-12-31 OSM道路，不使用旧年份道路
# 路网不连通：保留直线参考，不冒充步行距离

from pathlib import Path
from collections import defaultdict
import ast
import csv
import json
import math
import shutil

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsPointXY,
    QgsGeometry, QgsFeature, QgsField,
    QgsWkbTypes, QgsSpatialIndex,
    QgsVectorFileWriter,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform
)
from qgis.PyQt.QtCore import QVariant
from qgis.analysis import (
    QgsVectorLayerDirector,
    QgsNetworkDistanceStrategy,
    QgsGraphBuilder,
    QgsGraphAnalyzer
)

# ==================================================
# 1. 长沙路径
# ==================================================

BASE = Path(r"D:\大三（上）\大数据原理期中")

CITY = "changsha"
CN = "长沙"

SPLIT = (
    BASE / "data_file"
    / "15country_citywalk_data"
    / "split top20 cities data"
    / CITY
)

OSM = (
    BASE / "yn_qgis_file_2025"
    / CN
    / "changsha_osm_roads_2025-12-31.gpkg"
)

ROOT = BASE / "final result" / CITY

INP = ROOT / "input"
MET = ROOT / "metro"
BUS = ROOT / "bus"

POI = SPLIT / "changsha_top20_citywalk_wgs84.csv"

STOP = {
    "metro": SPLIT / "changsha_metro_stop_wgs84.csv",
    "bus": SPLIT / "changsha_bus_stop_wgs84.csv"
}

CRS = QgsCoordinateReferenceSystem("EPSG:32649")

MAX_ANCHORS = 3
NEAREST_ROADS = 10
METERS_PER_MIN = 75.0

project = QgsProject.instance()

if project.mapLayers():
    raise RuntimeError(
        "请先点击 Project > New，新建空白工程。"
    )

for p in (OSM, POI, *STOP.values()):
    if not p.is_file():
        raise FileNotFoundError(
            "找不到输入文件：" + str(p)
        )

for folder in (INP, MET, BUS):
    folder.mkdir(parents=True, exist_ok=True)

# 复制输入副本，不删除原始数据
for src in (OSM, POI, *STOP.values()):
    dst = INP / src.name

    if (
        not dst.exists()
        or src.stat().st_size != dst.stat().st_size
        or src.stat().st_mtime_ns != dst.stat().st_mtime_ns
    ):
        shutil.copy2(src, dst)

print("① 长沙输入已检查，准备覆盖旧结果。", flush=True)


# ==================================================
# 2. 读取 CSV
# ==================================================

def loadcsv(path, required):

    with path.open(
        "r", encoding="utf-8-sig", newline=""
    ) as f:

        reader = csv.DictReader(f)

        missing = (
            set(required)
            - set(reader.fieldnames or [])
        )

        if missing:
            raise RuntimeError(
                f"{path.name} 缺少字段：{missing}"
            )

        return list(reader)


POI_ROWS = loadcsv(
    POI,
    [
        "景点统一编码",
        "CityWalk景点名称",
        "lon_wgs84",
        "lat_wgs84"
    ]
)

STOPS = {
    mode: loadcsv(
        path,
        [
            "关联景点编码",
            "出入口/站点具体名称",
            "lon_wgs84",
            "lat_wgs84"
        ]
    )
    for mode, path in STOP.items()
}

if len(POI_ROWS) != 20:
    raise RuntimeError(
        f"TOP20不是20行，实际{len(POI_ROWS)}"
    )

print(
    "② 景点", len(POI_ROWS),
    "Metro候选", len(STOPS["metro"]),
    "Bus候选", len(STOPS["bus"]),
    flush=True
)


# ==================================================
# 3. 坐标转换
# ==================================================

WGS = QgsCoordinateReferenceSystem("EPSG:4326")

CT = QgsCoordinateTransform(
    WGS, CRS, project.transformContext()
)


def pxy(row):

    lon = float(row["lon_wgs84"])
    lat = float(row["lat_wgs84"])

    if not (
        math.isfinite(lon)
        and math.isfinite(lat)
        and 110 < lon < 115
        and 25 < lat < 30
    ):
        raise ValueError(
            "经纬度不在长沙附近：" + str((lon, lat))
        )

    return CT.transform(QgsPointXY(lon, lat))


def dist(a, b):
    return math.hypot(
        a.x() - b.x(),
        a.y() - b.y()
    )


def safe(x):

    if x is None:
        return ""

    s = str(x).strip()

    if s.lower() in ("null", "none", "nan"):
        return ""

    return s


pois = []
by_id = {}

for row in POI_ROWS:

    pid = safe(row["景点统一编码"])

    if not pid or pid in by_id:
        raise RuntimeError(
            "景点编码为空或重复：" + pid
        )

    obj = {
        "id": pid,
        "name": row["CityWalk景点名称"],
        "pt": pxy(row),
        "raw": row
    }

    pois.append(obj)
    by_id[pid] = obj


# ==================================================
# 4. 成都统一宽松道路规则
# ==================================================

BASE_TYPES = {
    "footway", "pedestrian", "path", "steps",
    "residential", "living_street", "service",
    "unclassified", "primary", "secondary",
    "tertiary"
}

EXTRA_TYPES = {
    "cycleway", "track", "road"
}

FOOT_YES = {
    "yes", "designated", "permissive"
}

SIDEWALK_YES = {
    "yes", "both", "left", "right", "separate"
}


def osmtags(feature, fields):

    tags = {}

    if "tags" in fields:

        v = feature["tags"]

        if isinstance(v, str):

            try:
                v = ast.literal_eval(v)

            except Exception:

                try:
                    v = json.loads(v)
                except Exception:
                    v = {}

        if isinstance(v, dict):

            tags = {
                str(k): safe(val).lower()
                for k, val in v.items()
            }

        elif isinstance(v, (list, tuple)):

            try:
                tags = {
                    str(k): safe(val).lower()
                    for k, val in v
                }
            except Exception:
                pass

    # 同时兼容独立字段
    keys = [
        "highway", "foot", "access", "motorroad",
        "sidewalk", "sidewalk:left", "sidewalk:right",
        "bridge", "tunnel", "layer"
    ]

    for key in keys:

        if key in fields:

            value = safe(feature[key]).lower()

            if value:
                tags[key] = value

    return tags


def walk_ok(t):

    if t.get("foot") in ("no", "private"):
        return False

    if t.get("access") in ("no", "private"):
        return False

    if t.get("motorroad") == "yes":
        return False

    kind = t.get("highway", "")

    if kind in BASE_TYPES:
        return True

    if kind in EXTRA_TYPES:

        if t.get("foot") in FOOT_YES:
            return True

        for key in (
            "sidewalk", "sidewalk:left", "sidewalk:right"
        ):

            if t.get(key) in SIDEWALK_YES:
                return True

    return False


# ==================================================
# 5. 读取2025 OSM，筛选道路
# ==================================================

src_road = QgsVectorLayer(
    str(INP / OSM.name),
    "长沙_2025原始OSM",
    "ogr"
)

if (
    not src_road.isValid()
    or src_road.geometryType() != QgsWkbTypes.LineGeometry
):
    raise RuntimeError(
        "2025年OSM无法作为线图层读取"
    )

rf = set(src_road.fields().names())

if not ({"tags", "highway"} & rf):
    raise RuntimeError(
        "2025 OSM没有tags或highway字段"
    )

if not src_road.crs().isValid():
    raise RuntimeError(
        "2025 OSM没有有效CRS"
    )

road_ct = QgsCoordinateTransform(
    src_road.crs(),
    CRS,
    project.transformContext()
)

roads = QgsVectorLayer(
    "LineString?crs=EPSG:32649",
    "长沙_宽松候选步行网",
    "memory"
)

roads.dataProvider().addAttributes([
    QgsField("osm_id", QVariant.String),
    QgsField("highway", QVariant.String),
    QgsField("risk", QVariant.String)
])

roads.updateFields()

chunk = []
nroad = 0
nmain = 0

for f in src_road.getFeatures():

    t = osmtags(f, rf)

    if not walk_ok(t):
        continue

    geom = QgsGeometry(f.geometry())

    if geom.isEmpty() or geom.isNull():
        continue

    if geom.transform(road_ct) != 0:
        continue

    lines = (
        geom.asMultiPolyline()
        if geom.isMultipart()
        else [geom.asPolyline()]
    )

    main_unknown = (
        t.get("highway")
        in ("primary", "secondary", "tertiary")
        and t.get("foot") not in FOOT_YES
        and not any(
            t.get(k) in SIDEWALK_YES
            for k in (
                "sidewalk",
                "sidewalk:left",
                "sidewalk:right"
            )
        )
    )

    risk = (
        "主干路步行标记不完整"
        if main_unknown
        else "未核验建筑/桥隧"
    )

    osmid = (
        safe(f["osm_id"])
        if "osm_id" in rf
        else str(f.id())
    )

    for line in lines:

        if len(line) < 2:
            continue

        feat = QgsFeature(roads.fields())

        feat.setGeometry(
            QgsGeometry.fromPolylineXY(line)
        )

        feat.setAttributes([
            osmid,
            t.get("highway", ""),
            risk
        ])

        chunk.append(feat)
        nroad += 1
        nmain += int(main_unknown)

        if len(chunk) >= 1000:

            ok, _ = roads.dataProvider().addFeatures(
                chunk
            )

            if not ok:
                raise RuntimeError(
                    "步行道路写入失败"
                )

            chunk = []

if chunk:

    ok, _ = roads.dataProvider().addFeatures(chunk)

    if not ok:
        raise RuntimeError(
            "剩余步行道路写入失败"
        )

roads.updateExtents()

if nroad < 1000:
    raise RuntimeError(
        f"候选步行道路仅{nroad}条，可能筛选失败"
    )

print(
    "③ 候选道路", nroad,
    "主干路缺明确步行标记", nmain,
    flush=True
)


# ==================================================
# 6. 覆盖保存GPKG
# ==================================================

def save_gpkg(layer, path):

    if layer.featureCount() == 0:

        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

        return None

    options = QgsVectorFileWriter.SaveVectorOptions()

    options.driverName = "GPKG"
    options.layerName = path.stem

    options.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteFile
    )

    result = (
        QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            str(path),
            project.transformContext(),
            options
        )
    )

    if result[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(
            "GPKG无法覆盖：" + str(path)
            + "\n请关闭其他QGIS工程。\n"
            + str(result)
        )

    loaded = QgsVectorLayer(
        str(path),
        path.stem,
        "ogr"
    )

    if (
        not loaded.isValid()
        or loaded.featureCount() != layer.featureCount()
    ):
        raise RuntimeError(
            "GPKG保存记录数不一致：" + str(path)
        )

    return loaded


network = save_gpkg(
    roads,
    INP / "changsha_walkable_2025.gpkg"
)


# ==================================================
# 7. 寻找多个道路接入位置
# ==================================================

si = QgsSpatialIndex(
    network.getFeatures(),
    flags=QgsSpatialIndex.FlagStoreFeatureGeometries
)

point_cache = {}
all_ties = []


def anchors(p):

    key = (
        round(p.x(), 3),
        round(p.y(), 3)
    )

    if key in point_cache:
        return point_cache[key]

    selected = []

    for fid in si.nearestNeighbor(
        p, NEAREST_ROADS
    ):

        g = si.geometry(fid)

        if not g or g.isEmpty():
            continue

        q = g.nearestPoint(
            QgsGeometry.fromPointXY(p)
        )

        if q.isNull() or q.isEmpty():
            continue

        pt = QgsPointXY(q.asPoint())

        if any(
            dist(pt, a["point"]) < 0.5
            for a in selected
        ):
            continue

        a = {
            "point": pt,
            "off": dist(p, pt),
            "idx": len(all_ties)
        }

        selected.append(a)
        all_ties.append(pt)

        if len(selected) >= MAX_ANCHORS:
            break

    point_cache[key] = selected

    return selected


for poi in pois:
    poi["anchors"] = anchors(poi["pt"])

groups = {
    mode: defaultdict(list)
    for mode in STOPS
}

for mode, rows in STOPS.items():

    for i, row in enumerate(rows, 1):

        pid = safe(row["关联景点编码"])

        x = {
            "pid": pid,
            "name": safe(
                row["出入口/站点具体名称"]
            ),
            "raw": row,
            "number": i,
            "error": "",
            "pt": None,
            "air": None,
            "anchors": []
        }

        if pid not in by_id:

            x["error"] = (
                "关联景点编码不存在TOP20"
            )

        else:

            try:

                x["pt"] = pxy(row)

                x["air"] = dist(
                    by_id[pid]["pt"],
                    x["pt"]
                )

                x["anchors"] = anchors(x["pt"])

                if not x["anchors"]:
                    x["error"] = (
                        "无法找到候选步行道路接入位置"
                    )

            except Exception as e:

                x["error"] = (
                    "站点坐标错误：" + str(e)
                )

        groups[mode][pid].append(x)

print(
    "④ 道路接入点", len(all_ties),
    "开始构建路网图……",
    flush=True
)


# ==================================================
# 8. 构建Dijkstra道路网络
# ==================================================

director = QgsVectorLayerDirector(
    network,
    -1, "", "", "",
    QgsVectorLayerDirector.DirectionBoth
)

director.addStrategy(
    QgsNetworkDistanceStrategy()
)

builder = QgsGraphBuilder(
    CRS, True, 0.5
)

tied = director.makeGraph(
    builder, all_ties
)

G = builder.graph()

if len(tied) != len(all_ties):
    raise RuntimeError(
        "路网接入点数量不一致"
    )

vtx = [
    G.findVertex(p)
    for p in tied
]


def valid(entries):

    return [
        a for a in entries
        if vtx[a["idx"]] >= 0
    ]


print(
    "⑤ 构图完成：",
    G.vertexCount(), "节点；",
    G.edgeCount(), "有向边",
    flush=True
)


# ==================================================
# 9. 恢复最短路线
# ==================================================

def path_points(tree, start, end):

    pts = [
        G.vertex(end).point()
    ]

    cur = end
    seen = set()

    while cur != start:

        if (
            cur < 0
            or cur in seen
            or tree[cur] < 0
        ):
            return []

        seen.add(cur)

        cur = G.edge(
            tree[cur]
        ).fromVertex()

        pts.append(
            G.vertex(cur).point()
        )

    return list(reversed(pts))


def memlayer(geom, name, spec):

    layer = QgsVectorLayer(
        f"{geom}?crs=EPSG:32649",
        name,
        "memory"
    )

    fields = []

    for n, typ in spec:

        dtype = (
            QVariant.Double if typ == "n"
            else QVariant.Int if typ == "i"
            else QVariant.String
        )

        fields.append(
            QgsField(n, dtype)
        )

    layer.dataProvider().addAttributes(fields)
    layer.updateFields()

    return layer


ROUTE_SPEC = [
    ("mode", "s"),
    ("poi_id", "s"),
    ("poi_name", "s"),
    ("station", "s"),
    ("road_m", "n"),
    ("start_m", "n"),
    ("end_m", "n"),
    ("total_m", "n"),
    ("is_nearest", "i"),
    ("risk", "s")
]

all_route = memlayer(
    "LineString",
    "长沙_全部可寻路候选",
    ROUTE_SPEC
)

nearest_route = memlayer(
    "LineString",
    "长沙_最近路线",
    ROUTE_SPEC
)

conn = memlayer(
    "LineString",
    "长沙_未核验道路接入线",
    [
        ("mode", "s"),
        ("poi_id", "s"),
        ("station", "s"),
        ("distance_m", "n")
    ]
)

fails = memlayer(
    "Point",
    "长沙_无法寻路候选",
    [
        ("mode", "s"),
        ("poi_id", "s"),
        ("station", "s"),
        ("reason", "s")
    ]
)


def add(layer, coords, attrs, point=False):

    if not point and len(coords) < 2:
        return False

    f = QgsFeature(layer.fields())

    if point:
        f.setGeometry(
            QgsGeometry.fromPointXY(coords)
        )

    else:
        f.setGeometry(
            QgsGeometry.fromPolylineXY(coords)
        )

    f.setAttributes(attrs)

    yes, _ = layer.dataProvider().addFeatures([f])

    return yes


def lines_no_dup(points):

    out = []

    for p in points:

        if (
            not out
            or dist(p, out[-1]) > 0.001
        ):
            out.append(p)

    return out


# ==================================================
# 10. 保存直线接入位置
# ==================================================

for poi in pois:

    for a in poi["anchors"]:

        if a["off"] > 0.01:

            add(
                conn,
                [poi["pt"], a["point"]],
                [
                    "poi",
                    poi["id"],
                    poi["name"],
                    round(a["off"], 2)
                ]
            )

for mode, gr in groups.items():

    for stationlist in gr.values():

        for s in stationlist:

            if s["pt"]:

                for a in s["anchors"]:

                    if a["off"] > 0.01:

                        add(
                            conn,
                            [s["pt"], a["point"]],
                            [
                                mode,
                                s["pid"],
                                s["name"],
                                round(a["off"], 2)
                            ]
                        )


# ==================================================
# 11. CSV字段
# ==================================================

SUMMARY = [
    "城市", "景点编码", "景点名称",
    "800米API候选数",
    "路网成功数",
    "仅直线参考数",
    "最近站点名称",
    "最近站点POI_ID",
    "最近站点直线_米",
    "路网内距离_米",
    "景点接入_米",
    "站点接入_米",
    "最近总估算距离_米",
    "估算步行分钟",
    "计算类型",
    "可能更近的未连通候选数",
    "路网计算状态",
    "质量提示",
    "OSM时间基准",
    "路网CRS"
]

DETAIL = [
    "候选序号", "景点编码", "景点名称",
    "交通类型", "站点名称", "站点POI_ID",
    "WGS84直线_米",
    "路网内_米",
    "景点接入_米",
    "站点接入_米",
    "道路加接入估算_米",
    "直线参考_米",
    "展示距离_米",
    "计算类型",
    "寻路状态",
    "质量提示"
]


def source_id(row):

    for key in (
        "高德设施POI_ID",
        "站点POI_ID",
        "高德POI_ID",
        "POI_ID"
    ):

        if safe(row.get(key)):
            return safe(row[key])

    return ""


def writer(path, cols):

    try:

        f = path.open(
            "w",
            encoding="utf-8-sig",
            newline=""
        )

    except PermissionError:

        raise RuntimeError(
            "无法覆盖CSV，可能被Excel打开："
            + str(path)
            + "\n请关闭Excel再运行。"
        )

    w = csv.DictWriter(
        f,
        fieldnames=cols,
        extrasaction="ignore"
    )

    w.writeheader()
    f.flush()

    return f, w


# ==================================================
# 12. 计算Metro和Bus
# ==================================================

mode_stats = {}

for mode, folder in [
    ("metro", MET),
    ("bus", BUS)
]:

    summaryfile, ws = writer(
        folder / f"changsha_{mode}_top20_summary.csv",
        SUMMARY
    )

    detailfile, wd = writer(
        folder / f"changsha_{mode}_all_candidates.csv",
        DETAIL
    )

    failedfile, wf = writer(
        folder / f"changsha_{mode}_failed_candidates.csv",
        DETAIL
    )

    success_count = 0
    failure_count = 0
    no_count = 0
    nearest_count = 0

    try:

        for no, poi in enumerate(pois, 1):

            stationlist = groups[mode].get(
                poi["id"], []
            )

            srows = []
            succeeded = []

            # 景点最多三个起点
            trees = []

            for a in valid(poi["anchors"]):

                t, c = QgsGraphAnalyzer.dijkstra(
                    G, vtx[a["idx"]], 0
                )

                trees.append((a, t, c))

            # 逐条计算候选站点
            for s in stationlist:

                error = s["error"]
                best = None

                if not error and not trees:
                    error = (
                        "景点无法接入候选路网"
                    )

                if not error:

                    for sa, t, c in trees:

                        sv = vtx[sa["idx"]]

                        for ea in valid(s["anchors"]):

                            ev = vtx[ea["idx"]]

                            if sv != ev and t[ev] < 0:
                                continue

                            length = float(c[ev])

                            if not math.isfinite(length):
                                continue

                            total = (
                                length
                                + sa["off"]
                                + ea["off"]
                            )

                            if (
                                best
                                and total >= best["total"]
                            ):
                                continue

                            ps = path_points(
                                t, sv, ev
                            )

                            if not ps:
                                continue

                            coords = lines_no_dup(
                                [poi["pt"]]
                                + ps
                                + [s["pt"]]
                            )

                            if len(coords) < 2:
                                continue

                            best = {
                                "total": total,
                                "road": length,
                                "start": sa,
                                "end": ea,
                                "coords": coords,
                                "stop": s
                            }

                    if best is None:
                        error = (
                            "候选路网不连通或无有效路径"
                        )

                if best:

                    method = (
                        "Dijkstra路网+直线接入"
                        "(未核验)"
                    )

                    success_count += 1
                    succeeded.append(best)

                    s["network_total"] = best["total"]

                else:

                    method = (
                        "仅直线参考(非步行距离)"
                    )

                    failure_count += 1
                    s["network_total"] = None

                    if s["pt"]:

                        add(
                            fails,
                            s["pt"],
                            [
                                mode,
                                poi["id"],
                                s["name"],
                                error
                            ],
                            True
                        )

                risk = (
                    "建筑、围墙、门禁、"
                    "桥隧连接未核验"
                )

                if (
                    best
                    and max(
                        best["start"]["off"],
                        best["end"]["off"]
                    ) > 30
                ):
                    risk += "；接入超过30米"

                if (
                    s["air"] is not None
                    and s["air"] > 800
                ):
                    risk += (
                        "；WGS84重算超过800米"
                        "（不删除原候选）"
                    )

                row = {
                    "候选序号": s["number"],
                    "景点编码": poi["id"],
                    "景点名称": poi["name"],
                    "交通类型": mode,
                    "站点名称": s["name"],
                    "站点POI_ID": source_id(
                        s["raw"]
                    ),

                    "WGS84直线_米": (
                        round(s["air"], 1)
                        if s["air"] is not None
                        else ""
                    ),

                    "路网内_米": (
                        round(best["road"], 1)
                        if best else ""
                    ),

                    "景点接入_米": (
                        round(best["start"]["off"], 1)
                        if best else ""
                    ),

                    "站点接入_米": (
                        round(best["end"]["off"], 1)
                        if best else ""
                    ),

                    "道路加接入估算_米": (
                        round(best["total"], 1)
                        if best else ""
                    ),

                    "直线参考_米": (
                        round(s["air"], 1)
                        if (
                            not best
                            and s["air"] is not None
                        )
                        else ""
                    ),

                    "展示距离_米": (
                        round(
                            best["total"]
                            if best else s["air"],
                            1
                        )
                        if (
                            best
                            or s["air"] is not None
                        )
                        else ""
                    ),

                    "计算类型": method,

                    "寻路状态": (
                        "路网可达，接入未核验"
                        if best else error
                    ),

                    "质量提示": risk
                }

                srows.append(row)

                if not best:
                    wf.writerow(row)

            # 没有候选，也写一行说明
            if not stationlist:

                no_count += 1

                srows.append({
                    "景点编码": poi["id"],
                    "景点名称": poi["name"],
                    "交通类型": mode,
                    "计算类型": "没有候选",
                    "寻路状态": (
                        "800米API候选表内"
                        "没有该类站点"
                    )
                })

            # =====================================
            # 13. 选择最近站点
            # =====================================

            if succeeded:

                chosen = min(
                    succeeded,
                    key=lambda v: v["total"]
                )

                cs = chosen["stop"]
                nearest_count += 1

                possible = sum(
                    1 for s in stationlist
                    if (
                        s["network_total"] is None
                        and s["air"] is not None
                        and s["air"] < chosen["total"]
                    )
                )

            else:

                valid_air = [
                    s for s in stationlist
                    if s["air"] is not None
                ]

                cs = (
                    min(
                        valid_air,
                        key=lambda s: s["air"]
                    )
                    if valid_air
                    else None
                )

                chosen = None
                possible = ""

            if chosen:

                value = chosen["total"]
                road = chosen["road"]
                start = chosen["start"]["off"]
                end = chosen["end"]["off"]

                method = (
                    "Dijkstra路网+直线接入"
                    "(未核验)"
                )

                status = (
                    "全部路网可达"
                    if len(succeeded) == len(stationlist)
                    else (
                        "部分可达；"
                        "其他仅直线参考"
                    )
                )

            elif cs:

                value = cs["air"]
                road = ""
                start = ""
                end = ""

                method = (
                    "仅直线参考(非步行距离)"
                )

                status = (
                    "全部候选无法有效寻路；"
                    "最近仅直线参考"
                )

            else:

                value = ""
                road = ""
                start = ""
                end = ""

                method = "没有有效候选"

                status = (
                    "没有800米候选"
                    if not stationlist
                    else "候选点坐标无效"
                )

            summary = {
                "城市": CN,
                "景点编码": poi["id"],
                "景点名称": poi["name"],

                "800米API候选数": len(stationlist),

                "路网成功数": len(succeeded),

                "仅直线参考数": (
                    len(stationlist)
                    - len(succeeded)
                ),

                "最近站点名称": (
                    cs["name"] if cs else "没有"
                ),

                "最近站点POI_ID": (
                    source_id(cs["raw"])
                    if cs else ""
                ),

                "最近站点直线_米": (
                    round(cs["air"], 1)
                    if (
                        cs
                        and cs["air"] is not None
                    )
                    else ""
                ),

                "路网内距离_米": (
                    round(road, 1)
                    if road != "" else ""
                ),

                "景点接入_米": (
                    round(start, 1)
                    if start != "" else ""
                ),

                "站点接入_米": (
                    round(end, 1)
                    if end != "" else ""
                ),

                "最近总估算距离_米": (
                    round(value, 1)
                    if value != "" else ""
                ),

                "估算步行分钟": (
                    round(
                        value / METERS_PER_MIN,
                        1
                    )
                    if chosen else ""
                ),

                "计算类型": method,

                "可能更近的未连通候选数": possible,

                "路网计算状态": status,

                "质量提示": (
                    "道路接入、建筑围墙和桥隧"
                    "尚未实地核验；"
                    "直线参考不可当步行距离"
                ),

                "OSM时间基准": (
                    "2025-12-31"
                    "（以A下载记录为准）"
                ),

                "路网CRS": "EPSG:32649"
            }

            # 逐景点保存，避免中途一直空文件夹
            ws.writerow(summary)

            for r in srows:
                wd.writerow(r)

            # 全部成功路线
            for it in succeeded:

                stop = it["stop"]

                isnear = int(chosen is it)

                attrs = [
                    mode,
                    poi["id"],
                    poi["name"],
                    stop["name"],
                    round(it["road"], 2),
                    round(it["start"]["off"], 2),
                    round(it["end"]["off"], 2),
                    round(it["total"], 2),
                    isnear,
                    "直线接入、主干路和桥隧未核验"
                ]

                add(
                    all_route,
                    it["coords"],
                    attrs
                )

                if isnear:

                    add(
                        nearest_route,
                        it["coords"],
                        attrs
                    )

            summaryfile.flush()
            detailfile.flush()
            failedfile.flush()

            print(
                f"[{mode} {no:02d}/20] "
                f"{poi['name']}："
                f"候选{len(stationlist)}，"
                f"路网成功{len(succeeded)}，"
                f"最近"
                f"{round(value,1) if value != '' else '没有'}",
                flush=True
            )

        # 关联编码不在TOP20的原始候选也保留
        for pid, stationlist in groups[mode].items():

            if pid in by_id:
                continue

            for s in stationlist:

                failure_count += 1

                row = {
                    "候选序号": s["number"],
                    "景点编码": pid,
                    "交通类型": mode,
                    "站点名称": s["name"],
                    "站点POI_ID": source_id(
                        s["raw"]
                    ),
                    "计算类型": "数据异常",
                    "寻路状态": s["error"]
                }

                wd.writerow(row)
                wf.writerow(row)

        detailfile.flush()
        failedfile.flush()

    finally:

        summaryfile.close()
        detailfile.close()
        failedfile.close()

    # ==================================================
    # 14. 检查输出CSV记录数量
    # ==================================================

    def count(path):

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as f:

            return sum(
                1 for _ in csv.DictReader(f)
            )

    sfile = (
        folder
        / f"changsha_{mode}_top20_summary.csv"
    )

    dfile = (
        folder
        / f"changsha_{mode}_all_candidates.csv"
    )

    expected = len(STOPS[mode]) + no_count

    if (
        count(sfile) != 20
        or count(dfile) != expected
    ):
        raise RuntimeError(
            f"{mode}记录数量有遗漏！"
            f"汇总{count(sfile)}/20；"
            f"明细{count(dfile)}/{expected}"
        )

    mode_stats[mode] = {
        "TOP20": 20,
        "source_candidates": len(STOPS[mode]),
        "routed": success_count,
        "non_routed": failure_count,
        "no_candidate_pois": no_count,
        "detail_rows": count(dfile),
        "nearest_network_pois": nearest_count
    }

    print(
        f"⑥ {mode}输出完成并通过行数核对：",
        mode_stats[mode],
        flush=True
    )


# ==================================================
# 15. 核对路线数量
# ==================================================

expected_routes = sum(
    v["routed"]
    for v in mode_stats.values()
)

if all_route.featureCount() != expected_routes:

    raise RuntimeError(
        "路线数量不一致："
        f"{all_route.featureCount()}"
        f"/{expected_routes}"
    )


# ==================================================
# 16. 覆盖保存GIS路线和QGIS工程
# ==================================================

project.setCrs(CRS)
project.addMapLayer(network)

output_layers = [
    (
        all_route,
        "changsha_all_candidate_routes.gpkg"
    ),
    (
        nearest_route,
        "changsha_nearest_routes.gpkg"
    ),
    (
        conn,
        "changsha_straight_connectors_NOT_verified.gpkg"
    ),
    (
        fails,
        "changsha_failed_candidate_points.gpkg"
    )
]

for layer, name in output_layers:

    saved = save_gpkg(
        layer,
        ROOT / name
    )

    if saved:
        project.addMapLayer(saved)


# ==================================================
# 17. 保存质量报告
# ==================================================

info = {
    "city": CN,
    "historical_osm": str(OSM),

    "source_roads": src_road.featureCount(),

    "walkable_segments": nroad,

    "main_road_without_explicit_foot": nmain,

    "graph_nodes": G.vertexCount(),

    "graph_edges": G.edgeCount(),

    "all_route_features": all_route.featureCount(),

    "nearest_features": nearest_route.featureCount(),

    "method": (
        "Dijkstra＋每点最多3个道路接入点；"
        "无法寻路时另存直线参考，"
        "不作为真实步行距离"
    ),

    "quality_limitations": [
        "未使用建筑物和围墙障碍数据",
        "直线接入可能穿过建筑物或围墙",
        "桥梁隧道连接关系未完全核验",
        "宽松道路类型不保证实际允许步行",
        "原API800米候选不再二次截断",
        "直线参考不能直接用于正式步行距离分析"
    ],

    "statistics": mode_stats
}

(ROOT / "changsha_quality_report.json").write_text(
    json.dumps(
        info,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

project.setFileName(
    str(ROOT / "changsha_distance.qgz")
)

if not project.write():
    raise RuntimeError(
        "QGIS工程保存失败"
    )

print("\n========== 长沙计算完成 ==========", flush=True)

print("结果目录：", ROOT, flush=True)

print(
    "Metro汇总：",
    MET / "changsha_metro_top20_summary.csv",
    flush=True
)

print(
    "Bus汇总：",
    BUS / "changsha_bus_top20_summary.csv",
    flush=True
)

print(
    "原始候选记录已进行数量核对。",
    flush=True
)

print(
    "提醒：直线后备值不是已验证步行距离。",
    flush=True
)
