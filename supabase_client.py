import json
import time
import httpx
from typing import List, Dict, Any, Optional, Set, Tuple
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import supabase
from logger import log_step, log_error
from state import state


BATCH_SIZE = 50
CONSECUTIVE_RUNS_THRESHOLD = 2


class SupabaseClient:
    def __init__(self):
        self.url = supabase.url
        self.headers = supabase.headers
        self.table_name = supabase.table_name
        self.source = supabase.source
        self.brand = supabase.brand

    def _get_rest_url(self, operation: str = "") -> str:
        if operation:
            return f"{self.url}/rest/v1/{self.table_name}{operation}"
        return f"{self.url}/rest/v1/{self.table_name}"

    def get_all_products_for_source(self) -> List[Dict]:
        log_step("SUPABASE", "Fetching all products for this source...")
        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "application/json"

        url = self._get_rest_url(f"?select=*&source=eq.{self.source}")

        try:
            with httpx.Client(timeout=60) as client:
                response = client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    logger.success(f"Found {len(data)} existing products")
                    return data
                else:
                    logger.warning(f"Fetch failed ({response.status_code})")
                    return []
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            return []

    def get_existing_products(self) -> Dict[str, str]:
        products = self.get_all_products_for_source()
        return {p.get("product_url"): p for p in products if p.get("product_url")}

    def get_product_by_id(self, product_id: str) -> Optional[Dict]:
        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "application/json"

        url = self._get_rest_url(f"?select=*&id=eq.{product_id}")

        try:
            with httpx.Client(timeout=30) as client:
                response = client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return data[0] if data else None
                return None
        except Exception as e:
            logger.error(f"Get product error: {e}")
            return None

    def _compare_products(self, scraped: Dict, existing: Dict) -> Tuple[bool, bool]:
        changed_fields = []
        needs_embedding = False

        fields_to_check = [
            ("title", str),
            ("description", str),
            ("price", str),
            ("sale", str),
            ("category", str),
            ("gender", str),
            ("size", str),
            ("image_url", str),
            ("additional_images", str),
        ]

        for field, field_type in fields_to_check:
            scraped_val = scraped.get(field)
            existing_val = existing.get(field)

            if scraped_val is None:
                scraped_val = ""
            if existing_val is None:
                existing_val = ""

            if str(scraped_val) != str(existing_val):
                changed_fields.append(field)
                if field == "image_url":
                    needs_embedding = True

        has_changes = len(changed_fields) > 0
        return has_changes, needs_embedding

    def _insert_batch(self, products: List[Dict], retry_count: int = 0) -> Tuple[int, int]:
        if not products:
            return 0, 0

        url = self._get_rest_url()
        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=representation"

        payload = [{k: v for k, v in p.items() if v is not None} for p in products]

        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(url, headers=headers, json=payload)

                if response.status_code in (200, 201):
                    inserted = response.json()
                    return len(inserted) if isinstance(inserted, list) else 1, 0

                elif response.status_code in (409, 23505) and retry_count < 3:
                    logger.warning(f"Batch conflict, retrying ({retry_count + 1}/3)...")
                    time.sleep(2 ** retry_count)
                    return self._insert_batch(products, retry_count + 1)

                else:
                    logger.error(f"Batch insert failed ({response.status_code}): {response.text[:200]}")
                    return 0, len(products)

        except Exception as e:
            if retry_count < 3:
                logger.warning(f"Batch insert error, retrying ({retry_count + 1}/3): {e}")
                time.sleep(2 ** retry_count)
                return self._insert_batch(products, retry_count + 1)
            logger.error(f"Batch insert failed after 3 retries: {e}")
            return 0, len(products)

    def _update_batch(self, products: List[Dict], retry_count: int = 0) -> Tuple[int, int]:
        if not products:
            return 0, 0

        success_count = 0
        fail_count = 0

        for product in products:
            product_id = product.get("id")
            if not product_id:
                fail_count += 1
                continue

            url = f"{self._get_rest_url()}?id=eq.{product_id}"
            headers = dict(self.headers)
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "return=representation"

            payload = {k: v for k, v in product.items() if v is not None}
            payload["updated_at"] = datetime.now().isoformat()

            try:
                with httpx.Client(timeout=60) as client:
                    response = client.patch(url, headers=headers, json=payload)
                    if response.status_code in (200, 206):
                        success_count += 1
                    else:
                        fail_count += 1
            except Exception as e:
                logger.error(f"Update error for {product_id}: {e}")
                fail_count += 1

        return success_count, fail_count

    def process_products_batch(
        self,
        products: List[Dict],
        existing_products: Dict[str, Dict]
    ) -> Dict[str, int]:
        new_products = []
        products_to_update = []
        unchanged_products = []

        for product in products:
            product_id = product.get("id")
            existing = existing_products.get(product_id)

            if not existing:
                new_products.append(product)
            else:
                has_changes, needs_embedding = self._compare_products(product, existing)

                if has_changes:
                    if needs_embedding:
                        product["_needs_embedding"] = True
                    products_to_update.append(product)
                else:
                    unchanged_products.append(product_id)

        results = {
            "new": 0,
            "updated": 0,
            "unchanged": 0,
            "failed": 0,
            "failed_ids": []
        }

        if new_products:
            for i in range(0, len(new_products), BATCH_SIZE):
                batch = new_products[i:i + BATCH_SIZE]
                inserted, failed = self._insert_batch(batch)
                results["new"] += inserted
                results["failed"] += failed
                if failed > 0:
                    results["failed_ids"].extend([p.get("id") for p in batch if p.get("id")])
                time.sleep(0.5)

        if products_to_update:
            for i in range(0, len(products_to_update), BATCH_SIZE):
                batch = products_to_update[i:i + BATCH_SIZE]
                updated, failed = self._update_batch(batch)
                results["updated"] += updated
                results["failed"] += failed
                if failed > 0:
                    results["failed_ids"].extend([p.get("id") for p in batch if p.get("id")])
                time.sleep(0.5)

        results["unchanged"] = len(unchanged_products)

        log_step("SUPABASE", f"Processed: {results['new']} new, {results['updated']} updated, {results['unchanged']} unchanged, {results['failed']} failed")

        return results

    def delete_stale_products(self, current_product_ids: Set[str], source: str) -> int:
        log_step("SUPABASE", "Checking for stale products...")

        all_products = self.get_all_products_for_source()
        all_ids = {p.get("id") for p in all_products}

        stale_ids = all_ids - current_product_ids

        if not stale_ids:
            logger.info("No stale products found")
            return 0

        logger.info(f"Found {len(stale_ids)} stale products to check")

        deleted_count = 0
        for product_id in stale_ids:
            product = self.get_product_by_id(product_id)
            if not product:
                continue

            last_seen = product.get("last_seen_count", 0) + 1

            if last_seen >= CONSECUTIVE_RUNS_THRESHOLD:
                url = f"{self._get_rest_url()}?id=eq.{product_id}"
                headers = dict(self.headers)
                headers["Content-Type"] = "application/json"

                try:
                    with httpx.Client(timeout=30) as client:
                        response = client.delete(url, headers=headers)
                        if response.status_code in (200, 204):
                            deleted_count += 1
                            logger.info(f"Deleted stale product: {product_id}")
                except Exception as e:
                    logger.error(f"Delete error for {product_id}: {e}")

        logger.success(f"Deleted {deleted_count} stale products")
        return deleted_count

    def update_last_seen_count(self, product_ids: List[str]):
        for product_id in product_ids:
            product = self.get_product_by_id(product_id)
            current_count = product.get("last_seen_count", 0) if product else 0

            url = f"{self._get_rest_url()}?id=eq.{product_id}"
            headers = dict(self.headers)
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "return=representation"

            payload = {"last_seen_count": current_count + 1}

            try:
                with httpx.Client(timeout=30) as client:
                    client.patch(url, headers=headers, json=payload)
            except Exception as e:
                logger.error(f"Update last_seen error for {product_id}: {e}")

    def delete_product(self, product_id: str) -> bool:
        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"

        url = f"{self._get_rest_url()}?id=eq.{product_id}"

        try:
            with httpx.Client(timeout=30) as client:
                response = client.delete(url, headers=headers)
                return response.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Delete error: {e}")
            return False

    def test_connection(self) -> bool:
        try:
            headers = dict(self.headers)
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "application/json"

            url = f"{self._get_rest_url()}?select=id&limit=1"

            with httpx.Client(timeout=30) as client:
                response = client.get(url, headers=headers)
                if response.status_code == 200:
                    logger.success("Supabase connection OK")
                    return True
                else:
                    logger.error(f"Supabase connection failed: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Supabase connection error: {e}")
            return False


_client: Optional[SupabaseClient] = None


def get_supabase_client() -> SupabaseClient:
    global _client
    if _client is None:
        _client = SupabaseClient()
    return _client


from datetime import datetime
