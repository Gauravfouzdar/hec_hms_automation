# Chapter 9 - Compute the runs (HEC-HMS, no GUI)

## Purpose
Run many simulations across many projects unattended, and get an honest verdict
for each one.

## You need
HEC-HMS installed (chapter 1) and projects with runs (chapter 8).

## Run
```cmd
hms-auto compute "E:\MyModels" --tags RP5,RP10,RP25,RP50,RP100
hms-auto compute "E:\MyModels" --tags Historical,SSP245 --project Bugi_Basin
```
Tags are the run names without the word `Run` (`Run RP5` -> `RP5`).

## What happens
For each project one HMS **Jython script** opens the project once, computes the
requested runs in sequence (each in its own `try/except`, so one failure does
not stop the rest), saves, and exits. The script and its launcher live in the
system temp folder **on purpose**: project paths often contain `&`, which
`cmd.exe` treats as a command separator.

HMS returns exit code 0 even when a compute fails, so the verdict is read from
each run's own `Run_<tag>.log`:

| Verdict | Meaning |
|---|---|
| `OK (runtime, n warn)` | log contains *Finished computing simulation run* |
| `OK ... +n ERR` | finished, but the log also has ERROR lines: read them |
| `FAILED: ERROR 41161: ...` | first error line |
| `STALE log (run did not execute)` | the log is older than this launch: nothing ran |
| `no log` | the run was never created |

## Check
- The final line: `Done in ...s -- n succeeded, m failed`.
- Spot-check one project: the output DSS `Run_<tag>.dss` exists and is not tiny.
- Read warnings once per basin. Typical and acceptable: *no ET method*, *no
  canopy method*, *R clamped to 0.5 x dt* on daily runs.

## Judgment checkpoint
**Code only, deliberately.** Whether a run succeeded is answered by regular
expressions on HMS's own log plus a timestamp guard, not by opinion. The
**human judgment** is hydrological: are the results plausible (peak, volume,
runoff coefficient)? The toolkit cannot answer that for you; see the
literature list for the method assumptions behind the numbers.

## If it fails
| Symptom | Fix |
|---|---|
| `HEC-HMS not found` | `--hms-home` or `HMS_HOME` |
| `STALE log` | HMS did not start: run the printed `hms output` tail by hand |
| `Invalid Muskingum K` (41161) | Reparameterise with chapter 3 (K is floored at 0.1 hr) |
| Very long runs | 30-year daily runs are slow; run projects in separate windows |

## Where the code is
`compute/runner.py`, `config.py` (`find_hms_home`, `scratch_dir`).
