# Alpha 8 DEV4 — Pre-registration: structural discovery map and structural transfer (written before the benchmark was run)

Scope: how well ASM's ProcedureCortex (default configuration, guard = abstain) **discovers hidden structure** from examples (Part A), and whether its existing
**families mechanism transfers structure between tasks** (Part B), each with controls. Not measured here: real-data behaviour, cross-domain transfer, continual
learning, causal discovery, active learning through ASM's information queries (this lab never answers a `needs_information` query, so Part A coverage is a lower bound).

## Disclosure
Before pre-registering, a 6-line exploratory probe showed that with two validated donors x*x+1 and x*x+5, induce(use_families=True) found y=x*x+3 in 14 candidates while the baseline and use_families=False were unresolved after 291; that y=max(x,7) is fitted spuriously by a constant when all examples lie below 7; and that threshold rules return needs_information. Target structures and arms were chosen with that knowledge; thresholds below were set before any benchmark run.

## Part A — structural discovery map (6 new families, ground truth known)
Unary integer: `affine` a*x+b; `quad` a*x*x+b (a in +-2,+-3); `clamp` min/max(x,c); `threshold` p if x<c else q. Two integer inputs: `linear2` a*x+b*y; `product2` x*y+c.
Each rule is drawn uniformly from a declared grid. Scored queries are held-out **interior** inputs whose answer is determined by the training pool under the grid
(so a perfect learner can reach 100%). A fresh learner per task and budget; shots cycle through a shuffled pool. Learners: `grid_reference` (given the grid; validates the harness),
`memorizer` (canary), `majority`, `shuffled_grid_reference`, `asm_struct` (ASM unmodified through an adapter), `shuffled_asm_struct` (ASM trained on within-task shuffled labels).

## Part B — structural transfer (target structure y = x*x + c)
Targets: 16 in-range constants (+-1..8) and 8 out-of-range constants (+-9..12), 3 fit-point seeds each. A fresh cortex per attempt; donors are validated procedures installed through the
public `propose` + held-out-validation lifecycle, **never using the target constant** (checked). Arms: `none`; `one_relevant` (one x*x+c' donor); `relevant` (two); `unrelated` (two affine and two max(x,c) donors);
`mixed` (relevant + unrelated); `relevant_shuffled` (relevant donors, target labels shuffled). Success = after the 3-example induction and 8-example validation, the active procedure answers every held-out interior query correctly.

## Criteria (machine-readable copy: asm/learning/structlab_prereg.py; a test asserts they are identical)
```json
{
  "part_a": {
    "asm_claims": {
      "A1_never_wrong_on_determined_queries": {
        "max_wrong_rate": 0.02
      },
      "A2_shuffled_labels_never_answered_wrongly": {
        "learner": "shuffled_asm_struct",
        "max_wrong_rate": 0.02
      },
      "A3_coverage": {
        "min_correct_rate_at_kmax": 0.8,
        "min_families": 3
      },
      "learner": "asm_struct"
    },
    "families": [
      "affine",
      "quad",
      "clamp",
      "threshold",
      "linear2",
      "product2"
    ],
    "ks": [
      8,
      16,
      24
    ],
    "tasks_per_family": 40,
    "validity": {
      "H1_reference_safe": {
        "learner": "grid_reference",
        "max_wrong_rate": 0.0
      },
      "H2_reference_learns": {
        "learner": "grid_reference",
        "min_correct_rate_at_kmax": 0.95
      },
      "H3_memorizer_canary": {
        "learner": "memorizer",
        "max_correct_rate": 0.0
      },
      "H4_shuffled_control_collapses": {
        "learner": "shuffled_grid_reference",
        "max_correct_rate_at_kmax": 0.25
      },
      "H5_majority_floor_is_beaten": {
        "learner": "grid_reference",
        "min_gap_over_majority": 0.15
      }
    }
  },
  "part_b": {
    "arms": [
      "none",
      "one_relevant",
      "relevant",
      "unrelated",
      "mixed",
      "relevant_shuffled"
    ],
    "claims": {
      "T1_capability_gain": {
        "min_success_gap_relevant_vs_none": 0.5
      },
      "T2_one_donor_is_not_enough": {
        "max_success_gain_over_none": 0.1
      },
      "T3_no_negative_transfer": {
        "arm": "unrelated",
        "max_cost_ratio": 1.1,
        "max_success_drop": 0.05
      },
      "T3b_no_interference": {
        "arm": "mixed",
        "max_success_drop_vs_relevant": 0.1
      },
      "T4_safe": {
        "max_wrong_active_rate": 0.02
      },
      "T5_parameter_range_limit": {
        "max_success_out_of_range": 0.1
      }
    },
    "fit_seeds": 3,
    "in_range_constants": [
      -8,
      -7,
      -6,
      -5,
      -4,
      -3,
      -2,
      -1,
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      8
    ],
    "out_of_range_constants": [
      -12,
      -11,
      -10,
      -9,
      9,
      10,
      11,
      12
    ],
    "target_structure": "y = x*x + c",
    "validity": {
      "V1_donors_never_contain_the_target_constant": true,
      "V2_shuffled_labels_do_not_succeed": {
        "arm": "relevant_shuffled",
        "max_success": 0.05
      }
    }
  },
  "probe_disclosure": "Before pre-registering, a 6-line exploratory probe showed that with two validated donors x*x+1 and x*x+5, induce(use_families=True) found y=x*x+3 in 14 candidates while the baseline and use_families=False were unresolved after 291; that y=max(x,7) is fitted spuriously by a constant when all examples lie below 7; and that threshold rules return needs_information. Target structures and arms were chosen with that knowledge; thresholds below were set before any benchmark run.",
  "seed": 20261102,
  "version": "DEV4-prereg-1"
}
```
H1-H5 and V1-V2 validate the harness; if any fails, the corresponding ASM results may not be interpreted. A1-A3 and T1-T5 are the ASM claims. T2 and T5 are falsifiable predictions about the mechanism
(it needs two donors; its parameter range is limited). All thresholds are the author's judgment; author and runner are the same party.

## Rules
1. Thresholds are fixed by the SHA-256 below; a later change must be a new labelled version with the original verdicts retained. 2. Results are reported whether they pass or fail.
3. A pass means "meets this bar in these toy families", not general structural discovery or transfer.

Pre-registration SHA-256: `2a308eca150df8928740af5ebd336e4612e96264f7455dcab1af28ac138486f6`
