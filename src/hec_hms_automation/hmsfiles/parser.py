"""
Generic reader for HEC-HMS v4.x plain-text block-keyword files
(.basin, .control, .met, .grid, .terrain, .pdata, .run, .hms).

File format (see docs/HMS_FILE_FORMAT.md):

    ElementType: Element Name
         Key: Value
         Key: Value
    End:

Top-level blocks always start at column 0 as "Type: Name" (or "Type:" with an
empty name) and always close with a column-0 "End:" line. Everything indented
between the header and the closing "End:" belongs to that block.

This module only resolves the TOP-LEVEL block boundaries and flat-parses each
block's directly-indented "Key: Value" lines. It does not build a nested tree
of inner sub-blocks (e.g. "Element Layer: ... End Layer:" inside "Basin Layer
Properties:") -- those are captured as opaque raw text, because HEC-HMS's use
of "End <Word>:" instead of "End:" for inner blocks is inconsistent and
round-tripping it is not needed for reading element data.

Reference: HEC-HMS file formats are not formally documented by USACE; this
parser was derived from real HMS 4.13 projects. See docs/LITERATURE.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Block:
    """One top-level block.

    block_type  the text before the first colon on the header line
    name        the text after it (may be empty)
    fields      flat key/value pairs in file order (duplicate keys keep the LAST value)
    start_line  1-indexed header line
    end_line    1-indexed closing ``End:`` line
    raw_lines   body lines, verbatim (used by writers that must round-trip a block)
    """

    block_type: str
    name: str
    fields: dict[str, str] = field(default_factory=dict)
    start_line: int = 0
    end_line: int = 0
    raw_lines: list[str] = field(default_factory=list)


def _leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_end_line(line: str) -> bool:
    stripped = line.strip()
    return stripped == "End:" or (stripped.startswith("End ") and stripped.endswith(":"))


def parse_blocks(path: str | Path) -> list[Block]:
    """Parse a .basin/.control/.met/... file into its top-level Block list."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    blocks: list[Block] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == "" or _leading_spaces(line) > 0:
            i += 1
            continue
        if _is_end_line(line):
            i += 1  # stray/unmatched End: at column 0 -- skip defensively
            continue

        # Column-0, non-blank, not an End line -> a block header "Type: Name"
        if ":" not in line:
            i += 1
            continue
        block_type, _, name = line.partition(":")
        block_type = block_type.strip()
        name = name.strip()

        body_start = i + 1
        j = body_start
        while j < n and not (_leading_spaces(lines[j]) == 0 and lines[j].strip() != ""):
            j += 1
        # j now points at the column-0 "End:" line that closes this block
        # (or at EOF if the file is malformed).
        body_lines = lines[body_start:j]

        blk = Block(
            block_type=block_type,
            name=name,
            start_line=i + 1,
            end_line=j + 1 if j < n else j,
            raw_lines=body_lines,
        )
        blk.fields = _parse_flat_fields(body_lines)
        blocks.append(blk)

        i = j + 1 if j < n else n

    return blocks


def _parse_flat_fields(body_lines: list[str]) -> dict[str, str]:
    """Parse the directly-indented ``Key: Value`` lines of a block body.

    Only lines at the body's minimum indentation are treated as this block's
    own fields; deeper-indented lines belong to an inner nested sub-block and
    are skipped (none of the element types read here -- Subbasin, Junction,
    Reach, Sink, Basin -- rely on nesting).
    """
    non_blank = [ln for ln in body_lines if ln.strip() != ""]
    if not non_blank:
        return {}
    base_indent = min(_leading_spaces(ln) for ln in non_blank)

    fields: dict[str, str] = {}
    for ln in body_lines:
        if ln.strip() == "" or _leading_spaces(ln) != base_indent:
            continue
        if _is_end_line(ln):
            continue
        if ":" not in ln:
            continue
        key, _, value = ln.strip().partition(":")
        fields[key.strip()] = value.strip()
    return fields


def blocks_by_type(blocks: list[Block], block_type: str) -> list[Block]:
    """Filter a parsed block list to one ``block_type`` (e.g. ``"Subbasin"``)."""
    return [b for b in blocks if b.block_type == block_type]
