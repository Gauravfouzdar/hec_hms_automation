"""hec_hms_automation -- global, reusable automation for HEC-HMS 4.x projects.

Sub-packages (import only what you need; the light ones need no GIS stack):

    hmsfiles    read/write HMS plain-text files (.basin .met .control .grid .run .hms)   [stdlib only]
    hydrology   parameter formulas (Kirpich, Clark, Muskingum ...) and design-storm maths [numpy/scipy]
    gis         terrain flow paths, LULC impervious %, HMS sqlite geometry, GIS export    [rasterio/geopandas]
    vortex      HEC-Vortex + Jython bridge: NetCDF -> gridded DSS                          [stdlib + Vortex]
    climate     CMIP6 clip/export pipeline                                                 [xarray/geopandas]
    dss         read HMS results from DSS, 10-daily (dekad) extraction                     [pydsstools]
    compute     run HMS simulations headlessly                                             [stdlib + HEC-HMS]
    workflows   end-to-end pipelines that combine the pieces above
    plots       diagnostic figures

Command line:  ``hms-auto --help``  (or ``python -m hec_hms_automation --help``).

Every path (HEC-HMS, Vortex, projects, data) is an argument or an environment
variable -- nothing is hard-coded to one machine.  See docs/DEVELOPER_GUIDE.md.
"""

__version__ = "0.1.0"
