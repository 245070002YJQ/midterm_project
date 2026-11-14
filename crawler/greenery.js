//长沙 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/changsha_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Changsha');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'changsha_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//成都 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/chengdu_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Chengdu');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'chengdu_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//重庆 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/chongqing_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Chongqing');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'chongqing_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//东莞 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/dongguan_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Dongguan');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'dongguan_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//佛山 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/foshan_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Foshan');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'foshan_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//杭州 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/hangzhou_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Hangzhou');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'hangzhou_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//合肥 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/hefei_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Hefei');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'hefei_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//南京 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/nanjing_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Nanjing');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'nanjing_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//宁波 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/ningbo_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Ningbo');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'ningbo_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//青岛 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/qingdao_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Qingdao');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'qingdao_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//苏州 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/suzhou_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Suzhou');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'suzhou_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//天津 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/tianjin_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Tianjin');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'tianjin_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//武汉 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/wuhan_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Wuhan');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'wuhan_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//西安 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/xian_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Xian');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'xian_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});


//郑州 NDVI计算
var grid = ee.FeatureCollection('projects/trusty-art-511713-b5/assets/zhengzhou_grid');

var startDate = '2025-06-01';
var endDate = '2025-08-31';

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(grid)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25));

var s2Masked = s2.map(function(image) {
  var scl = image.select('SCL');
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7));
  return image.updateMask(mask);
});

var s2WithNDVI = s2Masked.map(function(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
});

var ndviComposite = s2WithNDVI.select('NDVI').median().clip(grid);

var zonalStats = ndviComposite.reduceRegions({
  collection: grid,
  reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), null, true),
  scale: 30
}).select(['id', 'mean', 'stdDev'], ['grid_id', 'ndvi_mean', 'ndvi_std']);

var finalStats = zonalStats.map(function(feature) {
  return feature.set('city_name', 'Zhengzhou');
});

Export.table.toDrive({
  collection: finalStats,
  description: 'zhengzhou_green_metrics',
  folder: 'GEE_CityWalk',
  fileFormat: 'CSV'
});