---
title: The Mood Curve
sidebar_position: 4
hide_title: true
full_width: true
---

<!-- HERO ====================================================== -->

<div class="hero">
  <div class="hero-brand">
    <div class="hero-logo">ST</div>
    <div>
      <div class="hero-title">Sentiment Timeline</div>
      <div class="hero-sub">The 2020/21 season as a single mood curve — match by match, with the rivalries called out</div>
    </div>
  </div>
  <div class="hero-meta">
    <span class="chip">Oct 2020 → May 2021</span>
    <span class="chip">10 matches scored</span>
    <span class="chip chip-crimson">2 El Clásicos</span>
    <span class="chip">VADER weighted by comment volume</span>
  </div>
</div>

<div class="page-intro">
Average sentiment per match looks calm. <strong>Volatility tells the real story</strong> — rivalry matches see fans argue regardless of result, while comfortable wins produce the quietest fanbases. Both signals plotted below.
</div>

<!-- KPI ROW ==================================================== -->

```sql season_kpis
select
    round(avg(ms.avg_sentiment)::numeric, 3)            as season_avg,
    round(avg(ms.sentiment_volatility)::numeric, 3)     as season_volatility,
    round(avg(ms.positive_ratio)::numeric, 3)           as season_pos_ratio,
    (select home_team || ' vs ' || away_team
       from fansphere.matches m2
       join fansphere.match_sentiment ms2 using(match_id)
       order by ms2.avg_sentiment desc limit 1)         as most_positive_match,
    (select home_team || ' vs ' || away_team
       from fansphere.matches m3
       join fansphere.match_sentiment ms3 using(match_id)
       order by ms3.sentiment_volatility desc limit 1)  as most_volatile_match
from fansphere.match_sentiment ms
```

<Grid cols=4>
  <BigValue data={season_kpis} value=season_avg     title="Season avg sentiment"   fmt='+0.000;-0.000' />
  <BigValue data={season_kpis} value=season_pos_ratio title="Season positive ratio"  fmt='0.0%' />
  <BigValue data={season_kpis} value=most_positive_match title="Happiest fixture" />
  <BigValue data={season_kpis} value=most_volatile_match title="Most argued fixture" />
</Grid>

<!-- ======================================================= -->

## Average sentiment, match by match

Above zero = net-positive fanbase that match, below zero = net-negative. Rivalry fixtures are flagged crimson — note how the El Clásicos sit right at the season average, not at the extremes.

```sql sentiment_timeline
select
    m.match_date,
    m.home_team || ' vs ' || m.away_team as match_label,
    ms.avg_sentiment,
    ms.sentiment_volatility,
    ms.positive_ratio,
    ms.negative_ratio,
    ms.comment_count,
    case when m.is_rivalry then 'Rivalry (El Clásico)' else 'Non-rivalry' end as category
from fansphere.matches m
join fansphere.match_sentiment ms using(match_id)
order by m.match_date
```

<LineChart
  data={sentiment_timeline}
  x=match_date
  y=avg_sentiment
  series=category
  colorPalette={['#E11D5C','#94A3B8']}
  xAxisTitle="Match date"
  yAxisTitle="Average sentiment (VADER, volume-weighted)"
  yFmt='+0.00;-0.00'
  yMin=0 yMax=0.25
  chartAreaHeight=320
  markers=true
  pointLabels=match_label
  pointLabelPosition=top
/>

<Alert status="info">
  <strong>The averages lie a bit:</strong> all 10 matches sit between +0.10 and +0.21 — the fanbase is broadly positive about a Barcelona-focused season. The interesting variance is <em>around</em> that average, which is what the next chart shows.
</Alert>

<!-- ======================================================= -->

## Volatility — where the arguments were

Volatility = standard deviation of comment sentiment within the match. Higher bars = louder disagreement during play, not after the fact. <strong>This is where rivalries actually show up.</strong>

```sql volatility_bar
select
    home_team || ' vs ' || away_team as match_label,
    sentiment_volatility,
    match_date,
    case when is_rivalry then 'Rivalry' else 'Non-rivalry' end as category
from fansphere.matches m
join fansphere.match_sentiment ms using(match_id)
order by sentiment_volatility desc
```

<BarChart
  data={volatility_bar}
  x=match_label
  y=sentiment_volatility
  series=category
  colorPalette={['#E11D5C','#94A3B8']}
  swapXY=true
  sort=false
  xAxisTitle=""
  yAxisTitle="Sentiment volatility (within-match std dev)"
  yFmt='0.000'
  yMin=0.45 yMax=0.52
  chartAreaHeight=380
  labels=true
  labelFmt='0.000'
/>

<!-- ======================================================= -->

## The mood mix — positive vs negative share, per match

Stacked view of how the 93K comments split. Even at the volatile matches, the positive share stays around half — the *negative* share is what shifts.

```sql posneg_long
with base as (
    select m.match_date,
           m.home_team || ' vs ' || m.away_team as match_label,
           ms.positive_ratio, ms.negative_ratio
    from fansphere.matches m
    join fansphere.match_sentiment ms using(match_id)
)
select match_date, match_label, 'Positive' as polarity, positive_ratio as share from base
union all
select match_date, match_label, 'Negative', negative_ratio from base
order by match_date, polarity
```

<BarChart
  data={posneg_long}
  x=match_label
  y=share
  series=polarity
  type=grouped
  colorPalette={['#EF4444','#22C55E']}
  xAxisTitle=""
  yAxisTitle="Share of comments"
  yFmt='0.0%'
  yMin=0 yMax=0.6
  chartAreaHeight=320
  labels=true
  labelFmt='0%'
/>

<!-- ======================================================= -->

## The season ranked by mood swings

Use this as a quick reference: the table is sorted by volatility (most argued at the top), with average sentiment as a sanity column.

```sql mood_table
select
    rank() over (order by ms.sentiment_volatility desc) as "Rank by volatility",
    m.home_team || ' vs ' || m.away_team             as "Match",
    m.match_date                                      as "Date",
    case when m.is_rivalry then 'Rivalry' else '—' end as "Type",
    ms.comment_count                                  as "Comments",
    ms.avg_sentiment                                  as "Avg sentiment",
    ms.sentiment_volatility                           as "Volatility",
    ms.positive_ratio                                 as "% positive",
    ms.negative_ratio                                 as "% negative"
from fansphere.matches m
join fansphere.match_sentiment ms using(match_id)
order by ms.sentiment_volatility desc
```

<DataTable data={mood_table} rows=10 rowShading=true>
  <Column id="Rank by volatility" align=center/>
  <Column id="Match" wrap=true/>
  <Column id="Date" fmt='dd mmm yyyy'/>
  <Column id="Type" align=center/>
  <Column id="Comments" align=right fmt='#,##0' contentType=colorscale colorScale=engagement/>
  <Column id="Avg sentiment" align=right fmt='+0.000;-0.000'/>
  <Column id="Volatility" align=right fmt='0.000' contentType=colorscale colorScale=engagement/>
  <Column id="% positive" align=right fmt='0.0%'/>
  <Column id="% negative" align=right fmt='0.0%'/>
</DataTable>

<div class="page-footer">
  <span>Volatility uses comment-level VADER sentiment within a 4-hour window centred on kickoff · Page 5 has the model details</span>
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
