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
