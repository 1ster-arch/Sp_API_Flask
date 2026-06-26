import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from sp_api_client import get_product_data

app = FastAPI(title="SP-API Product Dashboard", version="1.0.0")
templates = Jinja2Templates(directory="templates")
DATA_DIR = Path(__file__).parent / "data"
DB_FILE = DATA_DIR / "products_db.json"
DATA_DIR.mkdir(exist_ok=True)

def load_db():
    if not DB_FILE.exists(): return []
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)

def normalize_product(item):
    key_map = {
        "ASIN": "asin", "Product Details": "product_details", "title": "product_details",
        "itemName": "product_details", "URL": "url", "url": "url", "Image URL": "image_url",
        "image_url": "image_url", "imageUrl": "image_url", "Brand": "brand", "brand": "brand",
        "Origin": "origin", "origin": "origin", "Price $": "price", "Price": "price",
        "price": "price", "BSR": "bsr", "bsr": "bsr", "Ratings": "ratings",
        "ratings": "ratings", "Review Count": "review_count", "review_count": "review_count"
    }
    norm = {key_map.get(k, k): v for k, v in item.items()}
    if "url" not in norm and "asin" in norm: norm["url"] = f"https://www.amazon.com/dp/{norm['asin']}?psc=1"
    return norm

def parse_sp_api_product(item):
    p = {"asin": item.get("asin", ""), "url": f"https://www.amazon.com/dp/{item.get('asin', '')}?psc=1"}
    if item.get("summaries"):
        p["product_details"] = item["summaries"][0].get("itemName", "")
        p["brand"] = item["summaries"][0].get("brand", "")
    if item.get("attributes", {}).get("list_price"):
        p["price"] = float(item["attributes"]["list_price"][0].get("value", 0))
    return p

def load_data_from_files():
    db_store = load_db()
    for json_file in DATA_DIR.glob("*.json"):
        if json_file.name == "products_db.json": continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                products = data if isinstance(data, list) else data.get("products", [data])
                for item in products:
                    if "asin" in item or "ASIN" in item:
                        parsed = normalize_product(item) if any(k in item for k in ["product_details", "brand", "price"]) else parse_sp_api_product(item)
                        existing = next((p for p in db_store if p.get("asin") == parsed.get("asin")), None)
                        if existing: existing.update(parsed)
                        else: db_store.append(parsed)
        except (json.JSONDecodeError, KeyError, TypeError, OSError):
            continue
    save_db(db_store)

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "products": load_db()})

@app.delete("/api/products")
async def clear_products():
    save_db([])
    return {"message": "Cleared"}

@app.post("/api/reload")
async def reload_data():
    save_db([])
    load_data_from_files()
    return {"message": "Reloaded"}

@app.post("/api/fetch/{asin}")
async def fetch_product(asin: str):
    product_data, errors = get_product_data(asin)
    product = product_data.model_dump(exclude_none=True)
    db_store = load_db()
    existing = next((p for p in db_store if p.get("asin") == asin), None)
    if existing:
        existing.update(product)
    else:
        db_store.append(product)
    save_db(db_store)
    return {"product": product, "errors": errors}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)