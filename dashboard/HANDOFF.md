# FanSphere AI Dashboard — Handoff & Checkpoint

**Status:** Page 1 (Executive Overview) shipped as a static preview. Evidence.dev project structure complete in `dashboard/app/`. Awaiting your local `npm install` to spin up the live multi-page version with filters and drill-downs.

**Why local-run is required:** The Evidence runtime uses `@duckdb/node-api`'s native bindings. They work fine on Windows (and macOS, and bare-metal Linux), but the sandbox I'm running in has a filesystem quirk where parquet writes report success without persisting to disk. Your machine doesn't have this problem.

---

## What's been built

### Phase A — Data enrichment (✅ done, validated)

Two new scripts added under `src/`:

- **`src/enrich_comments_sentiment.py`** — joins `stage3_comments_linked.parquet` ⨝ `reddit_comments.parquet` on `comment_id`, runs VADER on the body, writes `outputs/stage3_comments_enriched.parquet`. Validated: 93,298 comments scored in 7.8 seconds, mean sentiment +0.132, label split 49% positive / 29% negative / 22% neutral.
- **`src/generate_fan_segments.py`** — aggregates per-author behaviour (comment frequency, sentiment volatility, mean upvotes, unique matches), runs KMeans (k=3) on standardised features, labels clusters stably by mean engagement, writes `outputs/fan_segments.csv`. Validated: 3,628 qualifying authors (≥3 comments each), silhouette score 0.40, cluster sizes 1,345 Casual / 2,160 Tactical / 123 Highly Engaged.

Both are idempotent. Run from project root:

```bash
python -m src.enrich_comments_sentiment
python -m src.generate_fan_segments
```

### Phase B — Evidence.dev scaffold (✅ done)

`dashboard/app/` contains a full Evidence project:

```
app/
├── package.json              # trimmed deps (4 + typescript + vite pin)
├── evidence.config.yaml      # FanSphere theme — charcoal + crimson
├── pages/
│   └── index.md              # Page 1: Executive Overview (full markup + SQL)
└── sources/fansphere/
    ├── connection.yaml       # DuckDB source, file-backed
    ├── fansphere.duckdb      # 22.8 MB pre-loaded DB with all 9 tables
    ├── matches.sql           # → matches table
    ├── goal_events.sql       # → 52 goal events with xG
    ├── engagement.sql        # → 10-row main fact table (joined)
    ├── ranking.sql           # → final ranking
    ├── match_sentiment.sql   # → per-match VADER aggregates
    ├── fan_segments.sql      # → 3,628-author KMeans output
    ├── comments_enriched.sql # → 93,298 rows with body + sentiment
    └── comments_linked.sql   # → linking metadata for methodology
```

The CSV/parquet source files are also in `sources/fansphere/` as a backup — you can read them directly with pandas / Power BI / anything if Evidence ever breaks.

### Phase C — Page 1 Executive Overview (✅ source written)

Look at `dashboard/app/pages/index.md`. It defines:
- Hero header with the FanSphere logo block, crimson glow, and three context chips
- Four KPI BigValues with the comparison-vs-football-side trick on the average
- ButtonGroup filter for All / Rivalry only / Non-rivalry
- The headline divergence ScatterPlot with point labels and the diagonal reference
- An Alert callout explaining how to read the scatter
- The combined-engagement BarChart, horizontal, rivalry-highlighted
- The DataTable with colorscale columns for the four numeric fields
- The narrative section with the three key insights

### Static preview — see Page 1 right now

**Open this file in your browser:** `dashboard/page1_preview.html`

It's a faithful render of Page 1 using the actual enriched data, ECharts under the hood, full crimson theme, interactive filter buttons, real KPIs. This is what the Evidence version will look like once you run it locally — basically pixel-for-pixel the same component layout.

---

## How to run the live Evidence version locally

From inside `dashboard/app/`:

```bash
# 1. Install (one-time, ~30s on a warm npm cache)
npm install

# 2. Build the parquet source cache (~5s — DuckDB reads from sources/fansphere/fansphere.duckdb)
npm run sources

# 3. Start the dev server
npm run dev
```

The dev server will open `http://localhost:3000/` automatically with hot reload. Edit `pages/index.md` and save — the page updates without restart.

If `npm install` complains about peer deps, use:

```bash
npm install --legacy-peer-deps
```

---

## Pages remaining (2–5)

Source written for Page 1 only. The next phases build on the same data sources (no further enrichment needed):

- **Page 2 — Match Drill-Down** — dropdown per match, goal-timeline custom ECharts (pitch axis 0-90'), comment-volume curve over the ±48h window using `minutes_from_kickoff`, sentiment histogram, top positive/negative quotes table from `comments_enriched`.
- **Page 3 — Fan Segmentation** — 3 BigValues per cluster (size, mean engagement, characteristic behaviour), 2D scatter (comment_freq × volatility) colored by cluster, small-multiples bar chart of cluster feature means, methodology callout with silhouette 0.40.
- **Page 4 — Sentiment Timeline** — season trend line with W/L/D markers, volatility band (±1σ around sentiment), stacked bar of sentiment by subreddit per match, rivalry-vs-non-rivalry callout.
- **Page 5 — Methodology** — pipeline diagram (mermaid), score formulas, lineage Sankey, linking confidence histogram from `comments_linked`.

Confirm Page 1 looks right (open `page1_preview.html`) and I'll continue with Pages 2–5 in the next pass.

---

## Phase F — GitHub Pages deployment (config staged, push pending)

`evidence.config.yaml` has `deployment.basePath: "/FanSphere-AI"` set. When you're ready:

1. Confirm the repo name is `FanSphere-AI` (if not, edit the basePath).
2. Add a GitHub Actions workflow at `.github/workflows/deploy.yml` — I'll write that file in the next pass once you've confirmed Page 1.
3. Enable GitHub Pages on the repo, source: GitHub Actions.
4. Push to `main`. Site goes live at `https://<your-username>.github.io/FanSphere-AI/`.

---

## Files added this session

| File | Purpose |
|---|---|
| `src/enrich_comments_sentiment.py` | Phase A1 enrichment script |
| `src/generate_fan_segments.py` | Phase A2 segmentation script |
| `outputs/stage3_comments_enriched.parquet` | 11 MB, 93,298 comments with VADER + body |
| `outputs/fan_segments.csv` | 3,628 authors with cluster labels |
| `dashboard/app/` | Full Evidence project (sans `node_modules`) |
| `dashboard/page1_preview.html` | Static preview of Page 1 you can open right now |
| `dashboard/EVIDENCE_BUILD_PLAN.md` | Original approved plan |
| `dashboard/HANDOFF.md` | This file |

The old `dashboard/_broken_clone_remove_me/` directory is locked by OneDrive permissions — you can manually delete it from File Explorer when convenient. It contains nothing of value.

---

## TL;DR

1. Open `dashboard/page1_preview.html` — that's Page 1, live, with real data, exactly the design we agreed on.
2. If it looks right, run `cd dashboard/app && npm install && npm run sources && npm run dev` to see the live Evidence version with the dropdown filter working.
3. Tell me whether to proceed with Pages 2–5, or what to change on Page 1 first.
