import ast
from qgis.core import QgsProject

layer = QgsProject.instance().mapLayersByName(
    "dongguan_osm_roads_2025-12-31 — osm_roads_2025"
)[0]

keep = {"footway", "pedestrian", "path", "steps", "corridor"}
ids = []

for feature in layer.getFeatures():
    raw = feature["tags"]
    try:
        text = raw.strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        tags = dict(ast.literal_eval(text))
    except Exception:
        continue

    highway = str(tags.get("highway", "")).strip().lower()
    foot = str(tags.get("foot", "")).strip().lower()
    access = str(tags.get("access", "")).strip().lower()

    if (
        highway in keep
        and foot != "no"
        and access not in {"no", "private"}
    ):
        ids.append(feature.id())

layer.removeSelection()
layer.selectByIds(ids)

print("筛选匹配数：", len(ids))
print("QGIS 当前选中数：", layer.selectedFeatureCount())
