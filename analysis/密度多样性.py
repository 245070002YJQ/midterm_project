import os
import glob
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree

os.system("pip install pandas numpy scipy openpyxl -i https://pypi.tuna.tsinghua.edu.cn/simple")

# ================= 路径全部写死 =================
poi_folder = r"C:\Users\24551\Desktop\jisuan\商业poi"
spots_file = r"C:\Users\24551\Desktop\jisuan\景点表.xlsx"
# ================================================

print("1. 正在读取并清洗 POI 数据（提取中类算多样性）...")
all_pois = []
for file in glob.glob(os.path.join(poi_folder, "**", "*.csv"), recursive=True):
    if os.path.basename(file).startswith('._'): continue
    try:
        df = pd.read_csv(file)
        df.columns = [str(c).strip() for c in df.columns]
        lon = next((c for c in df.columns if 'lon' in c.lower() or '经度' in c), None)
        lat = next((c for c in df.columns if 'lat' in c.lower() or '纬度' in c), None)
        typ = next((c for c in df.columns if '中类' in c or '大类' in c or 'type' in c.lower() or '分类' in c), None)
        
        if lon and lat and typ:
            t = df[[lon, lat, typ]].copy()
            t.columns = ['lon', 'lat', 'type_detail']
            all_pois.append(t)
    except Exception as e: 
        print(f" 跳过 {os.path.basename(file)}: {e}")
        
if not all_pois:
    print("❌ 没读到任何数据！请检查商业poi文件夹里有没有csv。")
    input("按回车退出...")
    exit()

pois = pd.concat(all_pois).dropna()
pois['lon'] = pd.to_numeric(pois['lon'], errors='coerce')
pois['lat'] = pd.to_numeric(pois['lat'], errors='coerce')
pois = pois.dropna(subset=['lon', 'lat'])

# 处理用竖线 | 连在一起的多个分类
exploded_rows = []
for idx, row in pois.iterrows():
    if pd.isna(row['type_detail']): continue
    types = str(row['type_detail']).split('|')
    for t in types:
        t = t.strip()
        if t:
            exploded_rows.append({'lon': row['lon'], 'lat': row['lat'], 'type_detail': t})

pois_clean = pd.DataFrame(exploded_rows)
print(f"✅ POI清洗完毕！有效数据 {len(pois_clean)} 条。")


print("\n2. 正在读取景点表并计算 500 米...")
if not os.path.exists(spots_file):
    print(f"❌ 致命错误：找不到景点表！请确认文件真的在 {spots_file} 且名字叫 景点表.xlsx")
    input("按回车退出...")
    exit()

spots = pd.read_excel(spots_file)
spots.columns = [str(c).strip() for c in spots.columns]
s_lon = next((c for c in spots.columns if 'lon' in c.lower() or '经度' in c), None)
s_lat = next((c for c in spots.columns if 'lat' in c.lower() or '纬度' in c), None)

if not s_lon or not s_lat:
    print(f"❌ 景点表里找不到经纬度列！现在的列名是：{spots.columns.tolist()}")
    input("按回车退出...")
    exit()

spots = spots.rename(columns={s_lon: 'lon', s_lat: 'lat'}).dropna(subset=['lon', 'lat'])

def to_xy(lon, lat): return lon * 111320 * np.cos(np.radians(lat)), lat * 111320
px, py = to_xy(pois_clean['lon'].values, pois_clean['lat'].values)
tree = cKDTree(np.column_stack([px, py]))
sx, sy = to_xy(spots['lon'].values, spots['lat'].values)
s_xy = np.column_stack([sx, sy])
idxs = tree.query_ball_point(s_xy, r=500)

spots['500米商业总数'] = [len(i) for i in idxs]

for kw in ['餐饮', '购物', '休闲']:
    sub = pois_clean[pois_clean['type_detail'].str.contains(kw, na=False)]
    if len(sub)>0:
        tx, ty = to_xy(sub['lon'].values, sub['lat'].values)
        t_tree = cKDTree(np.column_stack([tx, ty]))
        spots[f'500米{kw}数'] = [len(i) for i in t_tree.query_ball_point(s_xy, r=500)]
    else:
        spots[f'500米{kw}数'] = 0

print("3. 正在按细分计算香农多样性指数...")
def div(idxs):
    if not idxs: return 0.0
    c = pois_clean.iloc[idxs]['type_detail'].value_counts()
    if len(c) <= 1: return 0.0
    return -np.sum((c/len(idxs)) * np.log(c/len(idxs)))

spots['业态多样性(香农指数)'] = [div(i) for i in idxs]

# 保存结果
out_file1 = r"C:\Users\24551\Desktop\jisuan\B_景点明细_最终版.csv"
out_file2 = r"C:\Users\24551\Desktop\jisuan\B_城市汇总_最终版.csv"

spots.to_csv(out_file1, index=False, encoding="utf-8-sig")

# 自动识别城市列
city_col = next((c for c in spots.columns if '城市' in c or 'city' in c.lower()), spots.columns[0])
spots.groupby(city_col)[['500米商业总数', '500米餐饮数', '500米购物数', '500米休闲数', '业态多样性(香农指数)']].mean().reset_index().to_csv(out_file2, index=False, encoding="utf-8-sig")

print("\n🎉 完美成功！")
print(f"文件1（给C）：{out_file1}")
print(f"文件2（给群）：{out_file2}")
input("按回车退出...")