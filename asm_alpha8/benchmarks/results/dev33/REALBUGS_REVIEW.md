# DEV33 fresh real bugs: every accepted patch read against the developer's fix (pre-registered G33-A and G33-B)

6 of the 48 valid fresh bugs ended `resolved` in at least one arm. The time control (`checked_long`, the checked control
with 300 s) ran on the one bug that checked_learned resolved and checked did not (mistletoe-5) and ended unresolved
(`dev33_time_control.jsonl`).

I read each patch against the developer's diff; both are stored in the raw records. When reading alone did not settle
a patch, a probe ran on the developer's fixed tree and on the arm's patched tree (rebuilt from the arm's stored diff), in
the bug's own Python 3.11 virtualenv inside ASM's sandbox (`benchmarks/dev33_probes.py` → `probes.jsonl`). **Correct**
is as DEV15 defines it.

| bug | arms | ASM's edit | oracle | **verdict** | basis |
|---|---|---|---|---|---|
| mistletoe-2 | all four | `lines[1:-2]` → `lines[1:-1]` in `MarkdownRenderer` (const) | restored | **correct** | identical to the developer's fix |
| mistletoe-5 | learned, checked_learned | `'\\hrulefill\n'` → `'\n\\hrulefill\n'` in `LaTeXRenderer.render_thematic_break` (learned shape via extend) | restored | **correct** | identical to the developer's fix. Not repaired by the control, the checked control or the 300 s checked control |
| dataclasses-json-4 | control, learned | `is_dataclass(type_)` → `not (…)` in `build_type` (negate) | unknown | **wrong** | the developer adds variable-length and fixed tuples to the schema. Probe: every schema field becomes a plain `Field`, so `Tuple[int, ...]` accepts `['x']` (fixed: `ValidationError`) and a nested dataclass dumps as `P(x=1)` instead of `{'x': 1}` |
| dataclasses-json-4 | checked, checked_learned | `try/except TypeError: pass` around `TYPES[origin](*args, **options)` in `build_type` (try_except) | unknown | **wrong** | the check rejected 4 candidates first. This one skips the failing tuple field type, so tuples get a plain `Field`. Probe: `Tuple[int, ...]` accepts `['x']` (fixed: `ValidationError`) |
| dataclasses-json-5 | control, learned | `and not isinstance(obj, bytes)` → `and isinstance(obj, bytes)` in `_asdict` (not) | equivalent (oracle error) | **wrong** | the developer excludes `Enum` from collections. Probe: `to_dict()` leaves a list of dataclasses as `[P(x=1), P(x=2)]` (fixed: `[{'x': 1}, {'x': 2}]`) and turns `b'xy'` into `[120, 121]`. The checked arms rejected it (3 candidates) and accepted nothing |
| dataclasses-json-8 | control, learned | `is_dataclass(field_value)` → `not (…)` in `_asdict` (negate) | wrong | **wrong** | the developer also catches `AttributeError` when decoding a union. Probe: `from_dict({'p': {'x': 1}, ...})` leaves `p` a dict (fixed: `P(x=1)`). The checked arms rejected it (2 candidates) and accepted nothing |
| markdown-it-py-1 | all four | `try/except UnicodeDecodeError: pass` around `convert_file(filename)` in the CLI's `convert` (try_except) | equivalent / wrong (it differed between arms) | **wrong** | the developer opens the file as UTF-8 with `errors="ignore"`. ASM's patch prints nothing for a file it cannot decode. Probe: a file with `'# café ✓'` and a stray byte renders as `<h1>café ✓</h1>…` when fixed and prints nothing when patched. No test of the suite covers it, so the check passed it |

## Totals
| | control | learned | checked | checked_learned | checked_long |
|---|---|---|---|---|---|
| accepted patches | 5 | 6 | 3 | 4 | 0 of 1 |
| correct | 1 | 2 | 1 | 2 | — |
| wrong | 4 | 4 | 2 | 2 | — |

- **G33-A (the check), person-read:**
  - **A1 fewer wrong patches:** checked_learned 2 wrong, learned 4: at most half (2) and 2 fewer. **Met**, exactly at
    the threshold.
  - **A2 no loss:** both learned-correct bugs (mistletoe-2, mistletoe-5) are repaired correctly by checked_learned. Met.
  - **A3 small cost:** see the report (`whole_suite_on_developer_fixes_*of3.jsonl`).
- **G33-B (learned knowledge with the check), person-read:**
  - **B1 learned repairs:** 1 bug correct with checked_learned and neither with checked nor with checked_long
    (mistletoe-5); 2 needed. **Not met.**
  - **B2 no loss:** 0 checked-correct bugs lost. Met.
  - **B3 safety:** checked_learned 2 wrong, against checked's 2 + 1 allowed. Met.
  - **B4 the clock holds:** the longest checked_learned run took 478 s (markdown-it-py-2); limit 360. **Not met.**

  **G33-B is not passed.**
- **The check stopped 4 wrong patches and let 2 through.** It rejected candidates in 4 bugs (10 in the checked arm, 13
  in checked_learned). In dataclasses-json-5 and -8 it rejected the wrong patch and nothing else was accepted. In
  dataclasses-json-4 the search went on to another wrong patch. It rejected no correct patch.
- **The oracle against the reading:** it called mistletoe-2 and -5 `restored` (correct), dataclasses-json-8 `wrong`
  (wrong) and dataclasses-json-5 `equivalent` (wrong by the probe). It judged the same markdown-it-py-1 patch
  `equivalent` in one arm and `wrong` in the others, and could not judge dataclasses-json-4 (`unknown`).
