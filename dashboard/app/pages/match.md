---
title: The Match Lens
sidebar_position: 3
hide_title: true
full_width: true
---

<!-- HERO ====================================================== -->

<div class="hero">
  <div class="hero-brand">
    <div class="hero-logo">M2</div>
    <div>
      <div class="hero-title">Match Drill Down</div>
      <div class="hero-sub">Pick a fixture · watch how 90 minutes of football moves a fanbase, minute by minute</div>
    </div>
  </div>
  <div class="hero-meta">
    <span class="chip chip-crimson">10 fixtures</span>
    <span class="chip">53 goals · with xG</span>
    <span class="chip">93,298 comments aligned to kickoff</span>
    <span class="chip">15-min sentiment buckets</span>
  </div>
</div>

<div class="page-intro">
Each match becomes a story when you align comments to kickoff. <strong>The goals tell you what happened. The comment curve tells you what mattered.</strong> Pick a fixture below, and the rest of the page re-renders for that match.
</div>

<!-- MATCH PICKER =============================================== -->

```sql match_list
select
    match_id,
    home_team || ' vs ' || away_team
      || ' (' || home_score || '-' || away_score || ')'
      || case when is_rivalry then '  ⚔ Clásico' else '' end as match_label,
    match_date
from fansphere.matches
order by match_date
```

<Dropdown
  name=match_pick
  data={match_list}
  value=match_id
  label=match_label
  defaultValue=3773585
  title="Select match"
/>

<!-- MATCH KPIS ================================================= -->

```sql match_meta
select
    m.match_id,
    m.home_team || ' vs ' || m.away_team as match_label,
    m.home_score || '-' || m.away_score as score_str,
    m.match_date,
    m.total_goals,
    m.is_rivalry,
    ms.comment_count,
    ms.avg_sentiment,
    ms.sentiment_volatility,
    ms.positive_ratio,
    ms.negative_ratio,
    ms.peak_hour_count,
    ms.engagement_score
from fansphere.matches m
join fansphere.match_sentiment ms using(match_id)
where m.match_id = '${inputs.match_pick.value}'
```

<Grid cols=4>
  <BigValue
    data={match_meta}
    value=comment_count
    title="Comments linked"
    fmt='#,##0'
  />
  <BigValue
    data={match_meta}
    value=peak_hour_count
    title="Peak hour volume"
    fmt='#,##0'
  />
  <BigValue
    data={match_meta}
    value=avg_sentiment
    title="Avg sentiment"
    fmt='+0.000;-0.000'
  />
  <BigValue
    data={match_meta}
    value=engagement_score
    title="Fan engagement score"
    fmt='0.000'
  />
</Grid>

<!-- ======================================================= -->

## Goals as they happened, with the xG behind each one

Every goal is one bar; bar height = xG (expected-goals quality). A lucky long shot reads short. A tap in from a textbook move reads tall.

```sql goals
select
    minute,
    team,
    player,
    xg,
    team as series
from fansphere.goal_events
where match_id = '${inputs.match_pick.value}'
order by minute
```

<BarChart
  data={goals}
  x=minute
  y=xg
  series=team
  xAxisTitle="Minute"
  yAxisTitle="xG (expected goals quality)"
  yFmt='0.00'
  chartAreaHeight=260
  labels=true
  labelFmt='0.00'
  xMin=0 xMax=95
/>

<Alert status="info">
  <strong>Reading xG:</strong> A high bar means the chance was "should have scored from there." A low bar means a brilliant or lucky finish. Compare the bar pattern to the comment curve below to see how each goal moved the fanbase.
</Alert>

<!-- ======================================================= -->

## How fans reacted, minute by minute

15-minute buckets aligned to kickoff (bucket 0 = kickoff). Above 0 on the y-axis = positive sentiment, below 0 = negative. Bar width is unchanged; what shifts is **how loud each window was**.

```sql comment_curve
select
    floor(minutes_from_kickoff / 15) * 15           as min_from_ko,
    count(*)                                         as comments,
    avg(sentiment_score)                             as avg_sentiment
from fansphere.comments_enriched
where match_id = '${inputs.match_pick.value}'
  and minutes_from_kickoff between -30 and 180
group by 1
order by 1
```

<BarChart
  data={comment_curve}
  x=min_from_ko
  y=comments
  xAxisTitle="Minutes from kickoff (negative = pre-match)"
  yAxisTitle="Comment volume"
  yFmt='#,##0'
  chartAreaHeight=240
  colorPalette={['#E11D5C']}
/>

<LineChart
  data={comment_curve}
  x=min_from_ko
  y=avg_sentiment
  xAxisTitle="Minutes from kickoff"
  yAxisTitle="Average sentiment (per 15-min bucket)"
  yFmt='+0.00;-0.00'
  yMin=-0.5 yMax=0.8
  chartAreaHeight=240
  colorPalette={['#E11D5C']}
  markers=true
/>

<!-- ======================================================= -->

## Sentiment mix: positive, neutral, negative

The composition of the conversation. A skewed positive match feels different to one where positive and negative were equal even with high average.

```sql sentiment_mix
select
    sentiment_label,
    count(*)                              as comments,
    round(100.0 * count(*)
          / sum(count(*)) over (), 1)    as share_pct
from fansphere.comments_enriched
where match_id = '${inputs.match_pick.value}'
group by sentiment_label
order by case sentiment_label
           when 'positive' then 1
           when 'neutral'  then 2
           else 3 end
```

<BarChart
  data={sentiment_mix}
  x=sentiment_label
  y=share_pct
  series=sentiment_label
  colorPalette={['#22C55E','#94A3B8','#EF4444']}
  xAxisTitle=""
  yAxisTitle="Share of comments (%)"
  yFmt='0.0'
  chartAreaHeight=240
  labels=true
  labelFmt='0.0"%"'
/>

<!-- ======================================================= -->

## The receipts: top fan quotes from this match

Highest scored comments on each side, after kickoff. These are the lines the fanbase upvoted; click through if you want to verify on Reddit later.

```sql top_pos
select
    body as "Comment",
    score as "Upvotes",
    subreddit as "Sub"
from fansphere.comments_enriched
where match_id = '${inputs.match_pick.value}'
  and sentiment_label = 'positive'
  and minutes_from_kickoff between 0 and 150
order by score desc
limit 5
```

```sql top_neg
select
    body as "Comment",
    score as "Upvotes",
    subreddit as "Sub"
from fansphere.comments_enriched
where match_id = '${inputs.match_pick.value}'
  and sentiment_label = 'negative'
  and minutes_from_kickoff between 0 and 150
order by score desc
limit 5
```

### <span class="quote-h good">Loudest praise</span>

<DataTable data={top_pos} rows=5 rowShading=true>
  <Column id="Comment" wrap=true/>
  <Column id="Upvotes" align=right fmt='#,##0'/>
  <Column id="Sub" align=center/>
</DataTable>

### <span class="quote-h bad">Loudest criticism</span>

<DataTable data={top_neg} rows=5 rowShading=true>
  <Column id="Comment" wrap=true/>
  <Column id="Upvotes" align=right fmt='#,##0'/>
  <Column id="Sub" align=center/>
</DataTable>

<div class="page-footer">
  <span>Curves use VADER sentiment scored at the comment level, bucketed by minutes from kickoff · Methodology details on Page 5</span>
</div>

<style>
  /* Widen the page (overrides Evidence default max-width) */
  .content-container,
  .content,
  main {
    max-width: 1400px !important;
  }

  /* HERO */
  .hero {
    background: linear-gradient(135deg, rgba(225,29,92,0.10) 0%, rgba(225,29,92,0) 60%);
    border: 1px solid var(--grey-200);
    border-radius: 16px;
    padding: 28px 32px;
    margin: 0 0 20px 0;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  .hero-brand { display: flex; align-items: center; gap: 16px; }
  .hero-logo {
    width: 56px; height: 56px;
    background: var(--primary);
    color: white;
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 18px; letter-spacing: -0.5px;
    box-shadow: 0 4px 16px rgba(225,29,92,0.30);
  }
  .hero-title {
    font-size: 30px; font-weight: 700; letter-spacing: -0.5px;
    line-height: 1.1;
  }
  .hero-sub {
    font-size: 14px; color: var(--grey-500); margin-top: 5px;
  }
  .hero-meta { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    display: inline-block;
    background: var(--grey-100);
    color: var(--grey-700);
    padding: 4px 12px;
    border-radius: 99px;
    font-size: 12px;
    font-weight: 500;
  }
  .chip-crimson {
    background: rgba(225,29,92,0.15);
    color: var(--primary);
  }

  /* Per-page intro line */
  .page-intro {
    font-size: 14px;
    color: var(--grey-600);
    margin: 0 0 24px 0;
    padding: 14px 18px;
    border-left: 3px solid #E11D5C;
    background: rgba(225,29,92,0.04);
    border-radius: 4px;
  }
  .page-intro strong { color: var(--grey-800); }

  /* Section headings (H2): crimson, descriptive, with subtle underline */
  h2 {
    color: #E11D5C !important;
    font-size: 20px !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em;
    margin-top: 40px !important;
    margin-bottom: 8px !important;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(225,29,92,0.20);
  }
  h3 { margin-top: 24px; margin-bottom: 8px; }
  .quote-h {
    font-size: 14px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .quote-h.good { color: #22C55E; }
  .quote-h.bad  { color: #EF4444; }

  @media (prefers-color-scheme: light) {
    h2 { color: #A50044 !important; border-bottom-color: rgba(165,0,68,0.25); }
    .page-intro { border-left-color: #A50044; background: rgba(165,0,68,0.04); }
  }

  .page-footer {
    margin-top: 48px;
    padding-top: 20px;
    border-top: 1px solid var(--grey-200);
    font-size: 12px;
    color: var(--grey-500);
  }
</style>
