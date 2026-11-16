import requests
import pandas as pd
import time
import os

# ================= 配置 =================
API_KEY = "15a202f9fb8b41ce6fdc2b93ab8cfb26"  # 你的高德API Key
API_URL = "https://restapi.amap.com/v3/place/text"

# 15个新一线城市
CITIES = [
    "成都", "东莞", "佛山", "杭州", "合肥", "南京", "宁波", "青岛",
    "苏州", "天津", "武汉", "西安", "长沙", "郑州", "重庆"
]

# 商业大类（050000: 餐饮, 060000: 购物, 080000: 休闲）
CATEGORIES = {
    "餐饮": "050000",
    "购物": "060000",
    "休闲": "080000"
}
# ========================================

def fetch_poi(city, category_code, page):
    """请求单页数据"""
    params = {
        "key": API_KEY,
        "city": city,
        "types": category_code,
        "offset": 25, # 每页25条
        "page": page,
        "extensions": "all",
        "output": "JSON"
    }
    try:
        res = requests.get(API_URL, params=params, timeout=10)
        data = res.json()
        if data.get("status") == "1":
            return data.get("pois", [])
        else:
            # 如果报错，打印高德的错误信息
            print(f"   [!] 接口报错: {data.get('info')}")
            return []
    except Exception as e:
        print(f"   [!] 请求异常: {e}")
        return []

def parse_poi(pois, city, category):
    """提取需要的字段"""
    parsed = []
    for poi in pois:
        parsed.append({
            "poi_id": poi.get("id"),
            "name": poi.get("name"),
            "type": poi.get("type"), # 细分业态
            "address": poi.get("address"),
            "lon": poi.get("location").split(",")[0] if poi.get("location") else None,
            "lat": poi.get("location").split(",")[1] if poi.get("location") else None,
            "city_name": poi.get("cityname"),
            "category": category
        })
    return parsed

def main():
    out_file = "15城市全域商业POI基础数据.csv"
    
    # 初始化文件
    if os.path.exists(out_file):
        print(f"发现已存在的 {out_file}，将进行追加爬取...")
    else:
        # 创建表头
        pd.DataFrame(columns=["poi_id", "name", "type", "address", "lon", "lat", "city_name", "category"]).to_csv(out_file, index=False, encoding="utf-8-sig")
    
    print("开始爬取 15 个城市全域商业数据，由于数据量巨大，请耐心等待...")
    
    for city in CITIES:
        print(f"\n========== 正在爬取城市：{city} ==========")
        
        for cat_name, cat_code in CATEGORIES.items():
            print(f"  -> 正在抓取分类：{cat_name} ({cat_code})")
            
            # 高德单类目最多翻 40 页（约 1000 条）
            for page in range(1, 41):
                pois = fetch_poi(city, cat_code, page)
                
                if not pois:
                    break # 没数据了，退出当前分类翻页
                
                parsed_pois = parse_poi(pois, city, cat_name)
                
                # 实时追加保存到 CSV，防断网
                df_batch = pd.DataFrame(parsed_pois)
                df_batch.to_csv(out_file, mode='a', header=False, index=False, encoding="utf-8-sig")
                
                print(f"      第 {page} 页：成功抓取 {len(parsed_pois)} 条")
                
                if len(pois) < 25:
                    break # 最后一页
                
                time.sleep(0.3) # 限速防封
            
            time.sleep(1) # 分类之间停一下
            
    print(f"\n✅ 15个城市全域数据爬取完成！文件保存为：{out_file}")

if __name__ == "__main__":
    main()