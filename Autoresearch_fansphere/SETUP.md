# FanSphere AutoResearch — Setup & Operating Guide

A Karpathy-style ratchet loop (propose → test → keep-if-better → repeat) adapted for
FanSphere AI. It experiments on your **real** pipeline code, keeps only changes that beat
a label-grounded baseline, logs everything, and **caps itself at 60% of your 5-hour usage
window**.

**Two hard limits:** `max_iterations` (default 3) and the usage guardrail (60% of your
rolling-max 5h block). Either one stops the session.

---

## One-time setup

1. This folder lives at the repo root: `FanSphere-AI/Autoresearch_fansphere/`.
2. Install the one new dependency (only needed once Phase 2 runs):
   ```bash
   pip install textblob
   ```
   Everything else — scikit-learn, pandas, numpy, pyarrow, vaderSentiment — is already in
   `requirements.txt`. `ccusage` needs no install (runs via `npx`; Node is already present).
3. Make sure Stage 3 has run so `outputs/stage3_comments_enriched.parquet` exists
   (`python -m src.enrich_comments_sentiment`).
4. (Recommended) Commit this folder once so reverts have a clean tracked baseline:
   ```bash
   git add Autoresearch_fansphere && git commit -m "AutoResearch baseline"
   ```

---

## Running a session

```bash
cd FanSphere-AI/Autoresearch_fansphere
claude
```
Claude Code reads `CLAUDE.md` automatically and runs the loop: it checks the guardrail,
measures the phase baseline if needed, then tries one hypothesis at a time, keeping only
improvements. Walk away. Read `results_log.md` when it stops.

To sanity-check the plumbing yourself first:
```bash
python guardrail.py                       # prints your current 5h usage %
python evaluate.py --phase 1 --baseline   # silhouette should be ~0.40
python evaluate.py --phase 3 --baseline   # shows each Clásico's current rank
```

---

## The usage guardrail (`guardrail.py`)

- Reads the same 5-hour blocks Claude Code bills against (via ccusage) and pauses at
  **60%** of your **rolling-max** block (your own recent peak). Config: `budget.json →
  usage_guardrail`.
- **Exit 0** = proceed (prints headroom). **Exit 2** = pause: it writes `PAUSED.flag` with
  the window's reset time and the agent stops. **Exit 1** = couldn't run ccusage (not
  enforced).
- **When it pauses:** the agent stops — a usage-blocked agent can't keep working. Note the
  `window_reset_utc` in `PAUSED.flag`, and **relaunch after that time**. The next
  `guardrail.py` run auto-clears the stale flag once the window has reset.
- **Tuning:** change `pause_at_fraction` (e.g. 0.5 for stricter). For a fixed budget
  instead of rolling-max, set `cap_mode:"explicit"` and `explicit_token_cap: <tokens>`.
- **Honest caveat:** Anthropic doesn't expose your Pro 5h cap to scripts, so this is a
  proxy against your own usage, not a literal billing percentage.

---

## Kill switch & graduation (`completion.py`)

Three kinds of stop: **pause** (usage — resume later), **budget** (`max_iterations` — review
then continue), and **graduation** (terminal — the project is done). `completion.py` is the
deterministic judge, run at STEP 0 right after the guardrail.

- **Manual kill switch:** set `completion.manual_halt: true` in `budget.json`, **or** just
  `touch HALT.flag` in this folder. At the next iteration boundary the agent writes
  `GRADUATION.md` and stops for good. (It's not an instant interrupt — to stop *right now*,
  close the Claude Code session; the flag stops it cleanly at the next check.)
- **Automatic graduation:** the project graduates when every phase with a non-null
  `completion.targets[phase]` has either met its target composite or **plateaued**
  (`no_improve_streak >= plateau_patience`). Seeded targets are `{1: 0.70, 2: 0.62, 3: 0.65}`
  — edit them to your bar, or set one to `null` to disable that phase's target.
- **Per-phase finish:** when the *active* phase hits its target or plateaus, the session ends
  and recommends advancing the phase (or graduating) — it won't burn the remaining iterations.
- **What graduation produces:** `GRADUATION.md` — a final scorecard (baseline → best → target
  per phase), recommended production ports, and a pointer to `PORTING.md` for the next project.

To **un-graduate** (resume research): set `completion.graduated: false`, `manual_halt: false`,
and delete `HALT.flag`.

---

## After each session
Read `results_log.md`, then edit `budget.json`:
- **More iterations, same phase:** set `iterations_run: 0`.
- **Advance phase:** set `phase: 2` (or 3) and `iterations_run: 0`. (Baselines auto-measure
  on the next run if still `null`.)
- **Change the cap:** edit `max_iterations`.
You control the budget; the agent never edits `max_iterations`, `usage_guardrail`, or `phase`.

---

## Promoting a winning config to production (manual, your call)
The loop **never edits `../src/`**. When a config wins, port it by hand:
- **Phase 1** → `src/generate_fan_segments.py`: `n_clusters`, scaler, and `feature_cols`.
- **Phase 2** → `src/enrich_comments_sentiment.py` (analyzer) / aggregation in
  `src/engagement.py`.
- **Phase 3** → `src/engagement.py`: `EngagementWeights(...)` defaults and the 0.5/0.5 split
  in `join_with_stage2`.
Re-run the pipeline, regenerate `outputs/`, and refresh the dashboard.

---

## File roles
| File | Role | Who edits |
|---|---|---|
| `CLAUDE.md` | Agent instructions | You (never agent) |
| `program.md` | Hypotheses + metric spec | You (never agent) |
| `evaluate.py` | Frozen evaluator (reads `outputs/`, calls `src/`) | You only (if it errors) |
| `guardrail.py` | Frozen usage cap | You only |
| `completion.py` | Frozen graduation / kill-switch judge | You only |
| `budget.json` | Iterations + baselines + guardrail + completion config | Agent increments iters/streaks; you set the rest |
| `experiment_{1,2,3}_*.py` | The knobs the agent turns | Agent (one phase at a time) |
| `results_log.md` | Experiment audit trail | Agent appends |
| `.snapshots/` | Revert backups | Agent |
| `PAUSED.flag` | Created when paused; carries reset time | Guardrail writes / clears |
| `HALT.flag` | Manual kill switch — presence graduates the project | You (`touch` it); delete to resume |
| `GRADUATION.md` | Final scorecard + production ports, written on graduation | Agent writes |
| `PORTING.md` | How to reuse this framework for the next project | Reference |
