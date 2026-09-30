"""
Advisors: narrow text judgments that sit BEHIND deterministic rules.

Order of decision in every advisor (rule "code first, Jev second"):
    1. exact / rule-based answer  -> return it, Jev is never called
    2. otherwise ask Jev          -> returns a banded suggestion
    3. Jev unavailable            -> return "no opinion"; caller keeps old behaviour
A suggestion is data for the caller to log and act on under its own policy; it
never writes files itself.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from . import constants as C
from .client import available, judge


@dataclass
class Suggestion:
    """One advisory answer.

    value   what was judged (a class name, variable name, candidate name ...)
    band    'yes' | 'review' | 'no' | 'none'   ('none' = no opinion available)
    score   Jev's P(yes) or Choice confidence, else None
    source  'rule' (deterministic) or 'jev' -- kept so decisions can be audited
    """

    value: str
    band: str
    score: float | None
    source: str


# ---------------------------------------------------------------- 1. LULC classes
def judge_impervious_classes(class_names: list[str],
                             known_impervious: list[str]) -> dict[str, Suggestion]:
    """Is each land-cover class name an impervious surface?

    ``known_impervious`` (exact names, e.g. gis.landuse.IMPERVIOUS_CLASS_NAMES)
    are answered by rule without calling Jev.  All remaining names go to Jev in
    a SINGLE request, one Noul per name (several labels can apply at once ->
    one Noul each, not a Choice).
    """
    out: dict[str, Suggestion] = {}
    unknown: list[str] = []
    for name in class_names:
        if name in known_impervious:
            out[name] = Suggestion(name, "yes", 1.0, "rule")
        else:
            unknown.append(name)
    if not unknown:
        return out
    if not available():          # no SDK / key: "no opinion", never a guess
        out.update({n: Suggestion(n, "none", None, "jev") for n in unknown})
        return out

    from typesafe_sdk import Noul, NoulCriteria  # imported lazily: SDK is optional
    questions = {
        f"c{i}": Noul(instructions=C.LULC_QUESTION.format(path=f"classes[{i}]"),
                      criteria=NoulCriteria(true=C.LULC_TRUE, false=C.LULC_FALSE))
        for i in range(len(unknown))
    }
    resp = judge({"classes": unknown}, questions)
    for i, name in enumerate(unknown):
        if resp is None:
            out[name] = Suggestion(name, "none", None, "jev")
            continue
        p = resp.nouls[f"c{i}"].noul
        band = ("yes" if p >= C.LULC_YES_AT_OR_ABOVE
                else "no" if p < C.LULC_NO_BELOW else "review")
        out[name] = Suggestion(name, band, p, "jev")
    return out


# ------------------------------------------------------- 2. precipitation variable
_PRECIP_ALIASES = ["pr", "precip", "precipitation", "rain", "tp", "rainfall"]


def judge_precip_variable(variables: list[dict]) -> Suggestion:
    """Pick the precipitation variable of a NetCDF.

    ``variables`` = [{"name":..., "units":..., "long_name":..., "dims":[...]}].
    Alias list first (rule); Jev only when no alias matches and >1 candidate.
    Ties are broken by higher score, then by file order (Noul values tie often
    because they are rounded to 0.01).
    """
    names = [v["name"] for v in variables]
    for alias in _PRECIP_ALIASES:
        if alias in names:
            return Suggestion(alias, "yes", 1.0, "rule")
    if len(variables) == 1:
        return Suggestion(names[0], "review", None, "rule")
    if not variables or not available():
        return Suggestion("", "none", None, "rule" if not variables else "jev")

    from typesafe_sdk import Noul
    questions = {f"v{i}": Noul(instructions=C.PRECIP_QUESTION.format(path=f"variables[{i}]"))
                 for i in range(len(variables))}
    resp = judge({"variables": variables}, questions)
    if resp is None:
        return Suggestion("", "none", None, "jev")
    scored = sorted(((resp.nouls[f"v{i}"].noul, -i, v["name"])
                     for i, v in enumerate(variables)), reverse=True)
    best_p, _, best_name = scored[0]
    band = "yes" if best_p >= C.PRECIP_YES_AT_OR_ABOVE else "review" if best_p >= 0.5 else "no"
    return Suggestion(best_name, band, best_p, "jev")


# ------------------------------------------------------------------ 3. name match
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def match_name(query: str, candidates: list[str]) -> Suggestion:
    """Which candidate is the same basin / element as ``query``?

    Rule 1: normalised exact match (case, spaces, punctuation ignored).
    Rule 2: code builds a SHORTLIST by string similarity; Jev chooses among the
    shortlist plus ``none_of_the_above``.  Jev is never asked to search a long
    list, so a candidate that is not shortlisted can never be picked.
    """
    nq = _norm(query)
    for c in candidates:
        if _norm(c) == nq:
            return Suggestion(c, "yes", 1.0, "rule")

    ranked = sorted(candidates,
                    key=lambda c: (-difflib.SequenceMatcher(None, nq, _norm(c)).ratio(), c))
    shortlist = ranked[: C.NAME_SHORTLIST_SIZE]
    if not shortlist or not available():
        return Suggestion("", "none", None, "rule" if not shortlist else "jev")

    from typesafe_sdk import Choice
    options = {c: None for c in shortlist}
    options[C.NONE_OF_THE_ABOVE] = "No candidate is clearly the same place"
    resp = judge(
        {"query": {"name": query}, "candidates": shortlist},
        {"match": Choice(instructions=C.NAME_MATCH_QUESTION, criteria=options)},
    )
    if resp is None:
        return Suggestion("", "none", None, "jev")
    ans = resp.choices["match"]
    if ans.choice == C.NONE_OF_THE_ABOVE:
        return Suggestion("", "no", ans.confidence, "jev")
    band = "yes" if ans.confidence >= C.NAME_MATCH_MIN_CONFIDENCE else "review"
    return Suggestion(ans.choice, band, ans.confidence, "jev")
