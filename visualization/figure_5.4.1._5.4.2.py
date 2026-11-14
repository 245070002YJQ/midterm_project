import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from sklearn.cluster import KMeans

# 1. Load your final data
file_path = r"C:\Users\lenovo\Documents\南大\3-1\大数据系统原理与应用\中期大作业\Citywalk_data\Final_15_Cities_Result.csv"
df = pd.read_csv(file_path)

# Translate PINYIN to CHINESE
city_name_map = {
    'changsha': '长沙', 'chengdu': '成都', 'chongqing': '重庆', 'dongguan': '东莞', 
    'foshan': '佛山', 'hangzhou': '杭州', 'hefei': '合肥', 'nanjing': '南京', 
    'ningbo': '宁波', 'qingdao': '青岛', 'suzhou': '苏州', 'tianjin': '天津', 
    'wuhan': '武汉', 'xian': '西安', 'zhengzhou': '郑州'
}
df['city_cn'] = df['city_name'].astype(str).str.strip().str.lower().map(city_name_map).fillna(df['city_name'])

# Set global font sizes
sns.set_theme(style="whitegrid", font_scale=1.5) 
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei'] 
plt.rcParams['axes.unicode_minus'] = False

# ==========================================
# CHART 1: Baseline City Ranking
# ==========================================
city_ranks = df.groupby('city_cn')['Score_Baseline'].mean().sort_values(ascending=False).reset_index()
plt.figure(figsize=(14, 10)) # Made the image larger
sns.barplot(x='Score_Baseline', y='city_cn', data=city_ranks, palette='viridis', hue='city_cn', legend=False)
plt.title('15个城市 CityWalk 基准适宜性排名', fontsize=24, pad=20)
plt.xlabel('基准得分', fontsize=20)
plt.ylabel('城市', fontsize=20)
plt.xticks(fontsize=18)
plt.yticks(fontsize=18)
plt.tight_layout()
plt.savefig('Chart1_Baseline_Ranking.png', dpi=300)
plt.close()

# ==========================================
# CHART 2: Preference Shift
# ==========================================
scenario_scores = df.groupby('city_cn')[['Score_Baseline', 'Score_Nature', 'Score_Shopper']].mean()
ranks = scenario_scores.rank(ascending=False, method='min')

plt.figure(figsize=(16, 11)) # Made the image larger
for city in ranks.index:
    plt.plot(ranks.columns, ranks.loc[city], marker='o', linewidth=2.5, markersize=8, label=city)

plt.gca().invert_yaxis() 
plt.title('不同游逛偏好下的城市排名变化', fontsize=24, pad=20)
plt.ylabel('排名 (1 = 最佳)', fontsize=20)
plt.xlabel('偏好情景', fontsize=20)
plt.xticks([0, 1, 2], ['基准情景', '自然偏好', '购物偏好'], fontsize=20)
plt.yticks(fontsize=18)

# Increase font size for legend
plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left', title='城市', title_fontsize=18, prop={'family': 'Microsoft YaHei', 'size': 16})
plt.tight_layout()
plt.savefig('Chart2_Preference_Shift.png', dpi=300)
plt.close()

# ==========================================
# CHART 3: K-Means Cluster Centers (Radar Chart)
# ==========================================
features = ['ndvi_mean_z', 'road_segments_density_z', 'metro_accessibility_z', '500米商业总数_z']
kmeans = KMeans(n_clusters=3, random_state=42)
kmeans.fit(df[features])
real_centers = kmeans.cluster_centers_

categories = ['绿化 (NDVI)', '路段密度', '交通接驳', '商业密度']
N = len(categories)
angles = [n / float(N) * 2 * np.pi for n in range(N)]
angles += angles[:1] 

fig, ax = plt.subplots(figsize=(12, 12), subplot_kw=dict(polar=True))

colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
labels = ['聚类 0', '聚类 1', '聚类 2']

for i in range(3):
    values = real_centers[i].tolist()
    values += values[:1] 
    ax.plot(angles, values, linewidth=3, linestyle='solid', label=labels[i], color=colors[i])
    ax.fill(angles, values, color=colors[i], alpha=0.1)

ax.set_xticks(angles[:-1])
# Removed bold, increased size
ax.set_xticklabels(categories, fontsize=22) 
plt.yticks(fontsize=18)
plt.title('K-Means 空间聚类中心特征 (Z-Score)', size=24, y=1.1)

# Increase font size for legend
plt.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), prop={'family': 'Microsoft YaHei', 'size': 18})
plt.tight_layout()
plt.savefig('Chart3_Cluster_Radar.png', dpi=300)
plt.close()

print("3张图表已成功生成并保存！(已调大字体且取消加粗)")