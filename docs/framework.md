# RAF: Rubric Auto-generation Framework

**RAF** turns a user query into a case-level, auditable evaluation rubric: an AND–OR tree of binary leaf criteria that separates *task completion* from *execution quality*. Rubric quality is not assumed — it is verified against human preference and iteratively repaired until the rubric demonstrably agrees with human judgements.

This document describes the framework as implemented in [`raf/`](../raf/). For the platform's commands and UI, see [RAF README](../raf/README.md); for field-level schemas, see [Data format](data_format.md).

## 1. The RAF pipeline

RAF couples LLM-based generation with quantitative alignment verification in five steps. Steps 2–5 form a loop that only terminates on verified alignment.

| Step | What happens | Implementation in `raf/` |
|---|---|---|
| 1. Rubric generation | An LLM produces an initial AND–OR rubric from a designed multi-module prompt. | `rubric/prompt_modules.py` + `generate_rubric.py`; also `batch_generate.py` and the optimization workbench's round generation (`rubric/optimizer.py`). |
| 2. Expert review | A human expert inspects the rubric for major defects (missing intent coverage, unjudgeable criteria). Defects jump straight to step 5. | Per-rubric review (1–5 stars + notes, `ReviewPage`/`/api/reviews`) and per-round batch quality gate in the optimization workbench (`approved` / `rejected`, `review_round_quality`). |
| 3. Score recording | A judge or human scores a batch of trajectories under the current rubric, alongside a human-annotated preference gold standard. | Optimization workbench score sheet: one `ScoreEntry` per rubric with `gold_score` + `rater_scores` (`POST .../rounds/{n}/scores`). |
| 4. Termination | An alignment score is computed. Above the threshold the rubric is accepted and frozen; otherwise inconsistencies are attributed and forwarded to step 5. | `rubric/metrics.py` computes Pearson / Spearman / QWK / composite; `optimizer.check_stopping` decides. |
| 5. Suggestion, adoption, refinement | The LLM proposes revisions from the expert's findings or from the quantitative diagnosis; the expert audits each suggestion; the LLM refines the affected prompt modules and the loop returns to step 2. | `rubric/diagnostics.py` (RIFT) → suggestions → human selection → `rubric/refiner.py` writes a new prompt version. |

```
                 ┌────────────────────────────────────────────────┐
                 │                                                │
   query ──▶ 1 generate ──▶ 2 expert review ──▶ 3 score recording ──▶ 4 termination
                 ▲                │                     │                   │
                 │                │ defects             │ misalignment      │ aligned
                 │                ▼                     ▼                   ▼
                 └── 5 refine ◀── suggestion / adoption / refinement   accept rubric
```

Every revision is traceable: a suggestion records the prompt module it targets and the problem it fixes, and the new prompt version records its `parent_version` and change description. The platform persists these links across prompt versions, optimization runs and rounds.

## 2. AND–OR rubric structure

A rubric contains two independent trees:

| Tree | Purpose | Aggregation |
|---|---|---|
| `completion_rubric` | Did the agent achieve the user's core goal(s)? "What" was done. | Boolean, all-pass. No weights. |
| `quality_rubric` | How well was it done — the key execution steps and deliverables. | Continuous 0–1, weighted by top-level item importance × difficulty. |

### Node types

| Node | Fields | Semantics |
|---|---|---|
| `leaf` | `id`, `type: "leaf"`, `name`, `combinator: "and"`, `children: []`, `tags: [capability…]` | One atomic, objectively judgeable binary check. `tags` name the capabilities the check exercises. |
| `group` | `id`, `type: "group"`, `name`, `combinator: "and" \| "or"`, `children: [...]`, `tags: []` | Combines child nodes. `and` = all children must pass; `or` = any child may pass (alternative achievement paths). |

Quality top-level entries are `{"weight": W, "node": <RubricNode>}`; valid weights are `{1, 2, 3, 4, 6}` (importance 1/2/3 × difficulty 1/2). Completion top-level entries carry no weight.

### Why AND and OR

- **AND** aggregates several conditions that must hold for *the same* goal/entity/dimension (e.g. "detected the conflict" **and** "proposed an adjusted time").
- **OR** encodes genuinely alternative achievement paths, e.g. a conditional branch in the user request ("if there is a conflict, adjust it; otherwise create the reminder"). Only the applicable branch is expected in a given trajectory, so OR collapses onto that branch at evaluation time.

This design is what makes a wide but reliable rubric possible: fine-grained leaves give discrimination, while AND/OR keeps the tree judgeable and lets each trajectory be evaluated on the path it actually took.

## 3. Scoring

### Completion (binary, all-pass)

Completion is a hard gate: every top-level completion item must pass for the task to count as complete.

```
nodePassed(leaf)  = results[leaf.id]
nodePassed(or)    = any(nodePassed(child))
nodePassed(and)   = all(nodePassed(child))
completed         = all(nodePassed(item) for item in completion_rubric)
complete_flag     = 1 if completed else 0
```

`completion.total` / `completion.passed` count leaves; `completion_rate = passed / total` is informational only.

### Quality (weighted)

Leaf scores are binary (passed → 1.0, not passed → 0.0); group aggregation depends on the quality-aggregation mode:

| Node | `paper` mode (default, paper Eq. 1) | `legacy_mean` mode (backward compatibility) |
|---|---|---|
| leaf | 1.0 / 0.0 | 1.0 / 0.0 |
| OR group | max(child scores) | max(child scores) |
| AND group | 1.0 only if **all** children score 1.0, otherwise 0.0 | mean(child scores) |
| empty group | 0.0 | 0.0 |

The rubric score is the weighted average of the top-level quality items:

```
quality_score = Σ (weight_i × nodeScore(item_i)) / Σ weight_i
```

`score` equals `quality_score`; `complete_flag` is derived from completion only. The mode is stored per scored run (`scoring_mode`) and must be kept consistent between the platform, the scorer and the report page.

### Completion vs quality boundary

The boundary is deliberately strict — a check belongs to exactly one tree:

| Question | Tree |
|---|---|
| Was the goal achieved? (what) | `completion_rubric` |
| Was the execution good? (how) | `quality_rubric` |
| Was the output file produced? | completion |
| Is the output file usable/readable/well-formatted? | quality |
| Did the agent actually act, or only promise to? | completion (checks the behavior, not the wording) |

## 4. Alignment metrics

Given a batch of scored cases, RAF compares the rubric-based quality scores with the human preference gold standard:

| Metric | Definition | Range | What it captures |
|---|---|---|---|
| Pearson `r` | Pearson correlation between gold scores and mean rater scores | [-1, 1] | Whether the rubric preserves the **ordering** of human preferences. |
| Spearman `ρ` | Spearman rank correlation over the same pairs | [-1, 1] | Ordering agreement that is robust to non-linear score spacing. |
| QWK | Quadratic weighted kappa on scores discretised into 5 levels | [-1, 1] | Whether absolute ratings **agree**, penalising large disagreements quadratically. |
| Composite (alignment score) | `0.8 × Pearson + 0.2 × QWK` | [-1, 1] | The single acceptance criterion (paper Eq. 3, α = 0.8, β = 0.2). |

Pearson dominates because model comparison ultimately rests on ranking; QWK prevents accepting a rubric that ranks correctly but rates inconsistently. The metrics module also reports per-rubric deviation (`mean rater score - gold`) so large local disagreements can be inspected. A batch needs at least two scored rubrics for the correlations to be defined; a single-rubric round can still be diagnosed with RIFT.

## 5. Termination

The paper's acceptance rule is: **accept the rubric when the alignment (composite) score is at least 0.8**; otherwise attribute the inconsistency and continue the loop.

The platform's optimization workbench applies this rule with a set of stopping checks in [`raf/rubric/optimizer.py`](../raf/rubric/optimizer.py). The target check is expressed through component thresholds (the operating point used during prompt iteration) rather than a single composite threshold:

| Check | Condition | Run status |
|---|---|---|
| Target reached | latest round has `pearson_r ≥ 0.85` **and** `qwk ≥ 0.75` | `converged` |
| Budget | 10 rounds have been used | `stopped` |
| Degradation | latest composite is more than 0.05 below the best composite so far | `stopped` |
| Convergence | at least 3 scored rounds and the last two improvements are both below 0.02 | `converged` |

Stopping is evaluated after metrics are computed; the check returns `should_stop`, the reason, the metrics and the thresholds to the caller (and updates the run status when it stops the run). A run may also be stopped manually at any point.

## 6. Prompt system

Generation prompts are assembled from **seven fixed-order modules**:

| # | Module | Content |
|---|---|---|
| 1 | `role` | Role definition: a rubric-design expert for AI-agent evaluation. |
| 2 | `structure` | Target rubric structure: completion vs quality, tree rules, AND/OR usage, top-level item and weight rules. |
| 3 | `principles` | Design principles: reliability (objective judgement, atomicity, self-containment), content validity (goal–process separation, full intent coverage), consequence validity (behavior orientation, discriminativeness, non-redundancy) and deliverable usability. |
| 4 | `examples` | Few-shot worked examples: a full query → intent analysis → completion tree → quality tree → JSON walk-through. |
| 5 | `constraints` | Pre-output self-check list: tree size, weight values, naming, tag coverage, boundary checks. |
| 6 | `capabilities` | Reference capability list and tag rules; the `{capabilities}` placeholder is replaced with the active capability list. |
| 7 | `output` | Output format: analysis reasoning followed by the strict JSON payload. |

Properties of the implementation:

- **Fixed order:** `role → structure → principles → examples → constraints → capabilities → output`; the assembled system prompt is the concatenation of the non-empty modules.
- **Versioned assets:** each prompt version is a JSON file in `raf/data/prompt_versions/` with `version`, `parent_version`, `created_at`, `change_description`, `metrics_summary` and a `modules` object. The active version is stored in `raf/data/active_prompt_version.txt`.
- **Strict structured output:** generation requests a JSON-Schema-constrained response (leaf/group tree with `tags` required, weight enum `{1,2,3,4,6}`), falling back to plain JSON mode after a structured-output failure.
- **Capability tags:** leaf nodes must be tagged with one or more names from `raf/data/capabilities.txt` (or `capabilities.en.txt`); group nodes must not carry tags.
- **Bilingual:** each version is distributed in Chinese (`<version>.json`) and English (`<version>.en.json`); English falls back to Chinese if a translation is missing. The capability list has the same fallback behaviour.

### Distributed prompt versions

| Version | Provenance | Notes |
|---|---|---|
| `v5.1` | 7-module prompt lineage; change: AND-group usage rules — AND aggregates multiple conditions of the same entity/dimension, while checks from different steps become separate top-level items. Recorded iteration metrics: Pearson 0.65 / QWK 0.57 / composite 0.634 on 50 queries and 3 raters. | **This is the version used to generate all 121 ClawBench rubrics.** |
| `v5.10` | Latest version; refined from `v5.9` by PROMPT-R, absorbing suggestions into the `structure`, `principles`, `constraints` and `output` modules. | Default active version for new generations. |

## 7. RIFT diagnostics

RIFT classifies rubric failure modes; RAF uses it as the diagnostic step of the refinement loop. Eight failure modes are implemented in [`raf/rubric/diagnostics.py`](../raf/rubric/diagnostics.py):

| Category | Failure mode | Definition |
|---|---|---|
| Reliability | Subjective | The leaf uses subjective wording without observable behavioral anchors, so raters cannot make the same judgement. |
| Reliability | Non-Atomic | One leaf bundles multiple independently judgeable conditions. |
| Reliability | Ungrounded | The check depends on external information that cannot be obtained from the trajectory, without naming the reference standard. |
| Content validity | Misaligned | The completion/quality boundary is crossed: completion checks process quality, or quality repeats goal achievement. |
| Content validity | Missing Criteria | An independent user intent (including implicit and conditional intents) has no corresponding completion check. |
| Consequence validity | Hackable | The check evaluates wording rather than actual behavior/outcome, so an agent can score by only promising to act. |
| Consequence validity | Low Signal | The check yields the same score on trajectories of different quality — no discriminative power. |
| Consequence validity | Redundant | Semantically duplicated checks across completion and quality. |

Diagnosis runs as two LLM calls: one per rubric to list findings (pattern, node, severity, evidence, suggestion), and one aggregate call that identifies systematic patterns and maps them to the prompt modules that should change. The aggregate suggestions are the input to the refinement step.

## 8. PROMPT-R refinement loop

The optimization workbench implements the following repeatable loop; each round is persisted and auditable:

| Step | Action | API |
|---|---|---|
| 1 | Start a round: record the current prompt version and generate one rubric per query in the run in the background. | `POST /api/optimize/runs/{run_id}/rounds` |
| 2 | Optional batch quality gate: a human marks the whole batch `approved` (record scores) or `rejected` (skip to diagnosis). | `POST .../rounds/{n}/quality-review` |
| 3 | Record the score sheet: gold score plus each rater's score per rubric. | `POST .../rounds/{n}/scores` |
| 4 | Compute metrics (no LLM call) and run RIFT diagnostics (LLM calls) to produce suggestions. | `POST .../rounds/{n}/metrics`, `POST .../rounds/{n}/analyze` |
| 5 | Human audits suggestions; adopted suggestions are refined module-by-module into a new prompt version. | `POST .../rounds/{n}/apply` (body: accepted suggestion ids + new version) |
| 6 | Check stopping (target / budget / degradation / convergence) and either start the next round or finish. | `GET /api/optimize/runs/{run_id}/check-stop` |

Refinement is local: each affected module is rewritten with the adopted suggestions while preserving its structure, headings, conventions and placeholders; all other modules are copied unchanged from the parent version. The new version becomes the run's current prompt version, and the next round generates rubrics with it — closing the loop until the termination check accepts the rubric.

## 9. Bilingual operation

| Asset | Chinese | English | Fallback |
|---|---|---|---|
| Prompt versions | `data/prompt_versions/<version>.json` | `data/prompt_versions/<version>.en.json` | English → Chinese |
| Capability list | `data/capabilities.txt` | `data/capabilities.en.txt` | English → Chinese |
| Generation language | `RAF_LANG=zh` (default) | `RAF_LANG=en` or `--lang en` | — |

Rubrics record the language of the prompt assets used to generate them (`language` field), so Chinese and English outputs of the same prompt version can coexist in the platform's storage.

## 10. Where things live

| Concern | Location |
|---|---|
| Prompt modules, versions, capabilities | `raf/rubric/prompt_modules.py`, `raf/data/prompt_versions/`, `raf/data/capabilities*.txt` |
| Generation | `raf/generate_rubric.py`, `raf/batch_generate.py`, `raf/rubric/client.py` |
| Rubric models and storage | `raf/rubric/models.py`, `raf/rubric/storage.py`, `raf/rubric/query_store.py` |
| Scoring | `raf/rubric/scoring.py` (mirrored in `raf/frontend/src/lib/scoring.ts`) |
| Metrics | `raf/rubric/metrics.py` |
| RIFT diagnostics | `raf/rubric/diagnostics.py` |
| PROMPT-R orchestration | `raf/rubric/optimizer.py`, `raf/rubric/refiner.py`, `raf/rubric/models_optim.py` |
| HTTP API | `raf/rubric/routes.py` |
| UI | `raf/frontend/src/pages/` |
