# DEV15 real bugs: every accepted patch read against the developer's fix (pre-registered G2)

9 of 83 bugs ended `resolved`. For each, I read ASM's diff and the developer's diff (both stored in the raw records,
`realbugs_eval_a.jsonl` / `realbugs_eval_b.jsonl`). Where the reading alone did not settle it, I ran a written probe in
the bug's own Python 3.8 virtualenv on the developer's fixed tree and on ASM's patched tree. Probes are reproduced below.
The developer's fixed test files pass on all 9 patched trees.

| bug | ASM's edit (family) | label | oracle | **verdict** | basis |
|---|---|---|---|---|---|
| thefuck-9 | `try/except IndexError: pass` around the second `pop` (try_except) | high | restored | **correct** | identical to the developer's fix |
| youtube-dl-28 | `try/except ValueError: pass` around `compat_chr(int(numstr, base))` (try_except) | high | restored | **correct** | identical to the developer's fix |
| youtube-dl-29 | `if upload_date:` before `return compat_str(upload_date)` (guard_stmt) | high | equivalent | **correct** | developer: `if upload_date is not None:`. They differ only for `upload_date == ''`, which this function cannot produce (it is `None` or an 8-digit `strftime('%Y%m%d')`). Probe: identical on `''`, `'nonsense'`, `'Dec 14, 2012'`, `'1968-12-10'` |
| thefuck-22 | `if commands:` around the re-sort in `_realise` (guard_stmt) | low | unknown | **correct (by reasoning)** | developer: `if self._cached:`. If `_cached` is empty, the generator is already exhausted, so `commands` is empty and ASM also skips. If `_cached` is non-empty and `commands` empty, the developer's branch sets `_cached = [_cached[0]]`, which equals the current one-element `_cached`. Otherwise both run the same code. The oracle could not replay `_realise` |
| thefuck-15 | `"Did you forget to 'git add'?" in` -> `not in` (single_site) | medium | wrong_generated | **wrong** | developer removed the clause. On stderr containing both messages the developer's `match` is True, ASM's False (DEV14 audit; the DEV15 oracle now finds this input itself) |
| thefuck-21 | `try/except IndexError: pass` around the whole `return` (try_except) | high | wrong | **wrong (minor)** | for a one-word script the developer returns `False`, ASM returns `None` (probe below). Callers that test truthiness behave the same; the oracle compares values, so `wrong` stands under the pre-registered definition |
| tqdm-6 | negated `hasattr(self.iterable, "__len__")` (single_site) | low | unknown | **wrong** | `len(tqdm([1,2,3], total=10, disable=True))`: fixed 3, patched AttributeError; `len(tqdm([1,2,3], total=10))`: fixed 3, patched 10 |
| tqdm-8 | `r_bar` -> `r_bar_user` (name) | high | **equivalent (oracle error)** | **wrong** | the developer changed BOTH `l_bar` -> `l_bar_user` and `r_bar` -> `r_bar_user`; ASM changed one. With `bar_format='L{n}\|{bar}\|R{total}'`: fixed `'L3\|...\|R10'`, patched `' 30%\|...\|R10'` (user's left format lost). The tests only check the right side; no recorded or generated input had a custom left part |
| youtube-dl-11 | `try/except TypeError: pass` around `re.sub(...)` (try_except) | high | **equivalent (oracle error)** | **wrong** | developer: non-strings are returned unchanged. `str_to_int(5.5)`: fixed 5.5, patched 5 |

## Totals
- **4 correct** (2 identical to the developer's fix, 2 behaviourally equivalent), **5 wrong** (one of them only in
  `None` vs `False`).
- DEV14 on the same 83 bugs: 2 accepted, 0 correct.
- By label: high 6 (3 correct, 3 wrong), medium 1 (wrong), low 2 (1 correct, 1 wrong). **Labels do not separate correct
  from wrong patches here.**
- **The oracle was wrong twice** (tqdm-8 and youtube-dl-11 called `equivalent`) and could not judge two (thefuck-22,
  tqdm-6). Of its 3 `equivalent` calls, 2 were wrong; its `wrong` calls (thefuck-15, thefuck-21) were right. An
  `equivalent` verdict on a real bug is not evidence of correctness without a person reading the diff.

## Probes (run in each bug's virtualenv, `python -I -W ignore`, cwd = the tree)
```
tqdm-8      tqdm.format_meter(3, 10, 1.0, ncols=40, bar_format='L{n}|{bar}|R{total}')
            fixed 'L3|█████████▉                       |R10'   patched ' 30%|█████████▎                     |R10'
youtube-dl-11  [str_to_int(5.5), str_to_int(7), str_to_int('1,000')]
            fixed [5.5, 7, 1000]                              patched [5, 7, 1000]
youtube-dl-29  [unified_strdate(x) for x in ['', 'nonsense', 'Dec 14, 2012', '1968-12-10']]
            fixed [None, None, '20121214', '19681210']        patched identical
thefuck-21  match(Command('git', '', ''))                     fixed False   patched None
tqdm-6      len(tqdm([1,2,3], total=10, disable=True)); len(tqdm([1,2,3], total=10))
            fixed 3; 3                                        patched AttributeError; 10
```
