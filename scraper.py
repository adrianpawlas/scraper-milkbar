import json
import re
from typing import Dict, List, Any, Optional
from loguru import logger

from shopify_client import ShopifyClient
from config import shopify
from utils import (
    parse_multi_price,
    parse_category,
    parse_gender,
    format_additional_images,
    truncate_text,
    generate_product_id,
)
from logger import log_step


class ProductScraper:
    def __init__(self, shopify_client: ShopifyClient):
        self.client = shopify_client
        self._all_handles: Optional[List[str]] = None

    def get_all_handles(self) -> List[str]:
        if self._all_handles is None:
            self._all_handles = self.client.get_all_product_handles()
        return self._all_handles

    def scrape_product(self, handle: str) -> Optional[Dict[str, Any]]:
        log_step("SCRAPE", f"Scraping product: {handle}")

        try:
            product = self.client.get_product_by_handle(handle)
            if not product:
                logger.warning(f"Product not found: {handle}")
                return None

            return self._normalize_product(product, handle)

        except Exception as e:
            logger.error(f"Failed to scrape product {handle}: {e}")
            raise

    def scrape_all_products(self) -> List[Dict[str, Any]]:
        log_step("SCRAPE", "Starting full product scrape...")
        handles = self.get_all_handles()
        log_step("SCRAPE", f"Found {len(handles)} products to scrape")

        products = []
        for i, handle in enumerate(handles, 1):
            try:
                product_data = self.scrape_product(handle)
                if product_data:
                    products.append(product_data)
                if i % 20 == 0:
                    logger.info(f"Progress: {i}/{len(handles)} scraped")
            except Exception as e:
                logger.error(f"Error scraping {handle}: {e}")
                continue

        logger.success(f"Successfully scraped {len(products)} products")
        return products

    def _normalize_product(self, product: Dict, handle: str) -> Dict[str, Any]:
        variants = self._extract_variants(product)
        images = self._extract_images(product)
        metafields = self._extract_metafields(product)
        tags = product.get("tags", [])
        product_type = product.get("productType", "")
        seo = product.get("seo", {})

        title = product.get("title", "")
        description = self._clean_html(product.get("description", ""))
        description_html = product.get("descriptionHtml", "")
        featured_image = product.get("featuredImage", {})

        price_range = product.get("priceRange", {})
        compare_at_range = product.get("compareAtPriceRange", {})

        min_price = price_range.get("minVariantPrice", {}).get("amount", "0")
        max_price = price_range.get("maxVariantPrice", {}).get("amount", "0")
        min_compare = compare_at_range.get("minVariantPrice", {}).get("amount")
        max_compare = compare_at_range.get("maxVariantPrice", {}).get("amount")

        is_sale = min_compare and float(min_compare) > 0

        if min_price == max_price:
            price = f"{float(min_price):.2f}AUD"
        else:
            price = f"{float(min_price):.2f}AUD-{float(max_price):.2f}AUD"

        if is_sale:
            if min_compare == max_compare:
                sale = f"{float(min_compare):.2f}AUD"
            else:
                sale = f"{float(min_compare):.2f}AUD-{float(max_compare):.2f}AUD"
        else:
            sale = price

        gender = metafields.get("gender") or parse_gender(None)
        category_meta = metafields.get("category") or parse_category(product_type)

        category = category_meta
        if not category:
            tag_cats = []
            for t in tags:
                t_lower = t.lower()
                if any(k in t_lower for k in ["outerwear", "jacket", "bomber", "coat", "parka"]):
                    tag_cats.append("Outerwear")
                elif any(k in t_lower for k in ["polo", "t-shirt", "t_shirt", "tee", "henley", "raglan"]):
                    tag_cats.append("Tops")
                elif any(k in t_lower for k in ["short", "pants", "jean", "chino", "jogger"]):
                    tag_cats.append("Bottoms")
                elif any(k in t_lower for k in ["singlet", "tank"]):
                    tag_cats.append("Singlets")
                elif any(k in t_lower for k in ["sweater", "hoodie", "sweatshirt", "crewneck", "cardigan", "knitted"]):
                    tag_cats.append("Knitwear")
                elif any(k in t_lower for k in ["gift", "card"]):
                    tag_cats.append("Accessories")
            unique_cats = []
            for c in tag_cats:
                if c not in unique_cats:
                    unique_cats.append(c)
            category = ", ".join(unique_cats) if unique_cats else "Tops"

        sizes = metafields.get("sizes", "")
        colors = metafields.get("colors", "")
        additional_info = metafields.get("additional_info", "")

        tags_str = ", ".join(tags) if tags else ""

        metadata_parts = []
        if title:
            metadata_parts.append(f"Title: {title}")
        if description:
            metadata_parts.append(f"Description: {description}")
        if tags_str:
            metadata_parts.append(f"Tags: {tags_str}")
        if sizes:
            metadata_parts.append(f"Sizes: {sizes}")
        if colors:
            metadata_parts.append(f"Colors: {colors}")
        if additional_info:
            metadata_parts.append(f"Additional Info: {additional_info}")

        metadata = " | ".join(metadata_parts)
        metadata = truncate_text(metadata, 4000)

        info_text_parts = [
            title,
            description,
            f"Category: {category}",
            f"Price: {price}",
            f"Gender: {gender}" if gender else "",
            tags_str,
            sizes,
            colors,
            additional_info,
            seo.get("description", ""),
        ]
        info_text = " ".join(p for p in info_text_parts if p)
        info_text = truncate_text(info_text, 2000)

        product_url = f"https://milkbarmelbourne.com/store-flat/{handle}"
        image_url = featured_image.get("url", "") if featured_image else ""
        additional_images = format_additional_images(images[1:]) if len(images) > 1 else ""

        normalized = {
            "id": generate_product_id(handle),
            "source": "scraper-milkbar",
            "product_url": product_url,
            "affiliate_url": None,
            "image_url": image_url,
            "brand": "Milkbar",
            "title": title,
            "description": truncate_text(description, 2000),
            "category": category,
            "gender": gender,
            "created_at": product.get("createdAt"),
            "metadata": metadata,
            "size": sizes,
            "second_hand": False,
            "image_embedding": None,
            "country": "AU",
            "compressed_image_url": None,
            "tags": tags,
            "title_tsv": None,
            "brand_tsv": None,
            "description_tsv": None,
            "other": json.dumps({
                "shopify_id": product.get("id"),
                "handle": handle,
                "vendor": product.get("vendor"),
                "product_type": product_type,
                "sizes": sizes,
                "colors": colors,
                "variants": variants,
                "seo_title": seo.get("title"),
                "seo_description": seo.get("description"),
            }),
            "price": price,
            "sale": sale,
            "additional_images": additional_images,
            "info_embedding": None,
        }

        return normalized

    def _extract_variants(self, product: Dict) -> List[Dict]:
        variants = []
        for edge in product.get("variants", {}).get("edges", []):
            node = edge.get("node", {})
            variants.append({
                "id": node.get("id"),
                "title": node.get("title"),
                "price": node.get("price", {}).get("amount"),
                "currency": node.get("price", {}).get("currencyCode"),
                "available": node.get("availableForSale"),
            })
        return variants

    def _extract_images(self, product: Dict) -> List[str]:
        images = []
        for edge in product.get("images", {}).get("edges", []):
            url = edge.get("node", {}).get("url")
            if url:
                images.append(url)
        return images

    def _extract_metafields(self, product: Dict) -> Dict[str, str]:
        metafields = {}
        for mf in product.get("metafields", []) or []:
            if mf and mf.get("value"):
                key = mf.get("key", "")
                metafields[key] = mf.get("value", "")
        return metafields

    def _clean_html(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        text = text.strip()
        return text