# DEV34 fresh real bugs: every accepted patch read against the developer's fix (pre-registered G34-A)

1 of the 59 valid fresh bugs ended `resolved`, in both arms, with the same patch. No bug was resolved by
checked_learned alone, so the time control (`checked_long`) ran on no bug.

| bug | arms | ASM's edit (family) | oracle | **verdict** | basis |
|---|---|---|---|---|---|
| pycparser-5 | checked, checked_learned | `assert len(self._scope_stack) > 1` → `>= 1` in `CParser._pop_scope` (compare) | wrong | **wrong (minor)** | the developer raises `ParseError("Unmatched '}'")` when the global scope would be popped. ASM's patch lets the assert pass and pops the global scope, so the input fails later with the parser's generic syntax error. Probe (`probes.jsonl`): on `int f() { return 1; } }`, `}`, `int x; }}` and two more, fixed `ParseError: Unmatched '}'`, patched `ParseError: :1:23: before: }` and the like. Both raise `ParseError`; the message and the parser's state differ, so `wrong` stands under DEV15's definition (as DEV15's thefuck-21) |

## Totals
| | checked | checked_learned | checked_long |
|---|---|---|---|
| accepted patches | 1 | 1 (the same) | — (no bug qualified) |
| correct | 0 | 0 | — |
| wrong | 1 | 1 | — |

- **G34-A, person-read:**
  - **A1 learned repairs:** 0 bugs correct with checked_learned alone; 2 needed. **Not met.**
  - **A2 no loss:** no checked-correct bug. Met.
  - **A3 safety:** checked_learned 1 wrong, against checked's 1 + 1 allowed. Met.
  - **A4 the clock holds:** the longest checked_learned run took 304 s; limit 360. Met (DEV33: 478 s).

  **G34-A is not passed.**
