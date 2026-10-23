# Design decisions

Short notes on *why* things are built the way they are. Useful for the proposal and for judges' questions.

| Decision | Why |
|---|---|
| **Quantity can only change through stock movements** (the PATCH endpoint rejects `quantity`) | Every change then has a ledger row (who, when, before/after) and an audit-log row. This is what later makes the AI anomaly feature and the activity log trustworthy. |
| **Stock status is calculated, never stored** | A stored status can go out of date. Rule: 0 = Out of Stock; 1 to threshold = Low Stock (reaching the threshold counts); above threshold = In Stock. One function, `compute_stock_status`. |
| **No negative stock, enforced 3 times** | (1) form blocks it, (2) the SQL `UPDATE ... WHERE quantity + change >= 0` refuses it atomically, so two people cannot take the last units at once, (3) a database `CHECK (quantity >= 0)` is the last safety net. |
| **Idempotency key (`request_id`) on stock movements** | Double clicks and network retries cannot change stock twice. Same pattern will protect delivery confirmation (Feature 5) and RunPod retries (Feature 9). |
| **Archive instead of delete** | Old orders, movements and audit logs still point at the product. Archived products keep their SKU reserved. |
| **Change + ledger row + audit row in ONE transaction** | All saved together or not at all. |
| **Permissions checked in the backend** | Each route declares the permission it needs. Hiding buttons in the GUI is only for convenience. |
| **Simulated login via `X-User-Id` header** | Lets us demo roles without building real authentication. Clearly labelled as simulated. A real Orbyte integration would use Orbyte's verified session instead. |
| **Every query filters by the caller's `business_id`** | Data stays separated per business. Asking for another business's product returns 404. |
| **Supplier is plain text for now** | Real supplier records arrive in Feature 6. The column will then be linked to the Suppliers table. |
| **Vite proxy for `/api`** | One public URL on Replit, no CORS problems. |
| **Plain JavaScript, no TypeScript, no UI library** | Fewer concepts for a student team; fewer dependencies. |

## Feature 2: low-stock alerts

| Decision | Why |
|---|---|
| **Alerts are created and closed by the backend, never by users** | Nobody can forget to raise one or close one early. The API has no create/edit/delete for alerts. |
| **The alert check runs in the same transaction as the stock change** | The quantity, movement, alert and audit rows are saved together or not at all, so an alert can never disagree with the stock. |
| **"At or below" the threshold** | Matches the brief ("falls below or reaches the minimum") and the Low Stock status from Feature 1. One rule, reused. |
| **One open alert per product, enforced by a partial unique index** | Code checks first, and the database refuses a second open alert even if two requests race. Resolved alerts are exempt so history can pile up. |
| **Resolved alerts are kept; a new episode makes a new alert** | Gives a history of how often a product ran low, useful for forecasting (Feature 8) and reports. |
| **Urgency is calculated, not stored** | It follows the live quantity, so an open alert gets more urgent as stock drops, with no extra writes. Rule: 0 = critical, half of threshold or less = urgent, else low. |
| **Thresholds are edited through the existing inventory PATCH (owner only)** | One place to change them, one permission, one audit entry. The alert then reacts automatically. |
| **Start-up scan (`reconcile_all`)** | Products that were already low before alerts existed would otherwise never get an alert. It is idempotent, so running it on every start is safe. |
| **System actions are logged with no user** | The scan has no person behind it. The log stores `user_id = NULL`, which the Activity Logs page (Feature 4) will show as "System". |

## Feature 3: purchase orders

| Decision | Why |
|---|---|
| **The system only ever creates DRAFTS** | The brief requires human approval before consequential actions. No code path creates an approved order. Approval is a separate endpoint that only the owner role may call. |
| **Reorder quantity = refill to 2 x the reorder level, at least the supplier minimum** | Simple, explainable to a shop owner, and the milk example gives 15 cartons (20 - 5). Feature 8 will replace it with a forecast-based quantity. |
| **Supplier = cheapest active price, tie goes to shorter delivery** | A documented rule is easier to defend than a hidden one. The owner can still switch the supplier while the order is a draft. |
| **Money stored as whole sen (RM x 100)** | No floating-point rounding errors in totals. The API shows RM with 2 decimals. |
| **`suppliers` and `supplier_products` tables arrive now** | An order needs a real supplier and a price from stored records (brief, Feature 3). Feature 6 adds the screens, so no table has to be redesigned later. |
| **One draft per supplier; new low products join it** | Fewer, bigger orders instead of one tiny order per product. Every addition is logged (`po.updated`). |
| **A product can be on only one outstanding order** | Prevents duplicate orders for the same need. Code checks first; a partial unique index (`outstanding = 1`) makes the database refuse a duplicate even if two requests race. Rejecting an order turns `outstanding` off. |
| **Auto-drafting runs AFTER the stock change is saved, in its own transaction** | A bug or failure in drafting can never undo or block a stock change. `AUTO_GENERATE_PO=false` switches it off. |
| **Approve and reject use a guarded UPDATE (`WHERE status IN (draft, pending_approval)`)** | An order is decided exactly once, even with a double click or two people deciding at once. The loser gets a clear 409. |
| **Edits re-check the status inside the transaction** | An edit cannot slip in after someone approved the order a moment earlier. |
| **Prices cannot be typed into an order** | Prices come from the supplier price list, so an order cannot carry a made-up price. A supplier switch re-prices every line. |
| **Rejection needs a reason** | The audit log then explains the decision, not only that it happened. |
| **`rejected` added to the status list** | The brief asks for rejecting orders but its status list has no "rejected". |
| **Employees may prepare and edit, not approve** | Matches the brief's role split. Full role-based rules and the Activity Logs page are Feature 4. |
| **Unused columns (`received_quantity`, `inventory_applied`) already exist** | Feature 5 needs them to prevent a delivery adding stock twice. Adding them now avoids changing existing tables later. |

## Feature 4: roles, approval and activity logs

| Decision | Why |
|---|---|
| **One permission table drives the checks, the API and the GUI** | `PERMISSION_INFO` in `auth/permissions.py` is the single source. The owner's permission set is built from it, so a new permission cannot be forgotten for the owner, and the "Roles and permissions" screen can never disagree with the backend. |
| **Permissions for Features 5 to 7 are defined now, enforced later** | The role design is settled in one place. Each later feature only attaches `require_permission(...)` to its new routes. |
| **Blocked attempts write an `access.denied` log entry** | The brief wants permissions checked by the backend. Logging refusals proves it and gives the owner visibility. Written in its own commit and wrapped so a logging error can never change the 403. |
| **Approval status is derived from the action code, not stored** | No new column, so existing Replit and local databases keep working with no migration. It cannot drift from the real decision. |
| **The log API is read-only** | Audit trails must be trustworthy. There is no endpoint to edit or delete an entry, and a test checks that. |
| **Owner-only log access** | The brief gives "view activity logs" to the Owner/Admin only. |
| **Entity names are looked up when reading (3 queries per page)** | Entries store the record id. Names (product, PO number) are joined at read time, so the log still works if a name later changes, and no extra column is needed. |
| **Date filters are UTC days** | Timestamps are stored in UTC. Documented as a limitation rather than hiding it. |
| **Employees see the role table but not the log** | Transparency about the rules without exposing other people's activity. |
