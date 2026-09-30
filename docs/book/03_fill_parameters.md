# Chapter 3 - Fill the model parameters

## Purpose
Turn a structurally complete but parameter-empty model into a runnable one by
computing every parameter from the project's own terrain, network and land-use
data.

## You need
Inside the project folder:

| Input | Where it is looked for |
|---|---|
| `.basin` file | exactly one `*.basin` |
| Basin geometry | `<basin>.sqlite` beside it (`Basin_1.basin` -> `Basin_1.sqlite`) with layers `subbasin2d` and `reach2d`. Open the project in HMS and define the structured discretization first |
| Terrain rasters | `terrain\<name>\<NN>\flowdir.tif` **and** `demsd8.tif` in the same folder (highest `NN` wins) |
| Land use | `Input data\*LULC*.tif` with its `.vat.dbf` class table |

## Run
```cmd
:: 1. see what would happen across many projects, write nothing
hms-auto batch-fill "E:\MyModels"

:: 2. fill one project (also writes computed_parameters.xlsx for review)
hms-auto populate "E:\MyModels\Lukha_basin"
hms-auto populate "E:\MyModels\Lukha_basin" --dry-run

:: 3. fill every skeleton project
hms-auto batch-fill "E:\MyModels" --write

:: 4. the LULC raster changed: refresh ONLY impervious %
hms-auto update-impervious "E:\MyModels\Lukha_basin" "E:\data\Lukha_LULC_2025.tif"
```

## What happens
For every subbasin and reach:

| Parameter | Formula (defaults in `ParameterSet`) |
|---|---|
| Longest flow path *L* | maximum D8 flow distance to the subbasin outlet, from `flowdir.tif` |
| Basin slope *S* | mean of `demsd8.tif` over the subbasin |
| Time of concentration | Kirpich: `Tc_min = 0.0195 * L^0.77 * S^-0.385` (L in m, S in m/m), then `/60` |
| Storage coefficient *R* | `R = (13/7) * Tc`, from `R/(Tc+R) = 0.65` |
| Baseflow | two linear-reservoir layers, fraction 0.4 each, initial 0.1 m3/s, routing coefficients `3R` and `10R` |
| Loss | Deficit and Constant: initial 30 mm, maximum 50 mm, percolation 0.5 mm/hr |
| Impervious % | share of classified cells in the impervious LULC classes |
| Muskingum *K* | Kirpich Tc of the reach from its length and slope, floored at 0.1 hr; *x* = 0.2; subreaches `ceil(2*x*K/dt)` |

Reach slope falls back in order: `reach2d.slope`, `strmdrop/length`, DEM drop
between the endpoints, the minimum-slope floor (reported per reach as *Slope
Source*). Results go to `computed_parameters.xlsx` next to the LULC raster, then
into the `.basin` through an **idempotent** writer with a timestamped backup.

To use different constants for one project, build your own `ParameterSet` and
pass it to `populate_project(..., pset=...)`. Nothing is hard-coded.

## Check
- The command prints `WROTE n subbasins, m reaches complete`. It re-reads the
  file and reports any element that is still missing parameters.
- Open `computed_parameters.xlsx`: sheets *Subbasins*, *Reaches*, *Method*.
- Run chapter 2's `read-basin` again: no `<- missing` markers.
- Open the model in HMS and compute once as a sanity check.

## Judgment checkpoint
| Decision | Decided by |
|---|---|
| Is the `.basin` already filled? Rewrite it? | **Code rule** (`fill_state`; needs `--force`) |
| Does the LULC raster share the project CRS and overlap the subbasins? | **Code rule** (`check_lulc_overlap`); a failure skips the project |
| Which raster values are impervious? | **Code rule first**: exact class names via the VAT (`Built-up`, `Transportations/Bridges`, `Industry`). Raster *values* differ between rasters, names do not |
| Same, when the exact names match **nothing** (e.g. classes called `Settlement`, `Roads and Railways`) | **Optional Jev advisor** with `--judge-lulc`: one question per class name. Only the `yes` band (P >= 0.85) is used, `review` (0.30 to 0.85) is printed for you, everything is logged. Without a key nothing changes |
| All numbers | **Code** (never delegated) |

Always read the printed `Jev LULC judgment:` lines. If a class you care about
lands in `review`, add its exact name to `IMPERVIOUS_CLASS_NAMES` in
`gis/landuse.py` instead of relying on advice.

## If it fails
| Message | Fix |
|---|---|
| `SKIP ... found 0, need exactly 1 (Input data/*LULC*.tif)` | Put exactly one LULC raster in `Input data`, or pass `--lulc` |
| `no terrain/*/*/ folder holding both flowdir.tif and demsd8.tif` | Run terrain preprocessing in the HMS GUI |
| `... no matching row in subbasin2d` | Open the project in HMS so it refreshes the sqlite |
| `LULC CRS ... != project EPSG` / `does not overlap` | Wrong or misplaced raster; reproject or replace it |
| `No VAT sidecar` | The raster needs `<name>.tif.vat.dbf` or `<name>.dbf` |
| `.basin already filled ... not rewritten` | Restore the `.bak-*` file, or add `--force` |
| HMS error 41161 *Invalid Muskingum K* | Already prevented by the K floor; report if it recurs |

## Where the code is
`workflows/populate.py` (orchestration), `hydrology/parameters.py` (formulas),
`gis/terrain.py`, `gis/landuse.py`, `gis/hms_geometry.py`,
`hmsfiles/basin_writer.py`, `judgment/advisors.py`.
