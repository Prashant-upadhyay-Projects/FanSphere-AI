---
title: What's New
sidebar_position: 6
hide_title: true
full_width: true
---

<div class="hero">
  <div class="hero-brand">
    <div class="hero-logo">FS</div>
    <div>
      <div class="hero-title">What's New</div>
      <div class="hero-sub">Release notes · changes are receipted to the experiment that produced them</div>
    </div>
  </div>
  <div class="hero-meta">
    <span class="chip chip-crimson">v1.1 (current)</span>
    <span class="chip">AutoResearch-tuned</span>
    <span class="chip">9 experiments</span>
  </div>
</div>

<div class="page-intro">
Every model choice on this dashboard used to be a gut call. As of <strong>v1.1</strong>, the two
weakest assumptions were re-tuned by an autonomous experiment loop (a Karpathy-style
<em>AutoResearch</em> ratchet: propose → test → keep only if it beats a label-grounded metric →
revert otherwise). The receipts below show exactly what changed, by how much, and which experiment
earned it.
</div>

## v1.1 · Scientific tuning via AutoResearch · 2026-06-04

| Decision | v1.0 (before) | v1.1 (after) | Measured result | Experiment |
|---|---|---|---|---|
| **Fan clustering** | KMeans k=3 · StandardScaler · silhouette **0.40** | KMeans **k=4** · **RobustScaler** · silhouette **0.64** | Cohorts separate far better; a distinct **Ultra** tier (19 power users) emerges | Phase 1 (H1.1 + H1.2) |
| **Engagement blend** | **0.5** football / **0.5** fan | **0.35** football / **0.65** fan | **El Clásico #4 → #1**; rivalry vs non-rivalry separation (AUC) **0.50 → 0.81** | Phase 3 (H3.1) |
| **Sentiment model** | VADER · mean aggregation | *unchanged* | All 6 model×aggregation combos tested. Confirmed a real ceiling (~0.58); sentiment is low-leverage here, so nothing was shipped | Phase 2 (H2.1–H2.3) |

<Alert status="info">
  <strong>Why trust these?</strong> Each change was kept only because it <em>strictly</em> beat the
  previous best on a metric grounded in real labels already in the data (cluster silhouette; and how
  well rivalry fixtures separate from the rest). 9 experiments ran in total: 6 kept, 2 discarded, 1
  reverted. Full audit trail in <code>Autoresearch_fansphere/RESEARCH_REPORT.md</code>.
</Alert>

### The headline: the El Clásico fix

v1.0's even 50/50 split buried El Clásico at #4, below 7-goal blowouts. Odd for a *fan*-intelligence
platform. Weighting the fan signal higher (0.35/0.65) lifts it to **#1**, where a charged, high-volume
rivalry reaction belongs. See the live ranking on the **Executive Overview**.

### The new Ultra cohort

k=4 + RobustScaler (median/IQR scaling, which stops a handful of heavy-upvote power users from
distorting the space) split the old "Highly Engaged" group cleanly, surfacing **The Ultra**: 19
authors posting ~500 comments each. See **The Tribes**.

## v1.0 · Initial release

StatsBomb fixtures + Reddit Pushshift comments · VADER sentiment · KMeans k=3 segmentation ·
0.5/0.5 engagement blend · Evidence.dev dashboard.

<div class="page-footer">
  <span>Tuning loop: Karpathy-style AutoResearch · usage-guarded · graduated 2026-06-03 · see <code>Autoresearch_fansphere/</code></span>
</div>

<style>
  .content-container, .content, main { max-width: 1400px !important; }

  .hero {
    background: linear-gradient(135deg, rgba(225,29,92,0.10) 0%, rgba(225,29,92,0) 60%);
    border: 1px solid var(--grey-200);
    border-radius: 16px; padding: 28px 32px; margin: 0 0 24px 0;
    display: flex; flex-direction: column; gap: 18px;
  }
  .hero-brand { display: flex; align-items: center; gap: 16px; }
  .hero-logo {
    width: 56px; height: 56px; background: var(--primary); color: white; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 18px; letter-spacing: -0.5px;
    box-shadow: 0 4px 16px rgba(225,29,92,0.30);
  }
  .hero-title { font-size: 30px; font-weight: 700; letter-spacing: -0.5px; line-height: 1.1; }
  .hero-sub  { font-size: 14px; color: var(--grey-500); margin-top: 5px; }
  .hero-meta { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    display: inline-block; background: var(--grey-100); color: var(--grey-700);
    padding: 4px 12px; border-radius: 99px; font-size: 12px; font-weight: 500;
  }
  .chip-crimson { background: rgba(225,29,92,0.15); color: var(--primary); }

  .page-intro {
    font-size: 14px; color: var(--grey-600); margin: 0 0 24px 0; padding: 14px 18px;
    border-left: 3px solid #E11D5C; background: rgba(225,29,92,0.04); border-radius: 4px;
  }
  .page-intro strong { color: var(--grey-800); }

  h2 {
    color: #E11D5C !important; font-size: 20px !important; font-weight: 600 !important;
    letter-spacing: -0.01em; margin-top: 40px !important; margin-bottom: 8px !important;
    padding-bottom: 6px; border-bottom: 1px solid rgba(225,29,92,0.20);
  }
  h3 { font-size: 16px !important; font-weight: 600 !important; margin-top: 24px !important; }
  @media (prefers-color-scheme: light) {
    h2 { color: #A50044 !important; border-bottom-color: rgba(165,0,68,0.25); }
    .page-intro { border-left-color: #A50044; background: rgba(165,0,68,0.04); }
  }

  .page-footer {
    margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--grey-200);
    font-size: 12px; color: var(--grey-500);
  }
</style>
