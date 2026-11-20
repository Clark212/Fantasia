"""DEV14 input generation beyond the test suite.

DEV13's oracle and verification replayed the inputs the tests use plus small perturbations of them. A change that no
test input reaches was invisible to both (139 of 158 test-passing decoys showed "no observable difference"). This module
generates additional inputs from three sources:
1. CONSTANT MINING: numbers and strings that appear in the function body (comparison boundaries, literals), each with
   its neighbours (c-1, c, c+1), because boundary edits (`>` vs `>=`, `10` vs `9`) only show at the boundary.
2. TYPE-DIRECTED VALUES for each recorded argument's type: boundary integers, signed/fractional floats, empty/short/
   unicode/whitespace strings, empty/singleton/longer/sorted/duplicated sequences, dicts with keys dropped or added.
3. COMBINATIONS: two arguments varied at once (single-argument perturbation cannot reach interaction effects), and
   literal attributes of recorded objects set to generated values.
Every generated input is tagged `origin="generated"` so callers can separate evidence from in-distribution inputs
(recorded, perturbed) from evidence on inputs no test ever used.

Honest scope: generated inputs may lie outside a function's intended domain; a difference found only there is weaker
evidence than one on a recorded input (it may be a case no caller ever produces). Values are kept small (|int| <= 1000,
sequences <= 8 items, strings <= 20 chars) so generated calls stay fast.
"""
from __future__ import annotations

import ast
import random

INT_BOUNDARY = [0, 1, -1, 2, -2, 3, 10, -10, 100, 1000]
FLOAT_VALUES = [0.0, -0.0, 0.5, -0.5, 1.5, -2.25, 1e-9, 1000.0]
STR_VALUES = ["", " ", "a", "A", "ab", "aB c", "0", "-1", "üß", "a\nb", "x" * 20]


def mine_constants(fn: ast.AST) -> dict:
    """Numbers and strings that appear in a function body, each number with its neighbours."""
    nums, strs = set(), set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Constant) and not isinstance(n.value, bool):
            if isinstance(n.value, int) and abs(n.value) <= 10 ** 6:
                nums.update({n.value - 1, n.value, n.value + 1})
            elif isinstance(n.value, float):
                nums.update({n.value, n.value + 1.0, n.value - 1.0})
            elif isinstance(n.value, str) and len(n.value) <= 20:
                strs.add(n.value)
    return {"nums": sorted(nums, key=lambda v: (abs(v), v)), "strs": sorted(strs)}


def _seq_variants(v, rng, mined):
    t = type(v)
    items = list(v)
    out = [t(), t(items[:1]), t(items + items[:1]), t(sorted(items, key=repr)), t(items[::-1])]
    if items:
        for x in typed_values(items[0], mined, rng)[:3]:
            out.append(t([x] + items[1:]))
    return [x for x in out if len(x) <= 8]


def typed_values(v, mined: dict, rng: random.Random) -> list:
    """Generated values of the same type as v (excluding v itself), deterministic for a given rng state."""
    if isinstance(v, bool):
        out = [not v]
    elif isinstance(v, int):
        out = INT_BOUNDARY + [x for x in mined["nums"] if isinstance(x, int) and abs(x) <= 1000] + [-v, v + 7]
    elif isinstance(v, float):
        out = FLOAT_VALUES + [float(x) for x in mined["nums"] if abs(x) <= 1000] + [-v]
    elif isinstance(v, str):
        out = STR_VALUES + list(mined["strs"]) + [v.upper(), v * 2 if len(v) <= 10 else v, v.strip()]
    elif isinstance(v, (list, tuple)):
        out = _seq_variants(v, rng, mined)
    elif isinstance(v, dict):
        keys = list(v)
        out = [{}] + [{k: x for k, x in v.items() if k != drop} for drop in keys[:3]]
        if keys:
            extra = dict(v)
            extra["__asm_extra__"] = v[keys[0]]
            out.append(extra)
    elif v is None:
        out = [0, "", []]
    else:
        out = []
    seen, uniq = set(), []
    for x in out:
        r = repr(x)
        if x != v and r not in seen and len(r) <= 200:
            seen.add(r)
            uniq.append(x)
    return uniq


def generate_sets(views: list, mined: dict, budget: int, seed: int) -> list:
    """For one recorded argument tuple (its literal 'views'), return up to `budget` lists of [idx, attr, literal]
    assignments: single-argument replacements first (round-robin over arguments), then two-argument combinations."""
    rng = random.Random(seed)
    slots = []  # (idx, attr, base value)
    for idx, v in enumerate(views):
        if v["k"] == "lit":
            try:
                slots.append((idx, None, ast.literal_eval(v["r"])))
            except (ValueError, SyntaxError):
                pass
        elif v["k"] == "obj":
            for attr, r in v["attrs"].items():
                try:
                    slots.append((idx, attr, ast.literal_eval(r)))
                except (ValueError, SyntaxError):
                    pass
    per_slot = [[(idx, attr, repr(x)) for x in typed_values(base, mined, rng)] for idx, attr, base in slots]
    singles = []
    for depth in range(max((len(p) for p in per_slot), default=0)):  # round-robin: every argument gets a share
        for p in per_slot:
            if depth < len(p):
                singles.append([list(p[depth])])
    out = singles[: budget * 2 // 3] if len(per_slot) > 1 else singles[:budget]
    if len(per_slot) > 1:
        pairs = []
        for i in range(len(per_slot)):
            for j in range(i + 1, len(per_slot)):
                if per_slot[i] and per_slot[j]:
                    for _ in range(4):
                        pairs.append([list(rng.choice(per_slot[i])), list(rng.choice(per_slot[j]))])
        rng.shuffle(pairs)
        out += pairs[: budget - len(out)]
    seen, uniq = set(), []
    for s in out:
        key = repr(s)
        if key not in seen:
            seen.add(key)
            uniq.append(s)
    return uniq[:budget]


def find_function_node(source: str, line: int):
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.lineno == line:
            return n
    return None
