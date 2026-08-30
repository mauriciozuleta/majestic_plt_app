from fastapi.testclient import TestClient

from price_capture_backend.main import app

client = TestClient(app)


def test_capture_and_query_round_trip():
    payload = {
        "domain": "example.com",
        "product_name": "Milk",
        "price": "2.49",
        "unit": "L",
        "country": "US",
        "supermarket_name": "Fresh Mart",
        "currency": "USD",
        "captured_at": "2026-08-30T12:00:00Z",
    }

    create_response = client.post('/capture', json=payload)
    assert create_response.status_code == 201, create_response.text
    data = create_response.json()

    assert data['domain'] == 'example.com'
    assert data['product_name'] == 'Milk'
    assert data['price'] == '2.49'
    assert data['id'] is not None

    list_response = client.get('/captures')
    assert list_response.status_code == 200
    captures = list_response.json()
    assert any(item['id'] == data['id'] for item in captures)

    single_response = client.get(f"/captures/{data['id']}")
    assert single_response.status_code == 200
    assert single_response.json()['id'] == data['id']

    delete_response = client.delete(f"/captures/{data['id']}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/captures/{data['id']}")
    assert missing_response.status_code == 404
