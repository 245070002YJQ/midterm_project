import pandas as pd
import geopandas as gpd
import os
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

# --- 1. SETUP PATHS ---
BASE_DIR = r"C:\Users\lenovo\Documents\南大\3-1\大数据系统原理与应用\中期大作业\Citywalk_data"
cities = ['changsha', 'chengdu', 'chongqing', 'dongguan', 'foshan',
          'hangzhou', 'hefei', 'nanjing', 'ningbo', 'qingdao',
          'suzhou', 'tianjin', 'wuhan', 'xian', 'zhengzhou']

city_name_map = {'changsha': '长沙', 'chengdu': '成都', 'chongqing': '重庆', 'dongguan': '东莞', 
                 'foshan': '佛山', 'hangzhou': '杭州', 'hefei': '合肥', 'nanjing': '南京', 
                 'ningbo': '宁波', 'qingdao': '青岛', 'suzhou': '苏州', 'tianjin': '天津', 
                 'wuhan': '武汉', 'xian': '西安', 'zhengzhou': '郑州'}

all_cities_data = []

# Load B's data (has lon/lat)
b_all_data = pd.read_csv(os.path.join(BASE_DIR, "b_data", "commercial_data.csv"), encoding='utf-8-sig')
b_all_data['spot_name'] = b_all_data['spot_name'].astype(str).str.strip()

for city in cities:
    print(f"\n--- Processing {city.upper()} ---")
    
    grid_path = os.path.join(BASE_DIR, "grid_data", f"{city}_grid_500m_clipped.gpkg")
    roads_path = os.path.join(BASE_DIR, "grid_data", f"{city}_osm_roads_clipped.gpkg")
    sentinel_path = os.path.join(BASE_DIR, "sentinel_data", f"sentinel_{city}.xlsx")
    metro_path = os.path.join(BASE_DIR, "transport_data", f"metro_{city}.csv")
    bus_path = os.path.join(BASE_DIR, "transport_data", f"bus_{city}.csv") 
    
    try:
        grid = gpd.read_file(grid_path)
        roads = gpd.read_file(roads_path)
        sentinel = pd.read_excel(sentinel_path)
        
        # --- LOAD METRO (C) ---
        try:
            c_data = pd.read_csv(metro_path, encoding='gbk')
        except:
            c_data = pd.read_csv(metro_path, encoding='utf-8')
            
        if '站点直线接入_米' in c_data.columns:
            c_data = c_data.rename(columns={'站点直线接入_米': 'metro_dist'})
        elif '景点直线接入_米' in c_data.columns: 
            c_data = c_data.rename(columns={'景点直线接入_米': 'metro_dist'})
            
        c_data['name_clean'] = c_data['景点名称'].astype(str).str.strip()

        # --- LOAD BUS (C) ---
        try:
            bus_data = pd.read_csv(bus_path, encoding='gbk')
        except:
            bus_data = pd.read_csv(bus_path, encoding='utf-8')
            
        if '站点直线接入_米' in bus_data.columns:
            bus_data = bus_data.rename(columns={'站点直线接入_米': 'bus_dist'})
        elif '景点直线接入_米' in bus_data.columns: 
            bus_data = bus_data.rename(columns={'景点直线接入_米': 'bus_dist'})
            
        bus_data['name_clean'] = bus_data['景点名称'].astype(str).str.strip()

        # Merge Metro and Bus by name
        c_merged = c_data.merge(bus_data[['name_clean', 'bus_dist']], on='name_clean', how='left')
        
        # Choose the best transport & apply 1000m penalty
        c_merged['best_transport_dist'] = c_merged[['metro_dist', 'bus_dist']].min(axis=1)
        c_merged['best_transport_dist'] = c_merged['best_transport_dist'].fillna(1000)
        c_merged['站点接入_米'] = c_merged['best_transport_dist']

        # --- MERGE C INTO B ---
        city_cn = city_name_map.get(city, city)
        b_city_data = b_all_data[b_all_data['city'] == city_cn].copy()
        
        merged_bc = b_city_data.merge(
            c_merged[['name_clean', '站点接入_米']], 
            left_on='spot_name', right_on='name_clean', how='inner'
        )

        # --- CALCULATE CONNECTIVITY (Roads) ---
        roads_in_grid = gpd.sjoin(roads, grid, how="inner", predicate="intersects")
        road_counts = roads_in_grid.groupby('id').size().reset_index(name='road_segments')
        grid = grid.merge(road_counts, on='id', how='left')
        grid['road_segments'] = grid['road_segments'].fillna(0)
        # ⚠️ Renamed to road_segments_density
        grid['road_segments_density'] = grid['road_segments'] / 0.25 

        # --- SPATIAL JOIN (B's lon/lat to A's grid) ---
        merged_gdf = gpd.GeoDataFrame(
            merged_bc, 
            geometry=gpd.points_from_xy(merged_bc['lon'], merged_bc['lat']),
            crs="EPSG:4326"
        )
        merged_gdf = merged_gdf.to_crs(grid.crs)
        
        joined = gpd.sjoin(merged_gdf, grid, how="inner", predicate="intersects")
        grid_id_col = 'id_right' if 'id_right' in joined.columns else 'id'
        joined = joined.drop_duplicates(subset=[grid_id_col]) 

        # --- FINAL MERGE WITH SENTINEL ---
        city_master = sentinel.merge(joined, left_on='grid_id', right_on=grid_id_col, how="inner")
        
        # Keep dropna() to get the 256 rows as agreed
        city_master = city_master.dropna(subset=['站点接入_米'])
        
        # Drop geometry column before appending
        if 'geometry' in city_master.columns:
            city_master = city_master.drop(columns=['geometry'])
            
        all_cities_data.append(city_master)
        print(f"Successfully processed {city} ({len(city_master)} spots)")

    except Exception as e:
        print(f"❌ Error processing {city}: {e}")

# --- COMBINE AND SCORE ---
print("\nCombining and scoring...")
master_df = pd.concat(all_cities_data, ignore_index=True)
print(f"Total spots collected: {len(master_df)}") 

master_df['metro_accessibility'] = (1 / (1 + master_df['站点接入_米'])).clip(upper=2.0)

# ⚠️ Updated feature name
features = ['ndvi_mean', 'road_segments_density', 'metro_accessibility', '500米商业总数']
scaler = StandardScaler()
master_df[[f'{col}_z' for col in features]] = scaler.fit_transform(master_df[features])

master_df['Score_Baseline'] = (
    0.25 * master_df['ndvi_mean_z'] + 
    0.25 * master_df['road_segments_density_z'] + 
    0.25 * master_df['metro_accessibility_z'] +
    0.25 * master_df['500米商业总数_z']
)

master_df['Score_Nature'] = (
    0.60 * master_df['ndvi_mean_z'] + 
    0.20 * master_df['road_segments_density_z'] + 
    0.10 * master_df['metro_accessibility_z'] +
    0.10 * master_df['500米商业总数_z']
)

master_df['Score_Shopper'] = (
    0.10 * master_df['ndvi_mean_z'] + 
    0.20 * master_df['road_segments_density_z'] + 
    0.20 * master_df['metro_accessibility_z'] +
    0.50 * master_df['500米商业总数_z']
)

kmeans = KMeans(n_clusters=3, random_state=42)
master_df['Cluster'] = kmeans.fit_predict(master_df[[f'{col}_z' for col in features]])
cluster_names = {0: '交通枢纽型', 1: '商业核心型', 2: '绿地休闲型'}
master_df['Region_Type'] = master_df['Cluster'].map(cluster_names)

# ⚠️ ALL THREE RANKINGS ARE BACK
print("\n--- CITY RANKING (Baseline) ---")
print(master_df.groupby('city_name')['Score_Baseline'].mean().sort_values(ascending=False))

print("\n--- CITY RANKING (Nature Preference) ---")
print(master_df.groupby('city_name')['Score_Nature'].mean().sort_values(ascending=False))

print("\n--- CITY RANKING (Shopper Preference) ---")
print(master_df.groupby('city_name')['Score_Shopper'].mean().sort_values(ascending=False))

output_file = os.path.join(BASE_DIR, "Final_15_Cities_Result.csv")
master_df.to_csv(output_file, index=False, encoding='utf-8-sig')
print(f"\nSUCCESS! Saved to {output_file}")