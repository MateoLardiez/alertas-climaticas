"""Importa todos los modelos para que queden registrados en Base.metadata (lo necesita Alembic)."""

from alertas_climaticas.models.alert import Alert
from alertas_climaticas.models.event import Event
from alertas_climaticas.models.farm import Farm
from alertas_climaticas.models.notification import Notification
from alertas_climaticas.models.region import Region
from alertas_climaticas.models.user import User
from alertas_climaticas.models.weather_forecast import WeatherForecast

__all__ = ["Alert", "Event", "Farm", "Notification", "Region", "User", "WeatherForecast"]
