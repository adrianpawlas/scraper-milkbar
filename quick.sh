#!/bin/bash
set -e

echo "=== Milkbar Scraper - Quick Run ==="
echo ""

MODE="${1:-full}"

case "$MODE" in
  full)
    echo "Running full pipeline: scrape -> embed -> import"
    python run.py --mode full
    ;;
  scrape)
    echo "Running scrape only"
    python run.py --mode scrape
    ;;
  embeddings)
    echo "Running embeddings only"
    python run.py --mode embeddings
    ;;
  db)
    echo "Running DB import only"
    python run.py --mode db
    ;;
  resume)
    echo "Resuming failed products"
    python run.py --mode resume
    ;;
  test)
    echo "Testing connections"
    python run.py --mode test
    ;;
  test-shopify)
    echo "Testing Shopify"
    python run.py --mode test-shopify
    ;;
  test-supabase)
    echo "Testing Supabase"
    python run.py --mode test-supabase
    ;;
  export)
    echo "Exporting products"
    python run.py --mode export
    ;;
  single)
    HANDLE="${2:-}"
    if [ -z "$HANDLE" ]; then
      echo "Usage: ./quick.sh single <handle>"
      exit 1
    fi
    echo "Scraping single product: $HANDLE"
    python run.py --mode single --handle "$HANDLE"
    ;;
  help)
    echo "Usage: ./quick.sh [mode]"
    echo ""
    echo "Modes:"
    echo "  full         - Scrape, embed, and import (default)"
    echo "  scrape      - Scrape products from Shopify only"
    echo "  embeddings  - Generate embeddings only"
    echo "  db          - Import to Supabase only"
    echo "  resume      - Retry failed products"
    echo "  test        - Test all connections"
    echo "  test-shopify - Test Shopify connection"
    echo "  test-supabase - Test Supabase connection"
    echo "  export      - Export products to JSON"
    echo "  single      - Scrape single product (pass handle)"
    echo "  help        - Show this help"
    echo ""
    echo "Examples:"
    echo "  ./quick.sh full"
    echo "  ./quick.sh single summer-nights-bomber-jacket-army-green"
    echo "  ./quick.sh test"
    ;;
  *)
    echo "Unknown mode: $MODE"
    echo "Run './quick.sh help' for usage"
    exit 1
    ;;
esac