import os,csv,json,shutil
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
from qgis.core import *
from qgis.PyQt.QtCore import QVariant,QSize
from qgis.PyQt.QtGui import QColor,QFont
app=QgsApplication([],False);app.initQgis()
root=Path(r'')
work=Path(r'')
out=work/'最终QGIS成果';out.mkdir(exist_ok=True);(out/'data').mkdir(exist_ok=True)
proj=QgsProject.instance();proj.setCrs(QgsCoordinateReferenceSystem('EPSG:32651'));proj.setFilePathStorage(Qgis.FilePathType.Relative)
audit=[]
def save(layer,key,title):
    assert layer.isValid(),title
    p=out/'data'/(key+'.gpkg')
    opt=QgsVectorFileWriter.SaveVectorOptions();opt.driverName='GPKG';opt.layerName=key
    result=QgsVectorFileWriter.writeAsVectorFormatV3(layer,str(p),proj.transformContext(),opt)
    assert result[0]==QgsVectorFileWriter.NoError,str(result)
    l=QgsVectorLayer(str(p)+'|layername='+key,title,'ogr');assert l.isValid()
    proj.addMapLayer(l);audit.append({'layer':title,'features':l.featureCount(),'crs':l.crs().authid()});return l
def source(p,key,title):return save(QgsVectorLayer(str(p),title,'ogr'),key,title)
def points(rows,x,y,key,title):
    rows=list(rows);l=QgsVectorLayer('Point?crs=EPSG:4326',title,'memory');p=l.dataProvider()
    numeric={'Score_Baseline','Score_Nature','Score_Shopper','ndvi_mean','road_segments_density','metro_accessibility','500米商业总数'}
    p.addAttributes([QgsField(k,QVariant.Double if k in numeric else QVariant.String) for k in rows[0]]);l.updateFields();fs=[]
    for r in rows:
        f=QgsFeature(l.fields());f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(r[x]),float(r[y]))))
        f.setAttributes([float(r[k]) if k in numeric and r[k] else r[k] for k in r]);fs.append(f)
    p.addFeatures(fs);l.updateExtents();return save(l,key,title)
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
city=root/'中国城市2020年建成区数据集/新一线城市/CITY'
grid=source(work/'citywalk_integrated/ningbo_grid_integrated.gpkg','green_grid','500米融合网格绿化NDVI')
ranges=[]
for lo,hi,color in [(-1,.1,'#f3f0db'),(.1,.2,'#dcebc7'),(.2,.3,'#b6d5a4'),(.3,.4,'#7bb77b'),(.4,1,'#3d8756')]:
    s=QgsFillSymbol.createSimple({'color':color,'outline_style':'no'});ranges.append(QgsRendererRange(lo,hi,s,f'{lo:g} – {hi:g}'))
grid.setRenderer(QgsGraduatedSymbolRenderer('ndvi_mean',ranges))
boundary=source(city/'ningbo2020_new_Urb_fixed_v2.gpkg','boundary','2020建成区')
boundary.renderer().setSymbol(QgsFillSymbol.createSimple({'style':'no','outline_color':'#555555','outline_width':'0.25'}))
roads=source(city/'ningbo_osm_2025_walkway.gpkg','walkways','2025步行相关道路')
roads.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color':'#52677d','line_width':'0.22'}))
inp=root/'final_citywalk_distance_file/final result/ningbo/input'
for mode,title,shape in [('bus','公交站点','circle'),('metro','地铁站点或出入口','square')]:
    rows=read(inp/f'ningbo_{mode}_stop_wgs84.csv');unique={}
    for r in rows:unique.setdefault((r['lon_wgs84'],r['lat_wgs84'],r['出入口/站点具体名称']),r)
    l=points(unique.values(),'lon_wgs84','lat_wgs84',mode,title)
    l.renderer().setSymbol(QgsMarkerSymbol.createSimple({'name':shape,'color':'#2768aa' if mode=='bus' else '#7845a4','size':'1.7','outline_style':'no'}))
poi=points(read(root/'商业poi/合并结果/宁波_POI合并.csv'),'lon','lat','commercial','商业POI')
cats=[]
for k,c in [('餐饮','#e69f00'),('购物','#d55e00'),('休闲','#cc79a7')]:cats.append(QgsRendererCategory(k,QgsMarkerSymbol.createSimple({'color':c,'size':'1.1','outline_style':'no'}),k))
poi.setRenderer(QgsCategorizedSymbolRenderer('大类',cats));proj.layerTreeRoot().findLayer(poi.id()).setItemVisibilityChecked(False)
final=Path(r'C:\Users\yongniy\Documents\WeChat Files\wxid_gvngsqub8keh22\FileStorage\File\2026-11\Final_15_Cities_Result(2)(2).csv')
rs=[r for r in read(final) if r['city_name']=='Ningbo'];assert len(rs)==16
orig=read(inp/'ningbo_top20_citywalk_wgs84.csv');lookup={r['CityWalk景点名称']:r for r in orig}
for r in rs:
    match=lookup.get(r['spot_name'])
    if match:
        r['display_lon']=match['lon_wgs84'];r['display_lat']=match['lat_wgs84'];r['coordinate_source']='C提供的WGS84目的地表';r['original_result_lon']=r['lon'];r['original_result_lat']=r['lat']
    else:raise ValueError('目的地无法匹配原始坐标：'+r['spot_name'])
dest=points(rs,'display_lon','display_lat','destinations','16个最终目的地｜Baseline综合得分')
ranges=[]
for lo,hi,c in [(-10,-.2,'#4575b4'),(-.2,0,'#91bfdb'),(0,.2,'#fee090'),(.2,.5,'#fc8d59'),(.5,10,'#d73027')]:
    ranges.append(QgsRendererRange(lo,hi,QgsMarkerSymbol.createSimple({'name':'circle','color':c,'size':'3.4','outline_color':'white','outline_width':'.3'}),f'{lo:g} – {hi:g}'))
dest.setRenderer(QgsGraduatedSymbolRenderer('Score_Baseline',ranges))
labels=QgsPalLayerSettings();labels.fieldName='spot_name';fmt=QgsTextFormat();fmt.setFont(QFont("Microsoft YaHei"));fmt.setSize(9);buf=QgsTextBufferSettings();buf.setEnabled(True);buf.setSize(.8);buf.setColor(QColor('white'));fmt.setBuffer(buf);labels.setFormat(fmt);dest.setLabeling(QgsVectorLayerSimpleLabeling(labels));dest.setLabelsEnabled(True)
ext=QgsCoordinateTransform(boundary.crs(),proj.crs(),proj).transformBoundingBox(boundary.extent());ext.scale(1.08)
proj.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(ext,proj.crs()))
proj.setTitle('宁波City Walk多源空间融合成果')
path=out/'ningbo_final.qgz';assert proj.write(str(path))
settings=QgsMapSettings();settings.setDestinationCrs(proj.crs());settings.setLayers([dest]+[l for l in proj.layerTreeRoot().layerOrder() if l.id() not in [dest.id(),poi.id()]]);settings.setExtent(ext);settings.setOutputSize(QSize(1500,1500));settings.setBackgroundColor(QColor('white'))
job=QgsMapRendererParallelJob(settings);job.start();job.waitForFinished();job.renderedImage().save(str(out/'地图预览.png'))
(out/'图层检查.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'使用说明.txt').write_text('打开ningbo_final.qgz即可查看。项目使用相对路径，分享时请发送整个文件夹。\n原始数据未修改。16个目的地使用C提供的WGS84点位展示，保留最终表原经纬度与评分，不重新计算指标。\n公交、地铁为样本周边候选站点，并非全市完整交通网络；重复名称与坐标记录已合并展示。\n商业POI坐标来源尚未确认，暂按经纬度载入并默认关闭；不得把该图层当前叠加位置当作已经核验。需确认原始坐标是否GCJ-02后再转换。\n绿化采用已有融合网格ndvi_mean字段，未通过此前几何匹配核验的网格保留缺失，不补零。网格属性含商业计数等融合字段。\n底图未添加，以避免将当前在线底图误当作2025历史数据。\n',encoding='utf-8-sig')
check=QgsProject();assert check.read(str(path));assert all(l.isValid() for l in check.mapLayers().values())
print(json.dumps({'project':str(path),'audit':audit,'reload':'all layers valid'},ensure_ascii=False),flush=True)

