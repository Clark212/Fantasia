# DEV32 fresh real bugs: every accepted patch read against the developer's fix (pre-registered G32-A and G32-B)

14 of the 143 valid fresh bugs ended `resolved` in at least one arm. The control resolved 10, and the learned and
guarded arms each resolved 14: the control's 10, with byte-identical patches, plus 4 more. The guarded arm accepted
exactly the learned arm's 14 patches, byte for byte. The time control (`control_long`, 300 s) ran on the 4 bugs only the
learned arms resolved and resolved none (`dev32_time_control.jsonl`: astroid-4 unresolved; autoflake-2, marko-4 and
sqlglot-14 time_budget).

I read each patch against the developer's diff; both are stored in the raw records. Probes then ran on the developer's
fixed tree and on ASM's patched tree, in the bug's own Python 3.11 virtualenv inside ASM's sandbox
(`benchmarks/dev32_probes.py` → `probes.jsonl`). The second round (`SECOND`) covers the four patches the first probe
did not tell apart. **Correct** is as DEV15 defines it: the same behaviour as the developer's fix on every input a probe
or the reading finds, so a patch that fixes one of two cases, or changes another valid input, is wrong (DEV15's tqdm-8
and thefuck-21).

## Resolved only with learned knowledge (learned and guarded arms, identical patches)
| bug | ASM's edit (learned knowledge) | oracle | **verdict** | basis |
|---|---|---|---|---|
| astroid-4 | `node_classes.Const("")` → `Const(b'')` in `UnicodeDecodeErrorInstanceModel.attr_object` (procedure: string content `''` → `b''`) | restored | **correct** | identical to the developer's fix (`b""`) |
| sqlglot-14 | `expression.text("unit")` → `expression.text('uni')` in DuckDB's `interval_sql` (procedure: string content) | unknown | **correct** | the developer deleted DuckDB's `interval_sql` override, so the parent's runs. `text('uni')` is always `''`, so the override never multiplies and always returns `super().interval_sql(expression)`: the same behaviour by another route, and an odd edit. Probe: `INTERVAL '1' WEEK`, `'2' QUARTER`, `'3' DAY` and `+ INTERVAL 1 MONTH`, read as DuckDB and as Postgres, give the same DuckDB SQL on both trees |
| autoflake-2 | `startswith(("import", "from"))` → `startswith(('import ', "from"))` in `extract_package_name` (shape via extend) | wrong | **wrong** | the developer returns `None` when the line has no second word. ASM's patch only stops a bare `import` from matching. Probe: `from` alone: fixed `None`, patched `IndexError`; `import\tos`: fixed `'os'`, patched `None`; `imported = 1`: fixed `'='`, patched `None` |
| marko-4 | `isinstance(state.children[-1], BlankLine)` → `AssertionError` (twice) in the list-item parser (learned step) | unknown | **wrong** | the developer joins a loose list's items with blank lines in the Markdown renderer. ASM's patch stops the parser from ever removing a list item's last blank line: the content came from the failing test's error type. Probe: `1. a\n\n   b\n2. c\n` renders back as `…\n\n2. c` when fixed and `…\n2. c` when patched |

The guard did not stop either wrong patch: neither writes a whole string of the failing tests into the code
(`'import '` is not one; `AssertionError` is a name, not a string). In autoflake-2 it dropped 10 other candidates first.

## Resolved in all three arms (byte-identical patches)
| bug | ASM's edit (family) | oracle | **verdict** | basis |
|---|---|---|---|---|
| astroid-1 | `value.value` → `getattr(value, 'value', None)` in `_infer_str_format_call` (getattr) | unknown | **correct** | the developer returns `Uninferable` when the receiver cannot be inferred. ASM's `None` template reaches `format_template.format(...)`, whose `AttributeError` the function already turns into `Uninferable`. Probe: `unknown_name.format(1)`, `"{}".format(1)` and `str(1).format(2)` infer the same on both trees |
| rich-11 | `(len(text) - 1)` → `(len(text) - 2)` in `Segment._split_cells` (const) | unknown | **correct** | the developer lowers the first guess of the split position by one, clamped at 0. ASM's guess is lower too, and the loop after it walks forward to the exact cut. Probe: all 1,764 splits (every mix of 1-6 narrow and wide characters, cuts 0-13) are identical on both trees |
| markdownify-4 | `try/except TypeError: pass` around `convert_fn(...)` (try_except) | equivalent | **wrong** | the developer renames `convert_hn` to `_convert_hn` so an `<hn>` tag finds no converter. ASM swallows every `TypeError` of every converter. Same output on `<hn>` and the heading tags, but a converter with the wrong signature, which raises `TypeError` when fixed, is silently skipped when patched |
| inflect-2 | `words.lowered[-1] == "s"` → `!= "s"` in `_sinoun` (compare) | wrong | **wrong** | the developer keeps words ending in `-ss` singular. Probe: `singular_noun('cats')`: fixed `'cat'`, patched `False`; `'cat'`: fixed `False`, patched `'ca'` |
| inflect-7 | `self._sinoun if count == 1` → `if count != 1` in `_handle_long_compounds` (compare) | wrong | **wrong** | the developer keeps a candidate when its inflection is not a string. ASM's patch swaps singular and plural. Probe: `_handle_long_compounds(Words('pair of scissors'), 2)`: fixed `'pairs of scissors'`, patched `'pair of scissors'` |
| inflect-9 | `word.lowered[-1] == "y"` → `!= "y"` in the proper-noun branch of `_plnoun` (compare) | equivalent | **wrong** | the developer tests whether the LAST word is capitalized. Probe: `plural('Kennedy')`: fixed `'Kennedys'`, patched `'Kennedies'` |
| jsonpickle-3 | `return data` → `return obj` in `RegexHandler.flatten` (name) | wrong | **wrong** | the developer stores and restores the pattern's flags. Probe: encoding `re.compile('a+', re.I)` succeeds when fixed and raises `TypeError` (Pattern is not JSON serializable) when patched |
| rich-15 | `markup is None and self._markup` → `markup is None or self._markup` in `Console.print` (bool) | unknown | **wrong** | the developer passes `markup=True` where `Prompt` prints its error. ASM's patch turns markup on for every `print` of a console made with `markup=False`, and ignores `print(..., markup=False)` on a console with markup on. Probe: `Console(markup=False).print('[bold]x[/bold]')` and `Console().print('[bold]x[/bold]', markup=False)`: fixed `'[bold]x[/bold]'`, patched `'x'` |
| soupsieve-2 | `pseudo in PSEUDO_SUPPORTED` → `not in` in `parse_pseudo_class` (compare) | unknown | **wrong** | the developer raises `SelectorSyntaxError` for every unrecognized pseudo-class. ASM's patch swaps the two errors, so known pseudo-classes used with invalid syntax now raise `NotImplementedError`. Probe: `p:nth-child`, `p:is`, `p:not`, `p:contains`, `:nth-of-type`, `p:lang`: fixed `SelectorSyntaxError`, patched `NotImplementedError` |
| soupsieve-4 | `isinstance(pattern, SoupSieve)` → `not (…)` in `compile` (negate) | unknown | **wrong** | the developer fixes how comments at the end of a selector are found. ASM's patch returns every string pattern unchanged instead of compiling it. Probe: `compile('div')` and three more: fixed compiled, patched `AttributeError`; `compile(compile('div'))` returns a `str` |

## Totals
| | control | learned | guarded | control_long |
|---|---|---|---|---|
| accepted patches | 10 | 14 | 14 (the learned arm's) | 0 of 4 |
| correct | 2 (astroid-1, rich-11) | 4 (+ astroid-4, sqlglot-14) | 4 | — |
| wrong | 8 | 10 (+ autoflake-2, marko-4) | 10 | — |
| flagged by the guard's rule | 0 | 0 | 0 | — |

- **G32-A (the guard), person-read:**
  - **A1 something to stop:** the learned arm accepted 0 flagged patches; 2 needed. **Not met.**
  - **A2 fewer wrong patches:** guarded 10 wrong, learned 10: 0 fewer; 2 needed. **Not met.**
  - **A3 no loss:** both learned-correct bugs (astroid-4, sqlglot-14) are repaired correctly by the guarded arm. Met.
  - **A4 small cost:** the rule flags 1 of 143 developer fixes (0.7%, loguru-10: `'#'`); at most 2%. Met.

  **G32-A is not passed.**
- **G32-B (DEV31's G31-A on these bugs), person-read:**
  - **B1 learned repairs:** 2 bugs correct with the learned arm alone and neither by the control nor by control_long
    (astroid-4, sqlglot-14); 2 needed. **Met** — the first time on fresh real bugs.
  - **B2 no loss:** 0 control-correct bugs lost. Met.
  - **B3 safety:** learned wrong patches 10, against the control's 8 + 1 allowed. **Not met** (autoflake-2, marko-4).
  - **B4 the clock holds:** the longest learned run took 345 s (sqlglot-14), within 360. Met.

  **G32-B is not passed.** Reported, not gated: the guarded arm meets B1, B2 and B3 the same way as the learned arm.
  On B4 its longest run took 361 s (sqlglot-12), 1 s over.
- **The oracle against the reading:** of 14 judged patches, it called 3 `restored`/`equivalent`: astroid-4
  (correct), markdownify-4 and inflect-9 (both wrong by the reading), and 4 `wrong` (autoflake-2, inflect-2, inflect-7, jsonpickle-3; all wrong by the reading). It could not judge 7
  (`unknown`), and the probes decided them.
