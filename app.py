import codecs
import json
import os
import re
import time
import uuid
from urllib.parse import unquote, urlparse

import requests
import zstandard as zstd
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "").strip()
SEARCH_INDEX = os.getenv("SEARCH_INDEX", "products_ubi_demo")
# Full ESCI-S dump includes top-level `image` URLs; the GitHub sample.json.gz omits them.
ESCI_S_FULL_URL = "https://esci-s.s3.amazonaws.com/esci.json.zst"
ESCI_S_SEED_LIMIT = 4000
DEMO_DOCS = [
    {"id": "sku-001", "title": "Wireless Noise-Canceling Headphones", "category": "audio", "price": 199.99, "description": "Over-ear headphones with active noise cancellation, deep bass, and 40-hour battery life.", "image_url": "https://picsum.photos/id/180/320/220"},
    {"id": "sku-002", "title": "Bluetooth Earbuds Pro", "category": "audio", "price": 89.0, "description": "Pocket-size earbuds with clear voice pickup, low latency mode, and all-day battery with charging case.", "image_url": "https://picsum.photos/id/367/320/220"},
    {"id": "sku-003", "title": "Mechanical Keyboard TKL", "category": "accessories", "price": 129.0, "description": "Compact tenkeyless mechanical keyboard with hot-swappable tactile switches and per-key RGB lighting.", "image_url": "https://picsum.photos/id/1/320/220"},
    {"id": "sku-004", "title": "Ergonomic Vertical Mouse", "category": "accessories", "price": 59.0, "description": "Vertical design to reduce wrist strain during long sessions, with adjustable DPI and silent clicks.", "image_url": "https://picsum.photos/id/48/320/220"},
    {"id": "sku-005", "title": "4K Webcam with HDR", "category": "video", "price": 149.0, "description": "Ultra HD webcam with auto framing, low-light enhancement, and dual microphones for remote meetings.", "image_url": "https://picsum.photos/id/250/320/220"},
    {"id": "sku-006", "title": "USB-C Docking Station", "category": "accessories", "price": 179.0, "description": "Single-cable laptop dock with dual monitor output, Ethernet, and high-speed USB ports.", "image_url": "https://picsum.photos/id/160/320/220"},
    {"id": "sku-007", "title": "Portable SSD 2TB", "category": "storage", "price": 189.0, "description": "Rugged external SSD with high transfer speed for creators and developers on the go.", "image_url": "https://picsum.photos/id/1060/320/220"},
    {"id": "sku-008", "title": "Ultrawide Monitor 34-inch", "category": "display", "price": 499.0, "description": "Curved ultrawide display with high refresh rate and color-accurate panel for productivity and gaming.", "image_url": "https://picsum.photos/id/119/320/220"},
    {"id": "sku-009", "title": "Laptop Stand Aluminum", "category": "accessories", "price": 39.0, "description": "Adjustable stand for improved posture and airflow, suitable for laptops up to 16 inches.", "image_url": "https://picsum.photos/id/20/320/220"},
    {"id": "sku-010", "title": "Conference Speakerphone", "category": "audio", "price": 119.0, "description": "360-degree microphone array with echo cancellation for clear hybrid meeting audio.", "image_url": "https://picsum.photos/id/99/320/220"},
]


def _client():
    if not OPENSEARCH_URL:
        raise RuntimeError("OPENSEARCH_URL is not set")
    parsed = urlparse(OPENSEARCH_URL)
    if not parsed.scheme or not parsed.hostname:
        raise RuntimeError("OPENSEARCH_URL must be a valid URL")
    host = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        host += f":{parsed.port}"
    session = requests.Session()
    if parsed.username:
        session.auth = (unquote(parsed.username), unquote(parsed.password or ""))
    return session, host


def _os_request(method: str, path: str, payload=None, timeout=20):
    session, host = _client()
    response = session.request(
        method=method,
        url=f"{host}{path}",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _parse_price(value):
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    match = re.search(r"[\d.,]+", text)
    if not match:
        return 0.0
    num = match.group(0)
    if "," in num and "." in num:
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif "," in num:
        parts = num.split(",")
        num = num.replace(",", ".") if len(parts[-1]) == 2 else num.replace(",", "")
    try:
        return float(num)
    except ValueError:
        return 0.0


def _price_from_esci(item):
    price = _parse_price(item.get("price"))
    if price > 0:
        return price
    formats = item.get("formats") or {}
    for raw in formats.values():
        price = _parse_price(raw)
        if price > 0:
            return price
    return 0.0


def _category_from_esci(item):
    category = item.get("category") or []
    if isinstance(category, list):
        parts = [str(part).strip() for part in category if str(part).strip()]
        return " › ".join(parts) if parts else "uncategorized"
    text = str(category).strip()
    return text or "uncategorized"


def _description_from_esci(item):
    description = (item.get("description") or item.get("desc") or "").strip()
    if description:
        return description[:2000]
    bullets = item.get("bullets") or []
    if isinstance(bullets, list):
        joined = " ".join(str(b).strip() for b in bullets if str(b).strip())
        if joined:
            return joined[:2000]
    return ""


def _image_url_from_esci(item):
    # ESCI-S schema: top-level main image URL, e.g.
    # "image": "https://m.media-amazon.com/images/I/81bdoltQWVL.__AC_SY300_SX300_QL70_FMwebp_.jpg"
    image = item.get("image")
    if isinstance(image, str):
        return image.strip()
    return ""


def _doc_from_esci(item):
    if item.get("type") == "error":
        return None
    asin = (item.get("asin") or "").strip()
    title = (item.get("title") or "").strip()
    if not asin or not title:
        return None
    return {
        "id": asin,
        "title": title,
        "category": _category_from_esci(item),
        "description": _description_from_esci(item),
        "price": _price_from_esci(item),
        "image_url": _image_url_from_esci(item),
    }


def _demo_docs():
    return list(DEMO_DOCS)


def _esci_s_docs(limit=ESCI_S_SEED_LIMIT):
    docs = []
    with requests.get(ESCI_S_FULL_URL, stream=True, timeout=120) as response:
        response.raise_for_status()
        response.raw.decode_content = False
        dctx = zstd.ZstdDecompressor()
        decoder = codecs.getincrementaldecoder("utf-8")()
        with dctx.stream_reader(response.raw) as reader:
            buffer = ""
            while len(docs) < limit:
                chunk = reader.read(65536)
                if not chunk:
                    buffer += decoder.decode(b"", final=True)
                    break
                buffer += decoder.decode(chunk)
                while "\n" in buffer and len(docs) < limit:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    doc = _doc_from_esci(json.loads(line))
                    if doc:
                        docs.append(doc)
    return docs


def _recreate_index():
    try:
        _os_request("DELETE", f"/{SEARCH_INDEX}")
    except Exception:
        pass
    _os_request("PUT", f"/{SEARCH_INDEX}", {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "title": {"type": "text"},
                "category": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "description": {"type": "text"},
                "price": {"type": "float"},
                "image_url": {"type": "keyword"},
            }
        },
    })


def _bulk_index(docs, batch_size=200):
    session, host = _client()
    indexed = 0
    for start in range(0, len(docs), batch_size):
        batch = docs[start:start + batch_size]
        bulk_ops = []
        for doc in batch:
            bulk_ops.append({"index": {"_index": SEARCH_INDEX, "_id": doc["id"]}})
            bulk_ops.append(doc)
        response = session.post(
            f"{host}/_bulk?refresh=false",
            headers={"Content-Type": "application/x-ndjson"},
            data="\n".join(json.dumps(op) for op in bulk_ops) + "\n",
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("errors"):
            failed = sum(1 for item in result.get("items", []) if "error" in item.get("index", {}))
            raise RuntimeError(f"Bulk indexing failed for {failed} documents")
        indexed += len(batch)
    _os_request("POST", f"/{SEARCH_INDEX}/_refresh")
    return indexed


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/seed")
def seed():
    body = request.get_json(force=True, silent=True) or {}
    dataset = (body.get("dataset") or "demo").strip().lower()
    loaders = {
        "demo": _demo_docs,
        "esci-s": _esci_s_docs,
    }
    if dataset not in loaders:
        return jsonify({"error": f"Unknown dataset '{dataset}'. Use: {', '.join(loaders)}"}), 400
    docs = loaders[dataset]()
    _recreate_index()
    indexed = _bulk_index(docs)
    with_images = sum(1 for doc in docs if doc.get("image_url"))
    return jsonify({
        "ok": True,
        "dataset": dataset,
        "indexed_docs": indexed,
        "with_images": with_images,
    })


@app.post("/api/search")
def search():
    body = request.get_json(force=True, silent=True) or {}
    query_text = (body.get("query") or "").strip()
    session_id = (body.get("sessionId") or "").strip()
    client_id = (body.get("clientId") or "demo-client").strip()
    query_id = str(uuid.uuid4())
    if not query_text:
        return jsonify({"error": "query is required"}), 400
    payload = {
        "size": 20,
        "ext": {
            "ubi": {
                "query_id": query_id,
                "user_query": query_text,
                "client_id": client_id,
                "object_id_field": "id",
                "query_attributes": {
                    "channel": "ubi-demo-ui",
                    "session_id": session_id,
                },
            }
        },
        "query": {
            "multi_match": {
                "query": query_text,
                "fields": ["title^2", "description", "category"],
            }
        },
    }
    response = _os_request("POST", f"/{SEARCH_INDEX}/_search", payload)
    hits = [
        {
            "id": h.get("_source", {}).get("id", h.get("_id")),
            "title": h.get("_source", {}).get("title", ""),
            "description": h.get("_source", {}).get("description", ""),
            "category": h.get("_source", {}).get("category", ""),
            "price": h.get("_source", {}).get("price", 0),
            "imageUrl": h.get("_source", {}).get("image_url", ""),
            "score": h.get("_score", 0),
        }
        for h in response.get("hits", {}).get("hits", [])
    ]
    return jsonify({
        "queryId": query_id,
        "total": response.get("hits", {}).get("total", {}).get("value", len(hits)),
        "tookMs": response.get("took", 0),
        "hits": hits,
    })


@app.post("/api/event")
def event():
    body = request.get_json(force=True, silent=True) or {}
    payload = {
        "action_name": body.get("actionName", "scroll_dwell"),
        "query_id": body.get("queryId"),
        "client_id": body.get("clientId", "demo-client"),
        "session_id": body.get("sessionId"),
        "timestamp": body.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user_query": body.get("userQuery", ""),
        "event_attributes": {
            "position": {"ordinal": body.get("position", 0)},
            "object": {"object_id": body.get("resultId", ""), "object_id_field": "id"},
            "dwell_ms": body.get("dwellMs", 0),
            "scroll_depth_percent": body.get("scrollDepthPercent", 0),
        },
    }
    _os_request("POST", "/ubi_events/_doc?refresh=false", payload)
    return jsonify({"ok": True})


@app.get("/api/ubi-summary")
def ubi_summary():
    queries = _os_request("POST", "/ubi_queries/_search", {
        "size": 0,
        "aggs": {
            "top_queries": {"terms": {"field": "user_query.keyword", "size": 5}},
            "total_queries": {"value_count": {"field": "query_id.keyword"}},
        },
    })
    events = _os_request("POST", "/ubi_events/_search", {
        "size": 0,
        "aggs": {
            "by_action": {"terms": {"field": "action_name.keyword", "size": 5}},
            "avg_dwell": {"avg": {"field": "event_attributes.dwell_ms"}},
        },
    })
    q_total = int(queries.get("aggregations", {}).get("total_queries", {}).get("value", 0))
    by_action_buckets = events.get("aggregations", {}).get("by_action", {}).get("buckets", [])
    by_action = {b["key"]: b["doc_count"] for b in by_action_buckets}
    clicks = by_action.get("click", 0)
    ctr = (clicks / q_total) if q_total else 0
    return jsonify({
        "totalQueries": q_total,
        "actionCounts": by_action,
        "avgDwellMs": round(events.get("aggregations", {}).get("avg_dwell", {}).get("value", 0) or 0, 2),
        "topQueries": [
            {"query": b["key"], "count": b["doc_count"]}
            for b in queries.get("aggregations", {}).get("top_queries", {}).get("buckets", [])
        ],
        "ctr": round(ctr, 4),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
