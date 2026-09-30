"""Optional Jev (TypeSafe AI) judgment layer -- advisory, never authoritative.

See judgment/constants.py for what it is (and is not) used for, and
docs/book/00_how_this_book_works.md for the "judgment checkpoints" convention.
"""
from .client import available
from .advisors import Suggestion, judge_impervious_classes, judge_precip_variable, match_name

__all__ = ["available", "Suggestion", "judge_impervious_classes",
           "judge_precip_variable", "match_name"]
