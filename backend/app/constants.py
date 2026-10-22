"""Shared constants. Keeping them in one place avoids typos in strings."""

# Roles (Feature 4 will extend the permission rules)
ROLE_OWNER = "owner"
ROLE_EMPLOYEE = "employee"
ROLES = (ROLE_OWNER, ROLE_EMPLOYEE)

# Stock statuses (calculated from quantity and reorder threshold, never stored)
STATUS_IN_STOCK = "in_stock"
STATUS_LOW_STOCK = "low_stock"
STATUS_OUT_OF_STOCK = "out_of_stock"

# Stock alert states (Feature 2)
ALERT_OPEN = "open"
ALERT_RESOLVED = "resolved"

# Why an alert was closed
RESOLUTION_REPLENISHED = "replenished"            # stock went back above the threshold
RESOLUTION_THRESHOLD_CHANGED = "threshold_changed"  # owner lowered the threshold
RESOLUTION_ARCHIVED = "archived"                  # product was archived

# How urgent an open alert is (see alert_service.urgency_for)
URGENCY_CRITICAL = "critical"  # out of stock
URGENCY_URGENT = "urgent"      # half of the threshold or less is left
URGENCY_LOW = "low"            # at or below threshold, but not yet urgent

# Stock movement types
MOVEMENT_INITIAL = "initial"  # opening quantity when a product is created
MOVEMENT_IN = "in"            # stock added
MOVEMENT_OUT = "out"          # stock removed / consumed

# Purchase order statuses (Feature 3 uses draft / pending_approval / approved / rejected;
# the rest are used by Feature 5, supplier order tracking)
PO_DRAFT = "draft"
PO_PENDING_APPROVAL = "pending_approval"
PO_APPROVED = "approved"
PO_ORDERED = "ordered"
PO_SHIPPED = "shipped"
PO_DELIVERED = "delivered"
PO_DELAYED = "delayed"
PO_CANCELLED = "cancelled"
PO_REJECTED = "rejected"  # owner said no (an addition to the brief's list, needed for "reject")

PO_STATUSES = (
    PO_DRAFT, PO_PENDING_APPROVAL, PO_APPROVED, PO_ORDERED, PO_SHIPPED,
    PO_DELIVERED, PO_DELAYED, PO_CANCELLED, PO_REJECTED,
)
# Still waiting for the owner's decision: the order can still be edited
PO_AWAITING_DECISION = (PO_DRAFT, PO_PENDING_APPROVAL)
# Orders that still "claim" their products: no second order may be raised for the same product
PO_OUTSTANDING = (PO_DRAFT, PO_PENDING_APPROVAL, PO_APPROVED, PO_ORDERED, PO_SHIPPED, PO_DELAYED)
# Finished orders: they no longer block a new order for the same product
PO_CLOSED = (PO_DELIVERED, PO_CANCELLED, PO_REJECTED)

# How a purchase order was created
PO_SOURCE_AUTO = "auto"      # created by the system after a low-stock alert
PO_SOURCE_MANUAL = "manual"  # user pressed "Check restocking needs"

# Reorder rule: order enough to refill up to this many times the reorder level
RESTOCK_TARGET_MULTIPLIER = 2
