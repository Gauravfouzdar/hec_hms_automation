"""
Percent impervious area per subbasin from a classified LULC raster.

The impervious percentage is the fraction of a subbasin's classified (non-
nodata) cells that fall in the impervious LULC classes.

IMPORTANT: raster VALUE numbering is NOT consistent across LULC rasters (e.g.
in the 2025 Meghalaya series value 3 is "Built-up" in one basin's raster but
"Forest" in another), while class NAMES are consistent. Always resolve
impervious classes by NAME through the raster's ``.vat.dbf`` sidecar
(:func:`resolve_impervious_values`); only fall back to explicit numeric values
when a raster has no VAT.

To use different class names, pass ``class_names=[...]`` -- or change
``IMPERVIOUS_CLASS_NAMES`` below for your region's legend.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize

IMPERVIOUS_CLASS_NAMES = ["Built-up", "Transportations/Bridges", "Industry"]


def vat_sidecar(lulc_tif: str | Path) -> Path | None:
    """Locate the VAT under both sidecar conventions:
    ``<name>.tif.vat.dbf`` (ArcGIS) and ``<name>.dbf`` (bare, seen in the field)."""
    lulc_tif = Path(lulc_tif)
    for cand in (Path(str(lulc_tif) + ".vat.dbf"), lulc_tif.with_suffix(".dbf")):
        if cand.exists():
            return cand
    return None


def read_vat_classes(vat_dbf: str | Path) -> dict[int, str]:
    """Read {raster value: class name} from an ESRI .vat.dbf sidecar.

    Minimal dBASE III reader (no dependency): first field = Value, last field
    = Class_Name, which is the layout of the VATs this project uses.
    """
    data = Path(vat_dbf).read_bytes()
    n_rec = struct.unpack("<I", data[4:8])[0]
    hdr_len = struct.unpack("<H", data[8:10])[0]
    rec_len = struct.unpack("<H", data[10:12])[0]
    fields = []
    pos = 32
    while data[pos] != 0x0D:  # 0x0D terminates the field descriptor array
        fields.append((data[pos:pos + 11].split(b"\x00")[0].decode(), data[pos + 16]))
        pos += 32
    out: dict[int, str] = {}
    for i in range(n_rec):
        rec = data[hdr_len + i * rec_len: hdr_len + (i + 1) * rec_len]
        off = 1  # byte 0 of each record is the deletion flag
        vals = []
        for _, flen in fields:
            vals.append(rec[off:off + flen].decode(errors="replace").strip())
            off += flen
        out[int(float(vals[0]))] = vals[-1]
    return out


def resolve_impervious_values(
    lulc_tif: str | Path,
    class_names: list[str] = IMPERVIOUS_CLASS_NAMES,
    judge_unmatched: bool = False,
) -> list[int]:
    """Map impervious class NAMES to this raster's values via its VAT.

    Exact-name matching is the rule and is always tried first.  Only when it
    finds NOTHING and ``judge_unmatched=True`` is the optional Jev advisor
    (judgment.advisors) asked whether the raster's own class names are
    impervious.  Only the high-confidence 'yes' band is accepted; 'review'
    classes are printed for a human and never used.  Every decision is printed
    so it can be audited.  Without a key/SDK this silently does nothing.
    """
    lulc_tif = Path(lulc_tif)
    vat = vat_sidecar(lulc_tif)
    if vat is None:
        raise FileNotFoundError(
            f"No VAT sidecar for {lulc_tif} (tried {lulc_tif.name}.vat.dbf and "
            f"{lulc_tif.with_suffix('.dbf').name}); cannot resolve class names "
            f"safely. Pass explicit numeric values instead."
        )
    classes = read_vat_classes(vat)
    exact = [v for v, name in classes.items() if name in class_names]
    if exact or not judge_unmatched:
        return exact

    from ..judgment import judge_impervious_classes  # optional layer, imported lazily
    verdicts = judge_impervious_classes(list(classes.values()), list(class_names))
    accepted: list[int] = []
    for value, name in classes.items():
        s = verdicts[name]
        print(f"  Jev LULC judgment: value {value} '{name}' -> {s.band} "
              f"(P={s.score}, {s.source})")
        if s.band == "yes":
            accepted.append(value)
    return accepted


@dataclass
class ImperviousStat:
    element_name: str
    percent_impervious: float   # 0-100
    impervious_cells: int
    classified_cells: int


def compute_impervious(
    lulc_tif: str | Path,
    subbasin_geoms: dict[str, object],
    impervious_classes: list[int],
) -> dict[str, ImperviousStat]:
    """Percent impervious per subbasin geometry (same CRS as the raster)."""
    with rasterio.open(lulc_tif) as ds:
        lulc = ds.read(1)
        transform = ds.transform
        nodata = ds.nodata

    names = list(subbasin_geoms.keys())
    zones = rasterize(
        [(subbasin_geoms[n], i + 1) for i, n in enumerate(names)],
        out_shape=lulc.shape,
        transform=transform,
        fill=0,
        dtype="int32",
    )

    imp_mask = np.isin(lulc, impervious_classes)
    results: dict[str, ImperviousStat] = {}
    for i, name in enumerate(names):
        zone = zones == (i + 1)
        classified = zone & (lulc != nodata) if nodata is not None else zone
        n_class = int(classified.sum())
        n_imp = int((classified & imp_mask).sum())
        pct = (100.0 * n_imp / n_class) if n_class else 0.0
        results[name] = ImperviousStat(
            element_name=name,
            percent_impervious=pct,
            impervious_cells=n_imp,
            classified_cells=n_class,
        )
    return results
