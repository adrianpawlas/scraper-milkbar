#!/bin/bash

set -e

echo "=============================================="
echo "  Milkbar Scraper - Setup & Run Script"
echo "=============================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

check_python() {
    if ! command -v python3 &> /dev/null; then
        echo "ERROR: Python 3 is required but not installed."
        echo "Install from: https://www.python.org/downloads/"
        exit 1
    fi
    PYTHON_VERSION=$(python3 -c 'import sys; print(sys.version_info.major + sys.version_info.minor / 10)')
    echo "✓ Python $PYTHON_VERSION found"
}

create_venv() {
    if [ ! -d "venv" ]; then
        echo ""
        echo "Creating virtual environment..."
        python3 -m venv venv
        echo "✓ Virtual environment created"
    else:
        echo "✓ Virtual environment already exists"
    fi
}

activate_venv() {
    source venv/bin/activate
    echo "✓ Virtual environment activated"
}

install_deps() {
    echo ""
    echo "Installing dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "✓ Dependencies installed"
}

setup_env() {
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            echo "✓ Created .env from .env.example"
            echo ""
            echo "⚠ IMPORTANT: Edit .env with your credentials:"
            echo "   - shopify_store_domain"
            echo "   - shopify_storefront_token"
            echo "   - supabase_url"
            echo "   - supabase_anon_key"
        else:
            echo "ERROR: .env.example not found"
            exit 1
        fi
    else:
        echo "✓ .env file already exists"
    fi
}

test_run() {
    echo ""
    echo "Running connection tests..."
    echo ""

    echo "--- Shopify Test ---"
    if python3 run.py --mode test-shopify 2>&1 | grep -q "OK"; then
        echo "✓ Shopify: OK"
    else
        echo "✗ Shopify: FAILED"
    fi

    echo ""
    echo "--- Supabase Test ---"
    if python3 run.py --mode test-supabase 2>&1 | grep -q "OK"; then
        echo "✓ Supabase: OK"
    else
        echo "✗ Supabase: FAILED"
    fi
}

MODE="${1:-test}"

echo ""
echo "=============================================="
echo "  Setup Phase"
echo "=============================================="
echo ""
check_python
create_venv
activate_venv
install_deps
setup_env

if [ "$MODE" == "test" ]; then
    test_run
fi

echo ""
echo "=============================================="
echo "  Ready!"
echo "=============================================="
echo ""
echo "Run modes:"
echo "  ./quick.sh full        - Full pipeline"
echo "  ./quick.sh scrape     - Scrape only"
echo "  ./quick.sh single HND - Single product"
echo "  ./quick.sh resume     - Resume failed"
echo "  ./quick.sh test       - Test connections"
echo ""
echo "Or directly:"
echo "  source venv/bin/activate"
echo "  python run.py --mode full"