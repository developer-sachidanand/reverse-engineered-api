from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from scraper import fetch_categories, fetch_item_detail, fetch_items


app = FastAPI(
    title="Books to Scrape Catalog API",
    description="A REST wrapper for the publicly accessible Books to Scrape catalog.",
    version="1.1.0",
)


def _list_items(limit: int, page: int, category: str = None):
    try:
        data = fetch_items(limit=limit, page=page, category=category)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "success": True,
        "count": len(data),
        "page": page,
        "limit": limit,
        "data": data,
    }


@app.get("/api/v1/categories", summary="List book categories")
def get_categories():
    try:
        categories = fetch_categories()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"success": True, "count": len(categories), "data": categories}


@app.get("/api/v1/items", summary="List catalog items")
def get_items(
    limit: int = Query(10, ge=1, le=50),
    page: int = Query(1, ge=1, le=50),
    category: Optional[str] = Query(None, min_length=1),
):
    return _list_items(limit, page, category)


@app.get("/api/v1/categories/{category_slug}/items", summary="List items in a category")
def get_category_items(
    category_slug: str,
    limit: int = Query(10, ge=1, le=50),
    page: int = Query(1, ge=1, le=50),
):
    return _list_items(limit, page, category_slug)


@app.get("/api/v1/items/{item_slug}", summary="Get item details")
def get_item(item_slug: str):
    try:
        item = fetch_item_detail(item_slug)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"success": True, "data": item}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000)
