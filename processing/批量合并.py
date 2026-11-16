import pandas as pd
import os

base_path = os.getcwd()

folders = {
    "餐饮": "餐饮服务",
    "购物": "购物服务",
    "休闲": "体育休闲服务"
}

def extract_city(filename):
    name = filename.replace(".csv", "")
    for kw in ["_餐饮POI", "餐饮POI", "_购物POI", "购物POI",
               "_体育休闲POI", "体育休闲POI", "_休闲POI", "休闲POI"]:
        name = name.replace(kw, "")
    return name.replace("_", "").strip()

canyin_folder = os.path.join(base_path, "餐饮服务")
cities = [extract_city(f) for f in os.listdir(canyin_folder) if f.endswith(".csv")]
print(f"找到 {len(cities)} 个城市：{cities}\n" + "="*50)

city_files = {city: {} for city in cities}
for cat, folder_name in folders.items():
    fp = os.path.join(base_path, folder_name)
    for f in os.listdir(fp):
        if f.endswith(".csv"):
            city = extract_city(f)
            if city in city_files:
                city_files[city][cat] = os.path.join(fp, f)

out = os.path.join(base_path, "合并结果")
os.makedirs(out, exist_ok=True)

for city in cities:
    print(f"\n【{city}】")
    dfs = []
    for cat in ["餐饮", "购物", "休闲"]:
        if cat in city_files[city]:
            df = pd.read_csv(city_files[city][cat])
            df["大类"] = cat
            dfs.append(df)
            print(f"  {cat}: {len(df)} 条")
        else:
            print(f"  {cat}: 缺失！")
    if dfs:
        m = pd.concat(dfs, ignore_index=True)
        m = m.drop_duplicates(subset=["uid"], keep="first")
        m = m.dropna(subset=["lon", "lat"])
        m["city"] = city
        m.to_csv(os.path.join(out, f"{city}_POI合并.csv"), index=False, encoding="utf-8-sig")
        print(f"  → 合并后 {len(m)} 条，已保存")

print("\n" + "="*50 + "\n全部完成！去「合并结果」文件夹看。")
