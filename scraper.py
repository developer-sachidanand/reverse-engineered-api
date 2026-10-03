from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://books.toscrape.com/"
HEADERS = {"User-Agent": "BooksToScrapeCatalogAPI/1.0 (public catalog client)"}
REQUEST_TIMEOUT = 10
MAX_SOURCE_PAGES = 50
ITEM_SLUG_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-_")


def _request_page(url: str) -> requests.Response:
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to fetch source page {url}: {exc}") from exc
    return response


def _get_categories() -> List[Dict[str, str]]:
    response = _request_page(BASE_URL)
    soup = BeautifulSoup(response.text, "html.parser")
    category_list = soup.select_one(".side_categories")
    if category_list is None:
        raise RuntimeError("Source page did not contain the category navigation")

    categories = []
    for link in category_list.select("a[href]"):
        href = link.get("href", "").strip()
        path_parts = urlparse(href).path.rstrip("/").split("/")
        if "category" not in path_parts or len(path_parts) < 2:
            continue

        category_path = path_parts[-2] if path_parts[-1] == "index.html" else path_parts[-1]
        slug = category_path.removesuffix(".html")
        name = link.get_text(" ", strip=True)
        if slug and name:
            categories.append({
                "slug": slug,
                "name": name,
                "url": urljoin(response.url, href),
            })

    if not categories:
        raise RuntimeError("Source page did not contain any book categories")
    return categories


def fetch_categories() -> List[Dict[str, str]]:
    """Fetch the publicly listed book categories."""
    return _get_categories()


def _get_category_url(category_slug: str) -> str:
    for category in _get_categories():
        if category["slug"].casefold() == category_slug.casefold():
            return category["url"]
    raise LookupError(f"Unknown category: {category_slug}")


def _parse_listing(response: requests.Response) -> Tuple[List[Dict[str, object]], Optional[str]]:
    soup = BeautifulSoup(response.text, "html.parser")
    products = soup.select("article.product_pod")
    items = []

    for product in products:
        title_link = product.select_one("h3 a[href]")
        price = product.select_one(".price_color")
        availability = product.select_one(".availability")
        if title_link is None or price is None or availability is None:
            raise RuntimeError("Source product listing did not match the expected page structure")

        title = title_link.get("title") or title_link.get_text(" ", strip=True)
        item_url = urljoin(response.url, title_link["href"])
        item_path = urlparse(item_url).path.rstrip("/").split("/")
        slug = item_path[-2] if item_path[-1] == "index.html" and len(item_path) > 1 else ""
        if not slug:
            raise RuntimeError("Source product listing contained an invalid item link")

        rating = product.select_one(".star-rating")
        rating_value = ""
        if rating is not None:
            rating_classes = [value for value in rating.get("class", []) if value != "star-rating"]
            rating_value = rating_classes[0] if rating_classes else ""

        items.append({
            "slug": slug,
            "title": title.strip(),
            "price": price.get_text(strip=True),
            "in_stock": "In stock" in availability.get_text(" ", strip=True),
            "rating": rating_value,
            "url": item_url,
        })

    next_link = soup.select_one("li.next a[href]")
    next_url = urljoin(response.url, next_link["href"]) if next_link is not None else None
    return items, next_url


def fetch_items(
    limit: int = 10,
    page: int = 1,
    category: Optional[str] = None,
) -> List[Dict[str, object]]:
    """Fetch a page of catalog items, optionally from a known category."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    if not 1 <= page <= MAX_SOURCE_PAGES:
        raise ValueError(f"page must be between 1 and {MAX_SOURCE_PAGES}")

    url = _get_category_url(category) if category else BASE_URL
    skip = (page - 1) * limit
    selected: List[Dict[str, object]] = []
    visited = set()

    while url and len(selected) < limit:
        if url in visited:
            raise RuntimeError("Source pagination contains a cycle")
        visited.add(url)
        response = _request_page(url)
        items, next_url = _parse_listing(response)

        if skip >= len(items):
            skip -= len(items)
        else:
            selected.extend(items[skip:skip + limit - len(selected)])
            skip = 0

        if len(selected) >= limit or next_url is None:
            break
        url = next_url

    return selected


def fetch_item_detail(item_slug: str) -> Optional[Dict[str, object]]:
    """Fetch one item by its catalog slug; return None when it does not exist."""
    if (
        not item_slug
        or item_slug[0] == "-"
        or item_slug[-1] in "-_"
        or not set(item_slug.casefold()) <= ITEM_SLUG_CHARS
        or "_" not in item_slug
    ):
        return None

    url = urljoin(BASE_URL, f"catalogue/{item_slug}/index.html")
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to fetch source page {url}: {exc}") from exc
    if response.status_code == 404:
        return None
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to fetch source page {url}: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    main = soup.select_one(".product_main")
    if main is None:
        raise RuntimeError("Source item page did not contain the expected product details")

    title = main.select_one("h1")
    price = main.select_one(".price_color")
    availability = main.select_one(".availability")
    if title is None or price is None or availability is None:
        raise RuntimeError("Source item page did not match the expected page structure")

    attributes = {}
    for row in soup.select("table.table-striped tr"):
        key = row.find("th")
        value = row.find("td")
        if key is not None and value is not None:
            attributes[key.get_text(" ", strip=True)] = value.get_text(" ", strip=True)

    description_section = soup.select_one("#product_description")
    description = ""
    if description_section is not None:
        description_element = description_section.find_next_sibling("p")
        if description_element is not None:
            description = description_element.get_text(" ", strip=True)

    rating = main.select_one(".star-rating")
    rating_value = ""
    if rating is not None:
        rating_classes = [value for value in rating.get("class", []) if value != "star-rating"]
        rating_value = rating_classes[0] if rating_classes else ""

    breadcrumbs = soup.select(".breadcrumb li a")
    category = breadcrumbs[-1].get_text(" ", strip=True) if len(breadcrumbs) > 1 else ""

    return {
        "slug": item_slug,
        "title": title.get_text(" ", strip=True),
        "price": price.get_text(strip=True),
        "in_stock": "In stock" in availability.get_text(" ", strip=True),
        "availability": availability.get_text(" ", strip=True),
        "rating": rating_value,
        "category": category,
        "description": description,
        "url": url,
        "attributes": attributes,
    }
