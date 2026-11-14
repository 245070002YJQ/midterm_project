
# -*- coding: utf-8 -*-
# 宁波 + 苏州 CityWalk距离计算
# 完全独立脚本，不读取01distance_code.py
# QGIS Python Console -> Show Editor运行
# Dijkstra + 最多3个接入点
# 路网失败时单独保留直线参考，不冒充步行距离

from pathlib import Path
from collections import defaultdict
import ast
import csv
import gc
import json
import math
import shutil
import subprocess
import sys

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsPointXY,
    QgsGeometry, QgsFeature, QgsField,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsWkbTypes,
    QgsSpatialIndex, QgsVectorFileWriter
)
from qgis.analysis import (
    QgsVectorLayerDirector,
    QgsNetworkDistanceStrategy,
    QgsGraphBuilder,
    QgsGraphAnalyzer
)

# ==================================================
# 1. 路径和城市设置
# ==================================================

BASE = Path(r"D:\大三（上）\大数据原理期中")

SPLIT = (
    BASE / "data_file"
    / "15country_citywalk_data"
    / "split top20 cities data"
)

OSM = BASE / "yn_qgis_file_2025"
FINAL = BASE / "final result"

CITIES = {
    "ningbo": "宁波",
    "suzhou": "苏州"
}

ROADS = {
    "ningbo": "ningbo_osm_roads_2025-12-31_v1.gpkg",
    "suzhou": "suzhou_osm_roads_2025-12-31.parquet"
}

MAX_ANCHORS = 3
NEIGHBOR_ROADS = 10
TOPOLOGY_TOLERANCE = 0.5
WALK_M_PER_MIN = 75.0

# 与原来13城市相同的宽松道路规则
BASE_ROADS = {
    "footway", "pedestrian", "path", "steps",
    "residential", "living_street", "service",
    "unclassified", "primary", "secondary",
    "tertiary"
}

EXTRA_ROADS = {"cycleway", "track", "road"}
FOOT_OK = {"yes", "designated", "permissive"}
SIDEWALK_OK = {
    "yes", "both", "left", "right", "separate"
}

# ==================================================
# 2. 统一输出字段
# ==================================================

SUMMARY = [
    "城市", "景点编码", "景点名称",
    "800米API候选数", "候选成功路网数",
    "候选仅直线参考数", "最近站点名称",
    "最近站点POI_ID", "最近站点直线_米",
    "最近站点路网内_米", "景点直线接入_米",
    "站点直线接入_米", "最近站点估算总距_米",
    "估算步行分钟", "最近距离计算类型",
    "可能更近的未连通候选数",
    "状态", "质量提示", "2025道路来源", "CRS"
]

DETAIL = [
    "候选序号", "景点编码", "景点名称",
    "交通类型", "站点名称", "站点POI_ID",
    "经度WGS84", "纬度WGS84",
    "原API直线距离_米", "WGS84重算直线距离_米",
    "路网内_米", "景点接入直线_米",
    "站点接入直线_米", "道路加接入估算_米",
    "直线替代参考_米", "提供的距离数值_米",
    "计算类型", "失败原因", "质量提示",
    "原始Excel行"
]

# ==================================================
# 3. Parquet转换程序
# ==================================================

CONVERT = r'''
import sys
import json
from pathlib import Path

import pandas as pd
import geopandas as gpd

from shapely import wkb, wkt
from shapely.geometry import shape

src, dst = map(Path, sys.argv[1:3])

try:
    g = gpd.read_parquet(src)
except Exception:

    t = pd.read_parquet(src)

    col = next(
        (
            x for x in (
                "geometry", "geom", "wkb_geometry"
            )
            if x in t.columns
        ),
        None
    )

    if col is None:
        raise ValueError("Parquet没有几何字段")

    def geom(x):

        if isinstance(
            x, (bytes, bytearray, memoryview)
        ):
            return wkb.loads(bytes(x))

        if isinstance(x, dict):
            return shape(x)

        if isinstance(x, str):

            if x.startswith("{"):
                return shape(json.loads(x))

            try:
                return wkb.loads(bytes.fromhex(x))
            except Exception:
                return wkt.loads(x)

        return x

    t[col] = t[col].map(geom)

    g = gpd.GeoDataFrame(
        t, geometry=col
    )

if g.crs is None:

    b = g.total_bounds

    if not (
        73 < b[0] < 135
        and 18 < b[1] < 54
        and 73 < b[2] < 136
        and 18 < b[3] < 55
    ):
        raise ValueError(
            "道路没有CRS且无法确认WGS84"
        )

    g = g.set_crs(epsg=4326)

g = g[
    g.geometry.notna()
    & ~g.geometry.is_empty
].copy()

g = g[
    g.geometry.geom_type.isin(
        ["LineString", "MultiLineString"]
    )
].copy()

if g.empty:
    raise ValueError("没有道路几何")

if {
    "osm_id", "osm_type"
}.issubset(g.columns):

    g = g.drop_duplicates(
        subset=["osm_type", "osm_id"]
    )

def scalar(v):

    if (
        hasattr(v, "tolist")
        and not isinstance(v, (str, bytes))
    ):
        v = v.tolist()

    if isinstance(v, (dict, list, tuple)):
        return repr(v)

    return v

for c in g.columns:

    if c != g.geometry.name:

        if g[c].dtype == "object":
            g[c] = g[c].map(scalar)

g.to_file(
    dst,
    layer="osm_roads_2025",
    driver="GPKG"
)

print("历史道路转换完成：", len(g))
'''

# ==================================================
# 4. 通用函数
# ==================================================

def csvread(file, required):

    if not file.is_file():
        raise FileNotFoundError(str(file))

    with file.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as fp:

        reader = csv.DictReader(fp)

        missing = (
            set(required)
            - set(reader.fieldnames or [])
        )

        if missing:
            raise ValueError(
                f"{file.name}缺少列：{sorted(missing)}"
            )

        return list(reader)


def csvwrite(path, fields, records):

    with path.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as fp:

        writer = csv.DictWriter(
            fp,
            fieldnames=fields,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(records)


def norm(x):
    return "" if x is None else str(x).strip()


def length(a, b):
    return math.hypot(
        a.x() - b.x(),
        a.y() - b.y()
    )


def maybe(x):
    return round(x, 1) if x is not None else ""


# ==================================================
# 5. 自动读取宁波GPKG、苏州Parquet
# ==================================================

def load_historical(src, input_folder, city):

    layer = QgsVectorLayer(
        str(src),
        city + "_OSM_2025",
        "ogr"
    )

    if (
        layer.isValid()
        and layer.geometryType()
        == QgsWkbTypes.LineGeometry
        and layer.featureCount() > 0
    ):
        return layer, str(src)

    if src.suffix.lower() != ".parquet":
        raise RuntimeError(
            "历史GPKG不是有效道路图层："
            + str(src)
        )

    dest = (
        input_folder
        / (city + "_osm2025_from_parquet.gpkg")
    )

    needs_convert = (
        not dest.exists()
        or dest.stat().st_mtime
        < src.stat().st_mtime
    )

    if needs_convert:

        if dest.exists():
            dest.unlink()

        errors = []

        commands = [
            [sys.executable, "-c"],
            ["py", "-3", "-c"],
            ["python", "-c"]
        ]

        for prefix in commands:

            try:

                p = subprocess.run(
                    prefix + [
                        CONVERT,
                        str(src),
                        str(dest)
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=900
                )

                if (
                    p.returncode == 0
                    and dest.exists()
                ):
                    break

                errors.append(
                    prefix[0] + ": "
                    + p.stderr[-450:]
                )

            except (
                OSError,
                subprocess.TimeoutExpired
            ) as exc:

                errors.append(str(exc))

        else:

            raise RuntimeError(
                "苏州历史Parquet转换失败："
                + " | ".join(errors)
                + "。可在Windows终端安装："
                + "py -m pip install "
                + "geopandas pyarrow pyogrio shapely"
            )

    layer = QgsVectorLayer(
        str(dest),
        city + "_OSM_2025_转换",
        "ogr"
    )

    if (
        not layer.isValid()
        or layer.geometryType()
        != QgsWkbTypes.LineGeometry
        or layer.featureCount() == 0
    ):
        raise RuntimeError(
            "Parquet转换后不是有效线图层："
            + str(dest)
        )

    return layer, str(dest)


# ==================================================
# 6. OSM道路属性及步行规则
# ==================================================

def tags(feature, names):

    t = {}

    if "tags" in names:

        raw = feature["tags"]

        if isinstance(raw, str):

            try:
                raw = ast.literal_eval(raw)

            except Exception:

                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = {}

        try:

            if isinstance(raw, dict):

                t = {
                    str(k): str(v).lower()
                    for k, v in raw.items()
                }

            elif isinstance(raw, (list, tuple)):

                t = {
                    str(k): str(v).lower()
                    for k, v in raw
                }

        except Exception:
            t = {}

    for key in (
        "highway", "foot", "access",
        "motorroad", "sidewalk",
        "sidewalk:left", "sidewalk:right",
        "bridge", "tunnel", "layer"
    ):

        if key in names:

            value = feature[key]

            if (
                value is not None
                and str(value).lower()
                not in ("", "none", "null")
            ):
                t[key] = str(value).strip().lower()

    return t


def walkable(t):

    if t.get("foot") in ("no", "private"):
        return False

    if t.get("access") in ("no", "private"):
        return False

    if t.get("motorroad") == "yes":
        return False

    kind = t.get("highway", "")

    if kind in BASE_ROADS:
        return True

    if kind in EXTRA_ROADS:

        return (
            t.get("foot") in FOOT_OK
            or any(
                t.get(k) in SIDEWALK_OK
                for k in (
                    "sidewalk",
                    "sidewalk:left",
                    "sidewalk:right"
                )
            )
        )

    return False


# ==================================================
# 7. 创建及保存GIS图层
# ==================================================

def newlayer(kind, crs, fields, name):

    v = QgsVectorLayer(
        f"{kind}?crs={crs.authid()}",
        name,
        "memory"
    )

    data = []

    for key, typ in fields:

        q = (
            QVariant.Int if typ == "int"
            else QVariant.Double if typ == "number"
            else QVariant.String
        )

        data.append(QgsField(key, q))

    v.dataProvider().addAttributes(data)
    v.updateFields()

    return v


def put(layer, geom, attrs):

    f = QgsFeature(layer.fields())

    f.setGeometry(geom)
    f.setAttributes(attrs)

    ok, _ = (
        layer.dataProvider()
        .addFeatures([f])
    )

    if not ok:
        raise RuntimeError(
            "无法创建路线要素："
            + layer.name()
        )


def savegpkg(layer, path, project):

    if layer.featureCount() == 0:

        if path.exists():
            path.unlink()

        return None

    opt = (
        QgsVectorFileWriter.SaveVectorOptions()
    )

    opt.driverName = "GPKG"
    opt.layerName = path.stem

    # 允许覆盖本城市之前生成的同名结果
    opt.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteFile
    )

    result = (
        QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            str(path),
            project.transformContext(),
            opt
        )
    )

    if result[0] != QgsVectorFileWriter.NoError:

        raise RuntimeError(
            "无法保存GPKG，请关闭其他QGIS"
            "中打开的图层："
            + str(path)
            + " "
            + str(result)
        )

    loaded = QgsVectorLayer(
        str(path),
        path.stem,
        "ogr"
    )

    if (
        not loaded.isValid()
        or loaded.featureCount()
        != layer.featureCount()
    ):
        raise RuntimeError(
            "GPKG要素数校验失败："
            + str(path)
        )

    return loaded


# ==================================================
# 8. Dijkstra路径恢复
# ==================================================

def route_points(graph, tree, start, end):

    points = [
        graph.vertex(end).point()
    ]

    seen = set()
    now = end

    while now != start:

        if (
            now < 0
            or now in seen
            or tree[now] < 0
        ):
            return []

        seen.add(now)

        now = graph.edge(
            tree[now]
        ).fromVertex()

        points.append(
            graph.vertex(now).point()
        )

    return points[::-1]


def unique_points(seq):

    out = []

    for p in seq:

        if (
            not out
            or length(out[-1], p) > 0.001
        ):
            out.append(p)

    return out


# ==================================================
# 9. 计算一个城市
# ==================================================

def process(city, cn):

    project = QgsProject.instance()
    project.clear()

    dest = FINAL / city

    inp = dest / "input"
    md = dest / "metro"
    bd = dest / "bus"

    source_dir = SPLIT / city

    poi_file = (
        source_dir
        / f"{city}_top20_citywalk_wgs84.csv"
    )

    stopfiles = {
        mode: (
            source_dir
            / f"{city}_{mode}_stop_wgs84.csv"
        )
        for mode in ("metro", "bus")
    }

    roadfile = OSM / cn / ROADS[city]

    # 先检查所有输入
    for file in (
        poi_file,
        roadfile,
        *stopfiles.values()
    ):

        if not file.is_file():
            raise FileNotFoundError(
                "缺少文件：" + str(file)
            )

    pois_csv = csvread(
        poi_file,
        [
            "景点统一编码",
            "CityWalk景点名称",
            "lon_wgs84",
            "lat_wgs84"
        ]
    )

    unique_ids = {
        norm(r["景点统一编码"])
        for r in pois_csv
    }

    if (
        len(pois_csv) != 20
        or len(unique_ids) != 20
        or "" in unique_ids
    ):
        raise RuntimeError(
            city + "必须有20个不重复景点"
        )

    stops_csv = {
        mode: csvread(
            file,
            [
                "关联景点编码",
                "出入口/站点具体名称",
                "lon_wgs84",
                "lat_wgs84"
            ]
        )
        for mode, file in stopfiles.items()
    }

    for folder in (inp, md, bd):
        folder.mkdir(
            parents=True,
            exist_ok=True
        )

    # 拷贝输入文件到本城市input目录
    for file in (
        poi_file,
        roadfile,
        *stopfiles.values()
    ):

        copied = inp / file.name

        if (
            not copied.exists()
            or copied.stat().st_size
            != file.stat().st_size
            or copied.stat().st_mtime_ns
            != file.stat().st_mtime_ns
        ):
            shutil.copy2(file, copied)

    # ==============================================
    # 10. 读取2025 OSM
    # ==============================================

    roads, actual = load_historical(
        inp / roadfile.name,
        inp,
        city
    )

    names = set(
        roads.fields().names()
    )

    if not ({"tags", "highway"} & names):
        raise RuntimeError(
            "OSM缺少tags/highway属性"
        )

    if not roads.crs().isValid():
        raise RuntimeError(
            "OSM道路CRS缺失"
        )

    # 自动选择城市对应的米制UTM投影
    lon = float(
        pois_csv[0]["lon_wgs84"]
    )

    zone = int(
        (lon + 180) // 6
    ) + 1

    crs = QgsCoordinateReferenceSystem(
        f"EPSG:{32600 + zone}"
    )

    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        crs,
        project.transformContext()
    )

    road_tx = QgsCoordinateTransform(
        roads.crs(),
        crs,
        project.transformContext()
    )

    def xy(row):

        lon = float(row["lon_wgs84"])
        lat = float(row["lat_wgs84"])

        if not (
            73 < lon < 135
            and 18 < lat < 54
            and math.isfinite(lon)
            and math.isfinite(lat)
        ):
            raise ValueError(
                "无效WGS84经纬度"
            )

        return transform.transform(
            QgsPointXY(lon, lat)
        )

    # ==============================================
    # 11. 筛选候选步行道路
    # ==============================================

    fields = [
        ("osm_id", "text"),
        ("highway", "text"),
        ("foot", "text"),
        ("access", "text"),
        ("bridge", "text"),
        ("tunnel", "text"),
        ("layer", "text"),
        ("main_foot_unknown", "int")
    ]

    candidate = newlayer(
        "MultiLineString",
        crs,
        fields,
        city + "_walkable"
    )

    batch = []
    main_unknown = 0
    kept = 0

    for f in roads.getFeatures():

        t = tags(f, names)

        if not walkable(t):
            continue

        g = QgsGeometry(
            f.geometry()
        )

        if (
            g.isNull()
            or g.isEmpty()
            or g.transform(road_tx) != 0
        ):
            continue

        if not g.isMultipart():
            g.convertToMultiType()

        unknown = (
            t.get("highway")
            in {
                "primary",
                "secondary",
                "tertiary"
            }
            and t.get("foot")
            not in FOOT_OK
            and not any(
                t.get(k) in SIDEWALK_OK
                for k in (
                    "sidewalk",
                    "sidewalk:left",
                    "sidewalk:right"
                )
            )
        )

        ff = QgsFeature(
            candidate.fields()
        )

        ff.setGeometry(g)

        osm_id = (
            norm(f["osm_id"])
            if "osm_id" in names
            else str(f.id())
        )

        ff.setAttributes([
            osm_id,
            t.get("highway", ""),
            t.get("foot", ""),
            t.get("access", ""),
            t.get("bridge", ""),
            t.get("tunnel", ""),
            t.get("layer", ""),
            int(unknown)
        ])

        batch.append(ff)

        kept += 1
        main_unknown += int(unknown)

        if len(batch) >= 1000:

            ok, _ = (
                candidate.dataProvider()
                .addFeatures(batch)
            )

            if not ok:
                raise RuntimeError(
                    "候选道路无法写入"
                )

            batch = []

    if batch:

        ok, _ = (
            candidate.dataProvider()
            .addFeatures(batch)
        )

        if not ok:
            raise RuntimeError(
                "候选道路最后一批写入失败"
            )

    candidate.updateExtents()

    if kept < 100:
        raise RuntimeError(
            "OSM候选道路太少："
            + str(kept)
        )

    network = savegpkg(
        candidate,
        inp / f"{city}_walkable_2025.gpkg",
        project
    )

    print(
        f"{cn} 原道路{roads.featureCount()}，"
        f"候选步行道{kept}",
        flush=True
    )

    # ==============================================
    # 12. 寻找最多3个道路接入位置
    # ==============================================

    si = QgsSpatialIndex(
        network.getFeatures(),
        flags=(
            QgsSpatialIndex.FlagStoreFeatureGeometries
        )
    )

    cache = {}
    all_ties = []

    def anchors(p):

        key = (
            round(p.x(), 3),
            round(p.y(), 3)
        )

        if key in cache:
            return cache[key]

        out = []

        nearby_ids = si.nearestNeighbor(
            p,
            NEIGHBOR_ROADS
        )

        for fid in nearby_ids:

            road_geom = si.geometry(fid)

            near = road_geom.nearestPoint(
                QgsGeometry.fromPointXY(p)
            )

            if near.isNull() or near.isEmpty():
                continue

            q = QgsPointXY(
                near.asPoint()
            )

            if any(
                length(q, x["point"]) < 0.5
                for x in out
            ):
                continue

            a = {
                "point": q,
                "off": length(p, q),
                "index": len(all_ties)
            }

            all_ties.append(q)
            out.append(a)

            if len(out) >= MAX_ANCHORS:
                break

        cache[key] = out

        return out

    pois = []
    pois_by_id = {}

    for row in pois_csv:

        p = {
            "id": norm(
                row["景点统一编码"]
            ),
            "name": norm(
                row["CityWalk景点名称"]
            ),
            "point": xy(row)
        }

        p["anchors"] = anchors(
            p["point"]
        )

        pois.append(p)
        pois_by_id[p["id"]] = p

    stations = {}

    for mode, rows in stops_csv.items():

        groups = defaultdict(list)

        for num, row in enumerate(rows, 1):

            pid = norm(
                row["关联景点编码"]
            )

            st = {
                "pid": pid,
                "name": norm(
                    row["出入口/站点具体名称"]
                ),
                "raw": row,
                "number": num,
                "error": "",
                "point": None,
                "air": None,
                "anchors": []
            }

            if pid not in pois_by_id:

                st["error"] = (
                    "关联编码不在TOP20"
                )

            else:

                try:

                    st["point"] = xy(row)

                    st["air"] = length(
                        st["point"],
                        pois_by_id[pid]["point"]
                    )

                    st["anchors"] = anchors(
                        st["point"]
                    )

                except Exception as e:

                    st["error"] = (
                        "经纬度无效：" + str(e)
                    )

            groups[pid].append(st)

        stations[mode] = groups

    print(
        f"{cn} 地铁{len(stops_csv['metro'])}条，"
        f"公交{len(stops_csv['bus'])}条，"
        f"接入点{len(all_ties)}",
        flush=True
    )

    # ==============================================
    # 13. 构建Dijkstra道路图
    # ==============================================

    director = QgsVectorLayerDirector(
        network,
        -1,
        "",
        "",
        "",
        QgsVectorLayerDirector.DirectionBoth
    )

    director.addStrategy(
        QgsNetworkDistanceStrategy()
    )

    builder = QgsGraphBuilder(
        crs,
        True,
        TOPOLOGY_TOLERANCE
    )

    tied = director.makeGraph(
        builder,
        all_ties
    )

    graph = builder.graph()

    if len(tied) != len(all_ties):
        raise RuntimeError(
            "路网接入点数量不一致"
        )

    vertices = [
        graph.findVertex(p)
        for p in tied
    ]

    def good(entries):

        return [
            a for a in entries
            if vertices[a["index"]] >= 0
        ]

    print(
        f"{cn} 构图："
        f"{graph.vertexCount()}节点，"
        f"{graph.edgeCount()}有向边",
        flush=True
    )

    # ==============================================
    # 14. 创建结果路线图层
    # ==============================================

    routefields = [
        ("mode", "text"),
        ("poi", "text"),
        ("station", "text"),
        ("road_m", "number"),
        ("estimate_m", "number"),
        ("is_nearest", "int"),
        ("risk", "text")
    ]

    all_routes = newlayer(
        "LineString",
        crs,
        routefields,
        "全部候选路网路线"
    )

    nearest_routes = newlayer(
        "LineString",
        crs,
        routefields,
        "最近路网路线"
    )

    connectors = newlayer(
        "LineString",
        crs,
        [
            ("kind", "text"),
            ("poi", "text"),
            ("station", "text"),
            ("access_m", "number")
        ],
        "直线接入未核验"
    )

    for poi in pois:

        for a in poi["anchors"]:

            if a["off"] > 0.01:

                put(
                    connectors,
                    QgsGeometry.fromPolylineXY([
                        poi["point"],
                        a["point"]
                    ]),
                    [
                        "景点",
                        poi["id"],
                        "",
                        round(a["off"], 2)
                    ]
                )

    for mode, groups in stations.items():

        for stops in groups.values():

            for st in stops:

                for a in st["anchors"]:

                    if a["off"] > 0.01:

                        put(
                            connectors,
                            QgsGeometry.fromPolylineXY([
                                st["point"],
                                a["point"]
                            ]),
                            [
                                mode,
                                st["pid"],
                                st["name"],
                                round(a["off"], 2)
                            ]
                        )

    # ==============================================
    # 15. 分别计算Metro与Bus
    # ==============================================

    stats = {}

    for mode, folder in [
        ("metro", md),
        ("bus", bd)
    ]:

        summary = []
        details = []
        failed = []

        route_n = 0
        fallback_n = 0
        empty_n = 0

        for i, poi in enumerate(pois, 1):

            stops = stations[mode].get(
                poi["id"],
                []
            )

            good_paths = []
            trees = []

            # 每个景点最多3次Dijkstra
            for a in good(poi["anchors"]):

                start = vertices[
                    a["index"]
                ]

                tree, costs = (
                    QgsGraphAnalyzer.dijkstra(
                        graph,
                        start,
                        0
                    )
                )

                trees.append((
                    a,
                    start,
                    tree,
                    costs
                ))

            # 每一条站点候选都计算
            for st in stops:

                best = None
                error = st["error"]

                if not error and not trees:
                    error = (
                        "景点没有有效路网接入点"
                    )

                if (
                    not error
                    and not good(st["anchors"])
                ):
                    error = (
                        "站点没有有效路网接入点"
                    )

                if not error:

                    for sa, sv, tree, costs in trees:

                        for ea in good(st["anchors"]):

                            ev = vertices[
                                ea["index"]
                            ]

                            if (
                                ev != sv
                                and tree[ev] < 0
                            ):
                                continue

                            road_m = float(
                                costs[ev]
                            )

                            total = (
                                road_m
                                + sa["off"]
                                + ea["off"]
                            )

                            if not math.isfinite(total):
                                continue

                            if (
                                best
                                and total >= best["total"]
                            ):
                                continue

                            points = route_points(
                                graph,
                                tree,
                                sv,
                                ev
                            )

                            if not points:
                                continue

                            coords = unique_points(
                                [poi["point"]]
                                + points
                                + [st["point"]]
                            )

                            if len(coords) < 2:
                                continue

                            best = {
                                "stop": st,
                                "road": road_m,
                                "total": total,
                                "start": sa,
                                "end": ea,
                                "coords": coords
                            }

                    if best is None:
                        error = (
                            "OSM候选道路网络不连通"
                        )

                if best:

                    route_n += 1
                    good_paths.append(best)

                elif st["air"] is not None:

                    fallback_n += 1

                value = (
                    best["total"]
                    if best
                    else st["air"]
                )

                review = (
                    "入口、建筑、围墙、门禁、"
                    "桥隧未核验"
                )

                if (
                    best
                    and max(
                        best["start"]["off"],
                        best["end"]["off"]
                    ) > 30
                ):
                    review += (
                        "；接入直线超过30米"
                    )

                if (
                    st["air"] is not None
                    and st["air"] > 800
                ):
                    review += (
                        "；WGS84重算直线超过800米，"
                        "请复核API"
                    )

                row = {
                    "候选序号": st["number"],
                    "景点编码": poi["id"],
                    "景点名称": poi["name"],
                    "交通类型": mode,
                    "站点名称": st["name"],

                    "站点POI_ID": st["raw"].get(
                        "高德设施POI_ID", ""
                    ),

                    "经度WGS84": st["raw"].get(
                        "lon_wgs84", ""
                    ),

                    "纬度WGS84": st["raw"].get(
                        "lat_wgs84", ""
                    ),

                    "原API直线距离_米": st["raw"].get(
                        "距景点直线距离(米)", ""
                    ),

                    "WGS84重算直线距离_米": maybe(
                        st["air"]
                    ),

                    "路网内_米": (
                        maybe(best["road"])
                        if best else ""
                    ),

                    "景点接入直线_米": (
                        maybe(best["start"]["off"])
                        if best else ""
                    ),

                    "站点接入直线_米": (
                        maybe(best["end"]["off"])
                        if best else ""
                    ),

                    "道路加接入估算_米": (
                        maybe(best["total"])
                        if best else ""
                    ),

                    "直线替代参考_米": (
                        maybe(st["air"])
                        if not best else ""
                    ),

                    "提供的距离数值_米": maybe(value),

                    "计算类型": (
                        "Dijkstra+两端直线接入(未核验)"
                        if best
                        else
                        "仅直线距离参考(不能当步行距离)"
                    ),

                    "失败原因": error,
                    "质量提示": review,

                    "原始Excel行": st["raw"].get(
                        "source_excel_row", ""
                    )
                }

                details.append(row)

                if not best:
                    failed.append(row)

            # 没有候选时保留景点
            if not stops:

                empty_n += 1

                details.append({
                    "景点编码": poi["id"],
                    "景点名称": poi["name"],
                    "交通类型": mode,
                    "计算类型": (
                        "800米API候选表内没有站点"
                    ),
                    "失败原因": "没有候选站点"
                })

            # ======================================
            # 16. 最近站点选择
            # ======================================

            if good_paths:

                selected = min(
                    good_paths,
                    key=lambda x: x["total"]
                )

                nearest = selected["stop"]

                total = selected["total"]
                road_m = selected["road"]

                start_m = selected["start"]["off"]
                end_m = selected["end"]["off"]

                method = (
                    "Dijkstra+直线接入(未核验)"
                )

                not_routed = [
                    s for s in stops
                    if not any(
                        x["stop"] is s
                        for x in good_paths
                    )
                ]

                possible = sum(
                    s["air"] is not None
                    and s["air"] < total
                    for s in not_routed
                )

                if len(good_paths) == len(stops):

                    status = (
                        "全部候选路网连通"
                        "（接入段未核验）"
                    )

                else:

                    status = (
                        "部分候选路网连通；"
                        "其余仅直线参考"
                    )

            else:

                candidates = [
                    s for s in stops
                    if s["air"] is not None
                ]

                nearest = (
                    min(
                        candidates,
                        key=lambda s: s["air"]
                    )
                    if candidates
                    else None
                )

                selected = None

                total = (
                    nearest["air"]
                    if nearest
                    else None
                )

                road_m = None
                start_m = None
                end_m = None

                possible = 0

                method = (
                    "仅直线参考(非步行距离)"
                    if nearest
                    else "没有有效候选"
                )

                if not stops:

                    status = "没有800米候选站点"

                elif nearest:

                    status = (
                        "全部候选路网失败；"
                        "最近仅按直线参考选择"
                    )

                else:

                    status = "候选点坐标无效"

            summary.append({
                "城市": cn,
                "景点编码": poi["id"],
                "景点名称": poi["name"],

                "800米API候选数": len(stops),

                "候选成功路网数": len(good_paths),

                "候选仅直线参考数": (
                    sum(
                        s["air"] is not None
                        for s in stops
                    ) - len(good_paths)
                ),

                "最近站点名称": (
                    nearest["name"]
                    if nearest
                    else "没有"
                ),

                "最近站点POI_ID": (
                    nearest["raw"].get(
                        "高德设施POI_ID", ""
                    )
                    if nearest
                    else ""
                ),

                "最近站点直线_米": (
                    maybe(nearest["air"])
                    if nearest
                    else ""
                ),

                "最近站点路网内_米": maybe(road_m),

                "景点直线接入_米": maybe(start_m),

                "站点直线接入_米": maybe(end_m),

                "最近站点估算总距_米": maybe(total),

                "估算步行分钟": (
                    maybe(total / WALK_M_PER_MIN)
                    if selected
                    else ""
                ),

                "最近距离计算类型": method,

                "可能更近的未连通候选数": possible,

                "状态": status,

                "质量提示": (
                    "路网接入段未核验；"
                    "仅直线参考不能当步行距离"
                ),

                "2025道路来源": roadfile.name,

                "CRS": crs.authid()
            })

            # 保存每条成功候选路线
            for item in good_paths:

                st = item["stop"]

                is_nearest = int(
                    item is selected
                )

                geom = (
                    QgsGeometry.fromPolylineXY(
                        item["coords"]
                    )
                )

                attrs = [
                    mode,
                    poi["id"],
                    st["name"],
                    round(item["road"], 2),
                    round(item["total"], 2),
                    is_nearest,
                    "直线接入、桥隧未核验"
                ]

                put(
                    all_routes,
                    geom,
                    attrs
                )

                if is_nearest:

                    put(
                        nearest_routes,
                        geom,
                        attrs
                    )

            print(
                f"[{cn} {mode} {i:02d}/20] "
                f"{poi['name']} "
                f"候选{len(stops)} "
                f"路网成功{len(good_paths)}",
                flush=True
            )

        # 关联到TOP20之外的候选也不丢弃
        for pid, items in stations[mode].items():

            if pid in pois_by_id:
                continue

            for st in items:

                row = {
                    "候选序号": st["number"],
                    "景点编码": pid,
                    "交通类型": mode,
                    "站点名称": st["name"],
                    "计算类型": "数据异常",
                    "失败原因": st["error"]
                }

                details.append(row)
                failed.append(row)

        expected = (
            len(stops_csv[mode]) + empty_n
        )

        if (
            len(summary) != 20
            or len(details) != expected
        ):
            raise RuntimeError(
                f"{cn} {mode}候选数核对失败："
                f"汇总{len(summary)}/20，"
                f"明细{len(details)}/{expected}"
            )

        # ======================================
        # 17. 保存Excel可打开的CSV
        # ======================================

        csvwrite(
            folder / f"{city}_{mode}_top20_summary.csv",
            SUMMARY,
            summary
        )

        csvwrite(
            folder / f"{city}_{mode}_all_candidates.csv",
            DETAIL,
            details
        )

        csvwrite(
            folder / f"{city}_{mode}_failed_candidates.csv",
            DETAIL,
            failed
        )

        stats[mode] = {
            "source_records": len(stops_csv[mode]),
            "detail_rows": len(details),
            "no_candidate_pois": empty_n,
            "network_routed": route_n,
            "air_reference": fallback_n,
            "failed_candidates": len(failed),

            "poi_nearest_has_road": sum(
                "Dijkstra" in r["最近距离计算类型"]
                for r in summary
            )
        }

    # ==============================================
    # 18. 核对并保存路线GPKG
    # ==============================================

    expected = sum(
        stats[m]["network_routed"]
        for m in stats
    )

    if all_routes.featureCount() != expected:
        raise RuntimeError(
            "全部路线数量与成功候选数不一致"
        )

    project.setCrs(crs)

    project.addMapLayer(network)

    output_layers = [
        (
            all_routes,
            f"{city}_all_candidate_routes.gpkg"
        ),
        (
            nearest_routes,
            f"{city}_nearest_routes.gpkg"
        ),
        (
            connectors,
            f"{city}_straight_connectors_NOT_verified.gpkg"
        )
    ]

    for layer, filename in output_layers:

        saved = savegpkg(
            layer,
            dest / filename,
            project
        )

        if saved:
            project.addMapLayer(saved)

    # ==============================================
    # 19. 保存质量报告
    # ==============================================

    report = {
        "city": cn,
        "OSM_2025_file": str(roadfile),
        "OSM_road_read": actual,

        "OSM_source_count": roads.featureCount(),

        "candidate_road_count": kept,

        "main_roads_foot_unknown": main_unknown,

        "graph_nodes": graph.vertexCount(),

        "graph_edges": graph.edgeCount(),

        "candidate_route_features": (
            all_routes.featureCount()
        ),

        "nearest_route_features": (
            nearest_routes.featureCount()
        ),

        "algorithm": (
            "Dijkstra、每点最多3个接入位置，"
            "失败单独保留直线参考"
        ),

        "notes": [
            "原API800米候选不再二次截断",
            "2025道路历史真实性以A来源核对",
            "直线接入可能穿过建筑、围墙和门禁",
            "桥隧连接关系未核验",
            "没有路网的候选只能用直线参考，"
            "不能称作真实步行距离"
        ],

        "modes": stats
    }

    quality_file = (
        dest / f"{city}_quality_report.json"
    )

    quality_file.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    # ==============================================
    # 20. 保存QGIS工程
    # ==============================================

    project.setFileName(
        str(dest / f"{city}_distance.qgz")
    )

    if not project.write():
        raise RuntimeError(
            "QGIS工程保存失败"
        )

    print(
        cn,
        "完成：",
        stats,
        flush=True
    )

    project.clear()
    gc.collect()

    return {
        "city": city,
        "name": cn,
        "status": "OK",
        "note": str(dest),

        **{
            m + "_" + k: v
            for m, one in stats.items()
            for k, v in one.items()
        }
    }


# ==================================================
# 21. 一次运行宁波、苏州
# ==================================================

if QgsProject.instance().mapLayers():

    raise RuntimeError(
        "请先点击 Project > New，"
        "打开空白QGIS工程"
    )

FINAL.mkdir(
    parents=True,
    exist_ok=True
)

results = []

for city, cn in CITIES.items():

    print(
        "\n======== 开始处理",
        cn,
        "========",
        flush=True
    )

    try:

        result = process(
            city,
            cn
        )

    except Exception as exc:

        result = {
            "city": city,
            "name": cn,
            "status": "FAILED",
            "note": repr(exc)
        }

        print(
            cn,
            "失败：",
            repr(exc),
            flush=True
        )

        QgsProject.instance().clear()
        gc.collect()

    results.append(result)

    # 单独保存两城市报告
    # 不覆盖13城市报告
    columns = [
        "city",
        "name",
        "status",
        "note"
    ]

    extras = set().union(
        *(set(r) for r in results)
    )

    columns += sorted(
        extras - set(columns)
    )

    csvwrite(
        FINAL
        / "distance_run_summary_ningbo_suzhou.csv",
        columns,
        results
    )

print(
    "\n======== 全部结束 ========",
    flush=True
)

for result in results:

    print(
        result["name"],
        result["status"],
        result["note"],
        flush=True
    )
