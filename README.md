# bookstore-delivery

Delivery **classification & dispatch bot** for the Enterprise Book Store
platform. Automates classification of orders based on **quantity, price, and
availability** to decide dispatch time from the store and other delivery
features. Maintains a **delivery-status timeline** that works in tandem with
`bookstore-tracking` to show per-order status on the orders page.

> **Status:** Initial scaffolding only. Files below are placeholders — no
> business logic is implemented yet.

## Responsibilities

- Classify each order using quantity, price, and stock availability.
- Decide dispatch time from the store and other delivery attributes
  (priority tier, packaging, carrier window).
- Maintain a delivery-status timeline per order, kept in sync with the
  tracking bot's checkpoints.
- Schedule classification/dispatch jobs on **Celery** and execute them
  asynchronously.

## Tech Stack

- **FastAPI** — ASGI web framework
- **Celery + Redis** — async task scheduling/execution (broker + result backend)
- **Pydantic v2** — data validation
- **httpx** — calls into the Django backend and the tracking service
- **Render** — hosting platform

## Architecture (planned)

```
app/
├── main.py                     FastAPI app + router wiring
├── celery_app.py               Celery application + beat schedule
├── core/
│   ├── config.py               Settings (pydantic-settings)
│   ├── backend_client.py       httpx client for the Django backend
│   └── tracking_client.py      httpx client for the tracking service
├── routers/
│   ├── health.py               GET /health
│   └── delivery.py             Delivery/classification endpoints
├── services/
│   ├── classifier.py           Order classification (qty / price / availability)
│   ├── dispatch_service.py     Dispatch-time decisioning
│   └── timeline_service.py     Delivery-status timeline management
├── tasks/
│   └── delivery_tasks.py       Celery tasks (classify, schedule dispatch)
└── schemas/                    Request/response models
```

## Local Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and configure environment file
cp .env.example .env

# 4. Start Redis (broker), the API, and a Celery worker (separate shells)
uvicorn app.main:app --reload --port 8004
celery -A app.celery_app worker --loglevel=info
celery -A app.celery_app beat --loglevel=info
```

## Deployment

Deploys on **Render free tier** via `render.yaml` (Blueprint) as a **single
Docker web service**. Render's free tier has no separate `worker` service and
no managed Redis, so — exactly like `bookstore-backend` — one container runs the
FastAPI app + Celery worker + Celery beat together under **supervisord**
(`supervisord.conf`), and Celery reuses the **shared Render Redis** instance via
`REDIS_URL` (the same Redis the Django backend uses). No new Redis is
provisioned.
