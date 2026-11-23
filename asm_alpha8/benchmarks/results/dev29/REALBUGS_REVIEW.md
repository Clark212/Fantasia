# DEV29 real bugs: every accepted patch read against the developer's fix (pre-registered G29-A)

10 bugs ended `resolved` in at least one arm: 9 in both arms and 1 in the learned arm only. For each accepted patch I
read ASM's diff against the developer's diff; both are stored in the raw records (`dev29_evaluate_{0,1,2}of3.jsonl`).

Nine of the patches are byte-identical in the two arms and identical to DEV15's patch for the same bug. The developer
patches are also identical to DEV15's records, on all 166 records. So each pair read here is exactly the pair DEV15
read (`benchmarks/results/dev15/REALBUGS_REVIEW.md`). I read them again rather than copying DEV15's verdicts.

The probes were run again in this run's rebuilt Python 3.8 environments, this time inside ASM's sandbox
(`benchmarks/dev29_probes.py` → `probes.jsonl`). Each runs on the developer's fixed tree and on ASM's patched tree.
thefuck-22, judged by reasoning in DEV15, now has a probe as well. The developer's fixed test files pass on all 10
patched trees.

| bug | arms | ASM's edit (family) | oracle: control / learned | **verdict** | basis |
|---|---|---|---|---|---|
| thefuck-19 | **learned only** | `'push --force'` → `'push --force-with-lease'` in `get_new_command` (a learned shape; its content is extended from the failing test's expected string `'git push --force-with-lease'`) | — / restored | **correct** | identical to the developer's fix: the patched file is byte-identical to the fixed file |
| thefuck-9 | both | `try/except IndexError: pass` around the second `pop` (try_except) | restored / restored | **correct** | identical to the developer's fix |
| youtube-dl-28 | both | `try/except ValueError: pass` around `compat_chr(int(numstr, base))` (try_except) | restored / restored | **correct** | identical to the developer's fix |
| youtube-dl-29 | both | `if upload_date:` before `return compat_str(upload_date)` (guard_stmt) | equivalent / equivalent | **correct** | the developer writes `if upload_date is not None:`. They differ only for `upload_date == ''`, which the function cannot produce (it is `None` or an 8-digit date). Probe: identical |
| thefuck-22 | both | `if commands:` around the re-sort in `_realise` (guard_stmt) | unknown / unknown | **correct** | the developer writes `if self._cached:`. See the reasoning below; probe: identical on 10 cases |
| thefuck-15 | both | `"Did you forget to 'git add'?" in` → `not in` (single_site) | wrong_generated / wrong_generated | **wrong** | the developer removed the clause. On the oracle's own input, stderr containing both messages, the fixed `match` gives True and the patched one False |
| thefuck-21 | both | `try/except IndexError: pass` around the whole `return` (try_except) | wrong / wrong | **wrong (minor)** | for a one-word script the developer returns `False` and ASM returns `None`. Callers that test truthiness behave the same; the values differ |
| tqdm-6 | both | `hasattr(self.iterable, "__len__")` negated (single_site) | unknown / unknown | **wrong** | `len(tqdm([1,2,3], total=10, disable=True))`: fixed 3, patched AttributeError; `len(tqdm([1,2,3], total=10))`: fixed 3, patched 10 |
| tqdm-8 | both | `r_bar` → `r_bar_user` (name) | **equivalent** / wrong | **wrong** | the developer changed both `l_bar` → `l_bar_user` and `r_bar` → `r_bar_user`; ASM changed one. With `bar_format='L{n}\|{bar}\|R{total}'` the user's left part is lost. The oracle judged the identical patch differently in the two arms |
| youtube-dl-11 | both | `try/except TypeError: pass` around `re.sub(...)` (try_except) | **equivalent** / **equivalent** | **wrong** | the developer returns non-strings unchanged. `str_to_int(5.5)`: fixed 5.5, patched 5 |

## thefuck-22: why the guard is equivalent
`_cached` holds exactly one element or none when `_realise` first runs (`_realise_first`), and nothing changes it
before. Three cases cover every run:
- **`_cached` is empty.** The generator is already exhausted, so ASM's `commands` is empty and ASM skips, as the
  developer does. Calling `_remove_duplicates` on an exhausted generator evaluates nothing, so it cannot fail.
- **`_cached` holds one element and `commands` is empty.** The developer sets `_cached = [_cached[0]]`, the same list,
  and ASM skips.
- **Otherwise** both run the same code on the same `commands`.

The probe tries generators of length 0, 1, 2 (with a duplicate script), 2 and 4, each read with and without `s[0]`
before realising. It gives identical results on both trees.

## Totals
| | control | learned |
|---|---|---|
| accepted patches | 9 | 10 |
| **correct** | 4 (thefuck-9, youtube-dl-28, youtube-dl-29, thefuck-22) | **5** (the same 4, plus thefuck-19) |
| wrong | 5 (thefuck-15, thefuck-21, tqdm-6, tqdm-8, youtube-dl-11) | 5 (the same) |

- **G29-A, person-read:**
  - C1 needs at least 2 bugs correct only with the learned arm: 1 (thefuck-19), **not met**;
  - C2 allows at most 1 control-correct bug the learned arm loses: 0, met;
  - C3 allows the learned arm at most the control's wrong patches + 1: 5 against 5, met.
  - **G29-A is not passed.**
- **The oracle against the reading:**
  - its `equivalent` was wrong 3 times: tqdm-8 (control) and youtube-dl-11 in both arms;
  - it was right once (youtube-dl-29);
  - on the identical tqdm-8 patch it said `equivalent` in one arm and `wrong` in the other.

  As in DEV15, an `equivalent` verdict on a real bug is not evidence of correctness without a person's reading.

## Probes (`probes.jsonl`; each bug's virtualenv, inside `run_python_worker`, warnings ignored)
```
tqdm-8         tqdm.format_meter(3, 10, 1.0, ncols=40, bar_format='L{n}|{bar}|R{total}')
               fixed 'L3|█████████▉                       |R10'   patched ' 30%|█████████▎                     |R10'
youtube-dl-11  [str_to_int(5.5), str_to_int(7), str_to_int('1,000')]
               fixed [5.5, 7, 1000]                              patched [5, 7, 1000]
youtube-dl-29  [unified_strdate(x) for x in ['', 'nonsense', 'Dec 14, 2012', '1968-12-10']]
               fixed [None, None, '20121214', '19681210']        patched identical
thefuck-21     match(Command('git', '', ''))                     fixed False   patched None
thefuck-15     match(Command('git submodule update unknown', '', "Did you forget to 'git add'? did not match any file(s) known to git."))
               fixed True                                        patched False
tqdm-6         [len(tqdm([1,2,3], total=10, disable=True)), len(tqdm([1,2,3], total=10))]
               fixed [3, 3]                                      patched ['AttributeError', 10]
thefuck-22     bool, len and items of SortedCorrectedCommandsSequence over 5 generators, with and without s[0] first
               fixed and patched identical on all 10 cases
```
