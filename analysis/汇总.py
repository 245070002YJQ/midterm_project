import pandas as pd
import os

cities = ["成都","东莞","佛山","杭州","合肥","南京","宁波","青岛",
          "苏州","天津","武汉","西安","长沙","郑州","重庆"]

result = []

for city in cities:
    poi_file = f"合并结果/{city}_POI合并.csv"
    dens_file = f"密度多样性结果/{city}_密度多样性.csv"
    
    if os.path.exists(poi_file):
        poi = pd.read_csv(poi_file)
        total = len(poi)
        cy = len(poi[poi["大类"]=="餐饮"])
        gw = len(poi[poi["大类"]=="购物"])
        xx = len(poi[poi["大类"]=="休闲"])
    else:
        total=cy=gw=xx=0
    
    if os.path.exists(dens_file):
        d = pd.read_csv(dens_file)
        grid_count = len(d)
        matched = d["总POI数"].sum()
        avg_density = d["总POI数"].mean()
        avg_div = d["多样性H"].mean()
    else:
        grid_count=matched=avg_density=avg_div=0
    
    rate = round(matched/total*100, 1) if total>0 else 0
    
    result.append({
        "城市": city,
        "餐饮POI": cy,
        "购物POI": gw,
        "休闲POI": xx,
        "POI总数": total,
        "匹配到网格数": int(matched),
        "匹配率%": rate,
        "有POI的网格数": grid_count,
        "平均每网格店数": round(avg_density, 2),
        "平均多样性": round(avg_div, 3)
    })

df = pd.DataFrame(result)
df.to_csv("城市质量汇总表.csv", index=False, encoding="utf-8-sig")
print(df.to_string(index=False))
print("\n已保存：城市质量汇总表.csv")
