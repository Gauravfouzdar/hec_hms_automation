# Literature and reading list

What to read to understand (and safely change) each part of this toolkit. Items
are grouped by the chapter of the book that uses them, and marked **Start here**
where it is the single best first read.

> **Verify before citing.** These references were written from knowledge of the
> standard literature, without access to the papers while writing. Titles,
> authors and years are the ones I am confident about; check volume and page
> numbers against the publisher before putting any of them in a formal report.

## A. HEC-HMS method references (chapters 3, 8, 9)

| Topic | Read |
|---|---|
| **All HMS methods - start here** | USACE Hydrologic Engineering Center, *HEC-HMS Technical Reference Manual* (current version on the HEC website) |
| Using and scripting HMS | USACE HEC, *HEC-HMS User's Manual* and the HMS scripting (Jython) guide, same site |
| Deficit and Constant loss, Linear Reservoir baseflow, Muskingum routing, MUSLE | Technical Reference Manual, the chapters on loss, baseflow, routing and sediment |
| **Modified Clark (ModClark)** | Kull, D.W. and Feldman, A.D. (1998). Evolution of Clark's unit graph method to spatially distributed runoff. *Journal of Hydrologic Engineering*, 3(1), 9-19 |
| Clark unit hydrograph | Clark, C.O. (1945). Storage and the unit hydrograph. *Transactions of the ASCE*, 110, 1419-1446 |
| Clark parameters `R/(Tc+R)` (the 0.65 ratio behind `R = 13/7 Tc`) | Straub, T.D., Melching, C.S. and Kocher, K.E. (2000). *Equations for estimating Clark unit-hydrograph parameters for small rural watersheds in Illinois.* USGS Water-Resources Investigations Report 00-4184 |
| **Kirpich time of concentration** | Kirpich, Z.P. (1940). Time of concentration of small agricultural watersheds. *Civil Engineering*, 10(6), 362. For its limits see the discussion of Tc formulas in Chow, Maidment and Mays below |
| Muskingum method | McCarthy, G.T. (1938). The unit hydrograph and flood routing. Paper at the Conference of the North Atlantic Division, U.S. Army Corps of Engineers |
| Muskingum-Cunge | Cunge, J.A. (1969). On the subject of a flood propagation computation method (Muskingum method). *Journal of Hydraulic Research*, 7(2), 205-230 |
| Sediment (MUSLE) | Williams, J.R. (1975). Sediment-yield prediction with universal equation using runoff energy factor. In *Present and Prospective Technology for Predicting Sediment Yields and Sources*, USDA ARS-S-40 |
| General hydrology text | Chow, V.T., Maidment, D.R. and Mays, L.W. (1988). *Applied Hydrology.* McGraw-Hill. **Start here** for Tc, unit hydrographs, routing and the alternating block hyetograph |

**Where it matters in the code:** `hydrology/parameters.py` implements Kirpich,
`R = (13/7) Tc`, `GW-1 = 3R`, `GW-2 = 10R` and the Muskingum stability count.
The constants are project decisions (Lukha reference model), *not* universal
values. Read Straub et al. and the TRM before reusing them in another climate
or terrain.

## B. Terrain and flow paths (chapter 3)

| Topic | Read |
|---|---|
| D8 flow direction | O'Callaghan, J.F. and Mark, D.M. (1984). The extraction of drainage networks from digital elevation data. *Computer Vision, Graphics, and Image Processing*, 28(3), 323-344 |
| TauDEM (the D8 codes 1-8 used by HMS terrain products) | Tarboton, D.G. (1997). A new method for the determination of flow directions and upslope areas in grid digital elevation models. *Water Resources Research*, 33(2), 309-319; software documentation at https://hydrology.usu.edu/taudem/ |

## C. Design storms (chapter 5)

| Topic | Read |
|---|---|
| **L-moments and regional frequency analysis - start here** | Hosking, J.R.M. and Wallis, J.R. (1997). *Regional Frequency Analysis: An Approach Based on L-Moments.* Cambridge University Press |
| L-moments definition and estimators | Hosking, J.R.M. (1990). L-moments: analysis and estimation of distributions using linear combinations of order statistics. *Journal of the Royal Statistical Society, Series B*, 52(1), 105-124 |
| Extreme value (Gumbel) distribution | Gumbel, E.J. (1958). *Statistics of Extremes.* Columbia University Press |
| Alternating block hyetograph | Chow, Maidment and Mays (1988), section on design storms |
| Gridded daily rainfall for India | Pai, D.S. et al. (2014). Development of a new high spatial resolution (0.25 x 0.25 degree) long period (1901-2010) daily gridded rainfall data set over India and its comparison with existing data sets over the region. *MAUSAM*, 65(1), 1-18 |
| Hourly distribution factors | Central Water Commission / IMD / RDSO **Flood Estimation Reports** for the relevant sub-zone. The bundled workbook holds the incremental factors per sub-zone; consult the report for your sub-zone for the authoritative table and its conditions (citation to be confirmed for your zone) |

**Known simplification (important):** `homogeneity_test` is a *simplified*
H-statistic: it simulates Gaussian L-skewness values instead of sampling the
four-parameter Kappa distribution, and it measures the spread of L-skewness
rather than L-CV as in Hosking and Wallis's V1. Only the Gumbel distribution is
fitted, with no goodness-of-fit comparison against GEV or others. To make it
publication-grade implement the full procedure from chapters 3-5 of Hosking and
Wallis (1997), or use an established L-moment package.

## D. Climate scenarios (chapter 6)

| Topic | Read |
|---|---|
| CMIP6 design | Eyring, V. et al. (2016). Overview of the Coupled Model Intercomparison Project Phase 6 (CMIP6) experimental design and organization. *Geoscientific Model Development*, 9, 1937-1958 |
| SSP scenarios | O'Neill, B.C. et al. (2016). The Scenario Model Intercomparison Project (ScenarioMIP) for CMIP6. *Geoscientific Model Development*, 9, 3461-3482 |
| Delta-change versus downscaling | Hay, L.E., Wilby, R.L. and Leavesley, G.H. (2000). A comparison of delta change and downscaled GCM scenarios for three mountainous basins in the United States. *Journal of the American Water Resources Association*, 36(2), 387-397 |
| CHIRPS rainfall | Funk, C. et al. (2015). The climate hazards infrared precipitation with stations - a new environmental record for monitoring extremes. *Scientific Data*, 2, 150066 |
| CF conventions / cftime calendars | https://cfconventions.org/ and the `cftime` documentation |

**Note:** the pipeline clips and unit-converts raw model output. It does **not**
bias-correct. Decide consciously whether that suffices (Hay et al. discuss the
options).

## E. Software and file formats (chapters 1, 7, 9, 10)

| Tool | Read |
|---|---|
| HEC-HMS | https://www.hec.usace.army.mil/software/hec-hms/ (downloads, manuals) |
| **HEC-Vortex** | https://github.com/HydrologicEngineeringCenter/Vortex (releases, documentation, Java API used by the generated Jython scripts) |
| HEC-DSS | HEC-DSS documentation on the HEC website; pathname parts A-F |
| pydsstools | https://github.com/gyanz/pydsstools |
| Jython 2.7 | https://www.jython.org/ (language level of the generated Vortex scripts: Python 2.7 syntax) |
| xarray, rasterio, GeoPandas, Shapely, netCDF4 | each project's official documentation |
| HMS text file formats | not formally documented by USACE; see `docs/HMS_FILE_FORMAT.md`, derived from real 4.13 projects |
