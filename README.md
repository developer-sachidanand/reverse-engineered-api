# Books to Scrape Catalog API

This FastAPI service exposes a small JSON API over the publicly accessible
Books to Scrape catalog. It reads the site's public HTML pages over HTTPS; it
does not access private data or bypass access controls.

## Setup

From the project directory, create and activate a virtual environment, then
install the dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell prevents activation because of the execution policy, run the
commands directly through the virtual environment instead:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

Start the API server from the project directory:

```powershell
python app.py
```

The interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Endpoints

- `GET /api/v1/categories` — list category names, slugs, and source URLs.
- `GET /api/v1/items?limit=10&page=1` — list catalog items. `limit` is 1–50;
  `page` is 1–50 and is numbered over the requested page size.
- `GET /api/v1/items?category=fiction_10` — list items in a category.
- `GET /api/v1/categories/{category_slug}/items` — equivalent category listing.
- `GET /api/v1/items/{item_slug}` — fetch a book's details and product attributes.

For example, `GET /api/v1/items/a-light-in-the-attic_1000` looks up the public
catalogue entry with that slug. An unknown item or category returns `404`;
upstream fetch or source-page parsing failures return `502`; invalid query
parameters return `422`.

## Tests

Run the offline test suite with:

```powershell
python -m pytest -q
```

The tests use sample public-page HTML and mocked HTTP responses, so they do not
depend on the source site being online.

## Limitations and long-term fix

- The source offers HTML pages rather than a documented JSON API. A redesign
  of its markup or URL structure can break the parser.
- Requests are live and uncached, so response time and availability depend on
  the source. Use the service respectfully and keep request volume low; access
  controls and rate limits are not bypassed.
- Books to Scrape is a scraping demo; displayed prices and ratings are
  randomly assigned and have no real-world meaning.

The durable solution is an official, documented API or data feed from the site
owner. Until one is available, run a low-frequency ingestion job with an
explicit cache, conservative request pacing, and monitoring for source markup
changes; serve API requests from that snapshot instead of scraping on demand.
