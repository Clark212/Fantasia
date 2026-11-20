# v0.3 Event–Program Bridge

Design input: the supplied Event–Program Network proposal plus the existing ASM seismic/event architecture.

## Implemented in alpha.1

```text
SemanticEvent
    ↓
persistent world state             ✅
    ↓
seismic/local dependency scheduler ✅
    ↓
selected local mechanism           substrate only
```

Alpha.1 does **not** yet implement the lower half:

```text
selected local mechanism
   ↙                   ↘
recurrent predictor   validated bounded program
   ↘                   ↙
predicted state change + uncertainty
    ↓
bounded planner / action
    ↓
observed result
    ↓
prediction error
```

## Planned sequence

1. Train local recurrent mechanisms on explicit state/action/change examples.
2. Establish held-out prediction baselines and failure behavior.
3. Test selective scheduling against dense mechanism evaluation.
4. Only then search for compact guarded programs that can replace a recurrent path.
5. Promote a program only when validation quality stays within tolerance and discovery/validation/execution cost amortizes.
6. Revoke or narrow programs when prediction error rises.

## Research rule

No temporal edge in alpha.1 is causal. Program compilation and planning should not be built on correlations mislabeled as mechanisms.
