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
