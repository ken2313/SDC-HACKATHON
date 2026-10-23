"""FastAPI entry point.

Run locally from the backend folder:
    uvicorn app.main:app --reload --port 8000
Interactive API docs: http://127.0.0.1:8000/docs
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (makes sure every table is registered)
from app.database import Base, SessionLocal, engine
from app.integrations import orbyte_mock
from app.routers import access, activity_logs, alerts, inventory, purchase_orders
from app.seed.seed_data import seed_if_empty, seed_suppliers_if_missing
from app.services.alert_service import reconcile_all


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)  # creates tables that do not exist yet
    with SessionLocal() as db:
        if os.getenv("AUTO_SEED", "true").lower() == "true" and seed_if_empty(db):
            print("Seeded synthetic demo data.")
        # Feature 3: demo suppliers for a database created before suppliers existed (safe to repeat)
        if os.getenv("AUTO_SEED", "true").lower() == "true":
            seed_suppliers_if_missing(db)
        # Open alerts for products that are already low (safe to repeat)
        reconcile_all(db)
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

app.include_router(orbyte_mock.router)
app.include_router(inventory.router)
app.include_router(alerts.router)
app.include_router(purchase_orders.router)
app.include_router(activity_logs.router)
app.include_router(access.router)


@app.get("/api/health", tags=["System"])
def health_check():
    return {"status": "ok"}
