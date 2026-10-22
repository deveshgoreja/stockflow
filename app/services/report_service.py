from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Inventory, Order, OrderItem, OrderStatus, Product
from app.schemas.report import SummaryRead


def get_summary(session: Session) -> SummaryRead:
    confirmed = Order.status == OrderStatus.CONFIRMED
    with session.begin():
        total_products, active_products = session.execute(
            select(func.count(Product.id), func.count(Product.id).filter(Product.is_active))
        ).one()
        low_stock_count = session.scalar(
            select(func.count(Inventory.id))
            .join(Inventory.product)
            .where(Product.is_active, Inventory.quantity <= Product.low_stock_threshold)
        )
        total_units = session.scalar(select(func.coalesce(func.sum(Inventory.quantity), 0)))
        confirmed_orders, cancelled_orders, total_sales = session.execute(
            select(
                func.count(Order.id).filter(confirmed),
                func.count(Order.id).filter(Order.status == OrderStatus.CANCELLED),
                func.coalesce(func.sum(Order.total_amount).filter(confirmed), Decimal("0")),
            )
        ).one()
        units_sold = session.scalar(
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(OrderItem.order)
            .where(confirmed)
        )
    return SummaryRead(
        total_products=total_products,
        active_products=active_products,
        low_stock_count=low_stock_count or 0,
        total_units_in_stock=total_units or 0,
        confirmed_orders=confirmed_orders,
        cancelled_orders=cancelled_orders,
        total_sales=Decimal(total_sales).quantize(Decimal("0.01")),
        units_sold=units_sold or 0,
    )
