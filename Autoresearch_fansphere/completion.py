#!/usr/bin/env python3
"""
FanSphere AutoResearch - Completion / Kill-Switch Check
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FROZEN FILE: the agent must NOT modify this file.

The deterministic judge for "is this project done?" - run it at STEP 0, right
after guardrail.py. It reads budget.json (+ an optional HALT.flag) and decides:

  • exit 3 → GRADUATE the project (terminal). Agent writes GRADUATION.md and stops.
  • exit 4 → the ACTIVE phase is done (target met or plateaued) but the project
             isn't fully graduated. Agent ends the session and recommends
             advancing the phase or flipping the kill switch.
  • exit 0 → proceed with iterations.

A phase is "done" when its best score reaches its target OR it has plateaued
(no_improve_streak >= plateau_patience). The project graduates when the kill
switch is flipped, or when every phase that has a target is done.

This is project-agnostic: it knows nothing about football. Reused as-is when the
framework is pointed at a new project (see PORTING.md).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUDGET_PATH = HERE / "budget.json"
HALT_PATH = HERE / "HALT.flag"

PHASES = ("1", "2", "3")


def main() -> int:
    if not BUDGET_PATH.exists():
        print("[completion] no budget.json - proceeding.")
        return 0

    b = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    c = b.get("completion", {})
    phase = str(b.get("phase", "1"))
    best = b.get("best_scores", {}) or {}
    targets = c.get("targets", {}) or {}
    patience = int(c.get("plateau_patience", 5))
    streaks = c.get("no_improve_streak", {}) or {}

    # 1) Already graduated, or manual kill switch.
    if c.get("graduated"):
        print("[completion] Project already GRADUATED (completion.graduated=true). Stopping.")
        return 3
    if c.get("manual_halt") or HALT_PATH.exists():
        why = "HALT.flag present" if HALT_PATH.exists() else "completion.manual_halt=true"
        print(f"[completion] >>> KILL SWITCH: {why}. GRADUATE the project. <<<")
        return 3

    def done(p: str):
        t = targets.get(p)
        bs = best.get(p)
        by_target = (t is not None and bs is not None and float(bs) >= float(t))
        by_plateau = int(streaks.get(p, 0)) >= patience
        return by_target, by_plateau

    # 2) Project graduation: every phase that HAS a target is done.
    targeted = [p for p in PHASES if targets.get(p) is not None]
    if targeted:
        flags = {p: done(p) for p in targeted}
        if all(bt or bp for (bt, bp) in flags.values()):
            print("[completion] >>> All targeted phases satisfied - GRADUATE the project. <<<")
            for p in targeted:
                bt, bp = flags[p]
                reason = "target met" if bt else "plateaued"
                print(f"            phase {p}: {reason}  (best={best.get(p)}, target={targets.get(p)})")
            return 3

    # 3) Active phase done, but project not fully graduated yet.
    bt, bp = done(phase)
    if bt or bp:
        reason = "target met" if bt else f"plateaued ({streaks.get(phase, 0)}/{patience})"
        print(f"[completion] Active phase {phase} is DONE ({reason}; "
              f"best={best.get(phase)}, target={targets.get(phase)}).")
        print("            Advance the phase in budget.json, or set completion.manual_halt:true "
              "(or `touch HALT.flag`) to graduate.")
        return 4

    # 4) Keep going.
    print(f"[completion] phase {phase}: best={best.get(phase)} target={targets.get(phase)} | "
          f"no_improve_streak={streaks.get(phase, 0)}/{patience}. Proceeding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
