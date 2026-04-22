import json
import time
import httpx
from typing import List, Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger

from config import shopify
from logger import log_step, log_error


GRAPHQL_PRODUCTS_QUERY = """
query getProducts($first: Int!, $after: String) {
  products(first: $first, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        handle
        title
        description
        descriptionHtml
        tags
        productType
        vendor
        createdAt
        updatedAt
        priceRange {
          minVariantPrice {
            amount
            currencyCode
          }
          maxVariantPrice {
            amount
            currencyCode
          }
        }
        compareAtPriceRange {
          minVariantPrice {
            amount
            currencyCode
          }
          maxVariantPrice {
            amount
            currencyCode
          }
        }
        featuredImage {
          url
          altText
          width
          height
        }
        images(first: 20) {
          edges {
            node {
              url
              altText
              width
              height
            }
          }
        }
        variants(first: 100) {
          edges {
            node {
              id
              title
              price {
                amount
                currencyCode
              }
              compareAtPrice {
                amount
                currencyCode
              }
              availableForSale
              quantityAvailable
              selectedOptions {
                name
                value
              }
              image {
                url
                altText
              }
            }
          }
        }
        options {
          name
          values
        }
        metafields(identifiers: [
          {namespace: "custom", key: "gender"},
          {namespace: "custom", key: "sizes"},
          {namespace: "custom", key: "colors"},
          {namespace: "custom", key: "additional_info"},
          {namespace: "custom", key: "category"}
        ]) {
          key
          namespace
          value
          type
        }
        seo {
          title
          description
        }
      }
    }
  }
}
"""

GRAPHQL_PRODUCT_HANDLES_QUERY = """
query getProductHandles($first: Int!, $after: String) {
  products(first: $first, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        handle
      }
    }
  }
}
"""


class ShopifyClient:
    def __init__(self):
        self.api_url = shopify.api_url
        self.headers = shopify.headers
        self.max_retries = 3

    def _post(self, query: str, variables: Optional[Dict] = None) -> Dict:
        payload = {"query": query, "variables": variables or {}}
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=shopify.request_timeout) as client:
                    response = client.post(
                        self.api_url,
                        headers=self.headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                    if data.get("errors"):
                        errors = data["errors"]
                        logger.error(f"GraphQL errors: {errors}")
                        raise Exception(f"GraphQL error: {errors}")
                    return data.get("data", {})
            except httpx.HTTPStatusError as e:
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(f"Attempt {attempt + 1} failed, retrying in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"All {self.max_retries} attempts failed: {e}")
                    raise
            except Exception as e:
                logger.error(f"Shopify API error: {e}")
                raise

    def get_all_product_handles(self) -> List[str]:
        log_step("SHOPIFY", "Fetching all product handles...")
        handles = []
        cursor = None
        page = 0

        while True:
            page += 1
            variables = {"first": 50, "after": cursor}
            data = self._post(GRAPHQL_PRODUCT_HANDLES_QUERY, variables)

            products = data.get("products", {})
            edges = products.get("edges", [])
            page_info = products.get("pageInfo", {})

            for edge in edges:
                handle = edge.get("node", {}).get("handle")
                if handle:
                    handles.append(handle)

            has_next = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

            logger.info(f"Page {page}: fetched {len(handles)} handles total")

            if not has_next or not cursor:
                break

        logger.info(f"Total handles fetched: {len(handles)}")
        return handles

    def get_product_by_handle(self, handle: str) -> Optional[Dict[str, Any]]:
        log_step("SHOPIFY", f"Fetching product: {handle}")

        query = """
        query getProductByHandle($handle: String!) {
          productByHandle(handle: $handle) {
            id
            handle
            title
            description
            descriptionHtml
            tags
            productType
            vendor
            createdAt
            updatedAt
            priceRange {
              minVariantPrice { amount currencyCode }
              maxVariantPrice { amount currencyCode }
            }
            compareAtPriceRange {
              minVariantPrice { amount currencyCode }
              maxVariantPrice { amount currencyCode }
            }
            featuredImage { url altText width height }
            images(first: 20) {
              edges { node { url altText width height } }
            }
            variants(first: 100) {
              edges {
                node {
                  id
                  title
                  price { amount currencyCode }
                  compareAtPrice { amount currencyCode }
                  availableForSale
                  quantityAvailable
                  selectedOptions { name value }
                  image { url altText }
                }
              }
            }
            options { name values }
            metafields(identifiers: [
              {namespace: "custom", key: "gender"},
              {namespace: "custom", key: "sizes"},
              {namespace: "custom", key: "colors"},
              {namespace: "custom", key: "additional_info"},
              {namespace: "custom", key: "category"}
            ]) {
              key namespace value type
            }
            seo { title description }
          }
        }
        """

        variables = {"handle": handle}
        data = self._post(query, variables)
        return data.get("productByHandle")

    def get_product_variants_prices(self, handle: str) -> List[Dict]:
        product = self.get_product_by_handle(handle)
        if not product:
            return []

        variants = []
        for edge in product.get("variants", {}).get("edges", []):
            node = edge.get("node", {})
            variants.append({
                "id": node.get("id"),
                "title": node.get("title"),
                "price": node.get("price", {}).get("amount"),
                "currency": node.get("price", {}).get("currencyCode"),
                "compare_at_price": node.get("compareAtPrice", {}).get("amount"),
                "available": node.get("availableForSale"),
                "quantity": node.get("quantityAvailable"),
                "options": node.get("selectedOptions", []),
                "image_url": node.get("image", {}).get("url"),
            })

        return variants

    def test_connection(self) -> bool:
        try:
            query = "{ shop { name } }"
            data = self._post(query, {})
            shop_name = data.get("shop", {}).get("name")
            logger.success(f"Shopify connection OK: {shop_name}")
            return True
        except Exception as e:
            logger.error(f"Shopify connection FAILED: {e}")
            return False