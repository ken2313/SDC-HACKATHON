# Design decisions (Feature 1)

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
