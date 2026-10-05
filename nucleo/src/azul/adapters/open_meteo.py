"""Clima con Open-Meteo (ADR 0024): gratuito para uso personal, sin cuenta ni clave.

Responde en ~1 s, frente a los 10-15 s de una búsqueda web.
"""

import logging
from typing import Any

import httpx2

from azul.core.ports import WeatherError

log = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MAX_DAYS = 7

# Códigos de tiempo de la OMM que usa Open-Meteo.
_DESCRIPTIONS = {
    0: "despejado",
    1: "mayormente despejado",
    2: "parcialmente nublado",
    3: "nublado",
    45: "niebla",
    48: "niebla con escarcha",
    51: "llovizna ligera",
    53: "llovizna",
    55: "llovizna intensa",
    56: "llovizna helada",
    57: "llovizna helada intensa",
    61: "lluvia ligera",
    63: "lluvia",
    65: "lluvia fuerte",
    66: "lluvia helada",
    67: "lluvia helada fuerte",
    71: "nieve ligera",
    73: "nieve",
    75: "nieve fuerte",
    77: "granizo fino",
    80: "chubascos ligeros",
    81: "chubascos",
    82: "chubascos fuertes",
    85: "chubascos de nieve",
    86: "chubascos de nieve fuertes",
    95: "tormenta",
    96: "tormenta con granizo",
    99: "tormenta con granizo fuerte",
}


class OpenMeteoWeather:
    def __init__(self, client: httpx2.AsyncClient | None = None) -> None:
        self._client = client or httpx2.AsyncClient(timeout=10)

    async def forecast(self, place: str, days: int) -> dict[str, Any]:
        days = max(1, min(days, MAX_DAYS))
        try:
            location = await self._locate(place)
            response = await self._client.get(
                FORECAST_URL,
                params={
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                    "precipitation,weather_code,wind_speed_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max",
                    "timezone": "auto",
                    "forecast_days": days,
                },
            )
            response.raise_for_status()
            data = response.json()
        except httpx2.HTTPError as error:
            log.error("Error consultando Open-Meteo: %s", error)
            raise WeatherError("No pude consultar el clima en este momento.") from error

        current, daily = data["current"], data["daily"]
        return {
            "lugar": ", ".join(
                part
                for part in (location.get("name"), location.get("admin1"), location.get("country"))
                if part
            ),
            "ahora": {
                "hora_local": current["time"],
                "descripcion": _describe(current["weather_code"]),
                "temperatura_c": current["temperature_2m"],
                "sensacion_c": current["apparent_temperature"],
                "humedad_pct": current["relative_humidity_2m"],
                "lluvia_mm": current["precipitation"],
                "viento_kmh": current["wind_speed_10m"],
            },
            "pronostico": [
                {
                    "fecha": daily["time"][i],
                    "descripcion": _describe(daily["weather_code"][i]),
                    "maxima_c": daily["temperature_2m_max"][i],
                    "minima_c": daily["temperature_2m_min"][i],
                    "probabilidad_lluvia_pct": daily["precipitation_probability_max"][i],
                }
                for i in range(len(daily["time"]))
            ],
        }

    async def _locate(self, place: str) -> dict[str, Any]:
        # "Villavicencio, Colombia": se busca la ciudad y se prefiere la que coincida con el resto.
        name, *hints = [part.strip() for part in place.split(",") if part.strip()]
        response = await self._client.get(
            GEOCODING_URL, params={"name": name, "count": 10, "language": "es", "format": "json"}
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        if not results:
            raise WeatherError(f"No encontré el lugar «{place}».")
        lowered = [hint.lower() for hint in hints]
        for result in results:
            region = f"{result.get('admin1', '')} {result.get('country', '')}".lower()
            if all(hint in region for hint in lowered):
                return result
        return results[0]


def _describe(code: int | None) -> str:
    return _DESCRIPTIONS.get(code, "sin dato") if code is not None else "sin dato"
