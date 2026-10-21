"""Shared constants. Keeping them in one place avoids typos in strings."""

# Roles (Feature 4 will extend the permission rules)
ROLE_OWNER = "owner"
ROLE_EMPLOYEE = "employee"
ROLES = (ROLE_OWNER, ROLE_EMPLOYEE)

# Stock statuses (calculated from quantity and reorder threshold, never stored)
STATUS_IN_STOCK = "in_stock"
STATUS_LOW_STOCK = "low_stock"
STATUS_OUT_OF_STOCK = "out_of_stock"

# Stock movement types
MOVEMENT_INITIAL = "initial"  # opening quantity when a product is created
MOVEMENT_IN = "in"            # stock added
MOVEMENT_OUT = "out"          # stock removed / consumed
