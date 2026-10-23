"""Importing every model here makes sure SQLAlchemy knows about all tables."""
from app.models.activity import ActivityLog
from app.models.alert import StockAlert
from app.models.business import Business, User
from app.models.inventory import InventoryItem, StockMovement, compute_stock_status
from app.models.order_history import OrderStatusHistory
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.supplier import Supplier, SupplierProduct

__all__ = [
    "ActivityLog",
    "StockAlert",
    "Business",
    "User",
    "InventoryItem",
    "StockMovement",
    "compute_stock_status",
    "OrderStatusHistory",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "Supplier",
    "SupplierProduct",
]
