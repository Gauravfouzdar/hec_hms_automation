# Chapter 11 - Export GIS layers

## Purpose
Publish the model's geometry for maps, reports and portals: one sub-basin
shapefile per project and one combined pour-point shapefile.

## You need
Projects whose basin sqlite holds `subbasin2d` (the structured discretization
defined in HMS) and a `.basin` with `Sink:` elements.

## Run
```cmd
hms-auto export-subbasins "E:\MyModels" "E:\out\subbasins"
hms-auto export-sinks     "E:\MyModels" "E:\out\subbasins"
```

## What happens
- **Sub-basins:** for each project, read `subbasin2d` (HMS's own current
  geometry, already reflecting GUI merges and edits), repair invalid polygons,
  compute `area_km2` from the geometry, write `<Project>_subbasins.shp`.
- **Sinks:** read each `.basin`'s Sink `Canvas X/Y` and write one point per
  project into `pour_points.shp`, in the CRS taken from the first project that
  has a `fromGIS.sqlite`.

## Check
- Each project prints `OK n subbasins, X km2`. Compare the total area with the
  `.basin` (`read-basin` in chapter 2).
- Open the shapefiles in GIS: outlets should sit on the main river.

## Judgment checkpoint
**Code only.** Geometry repair and area are exact. If projects in one folder
use different CRSs, the combined pour-point file takes the first one; export
per CRS group instead.

## If it fails
| Symptom | Fix |
|---|---|
| `subbasin2d is empty` | Define the discretization in HMS, save, re-run |
| `no .sqlite in project` | The project has no structured grid yet |
| Pour points offset | Mixed CRSs in the parent folder (see above) |

## Where the code is
`gis/export.py`.
