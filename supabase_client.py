import json
import httpx
from typing import List, Dict, Any, Optional
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import supabase
from logger import log_step, log_error
from state import state


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

    def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        json_data: Optional[List] = None,
        single_data: Optional[Dict] = None,
    ) -> httpx.Response:
        headers = dict(self.headers)
        if method in ("POST", "PATCH", "PUT"):
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "return=representation"

        with httpx.Client(timeout=60) as client:
            request_kwargs = {"headers": headers}
            if params:
                request_kwargs["params"] = params
            if json_data:
                request_kwargs["json"] = json_data
            if single_data:
                request_kwargs["json"] = single_data

            response = client.request(method, url, **request_kwargs)
            return response

    def upsert_product(self, product: Dict[str, Any]) -> Optional[Dict]:
        product_id = product.get("id")
        if not product_id:
            logger.warning("Product has no id, skipping")
            return None

        url = self._get_rest_url()
        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=representation"

        payload = {k: v for k, v in product.items() if v is not None}

        try:
            with httpx.Client(timeout=60) as client:
                response = client.post(
                    url,
                    headers=headers,
                    json=payload,
                )
                if response.status_code in (200, 201):
                    result = response.json()
                    if isinstance(result, list):
                        return result[0] if result else None
                    return result
                elif response.status_code in (409, 23505):
                    return self._update_product(product)
                elif response.status_code == 409:
                    return self._update_product(product)
                else:
                    logger.warning(f"Upsert failed ({response.status_code}): {response.text[:200]}")
                    return self._update_product(product)
        except Exception as e:
            logger.error(f"Upsert error: {e}")
            return None

    def _update_product(self, product: Dict[str, Any]) -> Optional[Dict]:
        product_id = product.get("id")
        if not product_id:
            return None

        url = f"{self._get_rest_url()}?id=eq.{product_id}"
        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=representation"

        payload = {k: v for k, v in product.items() if v is not None}

        try:
            with httpx.Client(timeout=60) as client:
                response = client.patch(
                    url,
                    headers=headers,
                    json=payload,
                )
                if response.status_code in (200, 206):
                    result = response.json()
                    if isinstance(result, list):
                        return result[0] if result else None
                    return result
                else:
                    logger.warning(f"Update failed ({response.status_code}): {response.text[:200]}")
                    return None
        except Exception as e:
            logger.error(f"Update error: {e}")
            return None

    def upsert_products_batch(self, products: List[Dict[str, Any]]) -> Dict[str, int]:
        log_step("SUPABASE", f"Batch upserting {len(products)} products...")

        success = 0
        failed = 0
        errors = 0

        for product in products:
            try:
                result = self.upsert_product(product)
                if result:
                    success += 1
                    state.db_import_count += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Failed to upsert {product.get('product_url', 'unknown')}: {e}")
                failed += 1
                errors += 1

        state.save()

        logger.info(f"Batch upsert: {success} success, {failed} failed")
        return {"success": success, "failed": failed}

    def get_existing_products(self) -> List[str]:
        log_step("SUPABASE", "Fetching existing product URLs...")
        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "application/json"

        url = self._get_rest_url("?select=product_url,id")

        try:
            with httpx.Client(timeout=60) as client:
                response = client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    product_urls = [p.get("product_url") for p in data if p.get("product_url")]
                    logger.success(f"Found {len(product_urls)} existing products")
                    return product_urls
                else:
                    logger.warning(f"Fetch failed ({response.status_code})")
                    return []
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            return []

    def check_product_exists(self, product_url: str) -> bool:
        product_urls = self.get_existing_products()
        return product_url in product_urls

    def delete_product(self, product_url: str) -> bool:
        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"

        url = f"{self._get_rest_url()}?product_url=eq.{product_url.replace('/', '%2F')}"

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