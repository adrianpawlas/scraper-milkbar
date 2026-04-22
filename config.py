import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.resolve()
STATE_FILE = BASE_DIR / ".scraper_state.json"
FAILED_PRODUCTS_FILE = BASE_DIR / "failed_products.json"
LOG_DIR = BASE_DIR / "logs"


@dataclass
class ShopifyConfig:
    store_domain: str = os.getenv("shopify_store_domain", "milkbarmelbourne.myshopify.com")
    storefront_token: str = os.getenv("shopify_storefront_token", "")
    api_version: str = os.getenv("shopify_api_version", "2025-07")
    product_fetch_limit: int = int(os.getenv("shopify_product_fetch_limit", "50"))
    max_pages: int = int(os.getenv("shopify_max_pages", "100"))
    request_timeout: int = int(os.getenv("request_timeout", "30"))

    @property
    def api_url(self) -> str:
        return f"https://{self.store_domain}/api/{self.api_version}/graphql.json"

    @property
    def headers(self) -> dict:
        return {
            "X-Shopify-Storefront-Access-Token": self.storefront_token,
            "Content-Type": "application/json",
        }


@dataclass
class SupabaseConfig:
    url: str = os.getenv("supabase_url", "")
    anon_key: str = os.getenv("supabase_anon_key", "")
    table_name: str = "products"
    source: str = "scraper-milkbar"
    brand: str = "Milkbar"

    @property
    def headers(self) -> dict:
        return {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.anon_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }


@dataclass
class EmbeddingConfig:
    model: str = os.getenv("embedding_model", "google/siglip-base-patch16-384")
    dimension: int = int(os.getenv("embedding_dimension", "768"))
    embeddings_per_product: int = int(os.getenv("embeddings_per_product", "1"))
    device: str = "cuda"
    batch_size: int = int(os.getenv("embedding_batch_size", "4"))


@dataclass
class ScraperConfig:
    batch_size: int = int(os.getenv("scrape_batch_size", "10"))
    user_agent: str = os.getenv(
        "user_agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    request_timeout: int = int(os.getenv("request_timeout", "30"))
    max_retries: int = int(os.getenv("max_retries", "3"))
    retry_delay: int = int(os.getenv("retry_delay", "5"))
    store_url: str = "https://milkbarmelbourne.com"
    store_flat_url: str = "https://milkbarmelbourne.com/store-flat"


@dataclass
class LogConfig:
    level: str = os.getenv("log_level", "INFO")
    format: str = os.getenv(
        "log_format",
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )


shopify = ShopifyConfig()
supabase = SupabaseConfig()
embedding = EmbeddingConfig()
scraper = ScraperConfig()
log = LogConfig()