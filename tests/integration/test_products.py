from tests.helpers import count_rows, create_product


def test_create_product_creates_zero_stock_inventory_row(client, db_session):
    response = client.post(
        "/products",
        json={
            "sku": "kb-100",
            "name": "Mechanical Keyboard",
            "price": "89.90",
            "category": "Peripherals",
            "description": "Hot-swappable switches",
        },
    )
    assert response.status_code == 201
    product = response.json()
    assert product["sku"] == "KB-100"
    assert product["price"] == "89.90"
    assert product["quantity"] == 0
    assert product["is_active"] is True
    assert product["low_stock_threshold"] == 5
    assert count_rows(db_session, "inventory", "product_id = :pid", pid=product["id"]) == 1


def test_duplicate_sku_is_rejected_with_409(client, db_session):
    create_product(client, sku="DUP-1")
    response = client.post("/products", json={"sku": "dup-1", "name": "Other", "price": "1.00"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_SKU"
    assert count_rows(db_session, "products") == 1
    assert count_rows(db_session, "inventory") == 1


def test_get_product(client):
    product = create_product(client, name="Mouse")
    response = client.get(f"/products/{product['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Mouse"


def test_missing_product_returns_consistent_404(client):
    response = client.get("/products/999")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "PRODUCT_NOT_FOUND",
            "message": "Product 999 not found",
            "details": {"product_id": 999},
        }
    }


def test_update_product(client):
    product = create_product(client, price="10.00")
    response = client.patch(
        f"/products/{product['id']}",
        json={"price": "12.50", "is_active": False, "low_stock_threshold": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["price"] == "12.50"
    assert body["is_active"] is False
    assert body["low_stock_threshold"] == 2
    assert body["updated_at"] >= product["updated_at"]


def test_update_to_existing_sku_is_rejected(client):
    create_product(client, sku="A-1")
    second = create_product(client, sku="B-1")
    response = client.patch(f"/products/{second['id']}", json={"sku": "a-1"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_SKU"


def test_update_missing_product_returns_404(client):
    assert client.patch("/products/42", json={"name": "x"}).status_code == 404


def test_list_search_and_filters(client):
    create_product(client, sku="KB-1", name="Wireless Keyboard", category="Peripherals")
    create_product(client, sku="MS-1", name="Gaming Mouse", category="Peripherals")
    create_product(client, sku="DSK-1", name="Standing Desk", category="Furniture", is_active=False)

    def skus(**params):
        body = client.get("/products", params=params).json()
        return sorted(p["sku"] for p in body["items"]), body["total"]

    assert skus(search="keyboard") == (["KB-1"], 1)
    assert skus(search="ms-") == (["MS-1"], 1)
    assert skus(category="Peripherals") == (["KB-1", "MS-1"], 2)
    assert skus(is_active="false") == (["DSK-1"], 1)
    assert skus(search="%") == ([], 0)


def test_list_pagination(client):
    for _ in range(5):
        create_product(client)
    body = client.get("/products", params={"limit": 2, "offset": 2}).json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert [p["id"] for p in body["items"]] == [3, 4]


def test_validation_errors_use_the_error_shape(client):
    response = client.post("/products", json={"sku": "X-1", "name": "Bad", "price": "-1"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["errors"][0]["loc"] == ["body", "price"]
