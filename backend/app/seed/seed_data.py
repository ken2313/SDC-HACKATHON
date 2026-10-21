"""Synthetic Malaysian SME demo data. Nothing here is real.

Run manually with:   python -m app.seed.seed_data
(The app also seeds automatically on first start when the database is empty.)

Two businesses are created so we can prove that data is separated per business.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import MOVEMENT_INITIAL, ROLE_EMPLOYEE, ROLE_OWNER
from app.models import Business, InventoryItem, StockMovement, User

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
    db.commit()
    return True


if __name__ == "__main__":
    from app.database import SessionLocal, engine, Base
    import app.models  # noqa: F401  (registers all tables)

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        print("Seeded demo data." if seed_if_empty(session) else "Database already has data. Nothing changed.")
