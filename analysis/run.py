import os
import glob
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree

os.system("pip install pandas numpy scipy openpyxl -i https://pypi.tuna.tsinghua.edu.cn/simple")

poi_folder = r"C:\Users\24551\Desktop\jisuan\商业poi"
spots_file = r"C:\Users\24551\Desktop\jisuan\景点表.xlsx"

print("正在读取数据...")
# 读POI
all_pois = []
for file in glob.glob(os.path.join(poi_folder, "**", "*.csv"), recursive=True):
    try:
        df = pd.read_csv(file)
        df.columns = [str(c).strip() for c in df.columns]
        lon = next((c for c in df.columns if 'lon' in c.lower() or '经度' in c), None)
        lat = next((c for c in df.columns if 'lat' in c.lower() or '纬度' in c), None)
        typ = next((c for c in df.columns if '大类' in c or 'type' in c.lower()), None)
        if lon and lat and typ:
            t = df[[lon, lat, typ]].copy()
            t.columns = ['lon', 'lat', 'type']
            all_pois.append(t)
    except: pass
pois = pd.concat(all_pois).dropna()
pois['lon'] = pd.to_numeric(pois['lon'], errors='coerce')
pois['lat'] = pd.to_numeric(pois['lat'], errors='coerce')

# 读景点
spots = pd.read_excel(spots_file)
spots.columns = [str(c).strip() for c in spots.columns]
s_lon = next((c for c in spots.columns if 'lon' in c.lower() or '经度' in c), None)
s_lat = next((c for c in spots.columns if 'lat' in c.lower() or '纬度' in c), None)
spots = spots.rename(columns={s_lon: 'lon', s_lat: 'lat'}).dropna(subset=['lon', 'lat'])

print("正在计算500米范围...")
def to_xy(lon, lat): return lon * 111320 * np.cos(np.radians(lat)), lat * 111320
px, py = to_xy(pois['lon'].values, pois['lat'].values)
tree = cKDTree(np.column_stack([px, py]))
sx, sy = to_xy(spots['lon'].values, spots['lat'].values)
s_xy = np.column_stack([sx, sy])
idxs = tree.query_ball_point(s_xy, r=500)

spots['500米商业总数'] = [len(i) for i in idxs]
for kw in ['餐饮', '购物', '休闲']:
    sub = pois[pois['type'].str.contains(kw, na=False)]
    if len(sub)>0:
        tx, ty = to_xy(sub['lon'].values, sub['lat'].values)
        t_tree = cKDTree(np.column_stack([tx, ty]))
        spots[f'500米{kw}数'] = [len(i) for i in t_tree.query_ball_point(s_xy, r=500)]
    else:
        spots[f'500米{kw}数'] = 0

def div(idxs):
    if not idxs: return 0
    c = pois.iloc[idxs]['type'].value_counts()
    return -np.sum((c/len(idxs)) * np.log(c/len(idxs)))
spots['业态多样性'] = [div(i) for i in idxs]

# 输出两张表
spots.to_csv(r"C:\Users\24551\Desktop\jisuan\B_每个景点数据.csv", index=False, encoding="utf-8-sig")
city_col = next((c for c in spots.columns if '城市' in c or 'city' in c.lower()), spots.columns[0])
spots.groupby(city_col)[['500米商业总数', '500米餐饮数', '500米购物数', '500米休闲数', '业态多样性']].mean().reset_index().to_csv(r"C:\Users\24551\Desktop\jisuan\B_15个城市汇总.csv", index=False, encoding="utf-8-sig")

print("完成！生成了 B_每个景点数据.csv 和 B_15个城市汇总.csv")
input("按回车退出...")