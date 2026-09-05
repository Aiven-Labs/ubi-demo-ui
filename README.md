# UBI Demo UI

This app demonstrates how User Behavior Insights (UBI) turns search logs into relevance signals:

- `ubi_queries` captures what users searched and what results were shown.
- `ubi_events` captures what users did (clicks, scroll, dwell time).
- Combining both gives actionability (for example: low CTR queries, high dwell results, weak results worth tuning).

## Features

- Search page backed by OpenSearch index `products_ubi_demo`
- Automatic UBI query capture via `ext.ubi` in search requests
- Scroll-based dwell measurements per result card
- Click events per result
- Real-time metrics panel (query volume, CTR, average dwell, top queries)

## Screenshots

### Demo UI

Search results and live UBI metrics for `racing game` (ESCI-S sample):

![Demo UI — racing game search](img/query_racing_game.png)

Same UI for an `asus` query:

![Demo UI — asus search](img/query_asus.png)

### OpenSearch Dashboards — product data

Dev Tools query against `products_ubi_demo` for `racing game`, showing indexed product `_source` (title, category, description):

![OpenSearch Dashboards — products_ubi_demo](img/osd_racing_game.png)

### OpenSearch Dashboards — `ubi_queries`

A logged search in `ubi_queries`: `user_query`, `query_id`, the executed query DSL, and the ordered hit IDs returned to the UI:

![OpenSearch Dashboards — ubi_queries](img/osd_ubi_query_racing.png)

### OpenSearch Dashboards — `ubi_events`

Engagement events in `ubi_events` for the same `racing game` query (`scroll_dwell`, position, `dwell_ms`, scroll depth), linked back by `query_id`:

![OpenSearch Dashboards — ubi_events](img/osd_ubi_events_racing.png)

## Environment variables

- `OPENSEARCH_URL` (required): injected by Aiven app integration to `os-5c7d963`
- `SEARCH_INDEX` (optional, default: `products_ubi_demo`)

## Local run

1. Create a `.env` file in the project root (already gitignored):

```bash
OPENSEARCH_URL=https://user:password@your-opensearch-host:port
```

2. Install and start:

```bash
pip install -r requirements.txt
python app.py
```

Open [http://localhost:8000](http://localhost:8000)

`load_dotenv()` reads `.env` for local development and does not override variables already set in the environment (for example Aiven app integrations).
