"""Populate StockFlow with a realistic demo dataset.

Everything goes through the service layer, so seeded data obeys exactly the
same rules (locking, movements, price capture) as data entered via the API.

    python -m scripts.seed           # refuses to run if products already exist
    python -m scripts.seed --reset   # wipes all tables first
"""

import argparse
import random
from decimal import Decimal

from sqlalchemy import func, select, text

from app.core.errors import AppError
from app.database.connection import SessionLocal
from app.models import MovementType, Product
from app.schemas.inventory import InventoryAdjustmentCreate
from app.schemas.order import OrderCreate
from app.schemas.product import ProductCreate, ProductUpdate
from app.services import inventory_service, order_service, product_service

# sku, name, category, price, low-stock threshold, opening stock
CATALOG = [
    ("KB-MX-RED", "Mechanical Keyboard (Red switches)", "Peripherals", "89.90", 5, 40),
    ("KB-WL-SLIM", "Slim Wireless Keyboard", "Peripherals", "49.00", 5, 25),
    ("MS-ERGO-01", "Ergonomic Vertical Mouse", "Peripherals", "39.50", 8, 60),
    ("MS-GAME-PRO", "Pro Gaming Mouse", "Peripherals", "59.99", 5, 18),
    ("MON-27-4K", '27" 4K IPS Monitor', "Displays", "329.00", 3, 12),
    ("MON-24-FHD", '24" Full HD Monitor', "Displays", "149.00", 4, 20),
    ("HUB-USBC-7", "7-in-1 USB-C Hub", "Accessories", "34.99", 10, 75),
    ("CAB-HDMI-2M", "HDMI 2.1 Cable, 2 m", "Accessories", "12.49", 20, 150),
    ("CAM-1080P", "1080p Webcam with Privacy Shutter", "Peripherals", "44.00", 6, 30),
    ("HS-ANC-01", "Noise-Cancelling Headset", "Audio", "129.00", 4, 15),
    ("SPK-DESK-2", "Desktop Speakers (pair)", "Audio", "69.00", 4, 9),
    ("CHR-ERGO-MESH", "Ergonomic Mesh Office Chair", "Furniture", "249.00", 2, 8),
    ("DSK-STAND-140", "Electric Standing Desk 140 cm", "Furniture", "499.00", 2, 5),
    ("LMP-LED-ARM", "LED Desk Lamp with Arm", "Furniture", "42.00", 5, 22),
    ("NB-A5-DOT", "A5 Dotted Notebook", "Stationery", "6.50", 25, 200),
    ("PEN-GEL-12", "Gel Pens, pack of 12", "Stationery", "8.99", 20, 120),
    ("SSD-EXT-1TB", "Portable SSD 1 TB", "Storage", "99.00", 5, 14),
    ("USB-64GB", "USB 3.2 Flash Drive 64 GB", "Storage", "11.99", 15, 80),
    ("MAT-DESK-XL", "XL Desk Mat", "Accessories", "19.90", 8, 4),
    ("KB-LEGACY-PS2", "PS/2 Keyboard (discontinued)", "Peripherals", "15.00", 0, 3),
]

TABLES = "stock_movements, order_items, orders, inventory, products"


def reset() -> None:
    with SessionLocal() as session, session.begin():
        session.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


def has_products() -> bool:
    with SessionLocal() as session:
        return bool(session.scalar(select(func.count(Product.id))))


def adjust(product_id: int, change: int, movement_type: MovementType, note: str) -> None:
    with SessionLocal() as session:
        inventory_service.adjust_inventory(
            session,
            InventoryAdjustmentCreate(
                product_id=product_id,
                change_quantity=change,
                movement_type=movement_type,
                note=note,
            ),
        )


def seed() -> None:
    ids: dict[str, int] = {}
    for sku, name, category, price, threshold, stock in CATALOG:
        with SessionLocal() as session:
            product = product_service.create_product(
                session,
                ProductCreate(
                    sku=sku,
                    name=name,
                    category=category,
                    price=Decimal(price),
                    low_stock_threshold=threshold,
                    description=f"{name} — demo catalogue item.",
                ),
            )
        ids[sku] = product.id
        adjust(product.id, stock, MovementType.RESTOCK, "Opening stock, PO-1000")

    adjust(ids["MON-27-4K"], -1, MovementType.ADJUSTMENT, "Cracked panel on arrival")
    adjust(ids["CAB-HDMI-2M"], -6, MovementType.ADJUSTMENT, "Cycle count correction")
    adjust(ids["HUB-USBC-7"], 25, MovementType.RESTOCK, "Supplier delivery, PO-1001")

    with SessionLocal() as session:
        product_service.update_product(
            session, ids["KB-LEGACY-PS2"], ProductUpdate(is_active=False)
        )

    rng = random.Random(42)
    sellable = [sku for sku in ids if sku != "KB-LEGACY-PS2"]
    placed: list[int] = []
    rejected = 0
    for index in range(30):
        basket = rng.sample(sellable, k=rng.randint(1, 4))
        payload = OrderCreate(
            items=[{"product_id": ids[sku], "quantity": rng.randint(1, 4)} for sku in basket]
        )
        with SessionLocal() as session:
            try:
                order, _ = order_service.create_order(session, payload, f"seed-order-{index}")
                placed.append(order.id)
            except AppError:
                rejected += 1

    # A price rise after some sales shows that historical orders keep their prices.
    with SessionLocal() as session:
        product_service.update_product(
            session, ids["MON-27-4K"], ProductUpdate(price=Decimal("349.00"))
        )

    for order_id in placed[3:6]:
        with SessionLocal() as session:
            order_service.cancel_order(session, order_id)

    print(
        f"Seeded {len(CATALOG)} products, {len(placed)} orders "
        f"({rejected} rejected for insufficient stock), 3 cancellations."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", help="delete all existing data first")
    args = parser.parse_args()
    if args.reset:
        reset()
    elif has_products():
        raise SystemExit("Database already has products; run with --reset to replace them.")
    seed()


if __name__ == "__main__":
    main()
