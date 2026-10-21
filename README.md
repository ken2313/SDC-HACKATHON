# Smart Inventory & Supplier Order Management System

Hackathon MVP for the **Orbyte Smart SME Challenge: Less Busywork, Better Business** (sponsored by Alpha Red Solutions).

A module that could plug into Orbyte and help Malaysian micro and small businesses watch stock, order from suppliers and catch unusual inventory movements, with a human approving every consequential action.

> **All data in this project is synthetic.** The Orbyte integration is **simulated**. The endpoints under `/api/orbyte-mock` are **not official Orbyte APIs**.

## Build status

We build **one feature at a time**.

| # | Feature | Status |
|---|---|---|
| 1 | Inventory management | **Code complete. Team must run the checks below before relying on it** |
| 2 | Automatic low-stock alerts | Planned |
| 3 | Automatic purchase order generation | Planned |
| 4 | Human approval and activity logs (full RBAC + log page) | Planned (backend permission checks and audit-log writing already started in Feature 1) |
| 5 | Supplier order tracking | Planned |
| 6 | Supplier management | Planned |
| 7 | Inventory dashboard | Planned |
| 8 | Demand forecasting | Planned |
| 9 | AI anomaly detection on RunPod GPU | Planned |
| 10 | Simulated Orbyte integration | Started (session/role mock); grows with each feature |

### Feature 1 verification checklist (tick when YOU have done it)

- [ ] `pytest -v` passes in `backend/`
- [ ] `npm run build` succeeds in `frontend/`
- [ ] Manual demo steps below work in the browser
- [ ] Replit run works (see Replit section)

## Technology stack

- **Frontend:** React, Vite, Tailwind CSS (Recharts arrives with the dashboard, Feature 7)
- **Backend:** Python, FastAPI, REST
- **Database:** SQLite via SQLAlchemy
- **AI (Feature 9):** PyTorch autoencoder served from a RunPod Serverless GPU endpoint
- **Tools:** VSCode (coding), GitHub (version control), Replit (running and demoing)

## Folder structure

```
backend/
  app/
    main.py            FastAPI entry point
    database.py        SQLite + SQLAlchemy setup
    constants.py       roles, statuses, movement types
    models/            database tables
    schemas/           input validation / output shapes (Pydantic)
    routers/           HTTP endpoints (thin)
    services/          business rules (stock, audit log)
    auth/              simulated session + permission checks
    integrations/      orbyte_mock.py (SIMULATED), runpod_client.py (Feature 9)
    seed/              synthetic Malaysian SME data
  tests/               pytest tests
frontend/
  src/ api/ components/ context/ pages/ utils/
docs/DECISIONS.md      why things are built this way
```

## Run it on Windows with VSCode (two terminals)

Needs Python 3.11+, Node.js 20+ and Git.

**Terminal 1: backend**
```powershell
cd backend
py -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
If PowerShell refuses to run the activate script, run this once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

The first start creates `backend/data/inventory.db` and fills it with demo data. API docs: http://127.0.0.1:8000/docs

**Terminal 2: frontend**
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173

**Run the backend tests** (Terminal 1, venv active):
```powershell
cd backend
pytest -v
```

**Reset the demo data:** stop the backend, delete `backend/data/inventory.db`, start it again.

## Run it on Replit

1. Replit → **Create App → Import from GitHub** → paste the repo URL.
2. Click **Run**. `run.sh` installs dependencies and starts both servers. The Vite page on port 5173 is the public URL.
3. Secrets (later, for RunPod) go in Replit's **Secrets** tool, never in files.
4. After pushing from VSCode, use Replit's **Git** pane → **Pull**.

> The `.replit` / `run.sh` setup has not been tested on Replit yet. If Run fails, copy the console error and we will adjust it.

## Environment variables

See `.env.example`. Copy it to `.env` (ignored by Git). Feature 1 needs none of them: the defaults work.

## Feature 1: what it does

- Add, edit, archive and restore products (Owner only)
- Table with name, SKU, category, supplier, quantity, reorder threshold, status
- Search (name, SKU, category, supplier), category filter, status filter, sorting, "Show archived"
- Add or remove stock (Owner and Employee). Quantity cannot go below zero
- Status is calculated automatically: **Out of Stock** = 0, **Low Stock** = at or below the threshold, **In Stock** = above it
- Stock history per product (who, when, before → after, reason)
- Safe retries: a repeated request cannot change stock twice
- Every change is stored in the database and written to the audit log (`activity_logs` table)

### API summary

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/inventory` | Owner, Employee | List/search/filter/sort products |
| GET | `/api/inventory/summary` | Owner, Employee | Counts for the page header |
| GET | `/api/inventory/categories` | Owner, Employee | Category names |
| POST | `/api/inventory` | Owner | Add product |
| GET | `/api/inventory/{id}` | Owner, Employee | One product |
| PATCH | `/api/inventory/{id}` | Owner | Edit details (not quantity) |
| POST | `/api/inventory/{id}/archive` | Owner | Archive |
| POST | `/api/inventory/{id}/restore` | Owner | Restore |
| POST | `/api/inventory/{id}/movements` | Owner, Employee | Add or remove stock |
| GET | `/api/inventory/{id}/movements` | Owner, Employee | Stock history |
| GET | `/api/orbyte-mock/users`, `/context` | anyone / session | **SIMULATED** Orbyte session |

Every request carries `X-User-Id` (simulated Orbyte session). Missing or unknown user gives 401. A role without permission gives 403. Another business's product gives 404.

### Manual demo (the café scenario)

1. Top-right dropdown: choose **Hafiz Ismail (employee)** under *Kopi Kita Café*.
2. Find **Fresh Milk 1L**: 20 cartons, reorder at 10, **In Stock**.
3. Click **Stock** → *Remove stock* → 15. The preview shows 5 cartons and **Low Stock**. Confirm.
4. Try removing 6 more: the form blocks it ("Only 5 available").
5. Note there are no Add/Edit/Archive buttons for the employee. In http://127.0.0.1:8000/docs, a `POST /api/inventory` with header `X-User-Id: 2` returns **403**.
6. Switch to **Aisyah Rahman (owner)**: add a product, edit a threshold, archive and restore a product.
7. Switch to **Din Hassan** (*Kedai Runcit Pak Din*): a different business with different products.
8. Optional: open `backend/data/inventory.db` in *DB Browser for SQLite* and look at `stock_movements` and `activity_logs`. (The Activity Logs page arrives in Feature 4.)

## Orbyte integration assumptions

We have no access to Orbyte's real APIs. The mock layer (`backend/app/integrations/orbyte_mock.py`) assumes a host platform would tell our module: which business is calling, which user, and their role. We turn the role into permissions and write completed actions to the audit log. In a real integration the `X-User-Id` header would be replaced by Orbyte's verified token.

## Known limitations (Feature 1)

- The simulated session has no passwords. It demonstrates role rules, not real security.
- The supplier on a product is plain text until Feature 6.
- The product list is not paginated (fine for SME-sized catalogues).
- No Activity Logs page yet (Feature 4). Logs are written to the database already.
- Quantities are whole numbers only.
- Timestamps display in the browser's local time.

## Future improvements

Alerts, purchase orders, supplier tracking, dashboard, forecasting, RunPod GPU anomaly detection, CSV import/export, barcode scanning.

## Git workflow

One branch per feature, one commit per completed feature, merge to `main` by pull request.

```powershell
git checkout -b feature/1-inventory
git add .
git status          # check: no .env, no node_modules, no .db files in the list
git commit -m "feat(inventory): add inventory management with stock movements, RBAC and audit log (Feature 1)"
git push -u origin feature/1-inventory
```
