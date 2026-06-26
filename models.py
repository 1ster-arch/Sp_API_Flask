from pydantic import BaseModel
from typing import Optional


class ProductData(BaseModel):
    product_details: Optional[str] = None
    asin: str
    url: Optional[str] = None
    image_url: Optional[str] = None
    brand: Optional[str] = None
    origin: Optional[str] = None
    price: Optional[float] = None
    bsr: Optional[int] = None
    ratings: Optional[float] = None
    review_count: Optional[int] = None
    bullet_points: Optional[list[str]] = None
    review_topics: Optional[dict] = None


class ReviewTopicMetrics(BaseModel):
    topic: Optional[str] = None
    number_of_mentions: Optional[int] = None
    occurrence_percentage: Optional[float] = None
    star_rating_impact: Optional[float] = None
