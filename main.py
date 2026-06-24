import json
import io
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from models import ProductData
from sp_api_client import get_product_data

app = FastAPI(title="SP-API Product Dashboard", version="1.0.0")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def startup_event():
    load_data_from_files()

# In-memory store for loaded products
product_store: list[dict] = []

DATA_DIR = Path(__file__).parent / "data"


def parse_sp_api_product(item: dict) -> dict:
    """
    Parse a single product in SP-API JSON response format
    (catalogItems_2022-04-01 + customerFeedback) into flat table row.
    """
    product = {}

    # ASIN
    product["asin"] = item.get("asin", "")

    # URL
    product["url"] = f"https://www.amazon.com/dp/{product['asin']}?psc=1"

    # --- summaries ---
    summaries = item.get("summaries", [])
    if summaries:
        summary = summaries[0]
        product["product_details"] = summary.get("itemName", "")
        product["brand"] = summary.get("brand", "")

    # --- images ---
    images = item.get("images", [])
    if images:
        image_sets = images[0].get("images", [])
        if image_sets:
            main_img = next(
                (img for img in image_sets if img.get("variant") == "MAIN"),
                image_sets[0]
            )
            product["image_url"] = main_img.get("link", "")

    # --- attributes ---
    attributes = item.get("attributes", {})

    # Brand (fallback if not in summaries)
    if "brand" not in product or not product["brand"]:
        brand_list = attributes.get("brand", [])
        if brand_list:
            product["brand"] = brand_list[0].get("value", "")

    # Bullet points
    bullet_points_raw = attributes.get("bullet_point", [])
    product["bullet_points"] = [
        bp.get("value", "") for bp in bullet_points_raw if bp.get("value")
    ]

    # Origin
    country_of_origin = attributes.get("country_of_origin", [])
    if country_of_origin:
        product["origin"] = country_of_origin[0].get("value", "N/A")

    # Price
    list_price = attributes.get("list_price", [])
    if list_price:
        price_val = list_price[0].get("value")
        if price_val is not None:
            try:
                product["price"] = float(price_val)
            except (ValueError, TypeError):
                pass

    # --- salesRanks ---
    sales_ranks = item.get("salesRanks", [])
    if sales_ranks:
        for rank_group in sales_ranks:
            class_ranks = rank_group.get("classificationRanks", [])
            display_ranks = rank_group.get("displayGroupRanks", [])
            if class_ranks:
                product["bsr"] = class_ranks[0].get("rank")
                break
            elif display_ranks:
                product["bsr"] = display_ranks[0].get("rank")
                break

    # --- customerFeedback ---
    feedback = item.get("customerFeedback", {})
    if feedback:
        star_rating = feedback.get("overallStarRating") or feedback.get("starRating")
        if star_rating is not None:
            product["ratings"] = float(star_rating)
        review_count = feedback.get("reviewCount") or feedback.get("numberOfReviews")
        if review_count is not None:
            product["review_count"] = int(review_count)

        # Review Topics (from getItemReviewTopics response)
        topics = feedback.get("topics", {})
        if not topics:
            topics = item.get("topics", {})
        if topics:
            product["review_topics"] = {
                "positiveTopics": [],
                "negativeTopics": [],
            }
            for topic in topics.get("positiveTopics", []):
                t = {"topic": topic.get("topic", "")}
                metrics = topic.get("asinMetrics", {})
                t["numberOfMentions"] = metrics.get("numberOfMentions")
                t["occurrencePercentage"] = metrics.get("occurrencePercentage")
                t["starRatingImpact"] = metrics.get("starRatingImpact")
                t["reviewSnippets"] = topic.get("reviewSnippets", [])
                t["subtopics"] = [
                    {"subtopic": s.get("subtopic", ""), "mentions": s.get("metrics", {}).get("numberOfMentions")}
                    for s in topic.get("subtopics", [])
                ]
                product["review_topics"]["positiveTopics"].append(t)
            for topic in topics.get("negativeTopics", []):
                t = {"topic": topic.get("topic", "")}
                metrics = topic.get("asinMetrics", {})
                t["numberOfMentions"] = metrics.get("numberOfMentions")
                t["occurrencePercentage"] = metrics.get("occurrencePercentage")
                t["starRatingImpact"] = metrics.get("starRatingImpact")
                t["reviewSnippets"] = topic.get("reviewSnippets", [])
                t["subtopics"] = [
                    {"subtopic": s.get("subtopic", ""), "mentions": s.get("metrics", {}).get("numberOfMentions")}
                    for s in topic.get("subtopics", [])
                ]
                product["review_topics"]["negativeTopics"].append(t)

    # Also check if topics are at the top level (direct paste from API response)
    if "topics" in item and "review_topics" not in product:
        topics = item["topics"]
        product["review_topics"] = {"positiveTopics": [], "negativeTopics": []}
        for topic in topics.get("positiveTopics", []):
            t = {"topic": topic.get("topic", "")}
            metrics = topic.get("asinMetrics", {})
            t["numberOfMentions"] = metrics.get("numberOfMentions")
            t["occurrencePercentage"] = metrics.get("occurrencePercentage")
            t["starRatingImpact"] = metrics.get("starRatingImpact")
            t["reviewSnippets"] = topic.get("reviewSnippets", [])
            product["review_topics"]["positiveTopics"].append(t)
        for topic in topics.get("negativeTopics", []):
            t = {"topic": topic.get("topic", "")}
            metrics = topic.get("asinMetrics", {})
            t["numberOfMentions"] = metrics.get("numberOfMentions")
            t["occurrencePercentage"] = metrics.get("occurrencePercentage")
            t["starRatingImpact"] = metrics.get("starRatingImpact")
            t["reviewSnippets"] = topic.get("reviewSnippets", [])
            product["review_topics"]["negativeTopics"].append(t)

    return product


def load_data_from_files():
    """Load all JSON files from the data/ directory on startup."""
    if not DATA_DIR.exists():
        return

    for json_file in DATA_DIR.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                products = data
            elif isinstance(data, dict):
                products = data.get("products", [data])
            else:
                continue

            for item in products:
                if "asin" in item:
                    parsed = parse_sp_api_product(item)
                    existing = next((p for p in product_store if p["asin"] == parsed["asin"]), None)
                    if existing:
                        existing.update(parsed)
                    else:
                        product_store.append(parsed)
        except Exception as e:
            print(f"Error loading {json_file.name}: {e}")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the product dashboard HTML table."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "products": product_store,
    })


@app.get("/api/products", response_model=list[ProductData])
async def get_all_products():
    """Return all loaded products as JSON."""
    return [ProductData(**p) for p in product_store]


@app.get("/api/product/{asin}")
async def get_product(asin: str):
    """Fetch product data from SP-API by ASIN and add to dashboard."""
    try:
        product, errors = get_product_data(asin)
        product_dict = product.model_dump()
        if errors:
            product_dict["errors"] = errors
        existing = next((p for p in product_store if p["asin"] == asin), None)
        if existing:
            existing.update(product_dict)
        else:
            product_store.append(product_dict)
        return product_dict
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/products/bulk")
async def fetch_bulk(asins: list[str]):
    """Fetch product data for multiple ASINs from SP-API."""
    results = []
    for asin in asins:
        try:
            product, errors = get_product_data(asin)
            product_dict = product.model_dump()
            if errors:
                product_dict["errors"] = errors
            existing = next((p for p in product_store if p["asin"] == asin), None)
            if existing:
                existing.update(product_dict)
            else:
                product_store.append(product_dict)
            results.append(product_dict)
        except Exception as e:
            results.append({"asin": asin, "error": str(e)})
    return results


@app.post("/api/upload/json")
async def upload_json(file: UploadFile = File(...)):
    """Upload a JSON file with product data."""
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="File must be .json")

    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if isinstance(data, list):
        products = data
    elif isinstance(data, dict):
        products = data.get("products", [data])
    else:
        raise HTTPException(status_code=400, detail="Unexpected JSON structure")

    count = 0
    for item in products:
        if "asin" in item or "ASIN" in item:
            # Normalize key names
            normalized = normalize_product(item)
            asin = normalized.get("asin")
            existing = next((p for p in product_store if p["asin"] == asin), None)
            if existing:
                existing.update(normalized)
            else:
                product_store.append(normalized)
            count += 1

    return {"message": f"Loaded {count} products", "total": len(product_store)}


@app.post("/api/upload/excel")
async def upload_excel(file: UploadFile = File(...)):
    """Upload an Excel file with product data (matching spreadsheet format)."""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="File must be .xlsx or .xls")

    content = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read Excel: {e}")

    # Map spreadsheet columns to our model fields
    column_map = {
        "Product Details": "product_details",
        "ASIN": "asin",
        "URL": "url",
        "Image URL": "image_url",
        "Brand": "brand",
        "Origin": "origin",
        "Price $": "price",
        "Price": "price",
        "BSR": "bsr",
        "Ratings": "ratings",
        "Review Count": "review_count",
    }

    df = df.rename(columns=column_map)
    df = df.where(pd.notnull(df), None)

    count = 0
    for _, row in df.iterrows():
        item = {k: v for k, v in row.to_dict().items() if k in column_map.values() and v is not None}
        if "asin" in item:
            # Generate URL if missing
            if "url" not in item or item["url"] is None:
                item["url"] = f"https://www.amazon.com/dp/{item['asin']}?psc=1"
            existing = next((p for p in product_store if p["asin"] == item["asin"]), None)
            if existing:
                existing.update(item)
            else:
                product_store.append(item)
            count += 1

    return {"message": f"Loaded {count} products from Excel", "total": len(product_store)}


def normalize_product(item: dict) -> dict:
    """Normalize various key formats to our standard model fields."""
    key_map = {
        "ASIN": "asin",
        "Product Details": "product_details",
        "product_details": "product_details",
        "title": "product_details",
        "itemName": "product_details",
        "URL": "url",
        "url": "url",
        "Image URL": "image_url",
        "image_url": "image_url",
        "imageUrl": "image_url",
        "Brand": "brand",
        "brand": "brand",
        "Origin": "origin",
        "origin": "origin",
        "Price $": "price",
        "Price": "price",
        "price": "price",
        "BSR": "bsr",
        "bsr": "bsr",
        "Ratings": "ratings",
        "ratings": "ratings",
        "Review Count": "review_count",
        "review_count": "review_count",
        "reviewCount": "review_count",
    }
    normalized = {}
    for k, v in item.items():
        new_key = key_map.get(k, k)
        normalized[new_key] = v

    # Generate URL if missing
    if "url" not in normalized and "asin" in normalized:
        normalized["url"] = f"https://www.amazon.com/dp/{normalized['asin']}?psc=1"

    return normalized


@app.delete("/api/products")
async def clear_products():
    """Clear all fetched products."""
    product_store.clear()
    return {"message": "All products cleared"}


@app.post("/api/reload")
async def reload_data():
    """Reload product data from JSON files in data/ folder."""
    product_store.clear()
    load_data_from_files()
    return {"message": f"Reloaded {len(product_store)} products from data/ folder"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
