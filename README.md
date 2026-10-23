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
| 5 | Supplier order tracking | **Code complete. Team must run the checks below before relying on it** |
| 6 | Supplier management | **Code complete. Team must run the checks below before relying on it** |
| 7 | Inventory dashboard | **Code complete. Team must run the checks below before relying on it** |
| 8 | Demand forecasting | **Code complete. Team must run the checks below before relying on it** |
| 9 | AI anomaly detection on RunPod GPU | Planned |
| 10 | Simulated Orbyte integration | Started (session/role mock); grows with each feature |
| + | Sign-in page and Settings | **Code complete. Team must run the checks below before relying on it** |

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

**Feature 4** (confirmed by the team: demo works locally)
- [x] Manual approval and activity log demo works in the browser
- [ ] `pytest -v` and `npm run build` results recorded here

**Feature 5**
- [ ] `pytest -v` passes in `backend/` (includes the new `test_supplier_orders_api.py`)
- [ ] `npm run build` succeeds in `frontend/`
- [ ] Manual supplier order demo below works in the browser

**Feature 6**
- [ ] `pytest -v` passes in `backend/` (includes the new `test_suppliers_api.py`)
- [ ] `npm run build` succeeds in `frontend/`
- [ ] Manual supplier management demo below works in the browser
- [ ] An existing `inventory.db` (not deleted) starts without errors and the backend prints "Database upgraded: added column suppliers.address" once

**Feature 7**
- [ ] `npm install recharts@3` run once in `frontend/` (adds the chart library to `package.json`)
- [ ] `pytest -v` passes in `backend/` (includes the new `test_dashboard_api.py`)
- [ ] `npm run build` succeeds in `frontend/`
- [ ] Manual dashboard demo below works in the browser

**Feature 8**
- [ ] `pytest -v` passes in `backend/` (includes the new `test_forecasting_api.py`)
- [ ] `npm run build` succeeds in `frontend/`
- [ ] Manual forecasting demo below works in the browser

**Sign-in and Settings**
- [ ] `pytest -v` passes in `backend/` (includes the new `test_auth_settings_api.py`)
- [ ] `npm run build` succeeds in `frontend/`
- [ ] Manual sign-in and settings demo below works in the browser

## Technology stack

- **Frontend:** React, Vite, Tailwind CSS, Recharts (dashboard charts, Feature 7)
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
Open http://localhost:5173 and sign in with the demo account (see "Sign-in page and Settings" below):
**business123@gmail.com** / **SISO67#**

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
5. Note there are no Add/Edit/Archive buttons for the employee. In http://127.0.0.1:8000/docs (click **Authorize** with a sign-in token first, see "Sign-in page and Settings"), a `POST /api/inventory` with header `X-User-Id: 2` returns **403**.
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

## Feature 5: Supplier order tracking

**The workflow:** the owner approves an order (Feature 3) -> **Approved** -> the owner **places it with the supplier** (simulated) -> **Ordered** -> staff mark **Shipped** or **Delayed** -> someone **confirms the delivery** and the quantities that really arrived -> **Delivered** and the **inventory updates automatically, once** -> every step is in the order timeline and the Activity Log.

| Rule | Detail |
|---|---|
| **What is tracked** | Orders the owner approved, plus their later states. Drafts and rejected orders are not shown here. |
| **Allowed moves** | Approved -> Ordered or Cancelled. Ordered -> Shipped, Delayed, Delivered, Cancelled. Shipped <-> Delayed, Shipped/Delayed -> Delivered or Cancelled. Anything else (for example Approved -> Shipped) is refused with 409. Delivered and Cancelled are final. |
| **Who** | **Owner only:** place with supplier, cancel (`orders:place`). **Owner and Employee:** mark shipped/delayed, confirm delivery (`orders:track`). The backend checks this; blocked attempts are logged. |
| **Placing is simulated** | No real supplier is contacted. The timeline says "Simulated". The expected delivery date is set to today + the supplier's typical delivery time (Malaysia time). |
| **Delayed** | Needs a new expected date (today or later) and an optional note. |
| **Overdue** | Calculated, not stored: ordered / shipped / delayed, not delivered, and the expected date is before today (Malaysia time, UTC+8). Shown in red with the number of days. **Nothing changes status by itself:** a person marks the order Delayed. |
| **Confirming a delivery** | Enter the received quantity for every line (0 or more, at least one item overall). Status, received quantities, stock, alerts, timeline and audit log are saved in **one transaction**. |
| **No duplicate inventory updates** | Three protections: (1) only Ordered/Shipped/Delayed orders can receive; (2) a guarded `UPDATE ... WHERE inventory_applied = 0` lets only one request win; (3) every stock movement has a unique `request_id` (`po-receipt-<order>-<line>`), so the database refuses a second one. A second attempt returns 409 and changes nothing. |
| **Short delivery** | Only what arrived is added. If a product is still low, the system prepares a new **draft** (never an approved order) for the owner. |
| **Cancel** | Owner only, needs a reason, stock is never touched, and the products become free for a new order. |
| **Alerts** | Receiving goods goes through the same alert check as any stock change, so a low-stock alert resolves automatically when stock is back above the reorder level. |

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/supplier-orders?view=active\|overdue\|delivered\|cancelled\|all` | Owner, Employee | List tracked orders with timeline |
| GET | `/api/supplier-orders/summary` | Owner, Employee | Counts for the page header |
| GET | `/api/supplier-orders/{id}` | Owner, Employee | One order |
| POST | `/api/supplier-orders/{id}/place` | **Owner only** | Place with supplier (simulated) |
| POST | `/api/supplier-orders/{id}/status` | Owner, Employee | Mark `shipped` or `delayed` |
| POST | `/api/supplier-orders/{id}/receive` | Owner, Employee | Confirm delivery, update stock once |
| POST | `/api/supplier-orders/{id}/cancel` | **Owner only** | Cancel (reason required) |

New table: `order_status_history` (the timeline). It is created automatically; no existing table changes. Orders from before this feature get a starting timeline entry at start-up. New audit-log actions: `po.placed`, `po.shipped`, `po.delayed`, `po.delivered`, `po.cancelled`.

### Manual demo (the full café workflow)

Use a fresh database for the cleanest run (stop the backend, delete `backend/data/inventory.db`, start again).

1. **Hafiz Ismail (employee)** -> Inventory -> **Fresh Milk 1L** -> Stock -> *Remove stock* 15 (20 -> 5). A draft order is prepared.
2. **Aisyah Rahman (owner)** -> Purchase Orders -> **Approve** the draft.
3. **Supplier Orders**: the order is **Approved**. Click **Place with supplier (simulated)** -> confirm. Status **Ordered**, with an expected date.
4. Switch to **Hafiz**. He sees the order but **no** Place or Cancel button. (In http://127.0.0.1:8000/docs, `POST /api/supplier-orders/1/cancel` with `X-User-Id: 2` returns **403**.)
5. As Hafiz click **Mark delayed**, choose a date a few days ahead, add a note. Then **Mark shipped**.
6. Click **Confirm delivery**. Leave 15 and confirm. Status **Delivered**; the message says Milk is now 20 cartons.
7. Inventory shows Milk at **20**. Stock Alerts shows the alert under **Resolved**.
8. Try to confirm the same delivery again (or double-click): refused, stock stays at 20.
9. Open the **Timeline** on the order, then (as owner) **Activity Logs**: `po.placed`, `po.shipped`, `po.delivered`, `stock.in` and `alert.resolved` are there.
10. Short delivery: repeat steps 1 to 6 but receive only **3**. Stock becomes 8 (still low) and a new draft order is prepared.
11. Overdue check (testing shortcut only): open `backend/data/inventory.db` in *DB Browser for SQLite* -> **Execute SQL** -> run `UPDATE purchase_orders SET estimated_delivery_date = '2020-01-01' WHERE status = 'ordered';` -> **Write Changes**. Refresh the page: the order shows **Overdue** in red and appears under the **Overdue** tab. Its status does not change by itself.

## Feature 6: Supplier management

**What it adds:** a **Suppliers** page where the owner keeps each supplier's contact details, usual delivery time and **price list** (which products it sells, at what price, minimum order). The price list is what Feature 3 uses to choose a supplier, so this page decides who new purchase orders go to. Each supplier also shows its **order history** and simple delivery statistics.

| Rule | Detail |
|---|---|
| **Who** | **Owner and Employee:** view suppliers, contacts, prices, order history (`suppliers:view`). **Owner only:** add, edit, deactivate, change prices (`suppliers:manage`). Blocked attempts get 403 and an `access.denied` log entry. |
| **Contact information** | Name (required, unique per business, not case-sensitive), contact person, phone, email, address, notes. Phone and email are checked for a sensible format. |
| **Delivery time** | Typical days from placing an order to delivery (0 to 365). Used for the expected date when an order is placed (Feature 5). |
| **Price list** | One entry per product per supplier: price in RM (at most 2 decimals, stored in sen) and a minimum order. Another business's product returns 404; archived products cannot be added. |
| **Which supplier is chosen** | Unchanged from Feature 3: the cheapest **active** supplier with a price (tie: shorter delivery time). The price list shows **Chosen** next to the supplier that new drafts would use. |
| **Price changes** | Apply to orders prepared from now on. An order that already exists keeps its own price, so the owner approves exactly what was shown. |
| **Products without a supplier** | Listed at the top of the page (low ones first) because they cannot be reordered. The owner can pick a supplier and add a price right there. If the product is low, a **draft** order is prepared straight away (never approved). |
| **Deactivate, never delete** | Order history must stay, so there is no delete. A deactivated supplier is never chosen for new orders. A supplier with unfinished orders (draft to delayed) cannot be deactivated. |
| **Renaming** | Products whose supplier label showed the old name are updated to the new name in the same transaction. |
| **Order history** | Every order with the supplier, its value, the value actually received, when it was placed and delivered, and how many days delivery took. A delivery is **late** when it took more days than the supplier's usual delivery time (Malaysia dates). |
| **Audit log** | `supplier.created`, `supplier.updated`, `supplier.deactivated`, `supplier.activated`, `supplier.product_added`, `supplier.price_changed`, `supplier.product_removed`. New "Suppliers" type in the Activity Logs filter. |

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/suppliers?include_inactive=&search=` | Owner, Employee | List suppliers with product and order counts |
| GET | `/api/suppliers/summary` | Owner, Employee | Counts for the page header |
| GET | `/api/suppliers/products-without-supplier` | Owner, Employee | Active products no active supplier sells |
| POST | `/api/suppliers` | **Owner only** | Add supplier |
| GET | `/api/suppliers/{id}` | Owner, Employee | Contact details, price list, order history, statistics |
| PATCH | `/api/suppliers/{id}` | **Owner only** | Edit details (send only what changes; null clears an optional field) |
| POST | `/api/suppliers/{id}/deactivate`, `/activate` | **Owner only** | Stop / restart using the supplier for new orders |
| POST | `/api/suppliers/{id}/products` | **Owner only** | Add a product with price and minimum order |
| PATCH | `/api/suppliers/{id}/products/{entry_id}` | **Owner only** | Change price and/or minimum order |
| DELETE | `/api/suppliers/{id}/products/{entry_id}` | **Owner only** | Take a product off the price list |

**Database:** no new table. The `suppliers` table gets three optional columns (`address`, `notes`, `updated_at`). An existing database is upgraded automatically at start-up by `backend/app/schema_upgrade.py`, which only **adds** missing columns, so you do **not** need to delete `inventory.db`. Demo suppliers get synthetic addresses only in a new database.

### Manual demo (suppliers and prices)

1. **Hafiz Ismail (employee)** -> **Suppliers**. He sees 5 café suppliers, their contacts and prices (click **View**), but no Add, Edit, Price or Deactivate buttons. In http://127.0.0.1:8000/docs, `POST /api/suppliers` with `X-User-Id: 2` returns **403**.
2. Switch to **Aisyah Rahman (owner)** -> Suppliers -> **Manage** on *Segar Dairy*. The price list shows Fresh Milk at RM 7.80 marked **Chosen** (Pasar Borong sells it too, at RM 8.50).
3. Open *Pasar Borong Jaya* -> **Price** on Fresh Milk -> change it to **7.00** -> save. Pasar Borong is now **Chosen** for milk.
4. As Hafiz, in Inventory remove 15 Fresh Milk. Purchase Orders shows the new draft from **Pasar Borong** at RM 7.00 (15 x RM 7.00 = RM 105.00).
5. As Aisyah, open Segar Dairy -> **Deactivate** while it has no unfinished orders: it disappears from the list (tick **Show inactive suppliers** to see it). Re-activate it.
6. Try to deactivate Pasar Borong while the milk draft is open: refused, with the order number.
7. In Inventory, **Add product** "Frozen Yoghurt 1L", 2 tubs, reorder at 5. Back on Suppliers it appears under **"1 product has no supplier price"**. Choose *Roti Segar Bakery Supply*, **Add price** 12.50, minimum 4. The message says a draft was prepared; Purchase Orders shows it (8 tubs).
8. **Add supplier**: try a bad email to see the check, then save a real one and add a product to its price list.
9. After a delivery from Feature 5, open the supplier's **Order history**: value received, days to deliver, and **late** if it took longer than usual.
10. **Activity Logs** -> Type **Suppliers**: every change above, with before/after values.

## Feature 7: Inventory dashboard

**What it adds:** a **Dashboard** page (now the start page) that answers "what needs my attention today?" in one screen. Every number is calculated by the backend from the database for the signed-in business. Nothing is typed in or faked.

| Part | What it shows | How it is calculated |
|---|---|---|
| **Summary cards** | Products, low stock, out of stock, pending orders, delayed orders, awaiting delivery | Active products by status; orders waiting for approval; orders marked Delayed **or** past their expected date (counted once) |
| **Money cards (owner only)** | Stock value, value waiting for approval, value on order, goods received in 30 days | Stock value = quantity x the cheapest active supplier price (products with no price are counted separately). Received = received quantities x order prices for deliveries confirmed in the last 30 days |
| **Stock trend** | For one product: stock at the end of each day, units used and added, reorder level line. 14 / 30 / 60 days | Rebuilt from the stock movements (Malaysia days). A note appears when there are fewer than 7 days with usage |
| **Stock status by category** | Stacked bars: in stock / low / out per category | Active products |
| **Urgent products** | The 5 most urgent open alerts, and whether an order already covers them | Same order as the Stock Alerts page |
| **Upcoming deliveries** | Orders with the supplier due in the next 14 days, and overdue ones | Expected delivery date vs today (Malaysia time) |
| **Recent inventory activity** | The last 10 stock movements: who, what, before -> after | `stock_movements` table |
| **AI anomaly alerts** | A clearly labelled placeholder | Arrives with Feature 9. Nothing is shown until real model results exist |

**Who sees what:** Owner and Employee see the dashboard (`inventory:view`). Only the owner gets the money cards (`reports:view`): for an employee the backend sends `financials: null`, so the numbers never reach their browser.

**Synthetic stock history:** a new demo database now also gets about **30 days of made-up daily usage and supplier deliveries** for each demo product (`backend/app/seed/history_data.py`), so the trend chart has something to show (Feature 8 forecasting will use it too). Fresh Milk uses about 10 cartons a day, as in the brief, and weekends are busier. The history is built **backwards from today's stock**, so the demo still starts at 20 cartons of milk with reorder at 10. Products you already used in a demo keep their real history. Set `SEED_HISTORY=false` in `.env` to switch this off. **For the full charts, delete `backend/data/inventory.db` once and restart.**

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/dashboard` | Owner, Employee (money: owner only) | Everything on the page in one request |
| GET | `/api/dashboard/trend?item_id=&days=7..90` | Owner, Employee | Daily stock, used and added for one product |

### Manual demo (dashboard)

1. Stop the backend, delete `backend/data/inventory.db`, start it again. The console says "Added synthetic stock history for the demo products."
2. Open http://localhost:5173 as **Aisyah Rahman (owner)**: the Dashboard opens. Cards show 10 products, 2 low, 1 out of stock. Stock value is about RM 2,362.
3. **Stock trend** shows Fresh Milk: a saw-tooth line (deliveries up, daily use down) above the dashed reorder line, about 10 cartons used per day. Switch to 14d / 60d and to another product.
4. Switch to **Hafiz Ismail (employee)**: same cards and charts, but **no money cards** ("Money totals are shown to the owner only").
5. As Hafiz, remove 15 Fresh Milk in Inventory. Back on the Dashboard: low stock 3, pending orders 1, milk under **Urgent products** with "On order: PO-0001 (draft)", and the removal at the top of **Recent inventory activity**. The trend's last day shows 5 cartons, below the reorder line.
6. As Aisyah approve and place the order (Features 3 and 5). It appears under **Upcoming deliveries**. Mark it delayed: **Delayed orders** becomes 1.
7. Confirm the delivery: it leaves Upcoming deliveries, **Received (30 days)** goes up, milk is back to 20.

## Feature 8: Demand forecasting

**What it adds:** a **Demand Forecasting** page that says, for every product, how much is used per day, when it will run out, **when to order** (allowing for the supplier's delivery time) and **how much**. It also checks its own accuracy against what really happened. It is advice: nothing is ordered or changed automatically.

**The method (a 7-day moving average, as the brief suggests):**

| Step | Rule |
|---|---|
| Demand history | Units used per day (every stock removal), per Malaysian calendar day. A day with no use counts as 0. Today is left out (not finished). |
| Forecast | Average daily use over the last **7 complete days**. The same number for every future day. |
| Runs out | Stock on hand ÷ daily demand. |
| Order by | The day stock falls to the demand during the supplier's **delivery time + 2 safety days**. If that day has passed: "Order now". |
| Order quantity | Demand for delivery time + **7 days** + 2 safety days, minus stock on hand and stock already on order, never below the supplier's minimum. The Feature 3 rule (refill to 2 x reorder level) is shown next to it for comparison. |
| Suggested reorder level | Demand during delivery time + 2 safety days. If the current level is lower, the page warns that stock can run out before a delivery arrives, and the owner can apply the suggestion (existing owner-only route). |
| Predicted vs actual | For each of the last **14 days**, forecast from the 7 days before it and compare with real use. **Accuracy = 100% − total error ÷ total use** (at least 0%). Below 50% the dates are marked uncertain. |
| Not enough data | Under **7 days** of records: no forecast, with a warning. Under **14 days**: a forecast with a "limited history" warning. |

**Statuses:** Order now · Order this week · On order (it should be ordered and an approved order is on its way) · OK · No recent use · Not enough data. Drafts waiting for approval do not count as "on order".

**Worked example (milk, demo data):** about 10 cartons a day, 20 on hand, Segar Dairy delivers in 1 day. Runs out in about 2 days. Order by = 2 − 1 − 2 → already passed → **Order now**. Suggested reorder level about 10 × (1 + 2) = **30**, so the current level of 10 is too low: by the time the low-stock alert fires, there is only one day of milk left.

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/forecasts` | Owner, Employee | Every active product, most urgent first, with a summary and the method settings |
| GET | `/api/forecasts/{item_id}?horizon_days=7..60` | Owner, Employee | One product: last 28 days (actual vs predicted) and the next days (forecast, projected stock) |

No new table and no new write endpoint: forecasts are calculated from `stock_movements` when the page is opened.

### Manual demo (forecasting)

1. Use the database with the synthetic history from Feature 7 (delete `backend/data/inventory.db` and restart if you have not done that yet).
2. **Demand Forecasting** as **Hafiz (employee)**. "Needs action" lists Fresh Milk as **Order now**, with about 10 cartons a day and a suggested reorder level around 30. Open **How the forecast works**.
3. Click **Details** on Fresh Milk: the **Predicted vs actual** chart (bars = real use, line = what was predicted), the projected stock falling to zero in about 2 days, and "How these numbers were worked out" with the real sums. Switch 7d / 14d / 30d. Hafiz has no button to change the reorder level.
4. Switch to **Aisyah (owner)** -> Details on Fresh Milk -> **Review new level** -> save the suggested level. Back in the list the warning is gone. Stock Alerts now shows milk as low (20 is below the new level) and a draft order was prepared.
5. **All products**: compare accuracy across products. Products with very uneven use have lower accuracy and an "uncertain" warning.
6. In Inventory add a new product. On the forecasting page it shows **Not enough data** with the warning.
7. Remove 15 milk, approve the draft in Purchase Orders: milk changes to **On order**.

## Sign-in page and Settings

**Sign-in:** the website now opens on a **sign-in page**. Every API route except signing in and `/api/health` answers **401** until you sign in.

| | |
|---|---|
| Demo account | **business123@gmail.com** / **SISO67#** (synthetic, not a real mailbox) |
| How it is checked | By the **backend**. The password is not in the website code and not stored as text: the backend keeps a salted PBKDF2-SHA256 hash and compares in constant time. |
| Session | A signed token (HMAC-SHA256) valid for 12 hours, saved in the browser. Changing it in any way makes it invalid. |
| Log out | Ends the session on the server too (the token stops working at once) and goes back to the sign-in page. |
| Wrong passwords | After 5 wrong attempts in 5 minutes from one address, sign-in is blocked for the rest of the 5 minutes (429). |
| Relation to roles | Signing in opens the workspace. The **user switcher** in the top bar still decides who you are (owner or employee), as before. In a real Orbyte integration both would come from Orbyte's own login. |

Optional `.env` settings: `DEMO_LOGIN_EMAIL`, `DEMO_LOGIN_PASSWORD` (to use a different password), `SESSION_SECRET` (keeps you signed in across backend restarts; without it a restart signs everyone out), `SESSION_HOURS` (default 12).

**Using http://127.0.0.1:8000/docs now:** first call `POST /api/auth/login` with the demo account, copy the `token`, click **Authorize** (top right) and paste it. Then add the `X-User-Id` header as before. The 403 demos in the earlier features still work this way.

**Settings page:**

| Section | What it does | Who |
|---|---|---|
| Account | Signed-in email, when the session ends, current demo user, **Log out** (with confirmation) | Everyone |
| Business | **Business name** and **Prepare purchase order drafts automatically** (on/off). Saved in the database, written to the Activity Log (`business.updated`, type "Settings") | Change: **Owner only** (`settings:manage`). Employees see them read-only |
| Preferences | **Start page** after signing in (Dashboard, Inventory, Stock Alerts, Purchase Orders, Demand Forecasting). Saved in this browser only | Everyone |
| About this demo | Version, business, a note that data is synthetic and the integration simulated | Everyone |

With automatic drafts switched off, a low product still gets its low-stock alert, and **Check restocking needs** on Purchase Orders still prepares drafts. The setting is per business. `AUTO_GENERATE_PO=false` in `.env` still switches it off for the whole server.

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/api/auth/login` | Anyone | Sign in, get a token |
| GET | `/api/auth/session` | Signed in | Is my token still valid? |
| POST | `/api/auth/logout` | Signed in | End the session |
| GET | `/api/settings` | Signed in | Business settings |
| PATCH | `/api/settings` | **Owner only** | Change business name / automatic drafts |

**Database:** one optional column `businesses.auto_draft_orders`, added automatically to existing databases at start-up (empty = on, as before).

### Manual demo (sign-in and settings)

1. Open http://localhost:5173: the sign-in page. Press **Sign in** with empty fields: both fields ask for input.
2. Enter the email with a wrong password: "Wrong email or password." Then sign in with **business123@gmail.com** / **SISO67#**: the Dashboard opens. Reload the page: still signed in.
3. Open **Settings** as **Aisyah (owner)**: change the business name and save. The top bar shows the new name; Activity Logs -> Type **Settings** shows the change.
4. Switch **Prepare purchase order drafts automatically** off. Remove 15 Fresh Milk: the alert opens but no draft is prepared. Switch it back on.
5. Choose **Inventory** as the start page.
6. **Log out** -> confirm: back on the sign-in page with "You have signed out." Sign in again: Inventory opens.
7. Switch to **Hafiz (employee)** -> Settings: the business settings are greyed out.
8. In http://127.0.0.1:8000/docs try `GET /api/inventory` without Authorize: **401**.

## Orbyte integration assumptions

We have no access to Orbyte's real APIs. The mock layer (`backend/app/integrations/orbyte_mock.py`) assumes a host platform would tell our module: which business is calling, which user, and their role. We turn the role into permissions and write completed actions to the audit log. In a real integration the `X-User-Id` header would be replaced by Orbyte's verified token.

## Known limitations (Features 1 to 8, sign-in, settings)

- There is one shared demo sign-in for the whole workspace, not one account per person. The user switcher (no password) still picks the role, to demonstrate role rules. A real deployment would use Orbyte's own login.
- Signed-out tokens and failed sign-in counts are kept in memory: restarting the backend forgets them (and, without `SESSION_SECRET`, also signs everyone out).
- The token is stored in the browser's localStorage, which is fine for a demo; a production app would prefer secure, http-only cookies.
- The supplier shown on a product in Inventory is still a text label. What really links a product to a supplier is the supplier's price list. Adding a price fills an empty label; renaming a supplier updates matching labels.
- The product list is not paginated (fine for SME-sized catalogues).
- Only the Owner can read the Activity Logs. Employees cannot see even their own entries.
- Log date filters use **UTC days** (the log stores UTC). A late-night entry in Malaysia (UTC+8) can fall on the previous UTC day.
- The log is protected by the application only. Anyone with direct access to the SQLite file can change it. A production system would use a tamper-evident store.
- "Permitted inventory records" for employees means all non-sensitive product fields. There is no per-product or per-location restriction.
- The dashboard refreshes when you open it or press Refresh. It does not update live.
- Stock value uses today's cheapest supplier price, not what was actually paid (an estimate for planning, not accounting).
- The trend mixes nothing across products: it shows one product at a time, because units (cartons, bags, packs) cannot be added together.
- The synthetic history writes stock movements only (no activity-log rows), because it is demo data rather than actions people took.
- The AI anomaly card is a placeholder until Feature 9.
- The forecast is a 7-day moving average: it does not model trends, weekdays, holidays or promotions, and reacts to a change in demand only after a few days.
- Every stock removal counts as demand, including corrections and waste. A mistaken large removal raises the forecast for a week (Feature 9 will flag such entries).
- Purchase order drafts still use the fixed Feature 3 quantity rule. The forecast quantity is shown as advice; using it automatically is a possible next step.
- The forecast assumes the supplier delivers in its usual time and that no other deliveries arrive.
- There is no Submit for approval button: a draft is shown to the owner as "awaiting approval". The `pending_approval` status exists but is not used yet.
- Supplier actions are simulated: nothing is sent to a supplier, and shipping/delay updates are typed in by staff.
- A delivery is confirmed in one step. There are no partial deliveries over several days: a short delivery closes the order and, if stock is still low, a new draft is prepared.
- Received quantities may exceed the ordered quantity (suppliers sometimes over-deliver). The log records both numbers.
- "Overdue" uses Malaysia time (UTC+8) for every business.
- Orders that were already Approved before Feature 5 can be placed straight away; their expected date is recalculated when placed.
- Alerts are only shown on the Stock Alerts page. There is no email or push notification.
- Urgency uses a simple documented rule (half the threshold), not a forecast. Forecast-based urgency arrives with Feature 8.
- Quantities are whole numbers only.
- Order quantity uses a fixed rule (refill to 2 x the reorder level). Forecast-based quantities arrive with Feature 8.
- Approving an order does not contact a supplier. Placing, shipping and delivery are Feature 5 (simulated).
- Archiving a product does not cancel an open order for it. Approval is blocked until the line is removed.
- Changing a supplier price does not update orders that already exist (by design). To use the new price on a draft, reject it and prepare a new one, or switch its supplier.
- A supplier can be deactivated only when it has no unfinished orders. A draft created in the same instant as the deactivation is not blocked (very unlikely for a small business).
- Delivery statistics use the supplier's current usual delivery time. If you change it, older deliveries are judged against the new number.
- Prices are per unit and in RM only. There are no volume discounts, delivery fees or price history (the audit log keeps old prices).
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
