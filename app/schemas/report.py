from decimal import Decimal

from pydantic import BaseModel


class SummaryRead(BaseModel):
    total_products: int
    active_products: int
    low_stock_count: int
    total_units_in_stock: int
    confirmed_orders: int
    cancelled_orders: int
    total_sales: Decimal
    units_sold: int
