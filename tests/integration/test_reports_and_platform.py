from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.database.connection import engine
from app.models import Base
from tests.helpers import create_product, place_order


def test_summary_counts_only_confirmed_sales(client):
    a = create_product(client, price="10.00", stock=10, low_stock_threshold=5)
    b = create_product(client, price="2.50", stock=3, low_stock_threshold=5)
    create_product(client, stock=0, is_active=False)

    place_order(client, [(a["id"], 2), (b["id"], 2)])
    cancelled = place_order(client, [(a["id"], 1)]).json()
    client.post(f"/orders/{cancelled['id']}/cancel")

    summary = client.get("/reports/summary").json()
    assert summary == {
        "total_products": 3,
        "active_products": 2,
        "low_stock_count": 1,
        "total_units_in_stock": 9,
        "confirmed_orders": 1,
        "cancelled_orders": 1,
        "total_sales": "25.00",
        "units_sold": 4,
    }


def test_summary_on_empty_database(client):
    summary = client.get("/reports/summary").json()
    assert summary["total_sales"] == "0.00"
    assert summary["confirmed_orders"] == 0


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}


def test_unknown_route_uses_error_shape(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_every_endpoint_is_documented(client):
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/products": {"get", "post"},
        "/products/{product_id}": {"get", "patch"},
        "/inventory": {"get"},
        "/inventory/{product_id}": {"get"},
        "/inventory/adjustments": {"post"},
        "/inventory/movements": {"get"},
        "/orders": {"get", "post"},
        "/orders/{order_id}": {"get"},
        "/orders/{order_id}/cancel": {"post"},
        "/reports/summary": {"get"},
        "/health": {"get"},
    }
    for path, methods in expected.items():
        assert set(paths[path]) == methods, path
    assert client.get("/docs").status_code == 200


def test_migrations_match_the_models(migrated_database):
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []


def test_cors_allows_the_dashboard_origin(client):
    response = client.options(
        "/products",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
