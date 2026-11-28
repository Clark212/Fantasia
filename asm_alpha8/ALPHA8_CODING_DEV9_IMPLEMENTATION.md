# ASM Alpha 8 Coding DEV9 — Deep Code Understanding (implementation report)

Status: **experimental; NOT promoted**. Parent: `ASM_alpha8_DEV8_COMBINED` (preserved unchanged).

## Added
`asm/coding/understanding.py`, entry point `CodingAgent.understand(root)` / `CodeUnderstanding().analyze(root)`. Static only; never imports or executes project code.

- **Control flow**: per-function CFG (if/while/for/try/except/else/finally/with/match/break/continue/return/raise, `while True`), unreachable-code detection, return/raise counts, McCabe complexity.
- **Data flow**: reaching definitions, use-def chains (`use_def(qname)`), possibly/definitely-unbound uses, dead and overwritten stores. Closures, `nonlocal`/`global`, late binding and `locals()/eval/exec` are handled conservatively.
- **Call graph**: resolved edges for plain names, nested functions, `self.m()`, inherited methods, `super()`, constructors (-> `__init__`), module-member calls, import aliases, relative imports, and single-assignment constructor receivers. Everything else is kept as an edge with an explicit **reason** (`dynamic_receiver`, `external`, `builtin`, `local_callable`, `external_base`, `unknown_name`, ...). Queries: `callers/callees` (transitive), `unreferenced_functions` (candidates only), recursion groups.
- **Classes**: bases (resolved/external), methods, attribute readers/writers per method, "read but never written" candidates (suppressed when an external base makes it unknowable).
- **Modules**: dependency edges, `impacted_modules(path)` (blast radius), **import-time cycles vs lazy cycles** (function-level or `TYPE_CHECKING` imports).
- Safety: symlinks skipped, file-size/file-count/CFG-size limits reported as diagnostics, syntax/encoding errors recorded without stopping, deterministic output, repository fingerprint unchanged.

## Validation actually run
- 30 new tests with hand-built ground truth; `test_alpha8_*`: **200 passed**, 8 subtests; `compileall` clean.
- Historical groups unchanged vs pristine DEV7: v01 72 passed; v02 13 failed, v03 3 collection errors, v04 6 failed (identical counts on DEV7; PyTorch absent in the test environment).
- **Mutation check**: 10 deliberate defects injected; all 10 caught.
- **Independent oracles on the 246-module ASM repo itself** (~4 s): complexity vs `radon` agreed on 2,458/2,458 functions without closures (note: counting rules were implemented to match radon's, so this verifies the implementation, not the definition); `pyflakes` F841 unused-local findings: 7/7 caught, plus a few stricter findings of mine.
- **Hand review of findings against source** found and fixed 4 real defects in my own analyzer: `nonlocal` false dead-store, double-modelled `finally` flagging reachable lines unreachable, bare names in methods resolving to sibling methods, and package-parent import edges creating noise cycles. Each has a regression test.

## Limits — read before relying on this
- Python only; structural, **not semantic** (what code *means* is DEV10).
- On ASM, only ~40% of in-repo call sites resolve; most of the rest are untyped receivers (`x.method()` where x's type is unknown) or calls into classes with external bases. Treat the call graph as a **lower bound** (precise but incomplete), never as complete impact analysis.
- CFG approximations: `return` inside `try` skips the `finally` copy; exception edges over-approximate; context managers that swallow exceptions are ignored.
- Data flow is intraprocedural over local names only; attributes, subscripts, globals, module/class bodies and cross-function flow are not tracked. Dead-store/unbound findings are **candidates** (e.g. a "maybe unbound" may be prevented by a runtime invariant the analyzer cannot see); I did not verify these invariants for the 6 such findings reported on ASM.
- Precision/recall of dead-store, unbound and call-edge findings has **not been measured systematically** beyond oracle comparison and a ~10-finding manual spot check, all on ASM's own code.
- No claim of improvement over DEV8 on any task; no consciousness-related claim — all behaviour is deterministic AST processing.

## Promotion gate for DEV9
(1) Run on at least 3 foreign repositories (not ASM); (2) measure call-graph **recall** against dynamic traces (run each repo's tests under `sys.setprofile`, compare observed vs static edges); (3) hand-label a random sample (>=50) of unbound/dead-store/unreachable findings for precision; (4) profile time and memory on a repo ~10x larger; (5) demonstrate downstream value (e.g. DEV13 debugging / DEV15 multi-file change planning using `impacted_modules` and `callers`) before promotion.
