from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

from scripts.moon_phase import calculate_phase, phase_emoji
from scripts.news_feed import Category
from scripts.news_feed import create_news_card as create_news_image
from scripts.news_feed import fetch_top_headlines
from scripts.weather_feed import (
    Units,
    create_weather_card,
    fetch_current_weather,
    fetch_forecast,
)
from scripts.year_progress import calculate_year_progress, progress_bar

load_dotenv()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _build_context() -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    generated_dir = Path("generated")
    generated_dir.mkdir(parents=True, exist_ok=True)

    news_cards: list[str] = []
    news_items: list[dict[str, str]] = []
    news_error: str | None = None

    try:
        news_data = fetch_top_headlines(category=Category.TECHNOLOGY)
        articles = news_data.get("articles", [])[:3]

        for idx, article in enumerate(articles, start=1):
            output = generated_dir / f"news_card_{idx}.png"
            create_news_image(article, output=str(output))
            news_cards.append(str(output.as_posix()))
            news_items.append(
                {
                    "title": article.get("title") or "Untitled",
                    "url": article.get("url") or "",
                    "source": article.get("source", {}).get("name") or "Unknown",
                }
            )
    except Exception as exc:
        logger.warning("Unable to build news cards: %s", exc)
        news_error = str(exc)

    weather_card: str | None = None
    weather_city = os.getenv("WEATHER_CITY", "Bengaluru")
    weather_error: str | None = None
    weather_details: dict[str, str] | None = None

    try:
        weather_data = fetch_current_weather(city=weather_city, units=Units.METRIC)
        forecast_data = fetch_forecast(city=weather_city, units=Units.METRIC)
        weather_path = generated_dir / "weather_card.png"
        create_weather_card(
            weather_data,
            forecast=forecast_data,
            units=Units.METRIC,
            output=str(weather_path),
        )
        weather_card = str(weather_path.as_posix())

        condition = (weather_data.get("weather") or [{}])[0].get("description", "N/A")
        temperature = weather_data.get("main", {}).get("temp")
        weather_details = {
            "city": weather_data.get("name", weather_city),
            "condition": condition.capitalize(),
            "temperature": f"{temperature:.1f} C" if isinstance(temperature, (int, float)) else "N/A",
        }
    except Exception as exc:
        logger.warning("Unable to build weather card: %s", exc)
        weather_error = str(exc)

    moon_pct = calculate_phase(now_utc) * 100
    year_stats = calculate_year_progress(now_utc)

    github_username = os.getenv("GITHUB_USERNAME", "rtk-rnjn")

    return {
        "name": os.getenv("PROFILE_NAME", "Ritik"),
        "github_username": github_username,
        "github_profile_url": f"https://github.com/{github_username}",
        "generated_at": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "moon_emoji": phase_emoji(now_utc),
        "moon_percent": f"{moon_pct:.2f}",
        "year": year_stats.year,
        "year_percent": f"{year_stats.percent_complete:.2f}",
        "year_progress_bar": progress_bar(year_stats.percent_complete, length=24),
        "news_cards": news_cards,
        "news_items": news_items,
        "news_error": news_error,
        "weather_card": weather_card,
        "weather_details": weather_details,
        "weather_error": weather_error,
    }


def build_readme() -> None:
    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("readme.jinja")

    context = _build_context()
    rendered = template.render(**context)

    Path("README.md").write_text(rendered.rstrip() + "\n", encoding="utf-8")
    logger.info("README.md generated successfully")


if __name__ == "__main__":
    build_readme()
