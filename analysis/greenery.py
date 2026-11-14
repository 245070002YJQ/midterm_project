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
