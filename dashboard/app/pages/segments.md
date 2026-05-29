---
title: The Tribes
sidebar_position: 2
hide_title: true
full_width: true
---

<!-- HERO ====================================================== -->

<div class="hero">
  <div class="hero-brand">
    <div class="hero-logo">FS</div>
    <div>
      <div class="hero-title">Fan Segmentation</div>
      <div class="hero-sub">3,628 authors · KMeans (k=3) on 5 behavioural features · silhouette 0.40</div>
    </div>
  </div>
  <div class="hero-meta">
    <span class="chip">Comment frequency</span>
    <span class="chip">Match coverage</span>
    <span class="chip">Avg sentiment</span>
    <span class="chip">Sentiment volatility</span>
    <span class="chip">Positive ratio</span>
  </div>
</div>

<div class="page-intro">
Most fanbase studies treat the audience as one block. Here, every Reddit author is a vector — and three groups fall out cleanly: <strong>Casuals who drop in, Tacticals who argue, and a tiny Highly-Engaged core that posts hundreds of times</strong>. The clusters explain why headline averages hide everything that matters.
</div>

<!-- PERSONA CARDS ============================================== -->

```sql segment_profile
select
    segment,
    count(*)                                            as authors,
    round(avg(comment_frequency)::numeric, 1)           as avg_comments,
    round(avg(matches_covered)::numeric, 2)             as avg_matches,
    round(avg(avg_sentiment)::numeric, 3)               as avg_sentiment,
    round(avg(sentiment_volatility)::numeric, 3)        as avg_volatility,
    round(avg(positive_ratio)::numeric, 3)              as avg_pos_ratio,
    round(avg(engagement_activity)::numeric, 1)         as avg_activity
from fansphere.fan_segments
group by segment
order by authors desc
```

```sql segment_casual
select * from ${segment_profile} where segment = 'Casual Fan'
```

```sql segment_tactical
select * from ${segment_profile} where segment = 'Tactical Fan'
```

```sql segment_highly
select * from ${segment_profile} where segment = 'Highly Engaged Fan'
```

<Grid cols=3>

  <div class="persona">
    <div class="persona-tag" style="background:rgba(148,163,184,0.15); color:#94A3B8;">CASUAL</div>
    <div class="persona-name">The Casual Fan</div>
    <div class="persona-count"><BigValue data={segment_casual} value=authors fmt='#,##0' /></div>
    <div class="persona-row"><span>Avg comments per author</span><b><Value data={segment_casual} column=avg_comments /></b></div>
    <div class="persona-row"><span>Matches covered</span><b><Value data={segment_casual} column=avg_matches /></b></div>
    <div class="persona-row"><span>Positive ratio</span><b><Value data={segment_casual} column=avg_pos_ratio /></b></div>
    <div class="persona-row"><span>Sentiment volatility</span><b><Value data={segment_casual} column=avg_volatility /></b></div>
    <div class="persona-blurb">Drop in, react, log off. <strong>Lower volatility, slightly more positive</strong> — they show up for big moments and skip the rest.</div>
  </div>

  <div class="persona">
    <div class="persona-tag" style="background:rgba(251,191,36,0.15); color:#FBBF24;">TACTICAL</div>
    <div class="persona-name">The Tactical Fan</div>
    <div class="persona-count"><BigValue data={segment_tactical} value=authors fmt='#,##0' /></div>
    <div class="persona-row"><span>Avg comments per author</span><b><Value data={segment_tactical} column=avg_comments /></b></div>
    <div class="persona-row"><span>Matches covered</span><b><Value data={segment_tactical} column=avg_matches /></b></div>
    <div class="persona-row"><span>Positive ratio</span><b><Value data={segment_tactical} column=avg_pos_ratio /></b></div>
    <div class="persona-row"><span>Sentiment volatility</span><b><Value data={segment_tactical} column=avg_volatility /></b></div>
    <div class="persona-blurb">The argumentative middle. <strong>Higher volatility, even split positive vs negative</strong> — they're the ones writing about Koeman's formation at half-time.</div>
  </div>

  <div class="persona">
    <div class="persona-tag" style="background:rgba(225,29,92,0.15); color:#E11D5C;">HIGHLY ENGAGED</div>
    <div class="persona-name">The Hardcore Core</div>
    <div class="persona-count"><BigValue data={segment_highly} value=authors fmt='#,##0' /></div>
    <div class="persona-row"><span>Avg comments per author</span><b><Value data={segment_highly} column=avg_comments /></b></div>
    <div class="persona-row"><span>Matches covered</span><b><Value data={segment_highly} column=avg_matches /></b></div>
    <div class="persona-row"><span>Positive ratio</span><b><Value data={segment_highly} column=avg_pos_ratio /></b></div>
    <div class="persona-row"><span>Sentiment volatility</span><b><Value data={segment_highly} column=avg_volatility /></b></div>
    <div class="persona-blurb">3% of authors, ~30% of the volume. <strong>Cover almost every match, post hundreds of times</strong>. Any product targeting "superfans" lives here.</div>
  </div>

</Grid>

<!-- ======================================================= -->

## How the three segments stack up by behaviour

Same five features the clustering used — now read across, not within, so you can see how different the segments actually are.

```sql segment_metrics_long
with base as (
    select segment,
           avg(comment_frequency)            as v_comments,
           avg(matches_covered)              as v_matches,
           avg(avg_sentiment)                as v_sentiment,
           avg(sentiment_volatility)         as v_volatility,
           avg(positive_ratio)               as v_pos_ratio
    from fansphere.fan_segments
    group by segment
)
select segment, 'Avg comments / author' as metric, v_comments as value from base
union all select segment, 'Matches covered',     v_matches      from base
union all select segment, 'Avg sentiment',       v_sentiment    from base
union all select segment, 'Volatility',          v_volatility   from base
union all select segment, 'Positive ratio',      v_pos_ratio    from base
order by metric
```

<BarChart
  data={segment_metrics_long}
  x=metric
  y=value
  series=segment
  type=grouped
  colorPalette={['#94A3B8','#E11D5C','#FBBF24']}
  yAxisTitle="Value (mixed units — read each metric on its own scale)"
  xAxisTitle=""
  yFmt='0.00'
  chartAreaHeight=360
/>

<Alert status="info">
  <strong>What jumps out:</strong> Hardcore fans post <strong>~11× more</strong> than Tacticals and <strong>~27× more</strong> than Casuals. They also cover <strong>~3× more matches</strong>. Their positive ratio sits right between the other two — they're loud, not louder-positive.
</Alert>

<!-- ======================================================= -->

## Every author plotted — coverage vs intensity

X = how many matches they showed up to. Y = total comment activity. Colour = segment. The clusters separate visually too — they're not arbitrary KMeans noise.

```sql author_scatter
select
    author,
    matches_covered,
    engagement_activity,
    comment_frequency,
    segment,
    case
      when segment = 'Casual Fan'         then 1
      when segment = 'Tactical Fan'       then 2
      else 3
    end as segment_order
from fansphere.fan_segments
order by segment_order, engagement_activity desc
```

<ScatterPlot
  data={author_scatter}
  x=matches_covered
  y=engagement_activity
  size=comment_frequency
  series=segment
  colorPalette={['#94A3B8','#FBBF24','#E11D5C']}
  xAxisTitle="Matches covered (of 10)"
  yAxisTitle="Engagement activity (total)"
  yScale=log
  yFmt='#,##0'
  chartAreaHeight=420
/>

<Alert status="info">
  <strong>Log y-axis used deliberately:</strong> the Hardcore cluster activity numbers (up to ~10,000) would compress the other two clusters into a single line on a linear scale. Log lets you see the structure inside each cluster.
</Alert>

<!-- ======================================================= -->

## The 15 loudest voices in the dataset

If you wanted to recruit a fan panel tomorrow, this is the shortlist.

```sql top_voices
select
    author as "Author",
    segment as "Segment",
    primary_subreddit as "Sub",
    comment_frequency as "Comments",
    matches_covered as "Matches",
    avg_sentiment as "Avg sentiment",
    sentiment_volatility as "Volatility",
    positive_ratio as "% positive"
from fansphere.fan_segments
order by engagement_activity desc
limit 15
```

<DataTable
  data={top_voices}
  rows=15
  rowShading=true
>
  <Column id="Author" wrap=true/>
  <Column id="Segment" align=center/>
  <Column id="Sub" align=center/>
  <Column id="Comments" align=right fmt='#,##0' contentType=colorscale colorScale=engagement/>
  <Column id="Matches" align=center contentType=colorscale colorScale=engagement/>
  <Column id="Avg sentiment" align=right fmt='+0.000;-0.000'/>
  <Column id="Volatility" align=right fmt='0.000'/>
  <Column id="% positive" align=right fmt='0.0%'/>
</DataTable>

<div class="page-footer">
  <span>Clustering: KMeans k=3 on standardised features (sklearn) · silhouette 0.40 · features explained on Page 5 (Methodology)</span>
</div>

<style>
  .content-container,
  .content,
  main {
    max-width: 1400px !important;
  }

  .hero {
    background: linear-gradient(135deg, rgba(225,29,92,0.10) 0%, rgba(225,29,92,0) 60%);
    border: 1px solid var(--grey-200);
    border-radius: 16px;
    padding: 28px 32px;
    margin: 0 0 20px 0;
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
    display: inline-block;
    background: var(--grey-100); color: var(--grey-700);
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

  /* Persona cards */
  .persona {
    background: var(--grey-50);
    border: 1px solid var(--grey-200);
    border-radius: 12px;
    padding: 20px 22px;
    display: flex; flex-direction: column; gap: 8px;
  }
  .persona-tag {
    display: inline-block; width: fit-content;
    padding: 3px 10px; border-radius: 4px;
    font-size: 10px; font-weight: 700;
    letter-spacing: 0.08em;
    margin-bottom: 4px;
  }
  .persona-name {
    font-size: 18px; font-weight: 700; letter-spacing: -0.01em;
  }
  .persona-count {
    margin: 4px 0 12px 0;
  }
  .persona-row {
    display: flex; justify-content: space-between;
    font-size: 12px; color: var(--grey-600);
    padding: 4px 0; border-bottom: 1px dashed var(--grey-200);
  }
  .persona-row b { color: var(--grey-800); font-weight: 600; }
  .persona-blurb {
    font-size: 12px; color: var(--grey-600);
    margin-top: 12px; line-height: 1.55;
  }
  .persona-blurb strong { color: var(--grey-800); }

  /* H2 — cyan chapter headings */
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
</style>
