# Chapter 0 - How this book works

This folder is a **book, not a reference**. Read chapters 1 to 11 in order and
you go from an empty machine to a computed HEC-HMS model with 10-daily flow
workbooks. Every process in the toolkit has exactly one chapter, and every
chapter has the same seven parts so you always know where to look:

| Part | What it tells you |
|---|---|
| **Purpose** | Why this step exists, in one paragraph |
| **You need** | Inputs and tools that must exist first |
| **Run** | The exact command (CMD syntax) |
| **What happens** | The steps the code performs, in order |
| **Check** | How to prove it worked, using deterministic checks |
| **Judgment checkpoint** | Where a decision is made, and *who* makes it: a code rule, a human, or the optional Jev advisor |
| **If it fails** | The known failure modes and their fixes |
| **Where the code is** | Files to open when you want to change behaviour |

## The judgment rule (read this once)

The toolkit makes three kinds of decisions, and they are kept apart on purpose.

1. **Code rules decide everything numeric or safety-critical.** Formulas
   (Kirpich, Muskingum, L-moments), unit conversion, dates, CRS and extent
   checks, "is this DSS present", "sum of CWC factors is 1.0", "do not
   overwrite a filled `.basin`". These are never delegated to a model, because
   they can be written exactly and a miss can damage a model.
2. **A human decides anything ambiguous with real consequences.** For example
   choosing which basin a name refers to when nothing matches, or accepting a
   reviewed LULC class.
3. **Jev (TypeSafe AI, optional) advises only on narrow questions about
   *text*** where code would otherwise have to guess from words. In this
   toolkit there are exactly three such questions, all in `judgment/`:

   | Question asked | Used by | Code rule that runs first |
   |---|---|---|
   | Is this land-cover **class name** an impervious surface? | `populate --judge-lulc`, `update-impervious --judge-lulc` | exact match against `IMPERVIOUS_CLASS_NAMES` |
   | Is this NetCDF **variable** the precipitation variable? | `inspect-nc --judge` | alias list (`pr`, `rain`, `tp`, ...) |
   | Which candidate is the **same basin / element name** as this query? | `judgment.match_name` | normalised exact match, then a code-built shortlist |

Rules that keep Jev safe here:

- **Code first, Jev second.** Jev is called only when the rule finds nothing.
- **Advice, never authority.** A Jev answer is a *band* (`yes` / `review` /
  `no` / `none`). Only `yes` is ever acted on, `review` is printed for a human,
  and no Jev answer alone writes a file that a rule has not already allowed.
- **No key, no problem.** Without `TYPESAFE_API_KEY` or the SDK, every advisor
  returns "no opinion" and the toolkit behaves exactly as if Jev did not exist.
- **Everything is logged.** Each decision prints its source (`rule` / `jev`),
  score and model id, so a run can be audited afterwards.
- **One place to tune.** Questions, thresholds and the pinned model
  (`jev-1.13.0`) are in `src/hec_hms_automation/judgment/constants.py`. The
  thresholds are starting points, not calibrated values: tune them on your own
  labelled examples before relying on them.

## Conventions

- **All commands are CMD (Command Prompt) syntax.** Quote every path; paths
  containing `&` such as `E:\AI & ML` only work when quoted.
- `hms-auto` is the command. `python -m hec_hms_automation` is identical.
- "Project" means one HEC-HMS project folder (contains a `.hms` file).
  "Parent" means a folder holding many projects.
- Every command that edits an HMS file first writes a `*.bak-YYYYmmdd-HHMMSS`
  backup next to it. To undo a run, copy the backup over the file.

## The whole workflow on one page

```
 1 Setup -> 2 Read the model -> 3 Fill parameters
                                     |
   4 Inspect rainfall NetCDF --+--> 5 Design storms ---+
                               +--> 6 Climate (CMIP6) -+
                                                       v
                                    7 NetCDF -> gridded DSS (Vortex)
                                                       v
                                    8 Scenarios + runs in every project
                                                       v
                                    9 Compute (HEC-HMS headless)
                                                       v
                                   10 Extract 10-daily flow (Excel)
                                                       v
                                   11 Export GIS layers  |  12 Troubleshooting
```
