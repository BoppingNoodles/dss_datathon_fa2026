# ZIP area map data

`east-bay-zips.geojson` contains simplified public 2020 Census ZCTA boundaries
for ZIP codes 94500–94899, retrieved November 14, 2026 from the Census Bureau's
2026 TIGERweb service. ZCTAs approximate ZIP service areas; they are not individual
property locations or exact USPS delivery boundaries.

Source: https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer/2

Query fields: ZCTA5, INTPTLAT, INTPTLON. Output EPSG:4326, maximum allowable
offset 0.0003 degrees, five decimal places. There are 113 features. Polygon and
multipolygon geometry is preserved. Internal points label the highlighted ZIP.

The frontend serves these boundaries locally and overlays them on a Leaflet map.
Street tiles load from `https://tile.openstreetmap.org/{z}/{x}/{y}.png` using normal
browser caching and visible OpenStreetMap attribution. No map key is needed.
Missing boundaries show an unavailable state; pins can still show known places.
Pins use the public Places dataset and are never derived from housing properties.
