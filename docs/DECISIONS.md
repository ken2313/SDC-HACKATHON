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

## Feature 5: supplier order tracking

| Decision | Why |
|---|---|
| **A fixed list of allowed status moves (`PO_TRANSITIONS`)** | An order cannot skip a step (Approved -> Delivered) or go backwards. The list is one constant, so the rules are easy to read and test. |
| **Every move is a guarded UPDATE (`WHERE status = <old status>`)** | If two people act at once only one wins; the other gets a clear 409 instead of overwriting. Same pattern as approve/reject in Feature 3. |
| **Placing and cancelling are owner-only (`orders:place`); shipping, delay and receiving are for staff too (`orders:track`)** | Placing spends money, cancelling discards an approved decision. Staff at the door are the people who know what arrived and what the supplier said. |
| **"Place with supplier" is a simulation and says so** | No supplier API exists. The timeline note and the dialog both state that nothing was sent. |
| **Overdue is calculated, never stored, and never changes status** | It cannot go stale, and the system does not act on its own. A person decides to mark an order Delayed. |
| **Malaysia time (fixed UTC+8) decides "today"** | Malaysia has no daylight saving, so a fixed offset is exact, and it avoids needing time-zone packages on Windows or Replit. |
| **One transaction for a delivery** | Status, received quantities, stock movements, alerts, history and audit log are saved together or not at all. |
| **Three layers against double stock updates** | Status check, a guarded `inventory_applied` flip, and a unique `request_id` on each stock movement. Each is tested, including the case where the first two are deliberately reset. |
| **Receiving writes the stock movement itself instead of calling `record_movement`** | `record_movement` commits on its own. A delivery needs the stock change inside the same transaction as the order change. The rules are copied (stock added with an UPDATE, a movement row, a log row, an alert check). |
| **A short delivery closes the order and may prepare a new DRAFT** | Simple and honest for an MVP. The owner still approves any follow-up order. Multi-day partial deliveries are listed as a limitation. |
| **Cancelling frees the products (`outstanding = 0`)** | Otherwise the "one outstanding order per product" rule from Feature 3 would block a replacement order forever. |
| **New table `order_status_history`, no changes to existing tables** | `create_all` adds new tables safely. The existing `estimated_delivery_date`, `received_quantity` and `inventory_applied` columns (added in Feature 3 for this purpose) are reused. |
| **Start-up backfill of history** | Orders created before this feature still get a timeline. It skips orders that already have history, so repeating it is harmless. |
| **History helper in its own file** | The purchase order service and the tracking service both write history; a shared file avoids them importing each other. |

## Feature 6: supplier management

| Decision | Why |
|---|---|
| **The price list is the link between suppliers and products** | Feature 3 already chooses suppliers from `supplier_products`. Managing that table directly means the Suppliers page and the purchase order logic can never disagree. The product's supplier text label is kept for display and filled in automatically where it was empty. |
| **"Chosen" uses the same function as the drafts (`_best_offer`)** | The page shows exactly which supplier the next draft will use, instead of a second copy of the rule that could drift. |
| **Price changes do not touch existing orders** | An order line keeps the price it was prepared with. The owner approves the amount on screen, and the history stays truthful. |
| **Deactivate instead of delete** | Orders, history and the audit log point to the supplier. Deleting it would break that trail. |
| **No deactivation while orders are unfinished** | Otherwise an approved or shipped order would belong to a supplier the system says it no longer uses. The owner finishes, rejects or cancels first (or switches the draft's supplier). |
| **Adding a price can prepare a draft right away** | A low product with no supplier was a dead end in Feature 3 ("No supplier price on file"). Adding the price is the moment it becomes orderable. It reuses the same best-effort `auto_draft_for_item` as a stock change, so it only ever creates a DRAFT, respects `AUTO_GENERATE_PO`, and cannot break the price save. |
| **A tiny additive schema upgrade instead of a migration tool** | Three optional columns were needed. `schema_upgrade.py` only adds missing nullable columns and checks first, so team members and Replit keep their data. Adding Alembic would be heavier than the problem. |
| **Supplier names unique per business, not case-sensitive** | "Segar Dairy" and "SEGAR DAIRY" would be the same supplier to a person. Checked in code; the existing database rule catches exact duplicates in a race. |
| **Email and phone checked with simple patterns** | Catches typing mistakes without adding a validation package. The check is the same in the form and in the backend. |
| **Late = more days than the usual delivery time, using Malaysia dates** | Simple and explainable. It uses the timeline from Feature 5 (placed and delivered times), so nothing new has to be recorded. |
| **Employees can see prices and contacts** | They prepare purchase order requests and receive deliveries, so they need the contact and the price. Changing them is owner-only. |

## Feature 7: inventory dashboard

| Decision | Why |
|---|---|
| **One overview endpoint, plus one for the trend** | The page loads with one request (one consistent moment in time). The trend is separate because the user changes product and period without reloading everything. |
| **Money totals are left out by the backend for employees** | `reports:view` is owner-only. Sending `null` instead of hiding the cards means the numbers never reach a browser that should not see them. The rest of the dashboard is operational and employees need it. |
| **"Delayed" counts Delayed orders and overdue orders once** | Both mean "a delivery is late". A delayed order that is also past its new date is still one late delivery. |
| **Stock value at the cheapest current supplier price** | It is the price the system would reorder at, and it is already in the database. It is labelled as an estimate; real purchase costs per batch are not tracked in this MVP. |
| **Trend per product, not total units** | Cartons, bags and packs cannot be summed into a meaningful number. One product at a time with its own reorder line is honest and readable. |
| **Trend rebuilt from stock movements** | No new table or nightly job. The movement ledger already has the quantity after every change, so the end-of-day stock is exact. |
| **Synthetic history built backwards from today's stock** | The demo scenario (milk 20, reorder 10) must not change. Walking backwards guarantees the history ends at the current quantity and never goes negative; a fixed random seed gives every team member the same data. Products already used in a demo are skipped, so real demo data is never rewritten. |
| **Recharts** | It is the charting library named in the brief, works with React, and needs no backend changes. |
| **AI anomaly card is a labelled placeholder** | The brief wants anomaly alerts on the dashboard "when Feature 9 is implemented". Showing fake alerts would misrepresent the system. |

## Feature 8: demand forecasting

| Decision | Why |
|---|---|
| **7-day simple moving average** | The brief asks to start simple. It is easy to explain to an SME owner and to check by hand, and seven days contain every weekday once, so weekend peaks are averaged in rather than chased. |
| **Accuracy is measured, not claimed** | A backtest over the last 14 days compares the prediction for each morning with what was really used. The accuracy figure (100% − WAPE) is shown for every product and low values come with a warning, so nobody trusts a shaky forecast blindly. |
| **WAPE instead of a percentage error per day** | Days with zero use make per-day percentages divide by zero. Total error ÷ total use is stable and easy to read. |
| **Order-by date uses the supplier's real delivery time** | The same supplier the drafts would use (cheapest active). A run-out date alone is not enough if the supplier needs four days. |
| **Safety buffer of 2 days, order covers 7 days** | Simple, documented constants at the top of `forecast_service.py`. A small business can tune them in one place. |
| **Suggest a reorder level, do not change it** | The forecast often shows the reorder level is too low (milk). The owner decides; applying it reuses the existing owner-only inventory route, so permissions and audit logging already work. |
| **Drafts do not count as "on order"** | Nothing is ordered until the owner approves. Counting drafts would hide a real shortage. |
| **Calculated on request, no forecast table** | Small catalogues make this fast, and results can never go stale. A `DemandForecasts` table can be added if forecasts need to be stored for history. |
| **Not enough data = no number** | Below 7 days the method has no full window. Showing nothing plus a clear warning is more honest than a guess. |

## Sign-in page and Settings

| Decision | Why |
|---|---|
| **The backend checks the password, not the website** | Anything in the website's JavaScript can be read by anyone who opens it. The backend stores only a salted PBKDF2 hash. |
| **Standard library only (hashlib, hmac, secrets)** | No new packages to install on Windows or Replit, and the code is short enough to read in one sitting. |
| **Signed tokens instead of a sessions table** | No new table or clean-up job. A revoked list in memory makes log-out immediate; the trade-off (forgotten on restart) is documented. |
| **The sign-in check runs before the role check** | It is attached to every router in `main.py`, so an anonymous caller is stopped with 401 before any permission code runs (and before an "access denied" log entry could be written). |
| **One demo account plus the existing user switcher** | Keeps every earlier demo (owner vs employee) working unchanged, while the module is no longer open to anyone who finds the URL. |
| **Brute-force limit (5 wrong tries per 5 minutes)** | Cheap protection against guessing; tested. |
| **Business settings in the database, preferences in the browser** | Business settings affect everyone and need the owner's permission and an audit trail. A start page is personal and harmless, so localStorage is enough. |
| **Automatic drafts as a per-business switch** | Some owners prefer to prepare orders themselves. The alert still opens and the manual button still works, so nothing is lost. |
| **Tests switch the sign-in check off by default** | The earlier tests focus on business rules. One test file switches it on and tests signing in, forged and expired tokens, log-out, the attempt limit and the 401-before-403 order. |

