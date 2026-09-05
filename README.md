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
