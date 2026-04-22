# Milkbar Scraper

Full scraper for Milkbar fashion store. Scrapes all products from Shopify, generates SigLIP image and text embeddings (768-dim), and imports everything to Supabase.

## Setup

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env file from example
cp .env.example .env

# 4. Install Playwright (if used for browser scraping)
playwright install chromium

# 5. Test connections
python run.py --mode test
```

## Usage

```bash
# Full pipeline: scrape -> embed -> import to Supabase
python run.py --mode full

# Test individual connections
python run.py --mode test-shopify
python run.py --mode test-supabase

# Scrape only
python run.py --mode scrape

# Generate embeddings only
python run.py --mode embeddings

# Import to database only
python run.py --mode db

# Single product
python run.py --mode single --handle summer-nights-bomber-jacket-army-green

# Resume failed products
python run.py --mode resume

# Export products to JSON
python run.py --mode export

# Resume mode (alias)
python run.py --resume
```

## Output Fields

| Field | Source | Notes |
|-------|--------|-------|
| `id` | Auto | `milkbar-{slug}` |
| `source` | `"scraper-milkbar"` | |
| `brand` | `"Milkbar"` | |
| `product_url` | Shopify | Full URL |
| `image_url` | Shopify | Featured image |
| `additional_images` | Shopify | Comma-separated |
| `title` | Shopify | |
| `description` | Shopify | |
| `category` | Shopify metafields | Comma-separated |
| `gender` | Shopify metafields | `unisex`, `men`, `women` |
| `price` | Shopify | Multi-currency format |
| `sale` | Shopify | Same as price if on sale |
| `metadata` | Shopify | Combined info |
| `size` | Shopify metafields | |
| `second_hand` | `false` | |
| `image_embedding` | SigLIP | 768-dim vector |
| `info_embedding` | SigLIP | 768-dim vector |
| `created_at` | Shopify | ISO timestamp |
| `tags` | Shopify | Array field |

## Architecture

- `shopify_client.py` - GraphQL API client for Shopify Storefront API
- `scraper.py` - Product scraping and normalization
- `embedding.py` - SigLIP embedding generation
- `supabase_client.py` - Supabase REST API client
- `scraper_orchestrator.py` - Main pipeline orchestrator
- `config.py` - Configuration and settings
- `state.py` - Scraper state persistence
- `logger.py` - Structured logging

## Embedding Model

- **Model**: `google/siglip-base-patch16-384`
- **Dimension**: 768
- **Image input**: 384x384 RGB
- **Device**: CUDA (auto) or CPU fallback

## Notes

- Products are scraped via Shopify GraphQL API (no browser needed)
- Embeddings are generated per-product sequentially
- Incremental scrape supported (only new products)
- State is persisted between runs
- Failed products are retried on resume