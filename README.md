# Smart Inventory & Supplier Order Management System

> A web module for Malaysian micro and small businesses that watches stock, drafts supplier purchase orders when items run low, tracks each order through to delivery, and uses a GPU-served AI model to flag unusual stock movements, with a human approving every consequential action and every step written to an audit log.

Built for the **Orbyte Smart SME Challenge: Less Busywork, Better Business** (sponsored by Alpha Red Solutions).

---

## Team Information

| Field                  | Details                                                                                      |
| ---------------------- | -------------------------------------------------------------------------------------------- |
| **Team Name**          | Bashamel                                                                                     |
| **Team Domain**        | Domain 2                                                                                     |
| **SDG Track (1–17)**   | SDG 8 — Decent Work and Economic Growth & SDG 9 — Industry, Innovation and Infrastructure    |
| **Team Leader**        | Tatiana Razak                                                                                |
| **University**         | Asia Pacific University                                                                      |
| **Number of Members**  | 5                                                                                            |

## Links

| Resource          | Link                                                       |
| ----------------- | ---------------------------------------------------------- |
| GitHub Repository | https://github.com/ken2313/SDC-HACKATHON                   |
| Replit Project    | https://smart-inventory-sdc.replit.app                     |
| Live Demo         | https://smart-inventory-sdc.replit.app                     |
| RunPod Endpoint   | RunPod Serverless endpoint (Load Balancer type), protected by an API key and token, so not a public URL. Proof of use in `submission/` |
| Slide Deck        | https://canva.link/7dbl8mch23qoyl0                         |
| Demo Video        | https://youtu.be/hEYaJW694Vw                                             |

**Demo sign-in:** `business123@gmail.com` / `SISO67#` (a synthetic demo account, not a real mailbox).

---

## Overview

### Problem

Many Malaysian micro and small businesses, such as cafés and neighbourhood grocery shops, still track stock by memory or in notebooks. Shortages are noticed only after an item runs out, supplier orders are placed by hand, and there is rarely a record of who ordered or approved what. The owner loses time on busywork and sales to empty shelves, and small mistakes such as double orders, wrong quantities, missed deliveries or an unnoticed large stock write-off quietly cost money.

### Solution

The system is built as a module that could plug into the Orbyte platform (the Orbyte layer is **simulated** in this project). It removes repetitive work and keeps a human in charge:

1. Stock only changes through recorded stock movements, so every change has a who, when and why.
2. A low-stock alert opens and closes automatically when an item reaches its reorder level.
3. The system prepares a **draft** purchase order using the cheapest active supplier, grouped by supplier. It never orders anything on its own.
4. Only the **owner** can approve or reject an order. Staff can prepare and edit drafts and track deliveries.
5. Deliveries are confirmed once and update inventory exactly once. Every step lands in an append-only activity log.
6. A 7-day moving-average forecast estimates demand and run-out dates, with a backtested accuracy score.
7. A small **PyTorch autoencoder** running on a **RunPod Serverless GPU endpoint** scores every stock-out. Unusual ones are flagged as *potential* anomalies for a person to review. The AI never changes stock.

### Where AI is used (and where it is not)

Only the anomaly detector is AI. Low-stock alerts, supplier selection and purchase order drafting are rule-based, and the forecast is a statistical moving average, not machine learning. This is deliberate: the rules are easy to explain to a shop owner, and AI is used only where "does this look normal?" is hard to hard-code.

### Key Features

- **Inventory management** — Add, edit, archive and restore products. Stock status (In / Low / Out of Stock) is calculated, never stored, and quantity can never go below zero.
- **Automatic low-stock alerts** — Alerts open and resolve automatically, with at most one open alert per product and urgency levels (Critical, Urgent, Low).
- **Purchase order drafts** — Quantity refills to 2 × the reorder level (respecting supplier minimums), the cheapest active supplier is chosen, and the owner approves or rejects with a written reason.
- **Role-based approval and audit trail** — Owner / employee permissions are enforced on the backend. Blocked attempts are logged, and the Activity Logs page (owner only) shows previous and updated values.
- **Supplier order tracking** — Approved → Ordered → Shipped / Delayed → Delivered, with an overdue flag, a timeline per order, and triple protection against updating stock twice.
- **Supplier management** — Contacts, delivery times, and per-product price lists that drive supplier selection, plus order history and late-delivery statistics.
- **Dashboard** — Owner-facing totals, trends and an AI anomaly summary card.
- **Demand forecasting** — 7-day moving average, run-out estimates and forecast-based reorder quantities. Each product gets a backtested accuracy score: for each of the last 14 days we forecast from the 7 days before it and compare with actual use (accuracy = 100% − total error ÷ total actual use). Below 50% the forecast is marked "uncertain". On our demo data the average was about 71%.
- **AI anomaly detection** — Each stock-out is scored by the RunPod model as Normal, Unusual or Highly Unusual, with the top contributing factor and the expected range. Flags go to a review queue; reviewing needs the `anomalies:review` permission and is written to the activity log. If the AI is unreachable the app carries on and shows "AI unavailable".
- **Sign-in and Settings** — Demo sign-in with a backend-checked, salted-hash password and a signed 12-hour session. Owners can rename the business and switch automatic draft ordering on or off.

### Tech Stack

| Layer         | Technology                                                                    |
| ------------- | ----------------------------------------------------------------------------- |
| Frontend      | React 19, Vite 7, Tailwind CSS 4, React Router 7, Recharts (plain JavaScript) |
| Backend       | Python 3.11, FastAPI, SQLAlchemy 2, Pydantic 2                                |
| Database      | SQLite                                                                        |
| AI / Compute  | PyTorch autoencoder served by FastAPI in a Docker container on RunPod Serverless (CUDA GPU) |
| Hosting       | Replit (hosts and publishes the app)                                          |
| Built with    | Claude Code (Sonnet 5.5) for code generation, directed and tested by the team |

---

## Project Structure

```
.
├── ai/                        # Anomaly model and its inference service (runs on RunPod)
│   ├── data_gen.py            # Synthetic normal + anomalous usage data
│   ├── features.py            # 5 input features
│   ├── model.py               # Autoencoder (5 → 3 → 5)
│   ├── train.py               # Trains on normal usage only, sets thresholds
│   ├── server.py              # FastAPI inference service (/health, /ping, /score)
│   ├── Dockerfile             # Container for RunPod Serverless (with .dockerignore)
│   ├── serverless.md          # Step-by-step Serverless setup
│   ├── start_server.sh        # Alternative: one-command start on a RunPod Pod
│   ├── latency_test.py        # Measures inference and end-to-end latency
│   ├── test_request.py        # Sends a sample request
│   ├── model.pt, scaler.json, config.json   # Trained weights, scaling, thresholds, metrics
│   ├── integration.md         # How the backend uses the service (written for the Pod setup)
│   └── requirements.txt
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── database.py        # SQLite + SQLAlchemy setup
│   │   ├── models/            # Database tables
│   │   ├── schemas/           # Input validation / output shapes
│   │   ├── routers/           # HTTP endpoints (inventory, alerts, orders, anomalies, auth, ...)
│   │   ├── services/          # Business rules (stock, alerts, orders, forecast, anomalies, audit log)
│   │   ├── auth/              # Sign-in, session and permission checks
│   │   ├── integrations/      # orbyte_mock.py (SIMULATED) and ai_client.py (RunPod client)
│   │   └── seed/              # Synthetic Malaysian SME demo data
│   ├── tests/                 # pytest tests
│   └── requirements.txt
├── frontend/
│   └── src/                   # api/, components/, context/, pages/, utils/
├── docs/
│   └── DECISIONS.md           # Why things are built this way
├── submission/                # Required submission documents
│   ├── SDC2026_Bashamel_Preliminary.pdf
│   ├── SDC2026_Bashamel_TechDeclaration.pdf
│   ├── SDC2026_Bashamel_Replit_POU.pdf
│   └── SDC2026_Bashamel_Runpod_POU.pdf
├── .env.example               # Example environment variables
├── .replit                    # Replit run configuration
├── run.sh                     # Starts backend and frontend together (Replit)
├── LICENSE
└── README.md
```

> **Note on layout:** the hackathon template uses `src/` and `runpod/`. We use `backend/` and `frontend/` instead of `src/` (the app is started with `run.sh`), `ai/` instead of `runpod/` (our RunPod Serverless service and its Dockerfile), and `backend/tests/` instead of `tests/`.

### Architecture

```
Browser (React + Vite)
        │  /api requests (Vite proxies to FastAPI)
        ▼
FastAPI backend ──► SQLite (inventory, orders, suppliers, activity logs, anomaly flags)
        │
        ├──► Simulated Orbyte layer (business, user and role)
        │
        └──► ai_client.py ──HTTPS: Authorization (RunPod API key) + x-api-token──►
                 (background task, after the stock-out is saved;
                  long timeout for cold starts, one retry,
                  never blocks or changes stock)
                                                                     │
                                       RunPod Serverless endpoint (Load Balancer)
                                       Docker container: FastAPI /score + /ping
                                       PyTorch autoencoder on a GPU worker
                                       (scales to zero when idle)
```

All data is synthetic. The endpoints under `/api/orbyte-mock` are **not official Orbyte APIs**.

---

## How to Run

### Option 1 — Run on Replit (Recommended)

Live copy: https://smart-inventory-sdc.replit.app

1. In Replit choose **Create App → Import from GitHub** and paste the repository URL.
2. Click **Run**. Replit uses `.replit` to run `bash run.sh`, which installs dependencies and starts the FastAPI backend (port 8000) and the Vite frontend (port 5173). The Vite page is the public URL.
3. To turn on AI anomaly detection, add `AI_BASE_URL` (`https://<endpoint-id>.api.runpod.ai`), `INFERENCE_TOKEN`, `RUNPOD_API_KEY` and `AI_TIMEOUT_S` (`90`, so a sleeping worker has time to start) in the **Secrets** tab (🔒), then republish. Without them the app works normally and the AI page shows "AI unavailable".

### Option 2 — Run Locally

Requires Python 3.11+, Node.js 20+ and Git.

```bash
# 1. Clone the repository
git clone https://github.com/ken2313/SDC-HACKATHON.git
cd SDC-HACKATHON

# 2. Terminal 1: backend
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Terminal 2: frontend (open a new terminal in the repo root)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and sign in with the demo account above. Interactive API docs are at http://127.0.0.1:8000/docs (call `POST /api/auth/login`, then **Authorize** with the token). The first start creates `backend/data/inventory.db` and fills it with demo data. To reset, stop the backend, delete that file and start again.

After signing in, use the user switcher (top right) to try the roles, for example **Aisyah Rahman (owner)** and **Hafiz Ismail (employee)** at *Kopi Kita Café*.

### Run Tests

```bash
cd backend
pytest -v
```

The backend has over 200 automated tests, including the AI client (tested against a fake AI server, so no GPU is needed). The inference service also has its own checks, `python ai/latency_test.py` and `python ai/test_request.py`, which need the endpoint running.

---

## How We Use Replit *(Required)*

- **Hosting:** `.replit` and `run.sh` start the FastAPI backend and the Vite frontend together. The Vite page on port 5173 is the single public URL, and it forwards `/api` to the backend. The deployed app is at https://smart-inventory-sdc.replit.app.
- **Development:** Replit was used to host and publish the app. It imports the code from GitHub and the team republishes after each merge. It was not used to generate code (see "How We Built It").
- **Secrets:** `AI_BASE_URL`, `INFERENCE_TOKEN`, `RUNPOD_API_KEY` and `AI_TIMEOUT_S` are stored in Replit Secrets, never in the code. `.env` is git-ignored and only `.env.example` is committed.

📄 Proof of use: [`submission/SDC2026_Bashamel_Replit_POU.pdf`](submission/SDC2026_Bashamel_Replit_POU.pdf)

## How We Use RunPod *(Required)*

- **Workload:** A small PyTorch autoencoder (5 inputs → 3 → 5) is trained on normal stock usage only. The inputs are how big a stock-out is compared with the recent average, how many standard deviations away it is, how variable recent usage has been, and the day of the week. A large reconstruction error means the movement does not look like normal usage. The Unusual and Highly Unusual thresholds are the 95th and 99th percentiles of validation error.
- **Setup:** `ai/server.py` is a FastAPI inference service (`/health`, `/ping`, `/score`). `ai/Dockerfile` packages it with the trained model on a PyTorch + CUDA base image, and the image is deployed as a **RunPod Serverless endpoint** of the **Load Balancer** type, with 0 always-on workers and a small GPU. RunPod starts a GPU worker only when a request arrives and stops it when idle, so we pay only for the seconds it works. `/health` reports the device so we can confirm it is on `cuda`. Full steps are in [`ai/serverless.md`](ai/serverless.md). The earlier Pod setup (`ai/start_server.sh`) still works.
- **Integration:** After a stock-out is saved, a background task in the FastAPI backend (`anomaly_service.py` → `integrations/ai_client.py`) sends the movement to the endpoint with the RunPod API key (`Authorization: Bearer`) and our own token (`x-api-token`). The result is stored in the `anomaly_flags` table and shown on the AI Anomaly Detection page and dashboard. The keys stay in the backend only and are never exposed to frontend code. Stock movements carry an idempotency key (`request_id`), so a retry cannot create a duplicate flag. The client never raises: on timeout or error the app continues and shows "AI unavailable".
- **Trade-off:** when no worker is awake, the first request waits for a cold start (often tens of seconds). The check runs in the background after the stock change, so nobody waits on the page; the flag just appears a little later. Before a demo we send one test request so a worker is warm.
- **Measured earlier on a GPU Pod (2026-10-23):** server inference median about 1.6 ms; end-to-end about 380–415 ms, almost all of it network. We have not re-measured on Serverless, where cold starts dominate.

Example request:

```bash
curl -X POST "$AI_BASE_URL/score" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "x-api-token: $INFERENCE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "mov-123",
    "product_id": "milk",
    "movement_type": "OUT",
    "quantity": 40,
    "day_of_week": 2,
    "recent_avg_usage": 10,
    "usage_std": 2,
    "history_days": 30
  }'
```

The response contains `status` (Normal, Unusual, Highly Unusual, Insufficient data, Not supported), `anomaly_score`, `top_contributing_features`, `expected_range` and `inference_ms`. A flag is a *potential anomaly for human review, not a confirmed error*.

**Honest note on accuracy.** On our synthetic test set the autoencoder scores AUC 0.988, precision 0.556 and recall 0.909. A plain z-score baseline scores AUC 0.999, precision 0.579 and recall 1.0, so on this simple synthetic data the baseline does as well or better. We kept the autoencoder because it learns a combined picture of normal behaviour across several signals and gives a path to richer inputs later, but we do not claim it beats simple statistics here.

📄 Proof of use: [`submission/SDC2026_Bashamel_Runpod_POU.pdf`](submission/SDC2026_Bashamel_Runpod_POU.pdf)

---

## How We Built It (AI-assisted development)

We used AI tools and declare them in the Technology Declaration:

- **Claude Code (Anthropic, Sonnet 5.5)** generated the backend and frontend code. The team directed the work, ran the app against written manual demo scripts, ran the automated backend tests (over 200) and fixed what failed.
- **Claude** also helped draft this README and the submission documents, which were checked against the repository.
- **Replit** was used only to host and publish the app, not to generate code.
- The anomaly model is our own: it was trained from scratch on synthetic data we generated. No pre-trained models or external datasets are used.

## Challenges & Learnings

- **Keeping everything consistent.** Stock, alerts, drafts and the audit log must agree. Each stock change happens in one database transaction, and deliveries are protected three ways so stock can never be updated twice.
- **AI must never block the business.** The anomaly check runs after the stock-out is saved, with a timeout and one retry, so a slow or sleeping GPU worker cannot affect stock.
- **Being honest about AI.** We separated the autoencoder from rule-based features and the statistical forecast, and compared the model against a simple baseline instead of assuming the GPU model wins.
- **Cost and cold starts.** A Pod bills every hour it is on, so we moved the model to a RunPod Serverless endpoint that scales to zero. The price is a cold start on the first request, which is why the AI check runs in the background. Campus Wi-Fi also blocked the RunPod proxy during early Pod testing.
- **Honest model limits.** In live testing the model flagged a normal removal of a low-volume product as Highly Unusual. This is why flags are only prompts for a human to check.
- **What we learned.** None of us had deployed a model on a GPU before, so we learned the full path from a trained PyTorch model to a working service: packaging it with Docker, serving it with FastAPI, and calling it securely from the backend with a token and API key. We started on a RunPod GPU Pod, found it costs money for every hour it is on, and moved to RunPod Serverless, where it scales to zero but has slow cold starts. That taught us to run the AI check in the background so it can never block stock updates. We also learned to test claims honestly: a simple z-score baseline matched our autoencoder, so we report that instead of overselling the AI.

## Known Limitations

- All data is synthetic; the Orbyte integration is simulated.
- The database is SQLite only (a non-SQLite `DATABASE_URL` is ignored). A hosted database is future work.
- Forecast accuracy (about 71% on average in our demo data) reflects synthetic history, not real shop sales. Products with under 7 days of data get no forecast, and under 14 days show a "limited history" warning.
- Sign-in is a single demo account; a real deployment would use Orbyte's own login.
- The anomaly model is trained on synthetic data and only scores stock-outs (OUT movements). It can raise false alarms on low-volume products, and the first check after the endpoint has been idle is slow because of the cold start.
- The AI check needs the Serverless endpoint and its secrets to be set up; without them the rest of the app works and the AI page shows "AI unavailable".

## Future Improvements

- [ ] Train the anomaly model on real shop data and compare it again against the baseline
- [ ] Tune the anomaly thresholds and handling of low-volume products
- [ ] Move from SQLite to a hosted database
- [ ] Replace the simulated Orbyte session with a verified Orbyte token
- [ ] Email or push notifications for alerts
- [ ] CSV import/export and barcode scanning

## Team

| Name           | Role                | GitHub                                              |
| -------------- | ------------------- | --------------------------------------------------- |
| Tatiana Razak  | Team Leader; AI and integration (RunPod) | [@tatyraz](https://github.com/tatyraz) |
| TASNIM ELSAYED | Backend and frontend (per git history) | [@TasnimElzanaty](https://github.com/TasnimElzanaty) |
| MEHREEN MEHRAJ | Frontend (Replit) and Prototype Pitching         | **[TODO]**                                          |
| YESNA FAISAL   | Video & SLide Production & Forms/Documents Submissions       | @yesnafaizal14                                          |
| TAN KEN POH    | Pitching on Prototype Demo           | @ken2313                                          |

The repository is owned by [@ken2313](https://github.com/ken2313). **[TODO: confirm each member's name and role.]**

---

## Submission Checklist

- [x] Team name, domain (Domain 1 / Domain 2) and SDG track filled in
- [x] Slide deck link added
- [x] Demo video link added
- [x] Replit used, with proof of use in `submission/`
- [x] RunPod used, with proof of use in `submission/`
- [x] Preliminary submission completed (`SDC2026_Bashamel_Preliminary.pdf`)
- [x] Technology declaration completed (`SDC2026_Bashamel_TechDeclaration.pdf`)
- [x] Submission files renamed with your team name (replace `TeamName`)
- [x] "How to Run" steps verified
- [x] No API keys or secrets committed to the repository

## License

This project is licensed under the [Apache License 2.0](LICENSE).
