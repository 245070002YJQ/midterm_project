
# -*- coding: utf-8 -*-
# 15城市CityWalk交通可达性统一代码
# 当前运行13城市，宁波和苏州暂不纳入
# QGIS Desktop -> Python Console -> Show Editor
# 输入：2025 OSM + TOP20景点 + Metro/Bus WGS84
# 方法：Dijkstra + 最多3个道路接入点
# 失败：单独给直线参考，绝不冒充路网距离

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
    QgsProject,
    QgsVectorLayer,
    QgsPointXY,
    QgsGeometry,
    QgsFeature,
    QgsField,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsWkbTypes,
    QgsSpatialIndex,
    QgsVectorFileWriter,
)
from qgis.analysis import (
    QgsVectorLayerDirector,
    QgsNetworkDistanceStrategy,
    QgsGraphBuilder,
    QgsGraphAnalyzer,
)

# =====================================================
# 1. 全部路径和13个城市
# =====================================================

ROOT = Path(r"D:\大三（上）\大数据原理期中")

FINAL = ROOT / "final result"

OSM_ROOT = ROOT / "yn_qgis_file_2025"

SPLIT = (
    ROOT / "data_file"
    / "15country_citywalk_data"
    / "split top20 cities data"
)

CITIES = {
    "chengdu": "成都",
    "chongqing": "重庆",
    "hangzhou": "杭州",
    "nanjing": "南京",
    "wuhan": "武汉",
    "xian": "西安",
    "changsha": "长沙",
    "zhengzhou": "郑州",
    "qingdao": "青岛",
    "tianjin": "天津",
    "hefei": "合肥",
    "foshan": "佛山",
    "dongguan": "东莞",
}

# 宁波、苏州补全之后，可以添加：
# "ningbo": "宁波",
# "suzhou": "苏州",

# 已经有完整QGIS工程的城市不覆盖
SKIP_EXISTING_PROJECT = True

# 成都统一宽松路网规则
TOPOLOGY_TOLERANCE = 0.5

# 每个点最多考虑3个不同道路接入点
MAX_ANCHORS = 3

# 从最近10条道路中寻找接入点
NEIGHBOR_ROADS = 10

# 估算步行速度：75米/分钟
WALK_M_PER_MIN = 75.0

# 允许进入候选步行网络的道路
ROAD_BASE = {
    "footway",
    "pedestrian",
    "path",
    "steps",
    "residential",
    "living_street",
    "service",
    "unclassified",
    "primary",
    "secondary",
    "tertiary",
}

# 需要明确步行标记才能纳入的道路
ROAD_EXTRA = {
    "cycleway",
    "track",
    "road",
}

WALK_TAGS = {
    "yes", "designated", "permissive"
}

SIDEWALK_TAGS = {
    "yes", "both", "left", "right", "separate"
}

VETO_FOOT = {"no", "private"}
VETO_ACCESS = {"no", "private"}

FINAL.mkdir(parents=True, exist_ok=True)

project = QgsProject.instance()

if project.mapLayers():
    raise RuntimeError(
        "请先保存当前QGIS工程，然后点击 "
        "Project -> New，新建空白工程再运行。"
    )

# =====================================================
# 2. 自动转换历史Parquet
# =====================================================

PARQUET_CONVERTER = r'''
from pathlib import Path
import sys
import json
import pandas as pd
import geopandas as gpd

from shapely import wkb, wkt
from shapely.geometry import shape
from shapely.ops import unary_union

src, out, aoi_path = map(Path, sys.argv[1:4])

try:
    g = gpd.read_parquet(src)

except Exception:

    t = pd.read_parquet(src)

    geom_col = next(
        (
            x for x in
            ("geometry", "geom", "wkb_geometry")
            if x in t.columns
        ),
        None
    )

    if geom_col is None:
        raise ValueError("Parquet没有几何字段")

    def asgeom(x):

        if isinstance(x, (bytes, bytearray, memoryview)):
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

    t[geom_col] = t[geom_col].map(asgeom)

    g = gpd.GeoDataFrame(
        t,
        geometry=geom_col
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
            "Parquet没有CRS且坐标无法确认"
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

if len(g) == 0:
    raise ValueError("历史Parquet没有有效道路线")

# 去除相同OSM要素的重复记录
if {"osm_id", "osm_type"}.issubset(g.columns):

    g = g.drop_duplicates(
        subset=["osm_type", "osm_id"]
    )

# 如果有A的AOI，按AOI范围裁切
if aoi_path.is_file():

    area = gpd.read_file(aoi_path)

    if area.crs is None:
        raise ValueError("AOI没有CRS")

    area = area.to_crs(g.crs)

    clipgeom = unary_union(
        list(area.geometry)
    )

    g = g[
        g.geometry.intersects(clipgeom)
    ].copy()

    g["geometry"] = g.geometry.intersection(
        clipgeom
    )

    g = g[
        g.geometry.notna()
        & ~g.geometry.is_empty
    ]

    g = g[
        g.geometry.geom_type.isin(
            ["LineString", "MultiLineString"]
        )
    ].copy()

def simple(v):

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

        if str(g[c].dtype) == "object":
            g[c] = g[c].map(simple)

if out.exists():
    out.unlink()

g.to_file(
    out,
    layer="osm_roads_2025",
    driver="GPKG"
)

print("2025历史道路转换完成：", len(g))
'''


def load_road(src, input_dir, city):

    layer = QgsVectorLayer(
        str(src),
        f"{city}_2025roads",
        "ogr"
    )

    if (
        layer.isValid()
        and layer.geometryType() == QgsWkbTypes.LineGeometry
        and layer.featureCount() > 0
    ):
        return layer, src

    if src.suffix.lower() != ".parquet":
        raise RuntimeError(
            f"2025道路不是有效线图层：{src.name}"
        )

    output = (
        input_dir
        / f"{city}_osm2025_from_parquet.gpkg"
    )

    aoi = (
        OSM_ROOT
        / CITIES[city]
        / f"{city}_aoi_projected.gpkg"
    )

    if not output.is_file():

        trials = [
            [sys.executable, "-c"],
            ["py", "-3", "-c"],
            ["python", "-c"],
        ]

        problems = []

        for command in trials:

            try:

                result = subprocess.run(
                    command + [
                        PARQUET_CONVERTER,
                        str(src),
                        str(output),
                        str(aoi),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=900,
                    encoding="utf-8",
                    errors="replace",
                )

                if (
                    result.returncode == 0
                    and output.is_file()
                ):
                    print(
                        "历史Parquet自动转换成功：",
                        result.stdout[-350:]
                    )
                    break

                problems.append(
                    command[0] + ": "
                    + result.stderr[-650:]
                )

            except (
                OSError,
                subprocess.TimeoutExpired
            ) as e:

                problems.append(
                    command[0] + ": " + str(e)
                )

        if not output.exists():

            raise RuntimeError(
                "QGIS无法读取历史Parquet，"
                "自动转换也失败。\n"
                "请在Windows Python安装：\n"
                "py -m pip install "
                "geopandas pyarrow pyogrio shapely\n"
                + "\n".join(problems)
            )

    layer = QgsVectorLayer(
        str(output),
        f"{city}_OSM2025转换后",
        "ogr"
    )

    if (
        not layer.isValid()
        or layer.geometryType() != QgsWkbTypes.LineGeometry
        or layer.featureCount() == 0
    ):
        raise RuntimeError(
            "Parquet转换后的GPKG无效"
        )

    return layer, output


# =====================================================
# 3. 通用辅助函数
# =====================================================

def read_csv(path, required, optional=False):

    if not path.is_file():

        if optional:
            return []

        raise FileNotFoundError(str(path))

    with path.open(
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        missing = (
            set(required)
            - set(reader.fieldnames or [])
        )

        if missing:
            raise ValueError(
                f"{path.name}缺少列：{sorted(missing)}"
            )

        return list(reader)


def norm_id(x):
    return str(x or "").strip()


def get_tags(feature, fields):

    tags = {}

    if "tags" in fields:

        value = feature["tags"]

        if isinstance(value, str):

            try:
                value = ast.literal_eval(value)

            except Exception:

                try:
                    value = json.loads(value)
                except Exception:
                    value = {}

        if isinstance(value, dict):

            tags = {
                str(k): str(v)
                for k, v in value.items()
            }

        elif isinstance(value, (tuple, list)):

            try:
                tags = {
                    str(k): str(v)
                    for k, v in value
                }
            except Exception:
                pass

    # 同时支持佛山的独立字段
    for key in (
        "highway",
        "foot",
        "access",
        "motorroad",
        "sidewalk",
        "sidewalk:left",
        "sidewalk:right",
        "bridge",
        "tunnel",
        "layer",
        "oneway:foot",
    ):

        if key in fields:

            value = feature[key]

            if (
                value is not None
                and str(value).strip().lower()
                not in ("", "null", "none")
            ):

                tags[key] = str(value).strip()

    return tags


def allowed(tags):

    kind = tags.get(
        "highway", ""
    ).lower()

    if (
        tags.get("foot", "").lower()
        in VETO_FOOT
    ):
        return False

    if (
        tags.get("access", "").lower()
        in VETO_ACCESS
    ):
        return False

    if (
        tags.get("motorroad", "").lower()
        == "yes"
    ):
        return False

    if kind in ROAD_BASE:
        return True

    if kind in ROAD_EXTRA:

        if (
            tags.get("foot", "").lower()
            in WALK_TAGS
        ):
            return True

        for key in (
            "sidewalk",
            "sidewalk:left",
            "sidewalk:right",
        ):

            if (
                tags.get(key, "").lower()
                in SIDEWALK_TAGS
            ):
                return True

    return False


def save_layer(layer, path, project):

    if layer.featureCount() == 0:
        return None

    if path.exists():
        raise FileExistsError(
            "输出图层已经存在，避免覆盖："
            + str(path)
        )

    options = (
        QgsVectorFileWriter.SaveVectorOptions()
    )

    options.driverName = "GPKG"
    options.layerName = path.stem

    result = (
        QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            str(path),
            project.transformContext(),
            options,
        )
    )

    if result[0] != QgsVectorFileWriter.NoError:

        raise RuntimeError(
            f"GPKG保存失败：{path} | {result}"
        )

    saved = QgsVectorLayer(
        str(path),
        path.stem,
        "ogr",
    )

    if (
        not saved.isValid()
        or saved.featureCount()
        != layer.featureCount()
    ):
        raise RuntimeError(
            "保存后的图层数量不一致："
            + str(path)
        )

    return saved


def point_xy(row, transformer):

    lon = float(row["lon_wgs84"])
    lat = float(row["lat_wgs84"])

    if not (
        73 < lon < 135
        and 18 < lat < 54
        and math.isfinite(lon)
        and math.isfinite(lat)
    ):
        raise ValueError(
            "WGS84坐标超出合理范围"
        )

    return transformer.transform(
        QgsPointXY(lon, lat)
    )


def distance(a, b):

    return math.hypot(
        a.x() - b.x(),
        a.y() - b.y(),
    )


def add_geometry(layer, geometry, attributes):

    feature = QgsFeature(
        layer.fields()
    )

    feature.setGeometry(geometry)
    feature.setAttributes(attributes)

    ok, _ = (
        layer.dataProvider().addFeatures(
            [feature]
        )
    )

    if not ok:
        raise RuntimeError(
            "无法写入路线图层"
        )


def save_csv(path, columns, records):

    with path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(records)


def new_layer(kind, crs, name, specs):

    layer = QgsVectorLayer(
        f"{kind}?crs={crs.authid()}",
        name,
        "memory",
    )

    fields = []

    for key, data_type in specs:

        if data_type == "double":
            typ = QVariant.Double

        elif data_type == "int":
            typ = QVariant.Int

        else:
            typ = QVariant.String

        fields.append(
            QgsField(key, typ)
        )

    layer.dataProvider().addAttributes(
        fields
    )

    layer.updateFields()

    return layer


def unique_coords(points):

    result = []

    for point in points:

        if (
            not result
            or distance(point, result[-1]) > 0.001
        ):
            result.append(point)

    return result


def restore_path(graph, tree, start, end):

    points = [
        graph.vertex(end).point()
    ]

    seen = set()
    vertex = end

    while vertex != start:

        if (
            vertex < 0
            or vertex in seen
            or tree[vertex] < 0
        ):
            return []

        seen.add(vertex)

        edge = graph.edge(
            tree[vertex]
        )

        vertex = edge.fromVertex()

        points.append(
            graph.vertex(vertex).point()
        )

    return points[::-1]


# =====================================================
# 4. 输出表格统一字段
# =====================================================

SUMMARY_COLUMNS = [
    "城市",
    "景点编码",
    "景点名称",
    "800米API候选数",
    "候选成功路网数",
    "候选仅直线参考数",
    "最近站点名称",
    "最近站点POI_ID",
    "最近站点直线_米",
    "最近站点路网内_米",
    "景点直线接入_米",
    "站点直线接入_米",
    "最近站点估算总距_米",
    "估算步行分钟",
    "最近距离计算类型",
    "可能更近的未连通候选数",
    "状态",
    "质量提示",
    "2025道路来源",
    "CRS",
]

DETAIL_COLUMNS = [
    "候选序号",
    "景点编码",
    "景点名称",
    "交通类型",
    "站点名称",
    "站点POI_ID",
    "经度WGS84",
    "纬度WGS84",
    "原API直线距离_米",
    "WGS84重算直线距离_米",
    "路网内_米",
    "景点接入直线_米",
    "站点接入直线_米",
    "道路加接入估算_米",
    "直线替代参考_米",
    "提供的距离数值_米",
    "计算类型",
    "失败原因",
    "质量提示",
    "原始Excel行",
]


# =====================================================
# 5. 一个城市完整计算
# =====================================================

def process_city(city, chinese_name):

    output = FINAL / city

    input_dir = output / "input"
    metro_dir = output / "metro"
    bus_dir = output / "bus"

    project_file = (
        output / f"{city}_distance.qgz"
    )

    # 已完成的不覆盖
    if (
        SKIP_EXISTING_PROJECT
        and project_file.exists()
    ):

        return {
            "city": city,
            "name": chinese_name,
            "status": "SKIPPED_EXISTING",
            "note": str(project_file),
        }

    csv_folder = SPLIT / city

    poi_source = (
        csv_folder
        / f"{city}_top20_citywalk_wgs84.csv"
    )

    metro_source = (
        csv_folder
        / f"{city}_metro_stop_wgs84.csv"
    )

    bus_source = (
        csv_folder
        / f"{city}_bus_stop_wgs84.csv"
    )

    # 如果TOP20不存在，跳过城市
    if not poi_source.is_file():

        return {
            "city": city,
            "name": chinese_name,
            "status": "SKIPPED_NO_TOP20",
            "note": str(poi_source),
        }

    osm_folder = (
        OSM_ROOT / chinese_name
    )

    road_options = [
        osm_folder
        / f"{city}_osm_roads_2025-12-31.gpkg",

        osm_folder
        / f"{city}_osm_roads_2025-12-31.parquet",
    ]

    road_source = next(
        (
            path for path in road_options
            if path.is_file()
        ),
        None
    )

    if road_source is None:

        return {
            "city": city,
            "name": chinese_name,
            "status": "SKIPPED_NO_2025_OSM",
            "note": str(osm_folder),
        }

    input_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    metro_dir.mkdir(
        exist_ok=True
    )

    bus_dir.mkdir(
        exist_ok=True
    )

    # 复制原始输入，不改变原文件
    for source in (
        poi_source,
        metro_source,
        bus_source,
        road_source,
    ):

        if source.is_file():

            destination = (
                input_dir / source.name
            )

            if not destination.exists():

                shutil.copy2(
                    source,
                    destination,
                )

    project = QgsProject.instance()
    project.clear()

    # ==============================================
    # 6. 读取20个景点
    # ==============================================

    poi_data = read_csv(
        poi_source,
        [
            "景点统一编码",
            "CityWalk景点名称",
            "lon_wgs84",
            "lat_wgs84",
        ],
    )

    if len(poi_data) != 20:

        raise ValueError(
            f"{city}景点数量是"
            f"{len(poi_data)}，不是20"
        )

    point_ids = [
        norm_id(
            row["景点统一编码"]
        )
        for row in poi_data
    ]

    if (
        len(set(point_ids)) != 20
        or not all(point_ids)
    ):

        raise ValueError(
            "TOP20景点编码重复或者为空"
        )

    # ==============================================
    # 7. 读取2025历史OSM
    # ==============================================

    historical_input = (
        input_dir / road_source.name
    )

    roads, actual_road_file = load_road(
        historical_input,
        input_dir,
        city,
    )

    road_fields = set(
        roads.fields().names()
    )

    if not (
        {"tags", "highway"}
        & road_fields
    ):

        raise ValueError(
            "2025道路没有tags和highway字段"
        )

    # 自动根据城市选择UTM米制投影
    lon = float(
        poi_data[0]["lon_wgs84"]
    )

    zone = int(
        (lon + 180) // 6
    ) + 1

    crs = QgsCoordinateReferenceSystem(
        f"EPSG:{32600 + zone}"
    )

    if not crs.isValid():
        raise ValueError("UTM投影错误")

    wgs = QgsCoordinateReferenceSystem(
        "EPSG:4326"
    )

    to_metric = QgsCoordinateTransform(
        wgs,
        crs,
        project.transformContext(),
    )

    if not roads.crs().isValid():

        raise ValueError(
            "历史OSM缺少坐标系CRS"
        )

    road_transform = QgsCoordinateTransform(
        roads.crs(),
        crs,
        project.transformContext(),
    )

    # ==============================================
    # 8. 筛选统一候选步行路网
    # ==============================================

    road_memory = new_layer(
        "MultiLineString",
        crs,
        "候选步行网络",
        [
            ("osm_id", "str"),
            ("highway", "str"),
            ("foot", "str"),
            ("access", "str"),
            ("bridge", "str"),
            ("tunnel", "str"),
            ("layer", "str"),
            ("main_foot_unknown", "int"),
        ],
    )

    features = []

    original_count = roads.featureCount()

    walkable_count = 0
    main_unknown_count = 0

    for feature in roads.getFeatures():

        tags = get_tags(
            feature,
            road_fields,
        )

        if not allowed(tags):
            continue

        geometry = QgsGeometry(
            feature.geometry()
        )

        if (
            geometry.isNull()
            or geometry.isEmpty()
        ):
            continue

        # 转换成以米为单位的真实几何
        if geometry.transform(road_transform) != 0:
            continue

        if geometry.isEmpty():
            continue

        if not geometry.isMultipart():
            geometry.convertToMultiType()

        # 标记没有明确人行道标签的主干道
        highway = tags.get(
            "highway", ""
        )

        unknown_main = (
            highway in {
                "primary",
                "secondary",
                "tertiary",
            }
            and tags.get(
                "foot", ""
            ) not in WALK_TAGS
            and not any(
                tags.get(key, "")
                in SIDEWALK_TAGS
                for key in (
                    "sidewalk",
                    "sidewalk:left",
                    "sidewalk:right",
                )
            )
        )

        new_feature = QgsFeature(
            road_memory.fields()
        )

        new_feature.setGeometry(
            geometry
        )

        osm_id = (
            str(feature["osm_id"])
            if "osm_id" in road_fields
            else str(feature.id())
        )

        new_feature.setAttributes([
            osm_id,
            tags.get("highway", ""),
            tags.get("foot", ""),
            tags.get("access", ""),
            tags.get("bridge", ""),
            tags.get("tunnel", ""),
            tags.get("layer", ""),
            int(unknown_main),
        ])

        features.append(
            new_feature
        )

        walkable_count += 1
        main_unknown_count += int(unknown_main)

        if len(features) >= 1000:

            ok, _ = (
                road_memory.dataProvider()
                .addFeatures(features)
            )

            if not ok:
                raise RuntimeError(
                    "写入道路网络失败"
                )

            features = []

    if features:

        ok, _ = (
            road_memory.dataProvider()
            .addFeatures(features)
        )

        if not ok:
            raise RuntimeError(
                "写入剩余道路失败"
            )

    road_memory.updateExtents()

    if walkable_count < 100:

        raise RuntimeError(
            f"{city}候选步行道路过少："
            f"{walkable_count}"
        )

    network_path = (
        input_dir
        / f"{city}_walkable_2025.gpkg"
    )

    network = save_layer(
        road_memory,
        network_path,
        project,
    )

    print(
        "原始OSM道路：",
        original_count,
        "候选步行道路：",
        walkable_count,
    )

    # ==============================================
    # 9. 寻找多个道路接入点
    # ==============================================

    spatial_index = QgsSpatialIndex(
        network.getFeatures(),
        flags=(
            QgsSpatialIndex.FlagStoreFeatureGeometries
        ),
    )

    cached_anchors = {}
    all_anchors = []

    def get_anchors(point):

        key = (
            round(point.x(), 3),
            round(point.y(), 3),
        )

        if key in cached_anchors:
            return cached_anchors[key]

        anchors = []

        nearby_ids = (
            spatial_index.nearestNeighbor(
                point,
                NEIGHBOR_ROADS,
            )
        )

        for feature_id in nearby_ids:

            road_geom = (
                spatial_index.geometry(
                    feature_id
                )
            )

            if (
                road_geom.isNull()
                or road_geom.isEmpty()
            ):
                continue

            nearest_geom = road_geom.nearestPoint(
                QgsGeometry.fromPointXY(
                    point
                )
            )

            if (
                nearest_geom.isNull()
                or nearest_geom.isEmpty()
            ):
                continue

            access_point = QgsPointXY(
                nearest_geom.asPoint()
            )

            access_distance = distance(
                point,
                access_point,
            )

            # 避免重复的接入位置
            if any(
                distance(
                    access_point,
                    existing["point"],
                ) < 0.5
                for existing in anchors
            ):
                continue

            entry = {
                "point": access_point,
                "distance": access_distance,
                "index": len(all_anchors),
            }

            anchors.append(entry)

            all_anchors.append(
                access_point
            )

            if len(anchors) >= MAX_ANCHORS:
                break

        if not anchors:

            raise RuntimeError(
                "无法找到邻近道路接入点"
            )

        cached_anchors[key] = anchors

        return anchors

    # 景点
    pois = []
    poi_by_id = {}

    for row in poi_data:

        point = point_xy(
            row,
            to_metric,
        )

        obj = {
            "id": norm_id(
                row["景点统一编码"]
            ),
            "name": row[
                "CityWalk景点名称"
            ],
            "point": point,
            "raw": row,
            "anchors": get_anchors(point),
        }

        pois.append(obj)

        poi_by_id[obj["id"]] = obj

    # Metro和Bus
    original_records = {}
    station_groups = {}

    for mode, path in (
        ("metro", metro_source),
        ("bus", bus_source),
    ):

        rows = read_csv(
            path,
            [
                "关联景点编码",
                "出入口/站点具体名称",
                "lon_wgs84",
                "lat_wgs84",
            ],
            optional=True,
        )

        original_records[mode] = rows

        groups = defaultdict(list)

        for rownum, row in enumerate(
            rows, 1
        ):

            pid = norm_id(
                row["关联景点编码"]
            )

            stop = {
                "id": pid,
                "name": row[
                    "出入口/站点具体名称"
                ],
                "raw": row,
                "rownum": rownum,
                "error": "",
                "point": None,
                "air": None,
                "anchors": [],
            }

            if pid not in poi_by_id:

                stop["error"] = (
                    "站点关联编码不在TOP20"
                )

            else:

                try:

                    point = point_xy(
                        row,
                        to_metric,
                    )

                    stop["point"] = point

                    stop["air"] = distance(
                        point,
                        poi_by_id[pid]["point"],
                    )

                    stop["anchors"] = (
                        get_anchors(point)
                    )

                except Exception as e:

                    stop["error"] = (
                        "站点坐标错误："
                        + str(e)
                    )

            groups[pid].append(stop)

        station_groups[mode] = groups

    print(
        "Metro候选：",
        len(original_records["metro"]),
        "Bus候选：",
        len(original_records["bus"]),
        "道路接入点：",
        len(all_anchors),
    )

    # ==============================================
    # 10. 构建Dijkstra网络
    # ==============================================

    director = QgsVectorLayerDirector(
        network,
        -1,
        "",
        "",
        "",
        QgsVectorLayerDirector.DirectionBoth,
    )

    director.addStrategy(
        QgsNetworkDistanceStrategy()
    )

    builder = QgsGraphBuilder(
        crs,
        True,
        TOPOLOGY_TOLERANCE,
    )

    tied_points = director.makeGraph(
        builder,
        all_anchors,
    )

    graph = builder.graph()

    if len(tied_points) != len(all_anchors):

        raise RuntimeError(
            "部分接入点没有加入路网"
        )

    vertices = [
        graph.findVertex(point)
        for point in tied_points
    ]

    def valid_anchors(entries):

        return [
            entry
            for entry in entries
            if vertices[entry["index"]] >= 0
        ]

    # ==============================================
    # 11. 创建路线图层
    # ==============================================

    route_specs = [
        ("mode", "str"),
        ("poi", "str"),
        ("station", "str"),
        ("road_m", "double"),
        ("estimate_m", "double"),
        ("is_nearest", "int"),
        ("risk", "str"),
    ]

    routes = new_layer(
        "LineString",
        crs,
        "全部成功候选路线",
        route_specs,
    )

    nearest_routes = new_layer(
        "LineString",
        crs,
        "每景点最近路线",
        route_specs,
    )

    connectors = new_layer(
        "LineString",
        crs,
        "未核验直线接入",
        [
            ("kind", "str"),
            ("poi", "str"),
            ("station", "str"),
            ("access_m", "double"),
        ],
    )

    # 保存景点接入线
    for poi in pois:

        for anchor in poi["anchors"]:

            if anchor["distance"] > 0.01:

                add_geometry(
                    connectors,
                    QgsGeometry.fromPolylineXY([
                        poi["point"],
                        anchor["point"],
                    ]),
                    [
                        "景点",
                        poi["id"],
                        "",
                        round(
                            anchor["distance"], 2
                        ),
                    ],
                )

    # 保存站点接入线
    for mode in ("metro", "bus"):

        for stations in (
            station_groups[mode].values()
        ):

            for stop in stations:

                if stop["point"] is None:
                    continue

                for anchor in stop["anchors"]:

                    if anchor["distance"] > 0.01:

                        add_geometry(
                            connectors,
                            QgsGeometry.fromPolylineXY([
                                stop["point"],
                                anchor["point"],
                            ]),
                            [
                                mode,
                                stop["id"],
                                stop["name"],
                                round(
                                    anchor["distance"],
                                    2,
                                ),
                            ],
                        )

    # ==============================================
    # 12. 分别计算Metro和Bus
    # ==============================================

    mode_counts = {}

    for mode, folder in (
        ("metro", metro_dir),
        ("bus", bus_dir),
    ):

        detail_rows = []
        summary_rows = []
        failed_rows = []

        routed_count = 0
        fallback_count = 0
        no_candidate_count = 0

        for i, poi in enumerate(pois, 1):

            stations = (
                station_groups[mode]
                .get(poi["id"], [])
            )

            successful = []

            # 景点最多三个起点
            trees = []

            for anchor in valid_anchors(
                poi["anchors"]
            ):

                start_vertex = vertices[
                    anchor["index"]
                ]

                tree, costs = (
                    QgsGraphAnalyzer.dijkstra(
                        graph,
                        start_vertex,
                        0,
                    )
                )

                trees.append((
                    anchor,
                    tree,
                    costs,
                ))

            # 逐条候选站点计算
            for stop in stations:

                road_distance = None
                estimated_distance = None

                best_route = None
                best_start = None
                best_end = None

                error = stop["error"]

                if not error and not trees:

                    error = (
                        "景点没有有效路网接入"
                    )

                if (
                    not error
                    and not valid_anchors(
                        stop["anchors"]
                    )
                ):

                    error = (
                        "站点没有有效路网接入"
                    )

                if not error:

                    best_cost = float("inf")

                    for (
                        start,
                        tree,
                        costs
                    ) in trees:

                        for end in valid_anchors(
                            stop["anchors"]
                        ):

                            end_vertex = vertices[
                                end["index"]
                            ]

                            start_vertex = vertices[
                                start["index"]
                            ]

                            if (
                                end_vertex != start_vertex
                                and tree[end_vertex] < 0
                            ):
                                continue

                            cost = float(
                                costs[end_vertex]
                            )

                            total = (
                                cost
                                + start["distance"]
                                + end["distance"]
                            )

                            if not math.isfinite(total):
                                continue

                            if total < best_cost:

                                path = restore_path(
                                    graph,
                                    tree,
                                    start_vertex,
                                    end_vertex,
                                )

                                if not path:
                                    continue

                                best_cost = total

                                road_distance = cost

                                estimated_distance = total

                                best_start = start
                                best_end = end
                                best_route = path

                    if road_distance is None:

                        error = (
                            "OSM候选道路网络不连通"
                        )

                if road_distance is not None:

                    method = (
                        "Dijkstra+两端直线接入"
                        "(未核验)"
                    )

                    routed_count += 1

                    coordinates = unique_coords(
                        [poi["point"]]
                        + best_route
                        + [stop["point"]]
                    )

                    if len(coordinates) < 2:

                        raise RuntimeError(
                            "已寻路路线几何退化"
                        )

                    successful.append({
                        "stop": stop,
                        "road": road_distance,
                        "estimate": estimated_distance,
                        "start": best_start,
                        "end": best_end,
                        "points": coordinates,
                    })

                else:

                    method = (
                        "仅直线距离参考"
                        "(不能当步行距离)"
                    )

                    if stop["air"] is not None:
                        fallback_count += 1

                review = (
                    "未核验建筑、围墙、门禁；"
                    "桥隧连接未验证"
                )

                if (
                    road_distance is not None
                    and max(
                        best_start["distance"],
                        best_end["distance"],
                    ) > 30
                ):

                    review += (
                        "；直线接入超过30米"
                    )

                if (
                    stop["air"] is not None
                    and stop["air"] > 800
                ):

                    review += (
                        "；WGS84重算超过800米，"
                        "需复核API候选记录"
                    )

                station_poi_id = stop[
                    "raw"
                ].get(
                    "高德设施POI_ID", ""
                )

                value = (
                    estimated_distance
                    if road_distance is not None
                    else stop["air"]
                )

                record = {
                    "候选序号": stop["rownum"],
                    "景点编码": poi["id"],
                    "景点名称": poi["name"],
                    "交通类型": mode,
                    "站点名称": stop["name"],
                    "站点POI_ID": station_poi_id,

                    "经度WGS84": stop[
                        "raw"
                    ].get(
                        "lon_wgs84", ""
                    ),

                    "纬度WGS84": stop[
                        "raw"
                    ].get(
                        "lat_wgs84", ""
                    ),

                    "原API直线距离_米": stop[
                        "raw"
                    ].get(
                        "距景点直线距离(米)", ""
                    ),

                    "WGS84重算直线距离_米": (
                        round(stop["air"], 1)
                        if stop["air"] is not None
                        else ""
                    ),

                    "路网内_米": (
                        round(road_distance, 1)
                        if road_distance is not None
                        else ""
                    ),

                    "景点接入直线_米": (
                        round(
                            best_start["distance"], 1
                        )
                        if best_start else ""
                    ),

                    "站点接入直线_米": (
                        round(
                            best_end["distance"], 1
                        )
                        if best_end else ""
                    ),

                    "道路加接入估算_米": (
                        round(
                            estimated_distance, 1
                        )
                        if estimated_distance is not None
                        else ""
                    ),

                    "直线替代参考_米": (
                        round(stop["air"], 1)
                        if (
                            road_distance is None
                            and stop["air"] is not None
                        )
                        else ""
                    ),

                    "提供的距离数值_米": (
                        round(value, 1)
                        if value is not None
                        else ""
                    ),

                    "计算类型": method,
                    "失败原因": error,
                    "质量提示": review,

                    "原始Excel行": stop[
                        "raw"
                    ].get(
                        "source_excel_row", ""
                    ),
                }

                detail_rows.append(record)

                if road_distance is None:

                    failed_rows.append(record)

            # 没有候选站点，也写一行说明
            if not stations:

                no_candidate_count += 1

                detail_rows.append({
                    "景点编码": poi["id"],
                    "景点名称": poi["name"],
                    "交通类型": mode,
                    "计算类型": (
                        "800米API候选表内没有站点"
                    ),
                    "失败原因": (
                        "没有候选站点"
                    ),
                })

            # ==========================================
            # 13. 确定最近站点
            # ==========================================

            if successful:

                chosen = min(
                    successful,
                    key=lambda x: x["estimate"],
                )

                possible_closer = sum(
                    1
                    for stop in stations
                    if (
                        stop["air"] is not None
                        and stop["air"]
                        < chosen["estimate"]
                        and not any(
                            item["stop"] is stop
                            for item in successful
                        )
                    )
                )

                fallback_nearest = False

            else:

                valid_air = [
                    stop
                    for stop in stations
                    if stop["air"] is not None
                ]

                chosen = (
                    min(
                        valid_air,
                        key=lambda x: x["air"]
                    )
                    if valid_air
                    else None
                )

                possible_closer = 0
                fallback_nearest = True

            if not stations:

                state = "没有800米候选站点"

            elif (
                successful
                and len(successful) == len(stations)
            ):

                state = (
                    "全部候选路网连通"
                    "（接入段未核验）"
                )

            elif successful:

                state = (
                    "部分候选路网连通；"
                    "其他仅直线参考"
                )

            elif chosen:

                state = (
                    "全部候选路网失败；"
                    "最近站点仅按直线参考选择"
                )

            else:

                state = (
                    "候选站点坐标无效，"
                    "无法提供距离"
                )

            if (
                chosen
                and not fallback_nearest
            ):

                nearest_stop = chosen["stop"]

                nearest_distance = (
                    chosen["estimate"]
                )

                nearest_road = (
                    chosen["road"]
                )

                start_access = (
                    chosen["start"]["distance"]
                )

                end_access = (
                    chosen["end"]["distance"]
                )

                nearest_method = (
                    "Dijkstra+直线接入(未核验)"
                )

            elif chosen:

                nearest_stop = chosen

                nearest_distance = (
                    chosen["air"]
                )

                nearest_road = None
                start_access = None
                end_access = None

                nearest_method = (
                    "仅直线参考(非步行距离)"
                )

            else:

                nearest_stop = None

                nearest_distance = None
                nearest_road = None

                start_access = None
                end_access = None

                nearest_method = (
                    "没有有效候选"
                )

            summary_rows.append({
                "城市": chinese_name,
                "景点编码": poi["id"],
                "景点名称": poi["name"],

                "800米API候选数": len(stations),

                "候选成功路网数": len(successful),

                "候选仅直线参考数": (
                    sum(
                        1
                        for s in stations
                        if s["air"] is not None
                    )
                    - len(successful)
                ),

                "最近站点名称": (
                    nearest_stop["name"]
                    if nearest_stop
                    else "没有"
                ),

                "最近站点POI_ID": (
                    nearest_stop["raw"].get(
                        "高德设施POI_ID", ""
                    )
                    if nearest_stop
                    else ""
                ),

                "最近站点直线_米": (
                    round(
                        nearest_stop["air"], 1
                    )
                    if (
                        nearest_stop
                        and nearest_stop["air"]
                        is not None
                    )
                    else ""
                ),

                "最近站点路网内_米": (
                    round(nearest_road, 1)
                    if nearest_road is not None
                    else ""
                ),

                "景点直线接入_米": (
                    round(start_access, 1)
                    if start_access is not None
                    else ""
                ),

                "站点直线接入_米": (
                    round(end_access, 1)
                    if end_access is not None
                    else ""
                ),

                "最近站点估算总距_米": (
                    round(nearest_distance, 1)
                    if nearest_distance is not None
                    else ""
                ),

                "估算步行分钟": (
                    round(
                        nearest_distance
                        / WALK_M_PER_MIN,
                        1,
                    )
                    if (
                        nearest_distance is not None
                        and not fallback_nearest
                    )
                    else ""
                ),

                "最近距离计算类型": nearest_method,

                "可能更近的未连通候选数": (
                    possible_closer
                ),

                "状态": state,

                "质量提示": (
                    "仅直线参考不能作为真实步行距离；"
                    "道路估算的接入线也未经障碍核查"
                ),

                "2025道路来源": road_source.name,

                "CRS": crs.authid(),
            })

            # ==========================================
            # 14. 保存全部成功路线
            # ==========================================

            for item in successful:

                stop = item["stop"]

                is_nearest = int(
                    not fallback_nearest
                    and item is chosen
                )

                geometry = (
                    QgsGeometry.fromPolylineXY(
                        item["points"]
                    )
                )

                attributes = [
                    mode,
                    poi["id"],
                    stop["name"],
                    round(item["road"], 2),
                    round(item["estimate"], 2),
                    is_nearest,
                    "直线接入及桥隧未核验",
                ]

                add_geometry(
                    routes,
                    geometry,
                    attributes,
                )

                if is_nearest:

                    add_geometry(
                        nearest_routes,
                        geometry,
                        attributes,
                    )

            print(
                f"[{i:02d}/20] "
                f"{chinese_name} {mode} "
                f"{poi['name']} | "
                f"候选{len(stations)} "
                f"路网{len(successful)} "
                f"最近"
                f"{round(nearest_distance, 1) if nearest_distance is not None else '没有'} "
                f"{nearest_method}"
            )

        # ==========================================
        # 15. 保存未匹配的原始站点记录
        # ==========================================

        invalid_source = [
            (pid, items)
            for pid, items
            in station_groups[mode].items()
            if pid not in poi_by_id
        ]

        invalid_count = 0

        for pid, items in invalid_source:

            for stop in items:

                invalid_count += 1

                record = {
                    "候选序号": stop["rownum"],
                    "景点编码": pid,
                    "交通类型": mode,
                    "站点名称": stop["name"],
                    "计算类型": "数据异常",
                    "失败原因": stop["error"],
                }

                detail_rows.append(record)
                failed_rows.append(record)

        # 每条源候选必须被记录
        # 再加上无候选景点的说明行
        expected_detail = (
            len(original_records[mode])
            + no_candidate_count
        )

        if (
            len(detail_rows) != expected_detail
            or len(summary_rows) != 20
        ):

            raise RuntimeError(
                f"{mode}记录数核查失败："
                f"明细{len(detail_rows)}，"
                f"预期{expected_detail}；"
                f"汇总{len(summary_rows)}，预期20"
            )

        save_csv(
            folder
            / f"{city}_{mode}_top20_summary.csv",
            SUMMARY_COLUMNS,
            summary_rows,
        )

        save_csv(
            folder
            / f"{city}_{mode}_all_candidates.csv",
            DETAIL_COLUMNS,
            detail_rows,
        )

        save_csv(
            folder
            / f"{city}_{mode}_failed_candidates.csv",
            DETAIL_COLUMNS,
            failed_rows,
        )

        mode_counts[mode] = {
            "source_records": len(
                original_records[mode]
            ),
            "detail_rows": len(detail_rows),
            "no_candidate_pois": no_candidate_count,
            "network_routed": routed_count,
            "air_reference": fallback_count,
            "invalid_records": invalid_count,
            "failed_candidates": len(failed_rows),

            "poi_nearest_has_road": sum(
                1
                for item in summary_rows
                if "Dijkstra"
                in item["最近距离计算类型"]
            ),
        }

    # ==================================================
    # 16. 最终路线数量验证
    # ==================================================

    expected_routes = sum(
        item["network_routed"]
        for item in mode_counts.values()
    )

    if (
        routes.featureCount()
        != expected_routes
    ):

        raise RuntimeError(
            "路线数量核对失败："
            f"{routes.featureCount()}"
            f" vs {expected_routes}"
        )

    project.setCrs(crs)

    project.addMapLayer(network)

    output_layers = [
        (
            routes,
            output
            / f"{city}_all_candidate_routes.gpkg",
        ),

        (
            nearest_routes,
            output
            / f"{city}_nearest_routes.gpkg",
        ),

        (
            connectors,
            output
            / f"{city}_straight_connectors_NOT_verified.gpkg",
        ),
    ]

    for layer, path in output_layers:

        saved_layer = save_layer(
            layer,
            path,
            project,
        )

        if saved_layer:

            project.addMapLayer(
                saved_layer
            )

    # 保存独立城市QGIS工程
    project.setFileName(
        str(project_file)
    )

    if not project.write():

        raise RuntimeError(
            "QGIS工程保存失败"
        )

    # 保存质量报告
    quality_file = (
        output
        / f"{city}_quality_report.json"
    )

    with quality_file.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            {
                "city": chinese_name,
                "OSM_2025_file": str(
                    road_source
                ),
                "OSM_road_read": str(
                    actual_road_file
                ),
                "OSM_source_count": original_count,
                "candidate_road_count": walkable_count,

                "main_roads_foot_unknown": (
                    main_unknown_count
                ),

                "graph_nodes": graph.vertexCount(),
                "graph_edges": graph.edgeCount(),

                "candidate_route_features": (
                    routes.featureCount()
                ),

                "nearest_route_features": (
                    nearest_routes.featureCount()
                ),

                "algorithm": (
                    "Dijkstra；每个点最多3个道路接入位置；"
                    "失败时仅保留直线参考"
                ),

                "notes": [
                    "2025日期仍需核对A的下载记录",
                    "原API800米候选不再二次筛选",
                    "建筑物、围墙、门禁未核验",
                    "桥隧连接关系未独立验证",
                    "两端直线接入不代表实际可走通道",
                    "仅直线参考不能与道路距离混为一谈",
                ],

                "modes": mode_counts,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        "完成：",
        city,
        "路网路线",
        routes.featureCount(),
        "输出：",
        output,
    )

    result = {
        "city": city,
        "name": chinese_name,
        "status": "OK",
        "note": str(output),
    }

    for mode, statistics in mode_counts.items():

        for key, value in statistics.items():

            result[
                f"{mode}_{key}"
            ] = value

    # 清理每城QGIS图层
    project.clear()

    gc.collect()

    return result


# =====================================================
# 17. 一次运行13个城市
# =====================================================

runs = []

print("=" * 65)
print("开始13城市批量计算")
print("宁波、苏州暂时不处理")
print("输出：", FINAL)
print("=" * 65)

for city, chinese_name in CITIES.items():

    print("\n" + "=" * 65)
    print("开始处理：", chinese_name, "/", city)

    try:

        outcome = process_city(
            city,
            chinese_name,
        )

    except Exception as error:

        outcome = {
            "city": city,
            "name": chinese_name,
            "status": "FAILED",
            "note": repr(error),
        }

        print(
            "城市处理失败：",
            repr(error),
        )

        QgsProject.instance().clear()

        gc.collect()

    runs.append(
        outcome
    )

    # 每完成一个城市立即更新总报告
    # 防止后面出错导致已有结果丢失
    report_columns = [
        "city",
        "name",
        "status",
        "note",
    ]

    extra_columns = sorted(
        set().union(
            *[set(record) for record in runs]
        ) - set(report_columns)
    )

    report_columns += extra_columns

    save_csv(
        FINAL / "distance_run_summary.csv",
        report_columns,
        runs,
    )

print("\n" + "=" * 65)
print("13城市批量任务结束")
print("=" * 65)

for result in runs:

    print(
        result["name"],
        result["status"],
        result["note"],
    )

print(
    "\n总报告：",
    FINAL / "distance_run_summary.csv"
)

print(
    "提醒：全部候选记录保留，"
    "不等于全部候选都有真实路网距离。"
)
