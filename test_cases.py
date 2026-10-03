import requests
from fastapi.testclient import TestClient

import app as api
import scraper


client = TestClient(api.app)

HOME_HTML = """
<aside><div class="side_categories"><ul>
  <li><a href="catalogue/category/books_1/index.html">Books</a>
    <ul><li><a href="catalogue/category/books/fiction_10/index.html">Fiction</a></li></ul>
  </li>
</ul></div></aside>
<article class="product_pod">
  <p class="star-rating Three"></p><h3><a href="catalogue/first-book_1/index.html"
    title="First Book">First</a></h3>
  <p class="price_color">£12.34</p><p class="instock availability">In stock</p>
</article>
<article class="product_pod">
  <p class="star-rating One"></p><h3><a href="catalogue/second-book_2/index.html"
    title="Second Book">Second</a></h3>
  <p class="price_color">£9.99</p><p class="instock availability">Out of stock</p>
</article>
<li class="next"><a href="page-2.html">next</a></li>
"""

DETAIL_HTML = """
<ul class="breadcrumb"><li><a href="/">Home</a></li><li><a href="/fiction/">Fiction</a></li></ul>
<div class="product_main">
  <h1>First Book</h1><p class="price_color">£12.34</p>
  <p class="instock availability">In stock (5 available)</p>
  <p class="star-rating Three"></p>
</div>
<div id="product_description"><h2>Description</h2></div>
<p>A public sample description.</p>
<table class="table-striped"><tr><th>UPC</th><td>abc123</td></tr></table>
"""


def make_response(url, html, status_code=200):
    response = requests.Response()
    response.status_code = status_code
    response.url = url
    response._content = html.encode("utf-8")
    response.encoding = "utf-8"
    return response


def test_fetch_items_follows_pagination_and_respects_limit(monkeypatch):
    page_two_url = f"{scraper.BASE_URL}page-2.html"
    responses = {
        scraper.BASE_URL: make_response(scraper.BASE_URL, HOME_HTML),
        page_two_url: make_response(page_two_url, HOME_HTML.replace(
            '<li class="next"><a href="page-2.html">next</a></li>', ""
        )),
    }
    requested = []

    def fake_get(url, **kwargs):
        requested.append(url)
        return responses[url]

    monkeypatch.setattr(scraper.requests, "get", fake_get)

    items = scraper.fetch_items(limit=3)

    assert [item["slug"] for item in items] == ["first-book_1", "second-book_2", "first-book_1"]
    assert items[0]["in_stock"] is True
    assert items[1]["rating"] == "One"
    assert requested == [scraper.BASE_URL, page_two_url]


def test_fetch_items_can_skip_to_api_page(monkeypatch):
    page_two_url = f"{scraper.BASE_URL}page-2.html"
    page_two_html = HOME_HTML.replace(
        '<li class="next"><a href="page-2.html">next</a></li>', ""
    )
    monkeypatch.setattr(
        scraper.requests,
        "get",
        lambda url, **kwargs: make_response(url, HOME_HTML if url == scraper.BASE_URL else page_two_html),
    )

    items = scraper.fetch_items(limit=1, page=2)

    assert items[0]["slug"] == "second-book_2"


def test_fetch_categories_extracts_public_slugs(monkeypatch):
    monkeypatch.setattr(
        scraper.requests,
        "get",
        lambda url, **kwargs: make_response(url, HOME_HTML),
    )

    categories = scraper.fetch_categories()

    assert [(category["slug"], category["name"]) for category in categories] == [
        ("books_1", "Books"),
        ("fiction_10", "Fiction"),
    ]


def test_fetch_items_filters_by_known_category(monkeypatch):
    category_url = f"{scraper.BASE_URL}catalogue/category/books/fiction_10/index.html"
    category_html = HOME_HTML.replace(
        '<li class="next"><a href="page-2.html">next</a></li>', ""
    )
    responses = {
        scraper.BASE_URL: make_response(scraper.BASE_URL, HOME_HTML),
        category_url: make_response(category_url, category_html),
    }
    monkeypatch.setattr(scraper.requests, "get", lambda url, **kwargs: responses[url])

    items = scraper.fetch_items(limit=1, category="fiction_10")

    assert items[0]["title"] == "First Book"


def test_fetch_item_detail_parses_public_details(monkeypatch):
    detail_url = f"{scraper.BASE_URL}catalogue/first-book_1/index.html"
    monkeypatch.setattr(
        scraper.requests,
        "get",
        lambda url, **kwargs: make_response(url, DETAIL_HTML),
    )

    item = scraper.fetch_item_detail("first-book_1")

    assert item["title"] == "First Book"
    assert item["description"] == "A public sample description."
    assert item["attributes"]["UPC"] == "abc123"
    assert item["category"] == "Fiction"
    assert item["url"] == detail_url


def test_fetch_item_detail_returns_none_for_missing_or_invalid_slug(monkeypatch):
    def not_found(url, **kwargs):
        return make_response(url, "Not found", status_code=404)

    monkeypatch.setattr(scraper.requests, "get", not_found)

    assert scraper.fetch_item_detail("missing-book_9999") is None
    assert scraper.fetch_item_detail("../outside") is None


def test_get_items_endpoint_response(monkeypatch):
    monkeypatch.setattr(
        api,
        "fetch_items",
        lambda **kwargs: [{"slug": "first-book_1", "title": "First Book"}],
    )

    response = client.get("/api/v1/items?limit=3&page=2")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "count": 1,
        "page": 2,
        "limit": 3,
        "data": [{"slug": "first-book_1", "title": "First Book"}],
    }


def test_get_categories_endpoint_response(monkeypatch):
    monkeypatch.setattr(
        api,
        "fetch_categories",
        lambda: [{"slug": "fiction_10", "name": "Fiction", "url": "https://example.test/"}],
    )

    response = client.get("/api/v1/categories")

    assert response.status_code == 200
    assert response.json()["data"][0]["slug"] == "fiction_10"


def test_category_endpoint_returns_not_found_for_unknown_category(monkeypatch):
    def unknown_category(**kwargs):
        raise LookupError("Unknown category: absent_1")

    monkeypatch.setattr(api, "fetch_items", unknown_category)

    response = client.get("/api/v1/categories/absent_1/items")

    assert response.status_code == 404


def test_source_failure_is_returned_as_bad_gateway(monkeypatch):
    def source_failure(**kwargs):
        raise RuntimeError("Source is unavailable")

    monkeypatch.setattr(api, "fetch_items", source_failure)

    response = client.get("/api/v1/items")

    assert response.status_code == 502
    assert response.json()["detail"] == "Source is unavailable"


def test_limit_validation():
    response = client.get("/api/v1/items?limit=0")

    assert response.status_code == 422
