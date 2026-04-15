from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from enum import StrEnum
from io import BytesIO
from textwrap import wrap
from typing import Final, Literal, TypedDict

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

NEWS_API_KEY = os.getenv("NEWS_API_KEY")


BASE_URL: Final[Literal["https://newsapi.org"]] = "https://newsapi.org"


def _require_api_key() -> str:
    if NEWS_API_KEY:
        return NEWS_API_KEY

    error_message = "'NEWS_API_KEY' environment variable is not set. Please set it to your News API key."
    logger.error("Missing environment variable: NEWS_API_KEY")
    raise RuntimeError(error_message)


def _build_headers() -> dict[str, str]:
    return {
        "X-Api-Key": _require_api_key(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


class Endpoint(StrEnum):
    TOP_HEADLINES = "/v2/top-headlines"
    EVERYTHING = "/v2/everything"
    SOURCES = "/v2/sources"


class Country(StrEnum):
    INDIA = "in"
    USA = "us"


class Category(StrEnum):
    BUSINESS = "business"
    ENTERTAINMENT = "entertainment"
    GENERAL = "general"
    HEALTH = "health"
    SCIENCE = "science"
    SPORTS = "sports"
    TECHNOLOGY = "technology"


class ResponseStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class Source(TypedDict):
    id: str | None
    name: str


class Article(TypedDict):
    source: Source
    author: str
    title: str
    description: str
    url: str
    urlToImage: str
    publishedAt: str
    content: str | None


class NewsAPIResponse(TypedDict):
    status: ResponseStatus
    totalResults: int
    articles: list[Article]


def fetch_top_headlines(*, country: Country | None = None, category: Category | None = None) -> NewsAPIResponse:
    logger.info("Fetching top headlines (country=%s, category=%s)", country, category)

    params = {}
    if country is not None:
        params["country"] = country.value
    if category is not None:
        params["category"] = category.value

    query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{Endpoint.TOP_HEADLINES}?{query}"
    logger.debug("Request URL: %s", url)

    request = urllib.request.Request(
        url,
        headers=_build_headers(),
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8")
            logger.debug("Response status code: %d", status_code)

            if status_code != 200:
                logger.error("Unexpected status code %d: %s", status_code, body)
                raise RuntimeError(f"Failed to fetch news: {status_code} - {body}")

            data: NewsAPIResponse = json.loads(body)
            logger.info(
                "Fetched %d article(s) successfully (API status: %s)",
                data.get("totalResults", 0),
                data.get("status"),
            )
            return data

    except urllib.error.HTTPError as e:
        logger.error("HTTP error while fetching headlines: %s - %s", e.code, e.read().decode())
        raise RuntimeError(f"HTTP error: {e.code} - {e.read().decode()}") from e
    except urllib.error.URLError as e:
        logger.error("Network error while fetching headlines: %r", e.reason)
        raise RuntimeError(f"Network error: {e.reason!r}") from e
    except json.JSONDecodeError as e:
        logger.error("Failed to parse API response: %r", e.msg)
        raise RuntimeError(f"Failed to parse response: {e.msg!r}") from e


def _download_image(url: str) -> Image.Image | None:
    if not url:
        logger.debug("No image URL provided, skipping download")
        return None
    logger.debug("Downloading image from: %s", url)

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            image = Image.open(BytesIO(r.read())).convert("RGB")
            logger.debug("Image downloaded successfully (%dx%d)", *image.size)
            return image
    except Exception:
        logger.warning("Failed to download image from %s", url, exc_info=True)
        return None


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", size)
        logger.debug("Loaded TrueType font at size %d", size)
        return font
    except Exception:
        logger.warning("DejaVuSans.ttf not found, falling back to default font (size=%d)", size)
        return ImageFont.load_default()


def create_news_card(article: Article, output: str = "generated/news_card.png") -> str:
    title = article.get("title", "No Title")
    source = article["source"]["name"]
    logger.info("Creating news card for article: %r (source: %s)", title, source)

    WIDTH, HEIGHT = 800, 450
    PADDING = 20
    IMAGE_HEIGHT = 240

    card = Image.new("RGB", (WIDTH, HEIGHT), (18, 18, 18))
    draw = ImageDraw.Draw(card)

    # top image
    img = _download_image(article.get("urlToImage", ""))
    if img is not None:
        img = img.resize((WIDTH, IMAGE_HEIGHT))
        card.paste(img, (0, 0))
        logger.debug("Article image pasted onto card")
    else:
        draw.rectangle((0, 0, WIDTH, IMAGE_HEIGHT), fill=(40, 40, 40))
        logger.debug("Using placeholder rectangle (no article image)")

    # fonts
    title_font = _load_font(28)
    body_font = _load_font(18)
    source_font = _load_font(16)
    title_font_size = getattr(title_font, "size", 28)
    body_font_size = getattr(body_font, "size", 18)
    source_font_size = getattr(source_font, "size", 16)

    y = IMAGE_HEIGHT + PADDING

    # title
    for line in wrap(title, width=42)[:2]:
        draw.text((PADDING, y), line, font=title_font, fill=(255, 255, 255))
        y += title_font_size + 4

    y += 6

    # description
    desc = article.get("description") or ""
    for line in wrap(desc, width=60)[:3]:
        draw.text((PADDING, y), line, font=body_font, fill=(200, 200, 200))
        y += body_font_size + 2

    # source footer
    draw.text(
        (PADDING, HEIGHT - PADDING - source_font_size),
        source,
        font=source_font,
        fill=(150, 150, 150),
    )

    card.save(output)
    logger.info("News card saved to: %s", output)
    return output


if __name__ == "__main__":
    try:
        news = fetch_top_headlines(category=Category.TECHNOLOGY)
        articles = news["articles"]

        for i, article in enumerate(articles[:3]):
            output_path = f"generated/news_card_{i+1}.png"
            create_news_card(article, output=output_path)

    except RuntimeError as e:
        logger.exception("Fatal error in main: %s", e)
