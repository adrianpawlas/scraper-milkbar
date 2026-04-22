import sys
import json
import argparse
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from loguru import logger

from config import scraper as scraper_config, embedding as embedding_config
from shopify_client import ShopifyClient
from scraper import ProductScraper
from embedding import get_embedding_model, encode_product, encode_product_image, encode_product_info
from supabase_client import get_supabase_client
from state import state
from utils import truncate_text
from logger import (
    setup_logger,
    log_step,
    log_batch_progress,
    log_error,
    log_product,
)
from config import BASE_DIR


class ScraperOrchestrator:
    def __init__(self):
        self.shopify = ShopifyClient()
        self.supabase = get_supabase_client()
        self.scraper = ProductScraper(self.shopify)
        self._products: List[Dict[str, Any]] = []
        self._failed: List[str] = []

    def test_connections(self) -> bool:
        log_step("SETUP", "Testing connections...")
        shopify_ok = self.shopify.test_connection()
        supabase_ok = self.supabase.test_connection()

        if shopify_ok and supabase_ok:
            logger.success("All connections OK")
            return True
        else:
            if not shopify_ok:
                logger.error("Shopify connection FAILED")
            if not supabase_ok:
                logger.error("Supabase connection FAILED")
            return False

    def run_full_scrape(self) -> Tuple[int, int]:
        log_step("ORCHESTRATOR", "Starting FULL scrape pipeline...")

        products = self._run_scrape_phase()
        if not products:
            logger.error("No products scraped, stopping")
            return 0, 0

        self._run_embedding_phase(products)

        inserted, skipped = self._run_db_phase(products)

        return inserted, skipped

    def _run_scrape_phase(self) -> List[Dict[str, Any]]:
        log_step("PHASE-1", "Scraping products from Shopify...")

        try:
            products = self.scraper.scrape_all_products()
        except Exception as e:
            log_error("scrape", e)
            logger.error("Scrape phase failed, trying incremental...")
            products = self._incremental_scrape()

        state.last_scrape_time = datetime.now().isoformat()
        state.products_scrape_count += len(products)
        state.save()

        logger.success(f"Scraped {len(products)} products")
        self._products = products
        return products

    def _incremental_scrape(self) -> List[Dict[str, Any]]:
        log_step("SCRAPE", "Incremental scrape (only new products)...")
        existing = self.supabase.get_existing_products()
        all_handles = self.scraper.get_all_handles()
        new_handles = [h for h in all_handles
                   if f"https://milkbarmelbourne.com/store-flat/{h}" not in existing]

        logger.info(f"Found {len(new_handles)} new products")
        products = []

        for i, handle in enumerate(new_handles, 1):
            try:
                p = self.scraper.scrape_product(handle)
                if p:
                    products.append(p)
                if i % 20 == 0:
                    logger.info(f"Progress: {i}/{len(new_handles)}")
            except Exception as e:
                log_error(handle, e)
                continue

        return products

    def _run_embedding_phase(self, products: List[Dict[str, Any]]):
        log_step("PHASE-2", "Generating embeddings...")

        try:
            model = get_embedding_model()
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            logger.warning("Continuing without embeddings...")
            return

        for i, product in enumerate(products, 1):
            try:
                image_url = product.get("image_url")
                info_text = product.get("title", "") + " " + product.get("description", "") + " " + product.get("category", "")

                embeddings = encode_product(image_url, info_text)
                product["image_embedding"] = embeddings.get("image_embedding")
                product["info_embedding"] = embeddings.get("info_embedding")

                if i % 5 == 0:
                    logger.info(f"Embedding progress: {i}/{len(products)}")

            except Exception as e:
                log_error(product.get("product_url", "unknown"), e)
                continue

        state.embeddings_count += len(products)
        state.save()
        logger.success(f"Generated embeddings for {len(products)} products")

    def _run_db_phase(self, products: List[Dict[str, Any]]) -> Tuple[int, int]:
        log_step("PHASE-3", "Importing to Supabase...")

        existing_urls = set(self.supabase.get_existing_products())
        to_insert = []
        skipped = 0

        for product in products:
            url = product.get("product_url")
            if url in existing_urls:
                result = self.supabase._update_product(product)
                if not result:
                    to_insert.append(product)
                else:
                    skipped += 1
            else:
                to_insert.append(product)

        if to_insert:
            batch_result = self.supabase.upsert_products_batch(to_insert)
            inserted = batch_result.get("success", 0)
            failed = batch_result.get("failed", 0)
        else:
            inserted, failed = 0, 0

        logger.success(f"DB import: {inserted} inserted, {skipped} skipped, {failed} failed")
        return inserted, skipped

    def scrape_product_urls(self) -> List[str]:
        handles = self.scraper.get_all_handles()
        urls = [f"https://milkbarmelbourne.com/store-flat/{h}" for h in handles]
        return urls

    def scrape_single_product(self, handle: str) -> Optional[Dict[str, Any]]:
        product = self.scraper.scrape_product(handle)
        if not product:
            return None

        image_url = product.get("image_url")
        info_text = product.get("title", "") + " " + product.get("description", "")

        try:
            embeddings = encode_product(image_url, info_text)
            product["image_embedding"] = embeddings.get("image_embedding")
            product["info_embedding"] = embeddings.get("info_embedding")
        except Exception as e:
            log_error(image_url, e)

        return product

    def import_to_supabase(self, product: Dict[str, Any]) -> bool:
        result = self.supabase.upsert_product(product)
        return result is not None

    def run_resume_failed(self) -> Tuple[int, int]:
        log_step("RESUME", "Resuming failed products...")

        failed_urls = state.load_failed_products()
        if not failed_urls:
            logger.info("No failed products in state file")
            failed_urls = state.failed_products

        logger.info(f"Retrying {len(failed_urls)} failed products")
        success = 0
        failed = 0

        for url in failed_urls:
            handle = url.split("/")[-1]
            try:
                product = self.scrape_single_product(handle)
                if product and self.import_to_supabase(product):
                    state.mark_completed(url)
                    success += 1
                else:
                    state.mark_failed(url)
                    failed += 1
            except Exception as e:
                log_error(url, e)
                state.mark_failed(url)
                failed += 1

        logger.success(f"Resume: {success} recovered, {failed} still failed")
        return success, failed

    def export_products(self, filepath: str = None) -> str:
        if not self._products:
            logger.warning("No products in memory, scraping first...")
            self._products = self.scraper.scrape_all_products()

        if filepath is None:
            filepath = str(BASE_DIR / f"milkbar_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

        products_to_save = []
        for p in self._products:
            clean = {k: v for k, v in p.items() if k not in ("image_embedding", "info_embedding")}
            products_to_save.append(clean)

        with open(filepath, "w") as f:
            json.dump(products_to_save, f, indent=2, default=str)

        logger.success(f"Exported {len(products_to_save)} products to {filepath}")
        return filepath


def main():
    import sys
    parser = argparse.ArgumentParser(description="Milkbar Scraper")
    parser.add_argument("--mode", default="full",
                        choices=["full", "scrape", "embeddings", "db", "test", "test-shopify",
                                "test-supabase", "export", "resume", "single"],
                        help="Operation mode")
    parser.add_argument("--handle", help="Product handle for single mode")
    parser.add_argument("--output", help="Output file for export mode")
    parser.add_argument("--resume", action="store_true", help="Resume failed products")

    args = parser.parse_args()
    setup_logger()
    logger.info(f"Milkbar Scraper starting in mode: {args.mode}")

    orch = ScraperOrchestrator()

    try:
        if args.mode == "test":
            ok = orch.test_connections()
            sys.exit(0 if ok else 1)

        elif args.mode == "test-shopify":
            ok = orch.shopify.test_connection()
            sys.exit(0 if ok else 1)

        elif args.mode == "test-supabase":
            ok = orch.supabase.test_connection()
            sys.exit(0 if ok else 1)

        elif args.mode == "full":
            inserted, skipped = orch.run_full_scrape()
            logger.success(f"DONE: {inserted} inserted, {skipped} skipped")

        elif args.mode == "scrape":
            products = orch._run_scrape_phase()
            logger.success(f"Scraped {len(products)} products")

        elif args.mode == "embeddings":
            orch._products = orch.scraper.scrape_all_products()
            orch._run_embedding_phase(orch._products)
            logger.success(f"Generated embeddings for {len(orch._products)} products")

        elif args.mode == "db":
            orch._products = orch.scraper.scrape_all_products()
            inserted, skipped = orch._run_db_phase(orch._products)
            logger.success(f"Imported: {inserted} inserted, {skipped} skipped")

        elif args.mode == "export":
            filepath = orch.export_products(args.output)
            print(filepath)

        elif args.mode == "resume":
            success, failed = orch.run_resume_failed()
            logger.success(f"Resume: {success} recovered, {failed} failed")

        elif args.mode == "single":
            if not args.handle:
                logger.error("--handle required for single mode")
                sys.exit(1)
            product = orch.scrape_single_product(args.handle)
            if product:
                logger.success(f"Product scraped: {product['title']}")
                if orch.import_to_supabase(product):
                    logger.success("Imported to Supabase")
                print(json.dumps(product, indent=2, default=str))
            else:
                logger.error("Product not found")

        else:
            logger.error(f"Unknown mode: {args.mode}")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        state.save()
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        state.save()
        sys.exit(1)


if __name__ == "__main__":
    main()