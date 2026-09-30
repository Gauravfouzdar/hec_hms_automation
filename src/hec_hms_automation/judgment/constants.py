"""
Every question, threshold and model pin used by the optional Jev judgment layer,
in ONE place so a human can review and tune them (rule: "questions, thresholds
and weights live in one constants module").

WHAT JEV IS USED FOR HERE -- and what it is NOT
-----------------------------------------------
Jev (TypeSafe AI "System One" model) answers narrow, typed snap-judgments about
TEXT.  In this project the only places where code has to *guess from words* are:

  1. Is a land-cover class NAME an impervious surface?      (gis.landuse)
  2. Is a NetCDF variable the precipitation variable?        (climate.netcdf_inspect)
  3. Which candidate is the same basin / element name?       (judgment.advisors)

Everything numeric or safety-critical stays in plain code and is never
delegated: Kirpich/Muskingum formulas, L-moments, unit conversion, dates, CRS
and extent checks, file writers, backups.  A Jev answer alone NEVER authorises
a file write -- it can only add candidates that pass a confidence band, and every
use is logged so it can be audited.

Thresholds below are starting points, NOT calibrated on labelled data.  Tune
them on your own examples (plot confidence vs. accuracy) before relying on them.
"""

# Pin the model version the thresholds were chosen against; an alias such as
# "jev-latest" moves when a new model is released and answers can change.
JEV_MODEL = "jev-1.13.0"

# ---- 1. impervious land-cover class -----------------------------------------
# Noul = P(yes).  Three bands (act / review / reject).
LULC_YES_AT_OR_ABOVE = 0.85      # treat as impervious (still logged)
LULC_NO_BELOW = 0.30             # treat as NOT impervious; in between = "review"

LULC_QUESTION = (
    "Is the land-cover class named in `{path}` an impervious surface that sheds "
    "rain as runoff -- buildings/built-up areas, roads, bridges, railways or "
    "industrial sites? Vegetation, forest, farmland, bare soil, mining, water "
    "and wetlands are NOT impervious."
)
LULC_TRUE = "Built or paved surface (buildings, settlement, roads, bridges, industry)"
LULC_FALSE = "Vegetation, cropland, bare ground, water or any natural surface"

# ---- 2. precipitation variable ----------------------------------------------
PRECIP_YES_AT_OR_ABOVE = 0.80
PRECIP_QUESTION = (
    "Is `{path}` a precipitation (rainfall) amount or rate -- not temperature, "
    "pressure, humidity, wind, radiation, a coordinate, a time axis or a bounds "
    "variable?"
)

# ---- 3. name matching --------------------------------------------------------
NONE_OF_THE_ABOVE = "none_of_the_above"
NAME_MATCH_MIN_CONFIDENCE = 0.60   # Choice confidence needed to suggest a match
NAME_SHORTLIST_SIZE = 6            # candidates offered to Jev (chosen by code first)
NAME_MATCH_QUESTION = (
    "Which candidate is the SAME place / model element as `query.name` (allow "
    "spelling variants, transliteration and prefix/suffix such as 'Basin', "
    "'River', 'Lui')? Choose none_of_the_above if no candidate is clearly the same."
)
