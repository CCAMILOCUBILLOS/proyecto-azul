import httpx2
import pytest

from azul.adapters.open_meteo import FORECAST_URL, GEOCODING_URL, OpenMeteoWeather
from azul.core.ports import WeatherError

pytestmark = pytest.mark.anyio

PLACES = {
    "results": [
        {
            "name": "Villavicencio",
            "admin1": "Otra Región",
            "country": "Perú",
            "latitude": 1.0,
            "longitude": 2.0,
        },
        {
            "name": "Villavicencio",
            "admin1": "Meta",
            "country": "Colombia",
            "latitude": 4.15,
            "longitude": -73.63,
        },
    ]
}
FORECAST = {
    "current": {
        "time": "2026-10-05T13:00",
        "temperature_2m": 29.4,
        "apparent_temperature": 32.1,
        "relative_humidity_2m": 70,
        "precipitation": 0.0,
        "weather_code": 2,
        "wind_speed_10m": 8.3,
    },
    "daily": {
        "time": ["2026-10-05", "2026-10-06"],
        "weather_code": [80, 61],
        "temperature_2m_max": [31.0, 30.2],
        "temperature_2m_min": [21.5, 21.0],
        "precipitation_probability_max": [60, 85],
    },
}


def weather_with(handler):
    return OpenMeteoWeather(httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))


async def test_forecast_for_a_place_with_country_hint():
    requests = []

    def handler(request):
        requests.append(request)
        if str(request.url).startswith(GEOCODING_URL):
            return httpx2.Response(200, json=PLACES)
        return httpx2.Response(200, json=FORECAST)

    result = await weather_with(handler).forecast("Villavicencio, Colombia", days=2)

    geocoding, forecast = requests
    assert geocoding.url.params["name"] == "Villavicencio"
    assert str(forecast.url).startswith(FORECAST_URL)
    assert forecast.url.params["latitude"] == "4.15"  # eligió el de Colombia, no el de Perú
    assert forecast.url.params["forecast_days"] == "2"
    assert result["lugar"] == "Villavicencio, Meta, Colombia"
    assert result["ahora"]["descripcion"] == "parcialmente nublado"
    assert result["ahora"]["temperatura_c"] == 29.4
    assert result["pronostico"][1] == {
        "fecha": "2026-10-06",
        "descripcion": "lluvia ligera",
        "maxima_c": 30.2,
        "minima_c": 21.0,
        "probabilidad_lluvia_pct": 85,
    }


async def test_days_are_kept_between_1_and_7():
    seen = []

    def handler(request):
        if str(request.url).startswith(GEOCODING_URL):
            return httpx2.Response(200, json=PLACES)
        seen.append(request.url.params["forecast_days"])
        return httpx2.Response(200, json=FORECAST)

    await weather_with(handler).forecast("Villavicencio", days=30)

    assert seen == ["7"]


async def test_unknown_place_is_reported():
    weather = weather_with(lambda request: httpx2.Response(200, json={}))

    with pytest.raises(WeatherError, match="No encontré el lugar"):
        await weather.forecast("Lugarquenoexiste", days=1)


async def test_service_failure_is_reported():
    weather = weather_with(lambda request: httpx2.Response(503))

    with pytest.raises(WeatherError, match="No pude consultar el clima"):
        await weather.forecast("Villavicencio", days=1)
