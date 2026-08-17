# FanSphere AutoResearch — Agent Instructions

> You are an autonomous ML experimentation agent running a ratchet loop on FanSphere AI.
> Read this entire file before doing anything. Work from inside this folder
> (`Autoresearch_fansphere/`). Be frugal with tokens — the usage guardrail is real.

---

## STEP 0 — Guardrail, completion, then budget (every session, before anything else)

There are THREE kinds of stop. Check them in this order:

**(a) Usage guardrail — a temporary pause:**
```bash
python guardrail.py
```
- **Exit 2 (PAUSE / STILL PAUSED)** → append a `PAUSED` note to `results_log.md` and
  **STOP immediately**. (The 5h window must reset; the human relaunches you.)
- **Exit 0** → continue.

**(b) Completion / kill switch — a terminal stop (the project is done):**
```bash
python completion.py
```
- **Exit 3 (GRADUATE)** → the project has reached its standard (or the kill switch is
  flipped). Write `GRADUATION.md` (template below), set `completion.graduated=true` in
  `budget.json`, append a one-line `GRADUATED` note to `results_log.md`, and **STOP for
  good**. Do not run experiments.
- **Exit 4 (ACTIVE PHASE DONE)** → this phase hit its target or plateaued, but the project
  isn't fully graduated. Write the Session Summary, recommend advancing the phase (or
  graduating), and **STOP the session**.
- **Exit 0** → continue.

**(c) Budget — a session cap:**
```bash
cat budget.json
```
- If `iterations_run >= max_iterations` → write the Session Summary (template below) and **STOP**.
- If `baselines[phase]` is `null` → measure the baseline first (STEP 1).

---

## Permissions

| What | Rule |
|---|---|
| **You MAY edit** | only `experiment_1_clustering.py` · `experiment_2_sentiment.py` · `experiment_3_engagement.py` |
| **FROZEN** (never edit) | `evaluate.py` · `guardrail.py` · `completion.py` · `program.md` · `AGENT.md` · everything in `../src/` and `../outputs/` |
| **budget.json** | increment `iterations_run`; update `best_scores[phase]` / `best_configs[phase]` on a KEPT; update `completion.no_improve_streak[phase]` each iteration; set `completion.graduated=true` only when writing GRADUATION.md. NEVER touch `max_iterations`, `usage_guardrail`, `baselines`, `phase`, `phase_names`, or `completion.targets` / `plateau_patience` / `manual_halt`. |
| **One change per iteration** | change exactly ONE config value (or one small block). Never refactor. |
| **Revert via snapshot** | the experiment files are untracked, so `git checkout` will NOT restore them. Use the `.snapshots/` copy (see loop). |
| **Always log** | every iteration — kept, discarded, or errored — appends to `results_log.md`. |

---

## STEP 1 — Measure the phase baseline (only if `baselines[phase]` is null)

```bash
python guardrail.py && python evaluate.py --phase <phase> --baseline
```
This records the baseline in `budget.json` and is your starting `best_scores[phase]`. It
does NOT count as an iteration. Log a one-line "Baseline measured" note, then start the loop.

---

## The Ratchet Loop

Repeat until a stop condition fires (`max_iterations`, guardrail pause, target met,
plateau, or the kill switch):

```
1.  python guardrail.py                 → exit 2? log PAUSED + STOP. exit 0? continue.
2.  python completion.py                → exit 3? GRADUATE (write GRADUATION.md) + STOP.
                                          exit 4? phase done → write summary + STOP session.
                                          exit 0? continue.
3.  read budget.json                    → phase, iterations_run, best_scores[phase], target
4.  read results_log.md                 → what's already been tried (don't repeat)
5.  pick the next untried hypothesis from program.md for THIS phase
6.  BACKUP:  copy experiment_<phase>_*.py  →  .snapshots/experiment_<phase>.bak
7.  EDIT  experiment_<phase>_*.py        → ONE targeted change
8.  python guardrail.py                  → exit 2? restore from .snapshots, log PAUSED, STOP.
9.  python evaluate.py --phase <phase>   → parse the JSON "composite"
10. python guardrail.py                  → catch the spend that just happened (exit 2 ⇒ STOP after logging)
11. COMPARE composite to best_scores[phase]:
        • strictly greater  → KEEP. Set best_scores[phase]=composite + best_configs[phase]=<change>;
                              reset completion.no_improve_streak[phase]=0.
        • equal or worse    → DISCARD. Restore .snapshots/experiment_<phase>.bak;
                              completion.no_improve_streak[phase] += 1.
        • JSON has "error"  → EVALUATE_ERROR. Restore the backup; streak += 1. Do NOT edit evaluate.py.
12. APPEND the result block to results_log.md
13. iterations_run += 1  in budget.json
14. PHASE-DONE CHECK (don't waste remaining iterations once satisfied):
        • if best_scores[phase] >= completion.targets[phase]  → TARGET MET
        • else if no_improve_streak[phase] >= completion.plateau_patience → PLATEAU
      If either: write the Session Summary noting it, then STOP the session
      (the next launch's completion.py will graduate the project if all targets are met).
15. loop
```

**Snapshot commands (Windows PowerShell or bash both fine):**
```bash
# backup before editing
cp experiment_1_clustering.py .snapshots/experiment_1.bak
# restore on discard
cp .snapshots/experiment_1.bak experiment_1_clustering.py
```
(Create `.snapshots/` once if it doesn't exist.)

---

## Phase routing
Read `budget.json -> phase`:

| phase | file you may edit | program.md section |
|---|---|---|
| 1 | `experiment_1_clustering.py` | Phase 1 — Clustering |
| 2 | `experiment_2_sentiment.py` | Phase 2 — Sentiment |
| 3 | `experiment_3_engagement.py` | Phase 3 — Engagement |

**Do NOT advance phases.** When a session ends (max_iterations, target met, plateau, or
pause), stop. The human advances phases and flips the kill switch.

---

## Results log — per-iteration template
```
---
### Iteration {N} | Phase {P} | {KEPT / DISCARDED / EVALUATE_ERROR / PAUSED}
**Hypothesis:** [H-number + one line from program.md]
**Change:** [param: old → new]
**composite:** {x.xxxx}   (best was {x.xxxx}, delta {+/-x.xxxx})
**Sub-metrics:** [silhouette/cluster_stability  OR  rivalry_auc/rivalry_margin_norm]
**Decision:** KEPT / DISCARDED / EVALUATE_ERROR / PAUSED
**Note:** [one sentence — for engagement phases, mention the Clásico rank if it moved]
```

## Session summary (write when a session ends without full graduation)
```
---
## SESSION COMPLETE ({reason: max_iterations / PAUSED / TARGET MET / PLATEAU})
- Phase: {P}   Iterations this session: {N}
- Baseline (this phase): {x.xxxx}   Best composite: {x.xxxx}   Target: {x.xx}
- Best config: [describe the winning change(s)]
- Kept: [...]   Discarded: [...]
- If PAUSED: window resets at {PAUSED.flag window_reset_utc} — relaunch after that.
- If TARGET MET / PLATEAU: phase {P} is done. Human: advance phase, or graduate
  (set completion.manual_halt:true / `touch HALT.flag`).
- Recommended next hypothesis: [...]
```

## GRADUATION report — write `GRADUATION.md` when completion.py returns exit 3
This is the terminal hand-off: the project has reached its standard. After writing it,
set `completion.graduated=true` and append a one-line `GRADUATED` note to `results_log.md`.
```
# FanSphere AutoResearch — GRADUATION
Project reached its standard on {date}. Trigger: {kill switch / all targets met}.

## Final scorecard (per phase)
| Phase | Baseline | Best | Target | Met? | Winning config |
|---|---|---|---|---|---|
| 1 clustering | {..} | {..} | {..} | yes/plateau | {..} |
| 2 sentiment  | {..} | {..} | {..} | ... | {..} |
| 3 engagement | {..} | {..} | {..} | ... | {..} |

## Recommended production ports (human applies; the loop never edits ../src/)
- [e.g. src/engagement.py join_with_stage2: football 0.5→0.35, fan 0.5→0.65 — moved El Clásico #4→#1]
- [...]

## Ready for the next project
Framework is reusable as-is. See PORTING.md — swap evaluate.py / program.md /
experiment_*.py for the new project; keep guardrail.py, completion.py, budget.json, this loop.
```

---

## Token-frugality rules (the guardrail backstops these, but help it out)
- Read only the files each step needs. Never speculatively read `../src/` or `../outputs/`.
- One `evaluate.py` run per iteration. Don't re-run to "double-check".
- Phase 2 with `model="textblob"` re-scores ~93K comment bodies — it's the slowest run;
  expect a minute or two. Everything else is seconds.
- If anything is ambiguous, STOP and leave a note rather than burning iterations guessing.
