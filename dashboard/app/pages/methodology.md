---
title: The Receipts
sidebar_position: 5
hide_title: true
full_width: true
---

<!-- HERO ====================================================== -->

<div class="hero">
  <div class="hero-brand">
    <div class="hero-logo">M5</div>
    <div>
      <div class="hero-title">Methodology &amp; Receipts</div>
      <div class="hero-sub">Where every number on the other four pages comes from — pipeline, models, caveats</div>
    </div>
  </div>
  <div class="hero-meta">
    <span class="chip">StatsBomb open-data</span>
    <span class="chip">Reddit Pushshift</span>
    <span class="chip">VADER (NLTK)</span>
    <span class="chip">KMeans (scikit-learn)</span>
    <span class="chip">DuckDB → Evidence.dev</span>
  </div>
</div>

<div class="page-intro">
If you can't audit the pipeline you can't trust the dashboard. <strong>Every transformation, model choice and caveat lives here</strong> — read it once, then the other pages stand on their own.
</div>

<!-- PIPELINE =================================================== -->

## The pipeline at a glance

Five stages, two open datasets, two models. Output is parquet/CSV consumed directly by Evidence's DuckDB connector.

<div class="pipeline">
  <div class="stage">
    <div class="stage-num">1</div>
    <div class="stage-name">Match data</div>
    <div class="stage-body">StatsBomb open-data — La Liga 2020/21 fixtures, scores, goal events with xG.</div>
    <div class="stage-meta">10 matches · 53 goals</div>
  </div>
  <div class="arrow">→</div>
  <div class="stage">
    <div class="stage-num">2</div>
    <div class="stage-name">Fan comments</div>
    <div class="stage-body">Reddit Pushshift dump, filtered to <code>r/barca</code> + <code>r/realmadrid</code> within a 4-hour window of kickoff.</div>
    <div class="stage-meta">907,158 raw · 93,298 linked</div>
  </div>
  <div class="arrow">→</div>
  <div class="stage">
    <div class="stage-num">3</div>
    <div class="stage-name">Sentiment</div>
    <div class="stage-body">VADER (NLTK) scores per comment. Compound score in [−1, +1]; label thresholded at ±0.05.</div>
    <div class="stage-meta">93,298 comments scored</div>
  </div>
  <div class="arrow">→</div>
  <div class="stage">
    <div class="stage-num">4</div>
    <div class="stage-name">Author segments</div>
    <div class="stage-body">KMeans k=3 on standardised behavioural features for authors with ≥3 comments.</div>
    <div class="stage-meta">3,628 authors · silhouette 0.40</div>
  </div>
  <div class="arrow">→</div>
  <div class="stage">
    <div class="stage-num">5</div>
    <div class="stage-name">Engagement score</div>
    <div class="stage-body">Composite = ½ × on-pitch (normalised) + ½ × fan-side (4-factor blend).</div>
    <div class="stage-meta">10 matches ranked</div>
  </div>
</div>

<!-- ======================================================= -->

## Data sources — what's in DuckDB

Every Evidence query on the other four pages reads from one of these tables. All loaded into `sources/fansphere/fansphere.duckdb`.

```sql data_sources
select * from (values
  ('matches',           '10 rows',     'Fixtures + scores + rivalry flag (StatsBomb)'),
  ('goal_events',       '53 rows',     'Per-goal minute, scorer, xG (StatsBomb)'),
  ('comments_enriched', '93,298 rows', 'Per-comment VADER sentiment + body + upvotes'),
  ('comments_linked',   '93,298 rows', 'Linking metadata only (confidence + reasons)'),
  ('match_sentiment',   '10 rows',     'Per-match aggregates: volume, sentiment, volatility'),
  ('fan_segments',      '3,628 rows',  'Per-author KMeans cluster + features'),
  ('engagement',        '10 rows',     'Per-match composite score components'),
  ('ranking',           '10 rows',     'Pre-sorted ranking (rank 1-10) by combined score')
) as t(table_name, row_count, what_it_holds)
```

<DataTable data={data_sources} rows=8 rowShading=true>
  <Column id=table_name      title="Table"            wrap=false/>
  <Column id=row_count       title="Rows"             align=center/>
  <Column id=what_it_holds   title="What it holds"    wrap=true/>
</DataTable>

<!-- ======================================================= -->

## Comment-to-match linking confidence

Each comment gets a confidence score for *which match it belongs to* based on subreddit, time-from-kickoff, and team-name mentions. The histogram below is what we ended up with — most comments are 0.6 confidence (sub + time match) with a long tail of high-confidence matches.

```sql link_confidence
select
    round(link_confidence, 1) as confidence,
    count(*)                   as comments
from fansphere.comments_linked
group by 1
order by 1
```

<BarChart
  data={link_confidence}
  x=confidence
  y=comments
  xAxisTitle="Linking confidence (0 → 1)"
  yAxisTitle="Comments"
  yFmt='#,##0'
  yScale=log
  chartAreaHeight=240
  colorPalette={['#22D3EE']}
  labels=true
  labelFmt='#,##0'
/>

<Alert status="info">
  <strong>Why log scale:</strong> the 0.6 bucket has 91,250 comments; the 1.0 bucket has 34. On a linear axis the right side would vanish. Log preserves the shape.
</Alert>

<!-- ======================================================= -->

## Models &amp; scoring formulae

The two ML touch-points and the deterministic scoring on top.

<div class="model-grid">

  <div class="model-card">
    <div class="model-tag">SENTIMENT</div>
    <div class="model-name">VADER (NLTK)</div>
    <div class="model-blurb">Lexicon + grammatical rules tuned for social-media text. Output is a compound score in [−1, +1]. We label as positive when compound ≥ +0.05, negative when ≤ −0.05, neutral otherwise — VADER's documented defaults.</div>
    <div class="model-why"><b>Why VADER:</b> built for short, informal text with emoji and slang. No training data required — appropriate when the corpus is small and the task is well-defined.</div>
  </div>

  <div class="model-card">
    <div class="model-tag">CLUSTERING</div>
    <div class="model-name">KMeans (k=3, scikit-learn)</div>
    <div class="model-blurb">Features per author (standardised): <code>comment_frequency</code>, <code>matches_covered</code>, <code>avg_sentiment</code>, <code>sentiment_volatility</code>, <code>positive_ratio</code>. <code>random_state=42</code> for reproducibility. Filtered to authors with ≥3 comments.</div>
    <div class="model-why"><b>Why k=3:</b> elbow method gave a clean knee at 3, silhouette 0.40 is acceptable for behavioural-segmentation work. Three clusters are also interpretable as personas ([[the-tribes]]).</div>
  </div>

  <div class="model-card">
    <div class="model-tag">COMPOSITE</div>
    <div class="model-name">Engagement Score</div>
    <div class="model-blurb">Combined = 0.5 × football_norm + 0.5 × fan_engagement.<br/>fan_engagement = 0.40·volume + 0.25·affect + 0.20·volatility + 0.15·reach (each normalised 0-1).<br/>football_norm = total_goals normalised across the 10-match window.</div>
    <div class="model-why"><b>Why these weights:</b> volume dominates raw conversation intensity; affect captures whether the conversation was loud or angry; volatility rewards back-and-forth; reach rewards cross-subreddit. The 50/50 fan-vs-football split is by design — see Page 1's diagonal chart.</div>
  </div>

</div>

<!-- ======================================================= -->

## Caveats worth knowing

The model is honest about its limits.

<div class="caveats">
  <div class="caveat">
    <div class="caveat-num">01</div>
    <div class="caveat-body">
      <b>Single-team bias.</b> Both subreddits in the comment corpus (<code>r/barca</code>, <code>r/realmadrid</code>) skew Barcelona-side. Of the 10 fixtures, 8 involve Barcelona. Conclusions generalise to *those fanbases* — not to neutrals or rival-team supporters of the other 8 La Liga teams.
    </div>
  </div>
  <div class="caveat">
    <div class="caveat-num">02</div>
    <div class="caveat-body">
      <b>VADER is rule-based, not deep.</b> It can't read sarcasm, language switches (Spanish ↔ English ↔ Catalan), or local idioms. A more recent transformer model would score differently — VADER was chosen for transparency and the small corpus size.
    </div>
  </div>
  <div class="caveat">
    <div class="caveat-num">03</div>
    <div class="caveat-body">
      <b>Linking confidence is fuzzy.</b> 91,250 of 93,298 comments sit at 0.6 confidence — they match on subreddit + time but not necessarily on team mention. False positives are possible; the directional signal is still defensible.
    </div>
  </div>
  <div class="caveat">
    <div class="caveat-num">04</div>
    <div class="caveat-body">
      <b>10 matches is a small N.</b> Statistical claims (rivalry premium, segment differences) are descriptive of *this season*, not generalisable to "La Liga" or "fans" in the abstract. Extend the dataset before drawing universal conclusions.
    </div>
  </div>
</div>

<!-- ======================================================= -->

## How to reproduce locally

Three commands. The DuckDB file is checked in so the dashboard runs offline.

```sh
git clone <repo>
cd FanSphere-AI/dashboard/app
npm install
npm run sources   # builds parquet cache from fansphere.duckdb
npm run dev       # opens http://localhost:3000
```

If `npm install` complains about peer deps, drop `node_modules` + `package-lock.json` and retry without `--legacy-peer-deps`.

<div class="page-footer">
  <span>Stack: Python (pandas, NLTK, scikit-learn, statsbombpy) → DuckDB → Evidence.dev (SvelteKit) · Source: <code>FanSphere-AI/</code> repo</span>
</div>

<style>
  .content-container, .content, main { max-width: 1400px !important; }

  .hero {
    background: linear-gradient(135deg, rgba(225,29,92,0.10) 0%, rgba(225,29,92,0) 60%);
    border: 1px solid var(--grey-200); border-radius: 16px;
    padding: 28px 32px; margin: 0 0 20px 0;
    display: flex; flex-direction: column; gap: 18px;
  }
  .hero-brand { display: flex; align-items: center; gap: 16px; }
  .hero-logo {
    width: 56px; height: 56px;
    background: var(--primary); color: white; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 18px; letter-spacing: -0.5px;
    box-shadow: 0 4px 16px rgba(225,29,92,0.30);
  }
  .hero-title { font-size: 30px; font-weight: 700; letter-spacing: -0.5px; line-height: 1.1; }
  .hero-sub  { font-size: 14px; color: var(--grey-500); margin-top: 5px; }
  .hero-meta { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    display: inline-block; background: var(--grey-100); color: var(--grey-700);
    padding: 4px 12px; border-radius: 99px;
    font-size: 12px; font-weight: 500;
  }
  .chip-crimson { background: rgba(225,29,92,0.15); color: var(--primary); }

  .page-intro {
    font-size: 14px; color: var(--grey-600);
    margin: 0 0 24px 0; padding: 14px 18px;
    border-left: 3px solid #22D3EE;
    background: rgba(34,211,238,0.04);
    border-radius: 4px;
  }
  .page-intro strong { color: var(--grey-800); }

  /* Pipeline strip */
  .pipeline {
    display: flex; flex-wrap: wrap; align-items: stretch;
    gap: 8px; margin: 0 0 12px 0;
  }
  .stage {
    flex: 1 1 0; min-width: 180px;
    background: var(--grey-50); border: 1px solid var(--grey-200);
    border-radius: 10px; padding: 14px 16px;
    display: flex; flex-direction: column; gap: 6px;
  }
  .stage-num {
    width: 24px; height: 24px;
    background: var(--primary); color: white;
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 12px;
  }
  .stage-name { font-weight: 700; font-size: 14px; }
  .stage-body { font-size: 12px; color: var(--grey-600); line-height: 1.45; }
  .stage-body code { background: var(--grey-100); padding: 1px 4px; border-radius: 3px; }
  .stage-meta {
    font-size: 11px; color: var(--primary);
    font-weight: 600; margin-top: auto; padding-top: 6px;
    border-top: 1px dashed var(--grey-200);
  }
  .arrow {
    align-self: center; color: var(--grey-400);
    font-size: 18px; font-weight: 300;
  }

  /* Model cards */
  .model-grid {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 14px; margin-bottom: 12px;
  }
  .model-card {
    background: var(--grey-50); border: 1px solid var(--grey-200);
    border-radius: 12px; padding: 18px 20px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .model-tag {
    display: inline-block; width: fit-content;
    background: rgba(34,211,238,0.15); color: #0891B2;
    padding: 2px 10px; border-radius: 4px;
    font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
  }
  .model-name { font-size: 16px; font-weight: 700; letter-spacing: -0.01em; }
  .model-blurb { font-size: 12px; color: var(--grey-600); line-height: 1.55; }
  .model-blurb code { background: var(--grey-100); padding: 1px 4px; border-radius: 3px; }
  .model-why { font-size: 12px; color: var(--grey-700); line-height: 1.55; margin-top: 4px; padding-top: 8px; border-top: 1px dashed var(--grey-200); }

  /* Caveats */
  .caveats { display: flex; flex-direction: column; gap: 8px; }
  .caveat {
    display: flex; gap: 14px; align-items: flex-start;
    padding: 14px 16px;
    background: rgba(245,158,11,0.04);
    border-left: 3px solid #F59E0B;
    border-radius: 4px;
  }
  .caveat-num {
    font-family: ui-monospace, monospace;
    font-size: 11px; color: #F59E0B;
    font-weight: 700;
  }
  .caveat-body { font-size: 13px; color: var(--grey-700); line-height: 1.55; flex: 1; }
  .caveat-body b { color: var(--grey-800); }
  .caveat-body code { background: var(--grey-100); padding: 1px 5px; border-radius: 3px; }

  h2 {
    color: #22D3EE !important;
    font-size: 20px !important; font-weight: 600 !important;
    letter-spacing: -0.01em;
    margin-top: 40px !important; margin-bottom: 8px !important;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(34,211,238,0.20);
  }
  @media (prefers-color-scheme: light) {
    h2 { color: #0891B2 !important; border-bottom-color: rgba(8,145,178,0.25); }
    .page-intro { border-left-color: #0891B2; background: rgba(8,145,178,0.04); }
  }

  .page-footer {
    margin-top: 48px; padding-top: 20px;
    border-top: 1px solid var(--grey-200);
    font-size: 12px; color: var(--grey-500);
  }

  @media (max-width: 1100px) {
    .model-grid { grid-template-columns: 1fr; }
    .pipeline { flex-direction: column; }
    .arrow { transform: rotate(90deg); }
  }
</style>
