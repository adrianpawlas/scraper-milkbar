import re
import unicodedata
from typing import List, Optional


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).lower().strip()
    text = re.sub(r"[-\s]+", "-", text)
    return text


def generate_product_id(handle: str) -> str:
    clean = slugify(handle)
    return f"milkbar-{clean}"


def parse_price(price_str: str) -> Optional[str]:
    if not price_str:
        return None
    price_str = price_str.strip()
    match = re.search(r"[\d,]+\.?\d*", price_str)
    if match:
        num = match.group().replace(",", "")
        return num
    return None


def format_price_with_currency(amount: float, currency: str = "USD") -> str:
    return f"{amount:.2f}{currency}"


def parse_multi_price(price_text: str) -> str:
    prices = re.findall(r"[\d,]+\.?\d*", price_text)
    currencies = re.findall(r"([A-Z]{3})", price_text)

    if not prices:
        return price_text.strip()

    result_parts = []
    for i, price in enumerate(prices):
        num = price.replace(",", "")
        curr = currencies[i] if i < len(currencies) else "USD"
        result_parts.append(f"{num}{curr}")

    return ",".join(result_parts)


def parse_category(category_text: str) -> str:
    if not category_text:
        return ""

    categories = []
    for cat in category_text.split(","):
        cat = cat.strip()
        cat = re.sub(r"\s*&\s*", ", ", cat)
        cat = re.sub(r"\band\b", "", cat).strip()
        if cat:
            categories.extend([c.strip() for c in re.split(r",\s*", cat) if c.strip()])

    return ", ".join(categories) if categories else category_text.strip()


def parse_gender(gender_text: Optional[str]) -> Optional[str]:
    if not gender_text:
        return None
    text = gender_text.lower().strip()
    if text in ("all", "unisex", "everyone", "all gender", "all genders"):
        return "unisex"
    if text in ("men", "man", "male", "guys"):
        return "men"
    if text in ("women", "woman", "female", "ladies"):
        return "women"
    if text in ("kids", "child", "children", "youth", "junior"):
        return "kids"
    return None


def format_additional_images(images: List[str]) -> str:
    cleaned = [img.strip() for img in images if img.strip()]
    if not cleaned:
        return ""
    return " , ".join(cleaned)


def truncate_text(text: Optional[str], max_chars: int = 2000) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def clean_product_data(data: dict) -> dict:
    cleaned = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        cleaned[key] = value
    return cleaned