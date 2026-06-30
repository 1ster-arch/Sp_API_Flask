from sp_api.api import CatalogItems, Products, CustomerFeedback
from sp_api.base import Marketplaces
from config import SP_API_CREDENTIALS, MARKETPLACE_ID
from models import ProductData, ReviewTopicMetrics
from sp_api_auth import AccessTokenCache, LwaException, SPAPIConfig


token_cache = AccessTokenCache()


def get_marketplace():
    marketplace_map = {
        "ATVPDKIKX0DER": Marketplaces.US,
        "A2EUQ1WTGCTBG2": Marketplaces.CA,
        "A1F83G8C2ARO7P": Marketplaces.UK,
    }
    return marketplace_map.get(MARKETPLACE_ID, Marketplaces.US)


def get_authenticated_client_kwargs() -> dict:
    spapi_config = SPAPIConfig.from_credentials(SP_API_CREDENTIALS)
    access_token = token_cache.get_lwa_access_token(config=spapi_config)
    return {
        "credentials": SP_API_CREDENTIALS,
        "marketplace": get_marketplace(),
        "restricted_data_token": access_token,
    }


def fetch_catalog_item(asin: str) -> dict:
    """
    Fetch catalog data for a single ASIN using Catalog Items API v2022-04-01.
    Schema: https://github.com/amzn/selling-partner-api-models/blob/main/models/catalog-items-api-model/catalogItems_2022-04-01.json
    """
    catalog = CatalogItems(**get_authenticated_client_kwargs())
    response = catalog.get_catalog_item(
        asin=asin,
        includedData=["attributes", "images", "productTypes", "summaries", "salesRanks"],
    )
    return response.payload


def fetch_product_pricing(asin: str) -> dict:
    """Fetch competitive pricing data for a single ASIN."""
    pricing = Products(**get_authenticated_client_kwargs())
    response = pricing.get_product_pricing_for_asins(
        asin_list=[asin],
        item_type="Asin",
    )
    return response.payload


def fetch_customer_feedback(asin: str) -> dict:
    """
    Fetch customer feedback (ratings, review count, review topics) for an ASIN.
    Schema: https://github.com/amzn/selling-partner-api-models/blob/main/models/customer-feedback-api-model/customerFeedback_2024-06-01.json
    Uses: get_item_review_topics and get_item_review_trends
    """
    feedback = CustomerFeedback(**get_authenticated_client_kwargs())
    result = {}

    # Get review trends (overall rating + review count)
    trends_response = feedback.get_item_review_trends(asin=asin, marketplaceIds=[MARKETPLACE_ID])
    if trends_response and trends_response.payload:
        result["trends"] = trends_response.payload

    # Get review topics (topic metrics)
    topics_response = feedback.get_item_review_topics(asin=asin, marketplaceIds=[MARKETPLACE_ID])
    if topics_response and topics_response.payload:
        result["topics"] = topics_response.payload

    return result


def parse_catalog_item(payload: dict) -> dict:
    """
    Parse catalog item payload based on catalogItems_2022-04-01 schema.
    Extracts: product title, brand, images, bullet points, origin, sales rank.
    """
    result = {}

    # --- summaries ---
    # Schema: summaries[].itemName, summaries[].brand
    summaries = payload.get("summaries", [])
    if summaries:
        summary = summaries[0]
        result["product_details"] = summary.get("itemName", "")
        result["brand"] = summary.get("brand", "")

    # --- images ---
    # Schema: images[].images[].link, images[].images[].variant (MAIN, PT01, etc.)
    images = payload.get("images", [])
    if images:
        image_sets = images[0].get("images", [])
        if image_sets:
            # Prefer MAIN variant image
            main_img = next(
                (img for img in image_sets if img.get("variant") == "MAIN"),
                image_sets[0]
            )
            result["image_url"] = main_img.get("link", "")

    # --- attributes ---
    attributes = payload.get("attributes", {})

    # bullet_point: [{language_tag, value, marketplace_id}]
    bullet_points_raw = attributes.get("bullet_point", [])
    result["bullet_points"] = [
        bp.get("value", "") for bp in bullet_points_raw if bp.get("value")
    ]

    # country_of_origin: [{value, marketplace_id}]
    country_of_origin = attributes.get("country_of_origin", [])
    if country_of_origin:
        result["origin"] = country_of_origin[0].get("value", "N/A")

    # list_price: [{value, currency}]
    list_price = attributes.get("list_price", [])
    if list_price:
        price_val = list_price[0].get("value")
        if price_val:
            try:
                result["price"] = float(price_val)
            except (ValueError, TypeError):
                pass

    # --- salesRanks ---
    # Schema: salesRanks[].classificationRanks[].rank, salesRanks[].displayGroupRanks[].rank
    sales_ranks = payload.get("salesRanks", [])
    if sales_ranks:
        for rank_group in sales_ranks:
            class_ranks = rank_group.get("classificationRanks", [])
            display_ranks = rank_group.get("displayGroupRanks", [])
            if class_ranks:
                result["bsr"] = class_ranks[0].get("rank")
                break
            elif display_ranks:
                result["bsr"] = display_ranks[0].get("rank")
                break

    return result


def parse_pricing(payload: list) -> dict:
    """Parse Product Pricing API response for price and BSR."""
    result = {}
    if payload:
        product = payload[0].get("Product", {})

        # Price from Offers
        offers = product.get("Offers", [])
        if offers:
            listing_price = offers[0].get("BuyingPrice", {}).get("ListingPrice", {})
            amount = listing_price.get("Amount")
            if amount:
                result["price"] = float(amount)

        # BSR from SalesRankings
        sales_rankings = product.get("SalesRankings", [])
        if sales_rankings:
            result["bsr"] = sales_rankings[0].get("Rank")

    return result


def parse_customer_feedback(payload: dict) -> dict:
    """
    Parse Customer Feedback API response.
    Trends schema: {asin, overallStarRating, reviewCount, ...}
    Topics schema: {asin, topics: [{topicTitle, metrics: {numberOfMentions, occurrencePercentage, starRatingImpact}}]}
    """
    result = {}

    # --- Review Trends (overall rating + review count) ---
    trends = payload.get("trends", {})
    if isinstance(trends, list) and trends:
        trends = trends[0]

    star_rating = trends.get("overallStarRating") or trends.get("starRating")
    if star_rating is not None:
        result["ratings"] = float(star_rating)

    review_count = trends.get("reviewCount") or trends.get("numberOfReviews")
    if review_count is not None:
        result["review_count"] = int(review_count)

    # --- Review Topics (topic metrics) ---
    topics_data = payload.get("topics", {})
    if isinstance(topics_data, list) and topics_data:
        topics_data = topics_data[0]

    review_topics = topics_data.get("topics", []) if isinstance(topics_data, dict) else []
    if review_topics:
        positive = []
        negative = []
        for topic in review_topics:
            metrics = topic.get("metrics", {})
            parsed_topic = {
                "topic": topic.get("topicTitle", ""),
                "numberOfMentions": metrics.get("numberOfMentions"),
                "occurrencePercentage": metrics.get("occurrencePercentage"),
                "starRatingImpact": metrics.get("starRatingImpact"),
            }
            impact = metrics.get("starRatingImpact") or 0
            if impact >= 0:
                positive.append(parsed_topic)
            else:
                negative.append(parsed_topic)
        result["review_topics"] = {
            "positiveTopics": positive,
            "negativeTopics": negative,
        }

    return result


def get_product_data(asin: str) -> tuple:
    """
    Fetch and combine all product data for an ASIN from multiple SP-API endpoints:
    1. Catalog Items API - title, brand, images, bullet points, origin, BSR
    2. Product Pricing API - price, BSR (backup)
    3. Customer Feedback API - ratings, review count, review topics
    """
    product = {"asin": asin}
    product["url"] = f"https://www.amazon.com/dp/{asin}?psc=1"
    errors = []

    # 1. Catalog Items API
    try:
        catalog_payload = fetch_catalog_item(asin)
        product.update(parse_catalog_item(catalog_payload))
    except LwaException:
        raise
    except Exception as e:
        errors.append(f"Catalog: {e}")

    # 2. Product Pricing API
    try:
        pricing_payload = fetch_product_pricing(asin)
        pricing_data = parse_pricing(pricing_payload)
        # Only fill price/bsr if catalog didn't provide them
        if "price" not in product or product.get("price") is None:
            if "price" in pricing_data:
                product["price"] = pricing_data["price"]
        if "bsr" not in product or product.get("bsr") is None:
            if "bsr" in pricing_data:
                product["bsr"] = pricing_data["bsr"]
    except LwaException:
        raise
    except Exception as e:
        errors.append(f"Pricing: {e}")

    # 3. Customer Feedback API (ratings + review count)
    try:
        feedback_payload = fetch_customer_feedback(asin)
        product.update(parse_customer_feedback(feedback_payload))
    except LwaException:
        raise
    except Exception as e:
        errors.append(f"CustomerFeedback: {e}")

    return ProductData(**{k: v for k, v in product.items() if not k.startswith("_")}), errors
