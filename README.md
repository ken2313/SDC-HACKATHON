# Smart Inventory & Supplier Order Management System

Hackathon MVP for the **Orbyte Smart SME Challenge: Less Busywork, Better Business** (sponsored by Alpha Red Solutions).

A module that could plug into Orbyte and help Malaysian micro and small businesses watch stock, order from suppliers and catch unusual inventory movements, with a human approving every consequential action.

> **All data in this project is synthetic.** The Orbyte integration is **simulated**. The endpoints under `/api/orbyte-mock` are **not official Orbyte APIs**.

## Build status

We build **one feature at a time**.

| # | Feature | Status |
|---|---|---|
| 1 | Inventory management | **Code complete. Team must run the checks below before relying on it** |
| 2 | Automatic low-stock alerts | **Code complete. Team must run the checks below before relying on it** |
| 3 | Automatic purchase order generation | **Code complete. Team must run the checks below before relying on it** |
| 4 | Human approval and activity logs (full RBAC + log page) | **Code complete. Team must run the checks below before relying on it** |
| 5 | Supplier order tracking | Planned |
| 6 | Supplier management | Planned |
| 7 | Inventory dashboard | Planned |
| 8 | Demand forecasting | Planned |
| 9 | AI anomaly detection on RunPod GPU | Planned |
| 10 | Simulated Orbyte integration | Started (session/role mock); grows with each feature |

### Verification checklist (tick when YOU have done it)

**Feature 1** (confirmed by the team: tests, build and demo passed locally)
- [x] `pytest -v` passes in `backend/`
- [x] `npm run build` succeeds in `frontend/`
- [x] Manual demo steps work in the browser
- [ ] Replit run works (see Replit section)

**Feature 2**
- [ ] `pytest -v` passes in `backend/` (includes the new `test_alerts_api.py`)
- [ ] `npm run build` succeeds in `frontend/`
- [ ] Manual alert demo below works in the browser

**Feature 3**
- [ ] `pytest -v` passes in `backend/` (includes the new `test_purchase_orders_api.py`)
- [ ] `npm run build` succeeds in `frontend/`
- [ ] Manual purchase order demo below works in the browser

**Feature 4**
- [ ] `pytest -v` passes in `backend/` (includes the new `test_activity_logs_api.py`)
- [ ] `npm run build` succeeds in `frontend/`
- [ ] Manual approval and activity log demo below works in the browser

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
    services/          business rules (stock, alerts, audit log)
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

## Feature 2: Automatic low-stock alerts

**The rule:** a product gets an alert when it is not archived and its quantity is **at or below** its reorder threshold (Low Stock or Out of Stock).

- Alerts open and close **automatically**, in the same database transaction as the stock change. Nobody creates or closes them by hand.
- **No duplicates:** at most one open alert per product, enforced in the code and by a database rule (a partial unique index).
- **Auto-resolve:** when stock goes back above the threshold, the alert is resolved and kept in the "Resolved" tab as history. If the product runs low again later, a new alert is opened.
- **Urgent products:** open alerts are sorted most urgent first.

| Urgency | Rule |
|---|---|
| Critical | quantity is 0 (out of stock) |
| Urgent | quantity is half of the threshold or less |
| Low | at or below the threshold, but not yet urgent |

- **Custom thresholds:** the Owner changes a product's reorder level from the Stock Alerts page (or the Edit form in Inventory). The alert opens or closes straight away. Employees can see alerts and add stock, but cannot change thresholds (backend returns 403).
- A **start-up scan** opens alerts for products that were already low before alerts existed. It is safe to repeat.
- Alert opening and resolving are written to the audit log (`alert.opened`, `alert.resolved`).

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/alerts?status=open\|resolved\|all` | Owner, Employee | List alerts (open ones most urgent first) |
| GET | `/api/alerts/summary` | Owner, Employee | Counts for the page header |

There are no create, edit or delete endpoints for alerts on purpose.

### Manual demo (the milk alert)

1. Choose **Hafiz Ismail (employee)**. Open **Stock Alerts**: you already see the demo products that start low (Chocolate Powder is Critical).
2. Go to **Inventory**. On **Fresh Milk 1L** (20 cartons, reorder at 10) click **Stock**, remove **15**.
3. The message says an alert is active. Open **Stock Alerts**: Milk shows **Urgent** (5 left, reorder at 10).
4. Remove 2 more: still **one** alert for Milk (no duplicate).
5. Click **Add stock** on the Milk row and add 10 (back to 15, above 10). The alert disappears from "Open alerts" and appears under **Resolved** with reason "Stock replenished".
6. Switch to **Aisyah Rahman (owner)**: on an alert row click **Reorder level**, lower it below the stock, and see the alert resolve. The employee has no such button.

## Feature 3: Automatic purchase order generation

**The workflow:** low-stock alert -> the system picks a supplier and a quantity -> **draft** purchase order -> the **owner** approves or rejects -> every step is written to the audit log. Nothing is ever ordered automatically.

| Rule | Detail |
|---|---|
| **Trigger** | A stock change, a new reorder level, a restored product or a new product leaves a product low (open alert). The draft is prepared right after the change is saved. "Check restocking needs" does the same for every low product on demand. |
| **Quantity** | Refill up to **2 x the reorder level**, never less than the supplier's minimum order. Milk: 5 left, level 10 -> 20 - 5 = **15 cartons**. |
| **Supplier** | The **cheapest active supplier** that sells the product (tie: shorter delivery time). Prices come from the supplier price list (`supplier_products` table), in sen (RM x 100) so money has no rounding errors. |
| **Grouping** | One draft per supplier. A second low product from the same supplier is added to the open draft. |
| **No duplicates** | A product can be on only **one outstanding order**. Checked in code and enforced by a database index. A rejected order frees its products again. |
| **Approval** | Only the **Owner** can approve or reject (backend returns 403 for employees). Rejecting needs a written reason. An order can be decided only once. |
| **Editing** | Owner and Employee can change quantity, supplier (only suppliers that sell every product on the order) and the note of an order that is still waiting. Prices cannot be typed in. |
| **No supplier price?** | The product is listed as "No supplier price on file" and skipped. No guess is made. |

Order statuses used in this feature: `draft`, `approved`, `rejected`. The other statuses from the brief (`ordered`, `shipped`, `delivered`, `delayed`, `cancelled`) are defined already and used in Feature 5. We added `rejected` because the brief asks for rejecting orders.

Set `AUTO_GENERATE_PO=false` in `.env` to switch automatic drafting off (the button still works). If drafting ever fails, the stock change that caused it is **not** affected.

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/purchase-orders?status=all\|awaiting\|draft\|approved\|rejected...` | Owner, Employee | List orders with their lines |
| GET | `/api/purchase-orders/summary` | Owner, Employee | Counts and value for the page header |
| GET | `/api/purchase-orders/needs` | Owner, Employee | Low products without an order, with the recommendation |
| POST | `/api/purchase-orders/generate` | Owner, Employee | Prepare drafts now |
| GET | `/api/purchase-orders/{id}` | Owner, Employee | One order |
| PATCH | `/api/purchase-orders/{id}` | Owner, Employee | Edit supplier / quantities / note (while waiting) |
| DELETE | `/api/purchase-orders/{id}/lines/{line_id}` | Owner, Employee | Remove a product from an order (never the last one) |
| POST | `/api/purchase-orders/{id}/approve` | **Owner only** | Approve |
| POST | `/api/purchase-orders/{id}/reject` | **Owner only** | Reject (reason required) |

Audit-log actions written: `po.generated`, `po.updated`, `po.line_removed`, `po.approved`, `po.rejected`.

**Suppliers in this feature:** the `suppliers` and `supplier_products` tables exist now (with synthetic demo suppliers and prices) because an order needs a supplier and a price. The screens to add and edit suppliers arrive in Feature 6. A database created before Feature 3 gets the demo suppliers automatically on the next start. Products you added yourself (for example "Frozen Yoghurt") have no supplier price yet, so they appear as "No supplier price on file".

### Manual demo (the milk order)

1. Choose **Hafiz Ismail (employee)**. In **Inventory**, **Fresh Milk 1L**: **Stock** -> *Remove stock* -> 15 -> confirm (20 -> 5).
2. The message says a draft order was prepared. Open **Purchase Orders**: **Awaiting approval** shows a draft from *Segar Dairy*: 15 cartons x RM 7.80 = **RM 117.00**.
3. As the employee, note there are Edit buttons but **no Approve / Reject** (and `POST /api/purchase-orders/1/approve` with header `X-User-Id: 2` in http://127.0.0.1:8000/docs returns **403**).
4. Click **Edit**, change the quantity to 24, save. The total updates and the line shows "(edited)".
5. Remove 2 more milk from Inventory: still **one** draft, no duplicate.
6. Switch to **Aisyah Rahman (owner)** -> Purchase Orders -> **Approve** -> confirm. Status becomes Approved with her name and time. (Or **Reject** with a reason, then press *Check restocking needs*: a fresh draft appears.)
7. Press **Check restocking needs**: drafts appear for any other low products that have a supplier price (for example Cup Lids), grouped by supplier. Low products without a price are listed as "No supplier price on file".
8. Optional: open `backend/data/inventory.db` and look at `purchase_orders`, `purchase_order_items` and the `po.*` rows in `activity_logs`.

## Feature 4: Human approval and activity logs

**What it adds:** one table of role rules that the backend enforces on every request, an owner-only **Activity Logs** page, and a record of blocked attempts. Features 1 to 3 already wrote the log and already made approval owner-only. Feature 4 completes the role rules and makes the log readable.

| Role | Can | Cannot |
|---|---|---|
| **Owner / Admin** | Manage inventory, record stock, prepare orders, **approve / reject orders**, read the **Activity Logs**, (later) manage suppliers, view reports | n/a |
| **Employee** | View inventory and alerts, **record stock movements**, **prepare / edit purchase order requests**, view orders, (later) track supplier orders | Approve or reject orders, add/edit/archive products, change reorder levels, read Activity Logs |

- The rules live in one place: `PERMISSION_INFO` and `ROLE_PERMISSIONS` in `backend/app/auth/permissions.py`. Every route declares the permission it needs. The GUI hides buttons only for tidiness.
- **Blocked attempts are logged.** When a role lacks a permission the backend answers 403 **and** writes an `access.denied` entry (who, which permission, which URL). The employee's action does not happen.
- **What each log entry records:** user (or "System" for automatic actions), action, timestamp, affected product or order, previous and updated values, and the approval status (`approved`, `rejected` or `blocked`). The approval status is derived from the action code, so it can never disagree with what was decided.
- **The log is append-only.** The API has no create, edit or delete endpoint for log entries. Entries are written in the same database transaction as the change they describe.
- **Filters:** search text, type (products, stock, alerts, orders, blocked), approval, user and date range. 25 entries per page, newest first. Click **Details** for the field-by-field previous/updated values.
- **Roles and permissions tab:** shows the rule table the backend enforces (`GET /api/access/matrix`).
- Logs are separated per business, like every other table.

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/activity-logs` | **Owner only** | List entries. Query: `category`, `action`, `approval`, `user_id`, `search`, `date_from`, `date_to`, `limit`, `offset` |
| GET | `/api/activity-logs/summary` | **Owner only** | Counts for the page header |
| GET | `/api/activity-logs/filters` | **Owner only** | Users and types for the filter boxes |
| GET | `/api/access/matrix` | Any signed-in user | Role and permission table |

Audit-log actions now visible on the page: `item.*`, `stock.in`, `stock.out`, `alert.opened`, `alert.resolved`, `po.generated`, `po.updated`, `po.line_removed`, `po.approved`, `po.rejected`, `access.denied`.

### Manual demo (approval and audit trail)

1. Choose **Hafiz Ismail (employee)**. The sidebar has **no Activity Logs** item. Open http://localhost:5173/activity-logs anyway: you see "Activity Logs are for the Owner / Admin" plus the roles table.
2. In **Inventory**, remove 15 **Fresh Milk 1L** (20 -> 5). A draft order is prepared (Feature 3).
3. In http://127.0.0.1:8000/docs call `POST /api/purchase-orders/1/approve` with header `X-User-Id: 2`. Result: **403**. The order is still a draft.
4. Switch to **Aisyah Rahman (owner)** -> **Activity Logs**. You see, newest first: the blocked attempt (badge **Blocked**), plus the stock removal, alert and draft order from step 2.
5. Click **Details** on the stock row: quantity **20 -> 5** and the reason.
6. In **Purchase Orders** approve the order. Back in Activity Logs the new row shows **Approved** by Aisyah, with status `draft -> approved`.
7. Filter **Approval = All decisions**, then **User = Hafiz Ismail**, then pick today's date. Press **Clear filters**.
8. Switch to **Din Hassan** (other business): the log is empty of café entries.
9. Open the **Roles and permissions** tab.

## Orbyte integration assumptions

We have no access to Orbyte's real APIs. The mock layer (`backend/app/integrations/orbyte_mock.py`) assumes a host platform would tell our module: which business is calling, which user, and their role. We turn the role into permissions and write completed actions to the audit log. In a real integration the `X-User-Id` header would be replaced by Orbyte's verified token.

## Known limitations (Features 1 to 4)

- The simulated session has no passwords. It demonstrates role rules, not real security.
- The supplier on a product is plain text until Feature 6.
- The product list is not paginated (fine for SME-sized catalogues).
- Only the Owner can read the Activity Logs. Employees cannot see even their own entries.
- Log date filters use **UTC days** (the log stores UTC). A late-night entry in Malaysia (UTC+8) can fall on the previous UTC day.
- The log is protected by the application only. Anyone with direct access to the SQLite file can change it. A production system would use a tamper-evident store.
- "Permitted inventory records" for employees means all non-sensitive product fields. There is no per-product or per-location restriction.
- Permissions for supplier screens, reports and delivery tracking are defined now but enforced when Features 5 to 7 add those screens.
- There is no Submit for approval button yet: a draft is shown to the owner as "awaiting approval". The `pending_approval` status is reserved for Feature 5.
- Alerts are only shown on the Stock Alerts page. There is no email or push notification.
- Urgency uses a simple documented rule (half the threshold), not a forecast. Forecast-based urgency arrives with Feature 8.
- Quantities are whole numbers only.
- Order quantity uses a fixed rule (refill to 2 x the reorder level). Forecast-based quantities arrive with Feature 8.
- Approving an order does not contact a supplier. Placing, shipping and delivery are Feature 5 (simulated).
- Archiving a product does not cancel an open order for it. Approval is blocked until the line is removed.
- Supplier prices can only be changed in the database until Feature 6 adds the Suppliers screens.
- Timestamps display in the browser's local time.

## Future improvements

Alerts, purchase orders, supplier tracking, dashboard, forecasting, RunPod GPU anomaly detection, CSV import/export, barcode scanning.

## Git workflow

One branch per feature, one commit per completed feature, merge to `main` by pull request.

```powershell
git checkout main
git pull
git checkout -b feature/2-low-stock-alerts
# ...make changes, then commit in small pieces:
git add <files>
git status          # check: no .env, no node_modules, no .db files in the list
git commit -m "feat(alerts): describe the change"
git push -u origin feature/2-low-stock-alerts
```
