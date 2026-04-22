import json
from pathlib import Path
from typing import Optional, List, Set
from datetime import datetime
from loguru import logger

from config import BASE_DIR, STATE_FILE, FAILED_PRODUCTS_FILE


class ScraperState:
    def __init__(self):
        self.state_file = STATE_FILE
        self.failed_file = FAILED_PRODUCTS_FILE
        self._load()

    def _load(self):
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                    self.last_scrape_time = data.get("last_scrape_time")
                    self.products_scrape_count = data.get("products_scrape_count", 0)
                    self.embeddings_count = data.get("embeddings_count", 0)
                    self.db_import_count = data.get("db_import_count", 0)
                    self.failed_products: Set[str] = set(data.get("failed_products", []))
                    self.completed_products: Set[str] = set(data.get("completed_products", []))
            except (json.JSONDecodeError, KeyError):
                self._reset()
        else:
            self._reset()

    def _reset(self):
        self.last_scrape_time: Optional[str] = None
        self.products_scrape_count: int = 0
        self.embeddings_count: int = 0
        self.db_import_count: int = 0
        self.failed_products: Set[str] = set()
        self.completed_products: Set[str] = set()

    def save(self):
        with open(self.state_file, "w") as f:
            json.dump({
                "last_scrape_time": self.last_scrape_time,
                "products_scrape_count": self.products_scrape_count,
                "embeddings_count": self.embeddings_count,
                "db_import_count": self.db_import_count,
                "failed_products": list(self.failed_products),
                "completed_products": list(self.completed_products),
            }, f, indent=2)

    def mark_completed(self, product_url: str):
        self.completed_products.add(product_url)
        self.failed_products.discard(product_url)
        self.save()

    def mark_failed(self, product_url: str):
        self.failed_products.add(product_url)
        self.save()

    def is_completed(self, product_url: str) -> bool:
        return product_url in self.completed_products

    def load_failed_products(self) -> Set[str]:
        if self.failed_file.exists():
            try:
                with open(self.failed_file) as f:
                    data = json.load(f)
                    return set(data.get("products", []))
            except json.JSONDecodeError:
                return set()
        return set()

    def save_failed_products(self, products: Set[str]):
        with open(self.failed_file, "w") as f:
            json.dump({"products": list(products), "saved_at": datetime.now().isoformat()}, f, indent=2)


state = ScraperState()