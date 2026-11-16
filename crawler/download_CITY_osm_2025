import json
import time
from pathlib import Path

import requests
from shapely.geometry import shape, box, mapping
from shapely.ops import unary_union

# ===== 每个城市只改这四项 =====
API_KEY = ""
FINAL_AOI_FILE = Path(r"\CITY_aoi_projected.gpkg")
OUT_FILE = Path(r"\CITY_osm_roads_2025-12-31.gpkg")
# ==============================

TIME = "2025-12-31T23:59:59Z"
FILTER = "highway=* and geometry:line"
URL = "https://api.heigit.org/ohsome-api/v2-rc/extraction/features.parquet"

# 分块边长，单位为经纬度。遇到 413 会继续自动减半。
START_STEP = 0.25
MIN_STEP = 0.015625
MAX_RETRIES = 4

def load_aoi(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["type"] == "FeatureCollection":
        geoms = [shape(f["geometry"]) for f in data["features"] if f.get("geometry")]
    elif data["type"] == "Feature":
        geoms = [shape(data["geometry"])]
    else:
        geoms = [shape(data)]
    geom = unary_union(geoms)
    if geom.is_empty:
        raise ValueError("AOI 几何为空")
    return geom

def make_grid(aoi, step):
    minx, miny, maxx, maxy = aoi.bounds
    cells = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            cell = box(x, y, min(x + step, maxx), min(y + step, maxy))
            if cell.intersects(aoi):
                cells.append(cell)
            y += step
        x += step
    return cells

def request_cell(session, cell):
    payload = {
        "aoi": mapping(cell),
        "filter": FILTER,
        "time": TIME,
        "clip": False,
    }
    return session.post(
        URL,
        json=payload,
        headers={"Authorization": API_KEY},
        timeout=300,
    )

def main():
    if not AOI_FILE.exists():
        raise FileNotFoundError(f"找不到 API AOI：{AOI_FILE}")
    if not FINAL_AOI_FILE.exists():
        raise FileNotFoundError(f"找不到最终裁切 AOI：{FINAL_AOI_FILE}")
    if OUT_FILE.exists():
        raise FileExistsError(f"输出文件已存在，请换一个文件名：{OUT_FILE}")

    aoi = load_aoi(AOI_FILE)
    session = requests.Session()
    parts = []
    queue = [(cell, START_STEP) for cell in make_grid(aoi, START_STEP)]
    done = 0
    total = len(queue)

    while queue:
        cell, step = queue.pop(0)
        response = request_cell(session, cell)

        if response.status_code == 413 and step > MIN_STEP:
            smaller = step / 2
            children = [
                c for c in make_grid(cell, smaller)
                if c.intersects(aoi)
            ]
            queue = [(c, smaller) for c in children] + queue
            total += len(children) - 1
            print(f"请求体过大，自动细分为 {len(children)} 块；待处理 {len(queue)} 块")
            continue

        if not response.ok:
            raise RuntimeError(
                f"请求失败 HTTP {response.status_code}；"
                f"分块边长={step}；响应={response.text[:1000]}"
            )
        if not response.content.startswith(b"PAR1"):
            raise RuntimeError("服务器返回内容不是 Parquet，已停止。")

        tmp = OUT_FILE.with_name(f"_part_{len(parts)+1:05d}.parquet")
        tmp.write_bytes(response.content)
        parts.append(tmp)
        done += 1
        print(f"已完成分块 {done}；成功文件 {len(parts)}；队列剩余 {len(queue)}")
        time.sleep(4.1)  # 避免超过 ohsome 每分钟请求频率限制

    if not parts:
        raise RuntimeError("没有成功获取任何分块。")

    print(f"分块下载完成，共 {len(parts)} 个 Parquet：")
    for p in parts:
        print(p)
    print("分块已保留，没有合并或删除。")

if __name__ == "__main__":
    main()
