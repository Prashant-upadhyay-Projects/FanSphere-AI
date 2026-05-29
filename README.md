# FanSphere AI

> Football audience intelligence system — 907K fan comments cross-referenced against 10 La Liga fixtures to separate engagement volume from engagement intensity.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Evidence.dev](https://img.shields.io/badge/Evidence.dev-0.36-E11D5C)
![DuckDB](https://img.shields.io/badge/DuckDB-1.x-FFF000)
![License](https://img.shields.io/badge/license-MIT-22C55E)

FanSphere AI investigates how football matches move fan communities. It joins on-pitch event data (StatsBomb) with subreddit conversation (Reddit), scores sentiment at comment level, segments authors into behavioural cohorts, and produces a composite engagement signal that decouples raw volume from emotional intensity.

**Headline finding:** El Clásico generates the highest raw comment volume in the dataset and ranks #7 of 10 on combined engagement. Volume and excitement are orthogonal signals.

---

## Why It Exists

Commercial and content teams at top clubs consume the same primitives: who is engaging, when, how strongly, and against which fixture. This system implements those primitives on open data — a reference architecture for fan behavioural intelligence, and a research probe into whether on-pitch events causally drive online fan affect or merely correlate with it.

---

## System Architecture

```mermaid
flowchart TB
    subgraph SOURCES[" Raw sources "]
        direction LR
        S1["StatsBomb Open Data\nLa Liga 2020/21 · 10 fixtures · 53 goals"]
        S2["Reddit Pushshift\nr/barca + r/realmadrid · 907,158 comments"]
    end

    subgraph ETL[" Python pipeline — src/ "]
        direction TB
        E1["load_statsbomb.py\nfixtures · scorelines · xG"]
        E2["load_reddit_archive.py\nJSONL → parquet"]
        L1["link_comments_to_matches.py\nconfidence scored joins"]
        N1["sentiment.py\nVADER · NLTK"]
        N2["generate_metrics.py\nKMeans k=3 · author cohorts"]
        SC["engagement.py\n0.5 × football + 0.5 × fan"]
    end

    subgraph STORE[" Storage "]
        DB[("fansphere.duckdb\n8 tables · parquet cache")]
    end

    subgraph VIZ[" Intelligence interface "]
        direction LR
        V1["Evidence.dev\n5-page interactive dashboard"]
        V2["fansphere_5pages_preview.html\nstandalone static render"]
    end

    S1 --> E1
    S2 --> E2
    E1 --> L1
    E2 --> L1
    L1 --> N1
    L1 --> N2
    N1 --> SC
    N2 --> SC
    SC --> DB
    DB --> V1
    DB --> V2

    classDef src fill:#1C2230,stroke:#E11D5C,color:#F9FAFB
    classDef etl fill:#161B22,stroke:#22D3EE,color:#F9FAFB
    classDef store fill:#0E1117,stroke:#FBBF24,color:#F9FAFB
    classDef viz fill:#1C2230,stroke:#22C55E,color:#F9FAFB
    class S1,S2 src
    class E1,E2,L1,N1,N2,SC etl
    class DB store
    class V1,V2 viz
```

---

## Pipeline Components

| Module | Responsibility |
|---|---|
| `load_statsbomb.py` | Fixture ingestion, rivalry tagging, xG |
| `load_reddit_archive.py` | Pushshift JSONL → parquet (907K comments) |
| `link_comments_to_matches.py` | Confidence scored comment-to-fixture joins (threshold 0.40) |
| `sentiment.py` | VADER compound scoring per comment |
| `generate_metrics.py` | KMeans k=3 author segmentation (silhouette 0.40) |
| `engagement.py` | Composite score: `0.5 × football_norm + 0.5 × fan_blend` |

Core logic lives in [`src/engagement.py`](src/engagement.py) and [`src/link_comments_to_matches.py`](src/link_comments_to_matches.py).

---

## Key Findings

| Fixture | Goals | Combined | Fan Score |
|---|---|---|---|
| Real Sociedad 1–6 Barcelona | 7 | **0.690** | 0.380 |
| Barcelona 5–2 Real Betis | 7 | **0.636** | 0.272 |
| Levante 3–3 Barcelona | 6 | **0.583** | 0.500 |
| El Clásico — Barcelona 1–3 Real Madrid | 4 | 0.563 | **0.681** |

El Clásico drew 17,089 comments — the highest raw volume in the dataset — yet ranks 4th overall. Rivalry volatility saturates the fan signal while goal count anchors the combined score. The divergence between those two axes is precisely the signal sponsors and broadcasters care about: a low-scoring Clásico still outperforms a seven-goal non-rivalry fixture on fan-side affect.

---

## Research Questions

The system was designed around four open questions:

1. Does rivalry sentiment correlate with match intensity, or do they operate on independent axes?
2. Can subreddit behavioural signatures predict post-match engagement before kickoff?
3. How does fan cohort composition shift across fixture types (rivalry vs. routine)?
4. What is the marginal effect of an additional goal on combined engagement score?

Findings so far suggest questions 1 and 4 have cleaner answers than 2 and 3 — the latter two remain active areas of extension.

---

## Quick Start

```bash
git clone https://github.com/Prashant-upadhyay-Projects/FanSphere-AI.git
cd FanSphere-AI
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Stages 1 and 2 — StatsBomb pipeline
python main.py --skip-reddit --no-persist

# Stage 3 — sentiment and segmentation (requires Reddit JSONL archives)
python -m src.load_reddit_archive --input data/raw/reddit --output data/interim/reddit_comments.parquet
jupyter nbconvert --to notebook --execute --inplace notebooks/stage3_audience_sentiment.ipynb

# Intelligence interface
cd dashboard/app && npm install && npm run sources && npm run dev
```

No Reddit data? **[Open the live dashboard preview →](https://htmlpreview.github.io/?https://github.com/Prashant-upadhyay-Projects/FanSphere-AI/blob/master/dashboard/fansphere_5pages_preview.html)** — standalone static render of all five pages, no install required.

Copy `.env.example` → `.env` and populate credentials before running the pipeline.

---

## Stack

`Python` · `pandas` · `VADER / NLTK` · `scikit-learn` · `DuckDB` · `Evidence.dev` · `ECharts`

---

## Future Direction

1. Replace VADER with a specialist football-domain transformer model
2. Expand across multiple seasons and competitions (UCL, Premier League)
3. Live ingestion via Reddit API with fixture-aware temporal windowing
4. Probabilistic match state modelling driven by xG timelines
5. Cohort stability analysis across consecutive seasons to measure fan drift

---

## License

MIT — see [`LICENSE`](LICENSE).
StatsBomb data: [StatsBomb Open Data license](https://github.com/statsbomb/open-data#license) — non-commercial use, attribution required.
Reddit content: sourced from public Pushshift archives for analytical use only.
