# Porting AutoResearch to a New Project

This framework is a **general ratchet loop**: propose one change → test it → keep it only
if a single scalar metric strictly improves → log → repeat, under hard usage/iteration/quality
limits. FanSphere is just the first project pointed at it. To research a new project, you keep
the engine and swap three files.

---

## The ideology (invariants — keep these every time)

1. **One scalar metric, higher = better.** Every experiment collapses to one number. No metric,
   no ratchet.
2. **The metric must be label-grounded and not gameable.** Reward *quality*, never *insensitivity*.
   (Our original FanSphere metric rewarded "ranking stability" — a frozen ranking scored perfectly
   while being useless. We replaced it with separation against free labels.)
3. **Measure the baseline fresh.** Never hard-code a baseline number; compute it from the current
   code (`--baseline`) so improvements are real, not relative to a guess.
4. **One change per iteration.** Isolate cause and effect. Refactors break the ratchet.
5. **Optimize the REAL code, not a shadow.** The evaluator imports production functions so a
   winning config is a 1–2 line port, not a reimplementation that drifts.
6. **Revert must be reliable.** Snapshot-copy before editing (`.snapshots/*.bak`); never rely on
   git for untracked files.
7. **Three stop tiers, always:** pause (usage), budget (`max_iterations`), graduation (quality
   reached / kill switch). The agent never decides it's "done" without one firing.
8. **The loop never edits production.** It proposes; the human reviews and ports.

---

## Reusable AS-IS (copy to the new project, no edits)

| File | Why it's generic |
|---|---|
| `guardrail.py` | Pure ccusage usage cap — knows nothing about the project. |
| `completion.py` | Pure budget.json logic — targets / plateau / kill switch. |
| `budget.json` (schema) | Same keys; just reset values (see checklist). |
| `AGENT.md` (skeleton) | The loop + stop tiers + snapshot revert. Edit only the phase table and project name. |
| `results_log.md`, `.snapshots/` | Log + revert mechanics. |

## Swap PER PROJECT (the only real work — 3 files)

1. **`evaluate.py`** — define the new project's metric. Requirements:
   - reads the project's real artifacts; imports the project's real code;
   - `--phase N` and `--baseline`; prints JSON with a `"composite"` float;
   - the metric obeys invariants #1, #2, #5.
2. **`program.md`** — the hypotheses to try, in order, per phase, and what the metric means.
3. **`experiment_{1,2,3}_*.py`** — thin config files exposing the knobs the agent may turn.

That's it. The engine, the guardrail, the kill switch, and the loop are unchanged.

---

## Choosing a good metric (the hard part — read invariant #2 twice)

Ask, in order:
- **Is there a free or cheap ground-truth label already in the data?** (FanSphere had `is_rivalry`
  and `total_goals` — no hand-labeling needed.) Separation/correlation against a real label beats
  any internal-consistency proxy.
- **Can the metric be trivially maximized the wrong way?** If a constant, frozen, or degenerate
  output scores well, the metric is broken. Test it: feed it a dumb baseline and confirm it scores
  poorly.
- **Is it fast?** It runs every iteration. Seconds, not minutes. Cache or sample heavy steps.
- **Does it have resolution?** Tiny datasets give coarse metrics (FanSphere's 10 fixtures → AUC in
  ~0.06 steps). Pair a coarse ranking metric with a continuous one (we added a margin term) so the
  agent has a gradient to climb.

---

## Spin-up checklist for "Project N+1"

1. Copy this folder; rename. Update the project name + phase table in `AGENT.md`, and the title
   in `program.md`.
2. Write the new `evaluate.py` (metric + `--baseline`). Smoke-test: a dumb/degenerate config must
   score near the floor.
3. Write `program.md` hypotheses and the matching `experiment_*.py` knobs.
4. Reset `budget.json`: `iterations_run:0`, `baselines/best_scores/best_configs` → null,
   `completion.graduated:false`, `manual_halt:false`, `no_improve_streak`→0, set new `targets`,
   keep `usage_guardrail` as-is.
5. `pip install` any new metric deps. Run `python evaluate.py --phase 1 --baseline` and confirm a
   sane number.
6. Run `python guardrail.py` and `python completion.py` once — both should exit 0.
7. `cd` in, launch the agent, walk away.

---

## Generic worked example (domain-neutral)

Say the next project is a **document retrieval system** and you have a small set of
(query → relevant-doc) labels.

- **Metric (`evaluate.py`):** `composite = recall@k` on the held-out labels (a real,
  non-gameable quality signal; a random retriever scores near 0). `--baseline` runs the current
  retriever; `--phase 1` re-runs it with the experiment config.
- **Knobs (`experiment_1_*.py`):** `embedding_model`, `chunk_size`, `k`, `rerank: on/off`.
- **Hypotheses (`program.md`):** H1.1 larger chunks; H1.2 add a reranker; H1.3 swap the embedding
  model; …
- **Targets:** `{"1": 0.85}` (graduate when recall@k ≥ 0.85 or it plateaus).

Same loop, same guardrail, same kill switch — only the three project files changed.
