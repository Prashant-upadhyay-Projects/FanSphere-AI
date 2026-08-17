#!/usr/bin/env python3
"""
FanSphere AutoResearch - Usage Guardrail
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FROZEN FILE: the agent must NOT modify this file.

Caps the agent at <pause_at_fraction> (default 0.60) of your 5-hour usage
window, measured against your own recent peak block (rolling max) via ccusage -
the same 5h blocks the agent's usage is billed against.

  • exit 0  → safe to proceed (prints headroom)
  • exit 2  → PAUSE: writes PAUSED.flag with the window reset time, then stops
  • exit 1  → guardrail could not run (ccusage/network/parse problem)

Honest caveats:
  • "60% of plan" is a proxy. The provider doesn't expose your plan's 5h cap to
    scripts, so the denominator is YOUR rolling-max block (or an explicit
    override in budget.json). totalTokens counts cheap cache-read tokens
    equally - fine for a self-consistent ratio, not a literal billing %.
  • A paused agent stops; it cannot keep working. Relaunch after the reset.

Config lives in budget.json -> "usage_guardrail".
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUDGET_PATH = HERE / "budget.json"
PAUSED_PATH = HERE / "PAUSED.flag"

DEFAULTS = {
    "enabled": True,
    "pause_at_fraction": 0.60,
    "cap_mode": "rolling_max",     # "rolling_max" | "explicit"
    "explicit_token_cap": None,
    "lookback_days": 30,
    "ccusage_offline": True,
}


def _cfg() -> dict:
    cfg = dict(DEFAULTS)
    if BUDGET_PATH.exists():
        try:
            cfg.update(json.loads(BUDGET_PATH.read_text(encoding="utf-8")).get("usage_guardrail", {}))
        except Exception:
            pass
    return cfg


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _run_ccusage(cfg: dict) -> dict | None:
    """Fetch ccusage blocks JSON, trying progressively simpler commands."""
    from datetime import timedelta
    start = (datetime.now(timezone.utc) - timedelta(days=int(cfg.get("lookback_days", 30)))).strftime("%Y%m%d")
    offline = "--offline" if cfg.get("ccusage_offline", True) else ""

    candidates = [
        f"npx ccusage@latest blocks --json {offline} --since {start}",
        f"npx ccusage@latest blocks --json {offline}",
        "npx ccusage@latest blocks --json",
    ]
    for cmd in candidates:
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=180
            )
        except Exception:
            continue
        out = (proc.stdout or "").strip()
        if not out:
            continue
        # ccusage prints clean JSON to stdout; find the first '{'.
        brace = out.find("{")
        if brace == -1:
            continue
        try:
            data = json.loads(out[brace:])
        except Exception:
            continue
        if isinstance(data, dict) and "blocks" in data:
            return data
    return None


def _check_existing_pause() -> bool:
    """If a PAUSED.flag exists and its window hasn't reset, stay paused."""
    if not PAUSED_PATH.exists():
        return False
    try:
        flag = json.loads(PAUSED_PATH.read_text(encoding="utf-8"))
        reset = _parse_iso(flag["window_reset_utc"])
    except Exception:
        return False
    now = datetime.now(timezone.utc)
    if now >= reset:
        PAUSED_PATH.unlink(missing_ok=True)
        print(f"[guardrail] Previous pause cleared - window reset at {reset.isoformat()}.")
        return False
    mins = int((reset - now).total_seconds() // 60)
    print("[guardrail] STILL PAUSED.")
    print(f"            Window resets at {reset.isoformat()} (~{mins} min away).")
    print("            Relaunch the loop after that time. Stopping now.")
    return True


def main() -> int:
    cfg = _cfg()

    if not cfg.get("enabled", True):
        print("[guardrail] disabled in budget.json - proceeding.")
        return 0

    if _check_existing_pause():
        return 2

    data = _run_ccusage(cfg)
    if data is None:
        print("[guardrail] WARNING: could not read ccusage. Not enforcing this check.")
        print("            (Is Node/npx available? Try: npx ccusage@latest blocks --json)")
        return 0

    blocks = data.get("blocks", [])
    completed = [b for b in blocks if not b.get("isActive") and not b.get("isGap")]
    active = next((b for b in blocks if b.get("isActive")), None)

    if active is None:
        print("[guardrail] No active 5h block - nothing to limit. Proceeding.")
        return 0

    # Determine the cap.
    explicit = cfg.get("explicit_token_cap")
    if cfg.get("cap_mode") == "explicit" and explicit:
        cap = float(explicit)
        cap_src = f"explicit ({int(cap):,} tokens)"
    elif explicit:
        cap = float(explicit)
        cap_src = f"explicit override ({int(cap):,} tokens)"
    elif completed:
        cap = float(max(b.get("totalTokens", 0) for b in completed))
        cap_src = f"rolling max of {len(completed)} completed blocks"
    else:
        print("[guardrail] WARNING: no completed blocks yet to set a rolling-max cap.")
        print("            Set usage_guardrail.explicit_token_cap in budget.json to enforce. Proceeding.")
        return 0

    if cap <= 0:
        print("[guardrail] WARNING: computed cap is 0 - not enforcing. Proceeding.")
        return 0

    used = float(active.get("totalTokens", 0))
    frac = used / cap
    threshold = float(cfg.get("pause_at_fraction", 0.60))
    reset = _parse_iso(active["endTime"])
    cost = active.get("costUSD")
    proj = (active.get("projection") or {}).get("totalTokens")

    print("[guardrail] 5h-window usage check")
    print(f"            used      : {int(used):,} tokens  (cost ~${cost:.2f})" if cost is not None
          else f"            used      : {int(used):,} tokens")
    print(f"            cap       : {int(cap):,} tokens  [{cap_src}]")
    print(f"            usage     : {frac * 100:.1f}%  (pause at {threshold * 100:.0f}%)")
    print(f"            resets at : {reset.isoformat()}")

    if frac >= threshold:
        flag = {
            "paused_at_utc": datetime.now(timezone.utc).isoformat(),
            "window_reset_utc": active["endTime"],
            "usage_fraction": round(frac, 4),
            "pause_at_fraction": threshold,
            "used_tokens": int(used),
            "cap_tokens": int(cap),
            "cap_source": cap_src,
            "cost_usd": cost,
            "note": "Usage hit the soft cap. Relaunch the loop after window_reset_utc.",
        }
        PAUSED_PATH.write_text(json.dumps(flag, indent=2), encoding="utf-8")
        print(f"\n[guardrail] >>> PAUSE: {frac * 100:.1f}% >= {threshold * 100:.0f}% cap. <<<")
        print(f"            Wrote {PAUSED_PATH.name}. Relaunch after {reset.isoformat()}.")
        return 2

    if proj and proj / cap >= threshold:
        print(f"            heads-up  : projected end-of-window ~{proj / cap * 100:.0f}% - may pause this window.")
    print(f"[guardrail] OK - {(threshold - frac) * 100:.1f}% headroom remaining. Proceeding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
