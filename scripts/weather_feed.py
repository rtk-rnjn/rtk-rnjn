from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from io import BytesIO
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

OPEN_WEATHER_MAP_KEY = os.getenv("OPEN_WEATHER_MAP_KEY")


BASE_URL: Final[Literal["https://api.openweathermap.org"]] = "https://api.openweathermap.org"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}
ICON_BASE_URL: Final[str] = "https://openweathermap.org/img/wn"


def _require_api_key() -> str:
    if OPEN_WEATHER_MAP_KEY:
        return OPEN_WEATHER_MAP_KEY

    error_message = "'OPEN_WEATHER_MAP_KEY' environment variable is not set. Please set it to your OpenWeatherMap API key."
    logger.error("Missing environment variable: OPEN_WEATHER_MAP_KEY")
    raise RuntimeError(error_message)


BG_DEEP = (16, 46, 77)
BG_TOP = (24, 62, 105)
BG_CIRCLE = (30, 78, 130)
BG_TILE = (18, 48, 78)
ACCENT = (122, 184, 219)
TEXT_PRIMARY = (255, 255, 255)
TEXT_SECONDARY = (147, 197, 232)
TEXT_PILL = (208, 234, 248)


class Endpoint(StrEnum):
    CURRENT_WEATHER = "/data/2.5/weather"
    FORECAST = "/data/2.5/forecast"


class Units(StrEnum):
    STANDARD = "standard"
    METRIC = "metric"
    IMPERIAL = "imperial"


class WeatherCondition(TypedDict):
    id: int
    main: str
    description: str
    icon: str


class MainMetrics(TypedDict):
    temp: float
    feels_like: float
    temp_min: float
    temp_max: float
    pressure: int
    humidity: int


class Wind(TypedDict):
    speed: float
    deg: int
    gust: float | None


class Sys(TypedDict):
    country: str
    sunrise: int
    sunset: int


class WeatherAPIResponse(TypedDict):
    coord: dict[str, float]
    weather: list[WeatherCondition]
    main: MainMetrics
    visibility: int
    wind: Wind
    clouds: dict[str, int]
    dt: int
    sys: Sys
    timezone: int
    id: int
    name: str
    cod: int


class ForecastAPIResponse(TypedDict):
    list: list[dict]
    city: dict


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()


def fetch_current_weather(*, city: str, units: Units = Units.METRIC) -> WeatherAPIResponse:
    logger.info("Fetching current weather (city=%s, units=%s)", city, units)
    params = {"q": city, "units": units.value, "appid": _require_api_key()}
    url = f"{BASE_URL}{Endpoint.CURRENT_WEATHER}?{urllib.parse.urlencode(params)}"
    logger.debug("Request URL: %s", url)

    try:
        body = _get(url)
        data: WeatherAPIResponse = json.loads(body)
        logger.info(
            "Fetched weather for %s, %s (condition: %s)",
            data.get("name"),
            data.get("sys", {}).get("country"),
            data.get("weather", [{}])[0].get("description"),
        )
        return data
    except urllib.error.HTTPError as e:
        logger.error("HTTP error %s: %s", e.code, e.read().decode())
        raise RuntimeError(f"HTTP error: {e.code}") from e
    except urllib.error.URLError as e:
        logger.error("Network error: %r", e.reason)
        raise RuntimeError(f"Network error: {e.reason!r}") from e
    except json.JSONDecodeError as e:
        logger.error("Failed to parse API response: %r", e.msg)
        raise RuntimeError(f"Failed to parse response: {e.msg!r}") from e


def fetch_forecast(*, city: str, units: Units = Units.METRIC) -> ForecastAPIResponse:
    logger.info("Fetching forecast (city=%s, units=%s)", city, units)
    params = {"q": city, "units": units.value, "cnt": 6, "appid": _require_api_key()}
    url = f"{BASE_URL}{Endpoint.FORECAST}?{urllib.parse.urlencode(params)}"
    logger.debug("Request URL: %s", url)

    try:
        body = _get(url)
        data: ForecastAPIResponse = json.loads(body)
        logger.info("Fetched %d forecast slot(s)", len(data.get("list", [])))
        return data
    except Exception as e:
        logger.warning("Could not fetch forecast, skipping: %s", e)
        return {"list": [], "city": {}}


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [name, "DejaVuSans-Bold.ttf" if "Bold" in name else "DejaVuSans.ttf"]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            pass
    logger.warning("No TrueType font found for size=%d, using default", size)
    return ImageFont.load_default()


def _download_icon(icon_code: str, size: int = 72) -> Image.Image | None:
    if not icon_code:
        return None
    url = f"{ICON_BASE_URL}/{icon_code}@2x.png"
    logger.debug("Downloading weather icon: %s", url)
    try:
        img = Image.open(BytesIO(_get(url))).convert("RGBA")
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        logger.debug("Icon downloaded (%dx%d)", size, size)
        return img
    except Exception:
        logger.warning("Failed to download icon %s", icon_code, exc_info=True)
        return None


def _wind_direction(deg: int | None) -> str:
    if deg is None:
        return ""
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[round(deg / 45) % 8]


def _format_unix_time(ts: int, tz_offset: int, fmt: str) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone(timedelta(seconds=tz_offset)))
    return dt.strftime(fmt)


def _rounded_rect(draw: ImageDraw.ImageDraw, xy: tuple, radius: int, fill: tuple) -> None:
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)


def _centered_text(draw: ImageDraw.ImageDraw, cx: int, y: int, text: str, font, fill: tuple) -> None:
    w = draw.textlength(text, font=font)
    draw.text((cx - w // 2, y), text, font=font, fill=fill)


def create_weather_card(
    data: WeatherAPIResponse,
    forecast: ForecastAPIResponse | None = None,
    units: Units = Units.METRIC,
    output: str = "generated/weather_card.png",
) -> str:
    W, H = 640, 400
    RADIUS = 24
    PAD = 28

    city = data.get("name", "Unknown")
    country = data.get("sys", {}).get("country", "")
    location = f"{city}, {country}" if country else city
    condition = (data.get("weather") or [{}])[0]
    main = data.get("main", {})
    wind = data.get("wind", {})
    tz_offset = data.get("timezone", 0)
    dt = data.get("dt", 0)
    symbol = {"metric": "°C", "imperial": "°F", "standard": "K"}[units.value]

    logger.info(
        "Creating weather card for %s (condition: %s)",
        location,
        condition.get("description"),
    )

    temp = main.get("temp")
    feels = main.get("feels_like")
    temp_min = main.get("temp_min")
    temp_max = main.get("temp_max")
    humidity = main.get("humidity")
    pressure = main.get("pressure")
    vis = data.get("visibility")
    wspeed = wind.get("speed")
    wdeg = wind.get("deg")
    sunrise = data.get("sys", {}).get("sunrise")
    sunset = data.get("sys", {}).get("sunset")

    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=RADIUS, fill=255)

    bg = Image.new("RGB", (W, H), BG_DEEP)
    draw = ImageDraw.Draw(bg)

    draw.rounded_rectangle([0, 0, W, 160], radius=RADIUS, fill=BG_TOP)
    draw.rectangle([0, RADIUS, W, 160], fill=BG_TOP)

    cx, cy = W - 110, 78
    for r_off, alpha in [(80, 30), (62, 55), (46, 85)]:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ov).ellipse(
            [cx - r_off, cy - r_off, cx + r_off, cy + r_off],
            fill=(*BG_CIRCLE, alpha),
        )
        bg.paste(ov, mask=ov)

    draw = ImageDraw.Draw(bg)

    f_city = _load_font("DejaVuSans-Bold.ttf", 22)
    f_date = _load_font("DejaVuSans.ttf", 12)
    f_pill = _load_font("DejaVuSans.ttf", 11)
    f_temp = _load_font("DejaVuSans-Bold.ttf", 58)
    f_feels = _load_font("DejaVuSans.ttf", 12)
    f_hilo = _load_font("DejaVuSans.ttf", 12)
    f_tile_val = _load_font("DejaVuSans-Bold.ttf", 22)
    f_tile_lbl = _load_font("DejaVuSans.ttf", 11)
    f_section = _load_font("DejaVuSans.ttf", 11)
    f_fc_temp = _load_font("DejaVuSans-Bold.ttf", 13)
    f_fc_time = _load_font("DejaVuSans.ttf", 10)

    draw.text((PAD, 24), location, font=f_city, fill=TEXT_PRIMARY)

    if dt:
        date_str = _format_unix_time(dt, tz_offset, "%A, %d %B %Y")
        draw.text((PAD, 52), date_str, font=f_date, fill=TEXT_SECONDARY)

    desc = condition.get("description", "").capitalize()
    pill_w = int(draw.textlength(desc, font=f_pill)) + 22
    _rounded_rect(draw, (PAD, 68, PAD + pill_w, 88), radius=10, fill=BG_CIRCLE)
    draw.text((PAD + 11, 71), desc, font=f_pill, fill=TEXT_PILL)

    icon = _download_icon(condition.get("icon", ""), size=72)
    if icon:
        ix, iy = cx - 36, cy - 36
        bg.paste(icon, (ix, iy), mask=icon)
        logger.debug("Icon pasted at (%d, %d)", ix, iy)

    temp_str = f"{temp:.0f}°" if temp is not None else "--°"
    _centered_text(draw, cx, 96, temp_str, f_temp, TEXT_PRIMARY)

    if feels is not None:
        _centered_text(draw, cx, 156, f"Feels like {feels:.0f}{symbol}", f_feels, TEXT_SECONDARY)

    if temp_min is not None and temp_max is not None:
        _centered_text(
            draw,
            cx,
            172,
            f"↑ {temp_max:.0f}°   ↓ {temp_min:.0f}°",
            f_hilo,
            TEXT_SECONDARY,
        )

    draw.line([(PAD, 192), (W - PAD, 192)], fill=(*ACCENT, 55), width=1)

    tiles = [
        ("Humidity", f"{humidity}%" if humidity is not None else "--", None),
        (
            "Wind",
            f"{wspeed:.1f}" if wspeed is not None else "--",
            f"m/s {_wind_direction(wdeg)}",
        ),
        ("Pressure", f"{pressure}" if pressure is not None else "--", "hPa"),
        ("Visibility", f"{vis / 1000:.1f}" if vis is not None else "--", "km"),
    ]
    tile_w = (W - 2 * PAD - 3 * 10) // 4
    tile_h = 76
    tile_y = 202

    for i, (label, value, unit) in enumerate(tiles):
        tx = PAD + i * (tile_w + 10)
        _rounded_rect(draw, (tx, tile_y, tx + tile_w, tile_y + tile_h), radius=12, fill=BG_TILE)
        tcx = tx + tile_w // 2
        _centered_text(draw, tcx, tile_y + 10, label, f_tile_lbl, ACCENT)
        _centered_text(draw, tcx, tile_y + 29, value, f_tile_val, TEXT_PRIMARY)
        if unit:
            _centered_text(draw, tcx, tile_y + 57, unit, f_tile_lbl, TEXT_SECONDARY)

    draw.line([(PAD, 290), (W - PAD, 290)], fill=(*ACCENT, 55), width=1)

    draw.text((PAD, 298), "Hourly forecast", font=f_section, fill=ACCENT)

    slots = (forecast or {}).get("list", [])[:6]
    circle_r = 18
    circle_y = 345

    if slots:
        slot_w = (W - 2 * PAD) // len(slots)
        for j, slot in enumerate(slots):
            sx = PAD + j * slot_w + slot_w // 2
            s_dt = slot.get("dt", 0)
            s_temp = slot.get("main", {}).get("temp")
            time_lbl = _format_unix_time(s_dt, tz_offset, "%I%p").lstrip("0") if s_dt else ""
            temp_lbl = f"{s_temp:.0f}°" if s_temp is not None else "--°"

            _centered_text(draw, sx, circle_y - circle_r - 16, time_lbl, f_fc_time, TEXT_SECONDARY)
            draw.ellipse(
                [
                    sx - circle_r,
                    circle_y - circle_r,
                    sx + circle_r,
                    circle_y + circle_r,
                ],
                fill=BG_TILE,
            )
            _centered_text(draw, sx, circle_y - 9, temp_lbl, f_fc_temp, TEXT_PRIMARY)

    if sunrise and sunset:
        sun_str = (
            f"Sunrise {_format_unix_time(sunrise, tz_offset, '%H:%M')}" f"   ·   " f"Sunset {_format_unix_time(sunset, tz_offset, '%H:%M')}"
        )
        sw = draw.textlength(sun_str, font=f_section)
        draw.text((W - PAD - sw, H - 18), sun_str, font=f_section, fill=TEXT_SECONDARY)

    card.paste(bg, mask=mask)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    card.save(output)
    logger.info("Weather card saved to: %s", output)
    return output


if __name__ == "__main__":
    cities = ["London", "New York", "Tokyo"]

    try:
        for i, city in enumerate(cities):
            data = fetch_current_weather(city=city, units=Units.METRIC)
            forecast = fetch_forecast(city=city, units=Units.METRIC)
            output = f"generated/weather_card_{i + 1}.png"
            create_weather_card(data, forecast=forecast, units=Units.METRIC, output=output)

    except RuntimeError as e:
        logger.exception("Fatal error in main: %s", e)
