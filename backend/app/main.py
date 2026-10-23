"""FastAPI entry point.

Run locally from the backend folder:
    uvicorn app.main:app --reload --port 8000
Interactive API docs: http://127.0.0.1:8000/docs
"""
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (makes sure every table is registered)
from app.auth.login import require_login
from app.database import Base, SessionLocal, engine
from app.integrations import orbyte_mock
from app.routers import (
    access,
    activity_logs,
    alerts,
    anomalies,
    auth,
    dashboard,
    forecasts,
    inventory,
    purchase_orders,
    settings,
    supplier_orders,
    suppliers,
)
from app.schema_upgrade import upgrade_schema
from app.seed.history_data import seed_history_if_missing
from app.seed.seed_data import seed_if_empty, seed_suppliers_if_missing
from app.services.alert_service import reconcile_all
from app.services.order_tracking_service import backfill_history


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)  # creates tables that do not exist yet
    # Feature 6: add new optional columns to tables from older databases (safe to repeat)
    for column in upgrade_schema(engine):
        print(f"Database upgraded: added column {column}.")
    with SessionLocal() as db:
        if os.getenv("AUTO_SEED", "true").lower() == "true" and seed_if_empty(db):
            print("Seeded synthetic demo data.")
        # Feature 3: demo suppliers for a database created before suppliers existed (safe to repeat)
        if os.getenv("AUTO_SEED", "true").lower() == "true":
            seed_suppliers_if_missing(db)
        # Feature 7: about 30 days of synthetic stock history for the demo products, so the
        # dashboard trends have data. Skips products already used in a demo (safe to repeat).
        if os.getenv("AUTO_SEED", "true").lower() == "true" and os.getenv("SEED_HISTORY", "true").lower() == "true":
            if seed_history_if_missing(db):
                print("Added synthetic stock history for the demo products.")
        # Open alerts for products that are already low (safe to repeat)
        reconcile_all(db)
        # Feature 5: give orders from before order tracking a starting timeline entry (safe to repeat)
        backfill_history(db)
    yield


app = FastAPI(
    title="Smart Inventory & Supplier Order Management (MVP)",
    description="Hackathon MVP. All data is synthetic. Orbyte integration is simulated.",
    version="0.1.0",
    lifespan=lifespan,
)

# The Vite dev server proxies /api to this server, so CORS is rarely needed.
# These origins only matter if the browser calls the backend directly.
allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Signing in is open; everything else needs a signed-in session (see app/auth/login.py).
app.include_router(auth.router)
SIGNED_IN = [Depends(require_login)]
for module in (
    orbyte_mock, inventory, alerts, purchase_orders, supplier_orders, suppliers,
    dashboard, forecasts, anomalies, settings, activity_logs, access,
):
    app.include_router(module.router, dependencies=SIGNED_IN)


@app.get("/api/health", tags=["System"])
def health_check():
    return {"status": "ok"}