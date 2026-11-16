import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl

os.system("pip install pandas matplotlib -i https://pypi.tuna.tsinghua.edu.cn/simple")

# 解决图表里的中文显示乱码问题
mpl.rcParams['font.sans-serif'] = ['SimHei']
mpl.rcParams['axes.unicode_minus'] = False

# 你的准确路径
file_path = r"C:\Users\24551\Desktop\商业poi\B_城市汇总_最终版.csv"

print("正在读取数据...")
try:
    df = pd.read_csv(file_path)
except Exception as e:
    print(f"❌ 读取失败，请检查文件是否存在！报错信息：{e}")
    input("按回车退出...")
    exit()

# ==========================================
# 第一张图：商业设施丰富度（POI总数）排行
# ==========================================
print("正在绘制【图1：商业丰富度】...")
df_total = df.sort_values(by='500米商业总数', ascending=True)
plt.figure(figsize=(10, 6))
# 用绿色系渐变
colors_total = plt.cm.Greens([(x - df_total['500米商业总数'].min()) / (df_total['500米商业总数'].max() - df_total['500米商业总数'].min() + 1e-9) for x in df_total['500米商业总数']])
bars = plt.barh(df_total['city'], df_total['500米商业总数'], color=colors_total, edgecolor='black', linewidth=0.5)
for bar in bars:
    plt.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2, 
             f'{bar.get_width():.1f}', va='center', ha='left', fontsize=10)
plt.title('15城市CityWalk景点周边商业设施丰富度排名', fontsize=15, pad=15)
plt.xlabel('平均商业POI总数 (个)', fontsize=12)
plt.tight_layout()
img1_path = r"C:\Users\24551\Desktop\商业poi\图1_商业丰富度排名.png"
plt.savefig(img1_path, dpi=300)
plt.close()

# ==========================================
# 第二张图：商业业态多样性（香农指数）排行
# ==========================================
print("正在绘制【图2：业态多样性】...")
df_div = df.sort_values(by='业态多样性(香农指数)', ascending=True)
plt.figure(figsize=(10, 6))
# 用蓝色系渐变
colors_div = plt.cm.Blues([(x - df_div['业态多样性(香农指数)'].min()) / (df_div['业态多样性(香农指数)'].max() - df_div['业态多样性(香农指数)'].min() + 1e-9) for x in df_div['业态多样性(香农指数)']])
bars = plt.barh(df_div['city'], df_div['业态多样性(香农指数)'], color=colors_div, edgecolor='black', linewidth=0.5)
for bar in bars:
    plt.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height()/2, 
             f'{bar.get_width():.2f}', va='center', ha='left', fontsize=10)
plt.title('15城市CityWalk景点周边商业业态多样性排名', fontsize=15, pad=15)
plt.xlabel('香农-威纳多样性指数 (Shannon-Wiener Index)', fontsize=12)
plt.tight_layout()
img2_path = r"C:\Users\24551\Desktop\商业poi\图2_商业多样性排名.png"
plt.savefig(img2_path, dpi=300)
plt.close()

print(f"\n✅ 大功告成！两张图已保存至文件夹：\n1. {img1_path}\n2. {img2_path}")
input("请按回车键退出...")