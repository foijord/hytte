# Kalsneset 27 — geodata for 3D model

Property: **Kalsneset 27, 4641 Søgne** (Kristiansand kommune 4204, gnr/bnr **437/109**, ~1277 m² waterfront lot).

All rasters share the same grid and CRS:

- **CRS:** EPSG:25833 (ETRS89 / UTM 33N), heights in NN2000 (EPSG:5941)
- **Bounding box:** E 71128 – 71728, N 6457799 – 6458399 (600 × 600 m)
- **Address point:** E 71428.47, N 6458099.03 (lat 58.056285, lon 7.729478)
- Terrain height at address point: 3.55 m; surface (roof) 7.06 m

## Files

| File | Contents |
|---|---|
| `dtm_25cm.tif` | Digital terrain model (bare earth), **0.25 m/px**, 2400×2400, float32 GeoTIFF, nodata −9999. Source: Kartverket hoydedata.no, LiDAR project **Kristiansand 2020** (5 pts/m², Terratec, flown 2020-04). |
| `dom_25cm.tif` | Digital surface model (includes buildings, vegetation, docks), same grid/source. `DOM − DTM` isolates above-ground objects — use it to extract building volumes. |
| `ortho_16cm.jpg` + `.jgw` | Orthophoto mosaic, **0.165 m/px**, 3630×3630, stitched from Norge i bilder WMTS (LOD 17). World file georeferences it to the same bbox. Use directly as terrain texture. |
| `property_437_109.geojson` | Parcel boundary polygon for 437/109 (EPSG:25833 coords). Source: Kartverket Matrikkelen WFS. |
| `teig_bbox.gml` | Raw WFS response — all neighbouring parcels in a 260 m box (437/6, 105, 111, 117, 119, 120, 121, 296…). |
| `osm_buildings.json` | 86 OSM building footprints in the wider area (Overpass, WGS84 lat/lon — reproject before use). |
| `preview_parcel_overlay.jpg` | Verification image: parcel outline (yellow) on the orthophoto, 200×200 m around the address. Buildings inside the outline are the ones on this property; the red-roofed house is the neighbour's. |
| `fetch_ortho.py` | Script that produced the orthophoto (token + tile stitch), for re-fetching at other bboxes/zoom. |

## Mapping rasters into THREE.js

GeoTIFF pixel (row, col) → world: `E = 71128 + col·res`, `N = 6458399 − row·res`
(res = 0.25 for the DEMs, 0.165283203125 for the ortho; both top-left anchored at the same corner, so UV mapping the ortho onto a DTM plane is a straight 0–1 stretch).

Suggested local scene origin: the address point (71428.47, 6458099.03), so
`x = E − 71428.47`, `z = −(N − 6458099.03)`, `y = height` (meters, Z-up→Y-up).

## Data sources / refreshing

- **DEM export** (no auth): `https://hoydedata.no/arcgis/rest/services/Prosjekt_DTM/ImageServer/exportImage` (and `Prosjekt_DOM`), with `mosaicRule={"mosaicMethod":"esriMosaicNone","where":"LAS_PROJECT_NAME='Kristiansand 2020'"}`, `pixelType=F32`, `format=tiff`, bbox in EPSG:25833. Max 15000×15000 px per request.
- **Orthophoto**: anonymous token from `GET https://backend-api.klienter-prod-k8s2.norgeibilder.no/token/nib` (send `Origin: https://norgeibilder.no`), then tiles from `https://tilecache.norgeibilder.no/arcgis/rest/services/Nibcache_UTM33_EUREF89_v2/MapServer/tile/{z}/{row}/{col}?token=…`. Tokens expire (~1 h); `fetch_ortho.py` handles it.
- **Parcels**: `https://wfs.geonorge.no/skwms1/wfs.matrikkelen-eiendomskart-teig` (WFS 2.0, open).
- Even denser data exists as raw LAZ point clouds (5 pts/m²) via hoydedata.no export if roof-shape extraction needs it.

License: Kartverket data CC BY 4.0 (attribution «© Kartverket»); orthophoto © Norge i bilder — check project license before publishing renders.
