# Price Capture Backend API

This project contains a small FastAPI backend that accepts product price captures from a browser extension, stores them in a local SQLite database, and exposes query/delete endpoints.

## Stack

- FastAPI
- SQLAlchemy
- SQLite
- Uvicorn

## Setup

1. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv .venv
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the API:
   ```bash
   uvicorn price_capture_backend.main:app --reload --host 0.0.0.0 --port 5000
   ```

The app will create a SQLite file named `price_capture_backend/price_captures.db` automatically on first run.

## Endpoints

### POST /capture
Accepts JSON like:

```json
{
  "domain": "example.com",
  "product_name": "Milk",
  "price": "2.49",
  "unit": "L",
  "country": "US",
  "supermarket_name": "Fresh Mart",
  "currency": "USD",
  "captured_at": "2026-08-30T12:00:00Z"
}
```

### GET /captures
Returns all records, newest first.
Supports optional filters:
- `domain`
- `country`
- `supermarket_name`

Example:

```bash
curl "http://localhost:5000/captures?country=US&domain=example.com"
```

### GET /captures/{id}
Returns a single capture by id.

### DELETE /captures/{id}
Deletes a capture by id. Returns 204 No Content.

## Notes

- `price` is stored as text to preserve original formatting from the browser extension.
- The API is configured with permissive CORS for local development so a Chrome extension origin can POST successfully.
- This should be tightened before any non-local deployment.
