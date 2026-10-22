"""Synthetic Malaysian SME demo data. Nothing here is real.

Run manually with:   python -m app.seed.seed_data
(The app also seeds automatically on first start when the database is empty.)

Two businesses are created so we can prove that data is separated per business.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import MOVEMENT_INITIAL, ROLE_EMPLOYEE, ROLE_OWNER
from app.models import Business, InventoryItem, StockMovement, Supplier, SupplierProduct, User
from app.services.alert_service import reconcile_all

# (sku, name, category, unit, quantity, reorder_threshold, supplier_name)
CAFE_ITEMS = [
    ("MILK-1L", "Fresh Milk 1L", "Dairy", "cartons", 20, 10, "Segar Dairy Sdn Bhd (demo)"),
    ("OATM-1L", "Oat Milk 1L", "Dairy", "cartons", 12, 6, "Segar Dairy Sdn Bhd (demo)"),
    ("COFB-1KG", "Arabica Coffee Beans 1kg", "Coffee", "bags", 14, 5, "Kopi Borneo Trading (demo)"),
    ("COFB-ROB", "Robusta Coffee Beans 1kg", "Coffee", "bags", 4, 5, "Kopi Borneo Trading (demo)"),
    ("SUGR-1KG", "Gula Pasir 1kg", "Dry Goods", "packs", 25, 10, "Pasar Borong Jaya (demo)"),
    ("TEHT-500", "Teh Tarik Premix 500g", "Beverage Mix", "packs", 9, 8, "Pasar Borong Jaya (demo)"),
    ("CHOC-500", "Chocolate Powder 500g", "Beverage Mix", "tins", 0, 4, "Pasar Borong Jaya (demo)"),
    ("CUP-12OZ", "Paper Cups 12oz (50 pcs)", "Packaging", "sleeves", 30, 15, "PakEco Packaging (demo)"),
    ("LID-12OZ", "Cup Lids 12oz (50 pcs)", "Packaging", "sleeves", 11, 15, "PakEco Packaging (demo)"),
    ("CROI-FRZ", "Frozen Croissant (24 pcs)", "Bakery", "boxes", 6, 3, "Roti Segar Bakery Supply (demo)"),
]

SHOP_ITEMS = [
    ("RICE-10KG", "Beras Wangi 10kg", "Rice & Grains", "bags", 18, 8, "Pak Mat Wholesale (demo)"),
    ("OIL-5L", "Minyak Masak 5L", "Cooking Oil", "bottles", 7, 6, "Pak Mat Wholesale (demo)"),
    ("EGG-A30", "Telur Gred A (30 biji)", "Fresh", "trays", 3, 5, "Ladang Telur Sejahtera (demo)"),
    ("NOOD-5PK", "Mi Segera (5 bungkus)", "Dry Goods", "packs", 40, 20, "Pak Mat Wholesale (demo)"),
    ("SOY-500", "Kicap Manis 500ml", "Sauces", "bottles", 0, 6, "Pak Mat Wholesale (demo)"),
    ("FLOUR-1KG", "Tepung Gandum 1kg", "Dry Goods", "packs", 22, 10, "Pak Mat Wholesale (demo)"),
]


def _add_business(db: Session, name: str, owner: tuple, employee: tuple, items: list) -> None:
    business = Business(name=name)
    db.add(business)
    db.flush()

    owner_user = User(business_id=business.id, name=owner[0], email=owner[1], role=ROLE_OWNER)
    employee_user = User(business_id=business.id, name=employee[0], email=employee[1], role=ROLE_EMPLOYEE)
    db.add_all([owner_user, employee_user])
    db.flush()

    for sku, item_name, category, unit, quantity, threshold, supplier in items:
        item = InventoryItem(
            business_id=business.id,
            sku=sku,
            name=item_name,
            category=category,
            unit=unit,
            quantity=quantity,
            reorder_threshold=threshold,
            supplier_name=supplier,
        )
        db.add(item)
        db.flush()
        if quantity > 0:
            db.add(
                StockMovement(
                    business_id=business.id,
                    item_id=item.id,
                    user_id=owner_user.id,
                    movement_type=MOVEMENT_INITIAL,
                    quantity_change=quantity,
                    quantity_before=0,
                    quantity_after=quantity,
                    reason="Opening quantity (demo data)",
                )
            )


# ---------------------------------------------------------------- suppliers (Feature 3)
# supplier name -> (contact, phone, email, typical lead time in days,
#                   {sku: (unit price in sen, minimum order quantity)})
# 1 RM = 100 sen. All names, phone numbers and prices are made up.
CAFE_SUPPLIERS = {
    "Segar Dairy Sdn Bhd (demo)": ("Lim Wei Jie", "+60 3-5555 0101", "orders@segardairy.example", 1,
                                   {"MILK-1L": (780, 6), "OATM-1L": (1150, 6)}),
    "Kopi Borneo Trading (demo)": ("Jenny Anak Ruai", "+60 82-555 0102", "sales@kopiborneo.example", 4,
                                   {"COFB-1KG": (6800, 2), "COFB-ROB": (4800, 2)}),
    "Pasar Borong Jaya (demo)": ("Rajesh Kumar", "+60 3-5555 0103", "hello@pasarborong.example", 2,
                                 {"SUGR-1KG": (380, 10), "TEHT-500": (1250, 4), "CHOC-500": (2450, 2),
                                  "MILK-1L": (850, 12)}),  # a second, dearer milk supplier
    "PakEco Packaging (demo)": ("Nurul Huda", "+60 7-555 0104", "sales@pakeco.example", 5,
                                {"CUP-12OZ": (1200, 5), "LID-12OZ": (950, 5)}),
    "Roti Segar Bakery Supply (demo)": ("Tan Mei Ling", "+60 3-5555 0105", "orders@rotisegar.example", 2,
                                        {"CROI-FRZ": (4200, 2)}),
}
SHOP_SUPPLIERS = {
    "Pak Mat Wholesale (demo)": ("Mat Zain", "+60 9-555 0201", "pakmat@wholesale.example", 3,
                                 {"RICE-10KG": (3200, 5), "OIL-5L": (2800, 6), "NOOD-5PK": (690, 10),
                                  "SOY-500": (520, 6), "FLOUR-1KG": (290, 10)}),
    "Ladang Telur Sejahtera (demo)": ("Hajah Normah", "+60 9-555 0202", "telur@sejahtera.example", 1,
                                      {"EGG-A30": (1750, 4)}),
}
SUPPLIERS_BY_BUSINESS = {
    "Kopi Kita Café (demo)": CAFE_SUPPLIERS,
    "Kedai Runcit Pak Din (demo)": SHOP_SUPPLIERS,
}


def seed_suppliers_if_missing(db: Session) -> bool:
    """Give each demo business its synthetic suppliers and price list, but only if that
    business has none yet. Safe to run on every start, and it also upgrades a database
    that was created before Feature 3 existed. Returns True if anything was added."""
    added = False
    for business in db.scalars(select(Business)).all():
        catalogue = SUPPLIERS_BY_BUSINESS.get(business.name)
        if catalogue is None:
            continue  # a business we did not create: leave it alone
        if db.scalar(select(Supplier.id).where(Supplier.business_id == business.id).limit(1)) is not None:
            continue
        items_by_sku = {
            item.sku: item
            for item in db.scalars(select(InventoryItem).where(InventoryItem.business_id == business.id))
        }
        for name, (contact, phone, email, lead_days, products) in catalogue.items():
            supplier = Supplier(
                business_id=business.id, name=name, contact_name=contact, phone=phone,
                email=email, typical_lead_time_days=lead_days,
            )
            db.add(supplier)
            db.flush()
            for sku, (price_sen, min_qty) in products.items():
                item = items_by_sku.get(sku)
                if item is None:
                    continue  # the demo product was renamed or removed
                db.add(
                    SupplierProduct(
                        business_id=business.id, supplier_id=supplier.id, item_id=item.id,
                        unit_price_sen=price_sen, min_order_qty=min_qty,
                    )
                )
        added = True
    if added:
        db.commit()
    return added


def seed_if_empty(db: Session) -> bool:
    """Create the demo data only when there are no businesses yet. Returns True if seeded."""
    if db.scalar(select(Business.id).limit(1)) is not None:
        return False

    _add_business(
        db,
        "Kopi Kita Café (demo)",
        owner=("Aisyah Rahman", "aisyah@kopikita.example"),
        employee=("Hafiz Ismail", "hafiz@kopikita.example"),
        items=CAFE_ITEMS,
    )
    _add_business(
        db,
        "Kedai Runcit Pak Din (demo)",
        owner=("Din Hassan", "din@pakdin.example"),
        employee=("Siti Aminah", "siti@pakdin.example"),
        items=SHOP_ITEMS,
    )
    db.flush()
    reconcile_all(db)  # opens alerts for the demo products that start out low (also commits)
    seed_suppliers_if_missing(db)
    return True


if __name__ == "__main__":
    from app.database import SessionLocal, engine, Base
    import app.models  # noqa: F401  (registers all tables)

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        print("Seeded demo data." if seed_if_empty(session) else "Database already has data. Nothing changed.")
        seed_suppliers_if_missing(session)
