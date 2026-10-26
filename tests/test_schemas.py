"""Tests de los schemas Pydantic: validacion de entrada y lectura desde objetos del modelo."""

import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from alertas_climaticas.schemas.alert import AlertCreate, AlertRead, AlertUpdate
from alertas_climaticas.schemas.event import EventRead
from alertas_climaticas.schemas.farm import FarmCreate, FarmRead, FarmUpdate
from alertas_climaticas.schemas.notification import NotificationRead
from alertas_climaticas.schemas.region import RegionRead
from alertas_climaticas.schemas.user import UserCreate, UserDetailRead, UserRead, UserUpdate


def test_user_create_accepts_a_valid_name() -> None:
    assert UserCreate(name="Mateo").name == "Mateo"


def test_user_create_strips_surrounding_whitespace() -> None:
    assert UserCreate(name="  Mateo  ").name == "Mateo"


def test_user_create_keeps_unicode_names() -> None:
    assert UserCreate(name="José Ñandú").name == "José Ñandú"


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_user_create_rejects_empty_or_blank_names(name: str) -> None:
    with pytest.raises(ValidationError):
        UserCreate(name=name)


def test_user_update_strips_whitespace_and_keeps_unicode() -> None:
    assert UserUpdate(name="  José Ñandú  ").name == "José Ñandú"


@pytest.mark.parametrize("name", ["", "   ", None, 123, ["Mateo"]])
def test_user_update_rejects_invalid_names(name: object) -> None:
    with pytest.raises(ValidationError):
        UserUpdate(name=name)  # type: ignore[arg-type]


def test_user_update_requires_the_name() -> None:
    with pytest.raises(ValidationError):
        UserUpdate()  # type: ignore[call-arg]


def test_user_update_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        UserUpdate(name="Mateo", id="x")  # type: ignore[call-arg]


@pytest.mark.parametrize("name", [None, 123, ["Mateo"]])
def test_user_create_rejects_non_string_names(name: object) -> None:
    with pytest.raises(ValidationError):
        UserCreate(name=name)  # type: ignore[arg-type]


def test_user_create_requires_a_name() -> None:
    with pytest.raises(ValidationError):
        UserCreate()  # type: ignore[call-arg]


def test_user_create_has_no_id_field() -> None:
    assert "id" not in UserCreate.model_fields


def test_user_read_is_built_from_a_model_object() -> None:
    obj = SimpleNamespace(id=uuid.uuid4(), name="Mateo", extra="ignorado")

    user = UserRead.model_validate(obj)

    assert user.id == obj.id
    assert user.name == "Mateo"
    assert set(user.model_dump()) == {"id", "name"}


def test_user_detail_read_extends_user_read_with_farm_ids() -> None:
    farm_id = uuid.uuid4()
    obj = SimpleNamespace(id=uuid.uuid4(), name="Mateo", farm_ids=[farm_id])

    detail = UserDetailRead.model_validate(obj)

    assert issubclass(UserDetailRead, UserRead)
    assert detail.farm_ids == [farm_id]
    assert set(detail.model_dump()) == {"id", "name", "farm_ids"}


def test_user_detail_read_requires_farm_ids() -> None:
    with pytest.raises(ValidationError):
        UserDetailRead.model_validate(SimpleNamespace(id=uuid.uuid4(), name="Mateo"))


def _farm_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "region_id": uuid.uuid4(),
        "name": "La Esperanza",
    }
    return data | overrides


def test_farm_create_accepts_valid_data_and_parses_uuid_strings() -> None:
    user_id = uuid.uuid4()

    farm = FarmCreate.model_validate(_farm_data(user_id=str(user_id)))

    assert farm.user_id == user_id
    assert farm.name == "La Esperanza"


def test_farm_create_strips_the_name() -> None:
    assert FarmCreate.model_validate(_farm_data(name="  Campo  ")).name == "Campo"


@pytest.mark.parametrize("field", ["user_id", "region_id", "name"])
def test_farm_create_requires_every_field(field: str) -> None:
    data = _farm_data()
    del data[field]

    with pytest.raises(ValidationError):
        FarmCreate.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_id", "no-es-un-uuid"),
        ("user_id", 123),
        ("region_id", "no-es-un-uuid"),
        ("region_id", None),
        ("name", ""),
        ("name", "   "),
        ("name", None),
        ("name", 5),
    ],
)
def test_farm_create_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        FarmCreate.model_validate(_farm_data(**{field: value}))


def test_farm_update_accepts_only_the_name() -> None:
    update = FarmUpdate(name="Nuevo")

    assert update.model_dump(exclude_unset=True) == {"name": "Nuevo"}


def test_farm_update_accepts_only_the_region() -> None:
    region_id = uuid.uuid4()

    update = FarmUpdate(region_id=region_id)

    assert update.model_dump(exclude_unset=True) == {"region_id": region_id}


def test_farm_update_accepts_name_and_region() -> None:
    region_id = uuid.uuid4()

    update = FarmUpdate(name="Nuevo", region_id=region_id)

    assert update.model_dump(exclude_unset=True) == {"name": "Nuevo", "region_id": region_id}


def test_farm_update_strips_the_name() -> None:
    assert FarmUpdate(name="  Nuevo  ").name == "Nuevo"


def test_farm_update_rejects_an_empty_update() -> None:
    with pytest.raises(ValidationError, match="at least one field"):
        FarmUpdate()


@pytest.mark.parametrize("data", [{"name": None}, {"region_id": None}, {"name": "ok", "region_id": None}])
def test_farm_update_rejects_explicit_nulls(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="cannot be null"):
        FarmUpdate.model_validate(data)


@pytest.mark.parametrize("data", [{"name": ""}, {"name": "   "}, {"name": 5}, {"region_id": "xyz"}])
def test_farm_update_rejects_invalid_values(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        FarmUpdate.model_validate(data)


@pytest.mark.parametrize("extra", ["user_id", "id", "desconocido"])
def test_farm_update_rejects_fields_that_cannot_be_changed(extra: str) -> None:
    with pytest.raises(ValidationError):
        FarmUpdate.model_validate({"name": "Nuevo", extra: str(uuid.uuid4())})


def test_farm_create_has_no_id_field() -> None:
    assert "id" not in FarmCreate.model_fields


def test_farm_read_is_built_from_a_model_object() -> None:
    obj = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4(), region_id=uuid.uuid4(), name="X")

    farm = FarmRead.model_validate(obj)

    assert set(farm.model_dump()) == {"id", "user_id", "region_id", "name"}
    assert farm.id == obj.id


def test_region_read_is_built_from_a_model_object() -> None:
    obj = SimpleNamespace(id=uuid.uuid4(), name="Tandil")

    region = RegionRead.model_validate(obj)

    assert region.id == obj.id
    assert region.name == "Tandil"
    assert set(region.model_dump()) == {"id", "name"}


def _alert_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "farm_id": uuid.uuid4(),
        "event_id": uuid.uuid4(),
        "threshold": 60,
    }
    return data | overrides


@pytest.mark.parametrize("threshold", [0, 1, 60, 99, 100])
def test_alert_create_accepts_thresholds_from_0_to_100(threshold: int) -> None:
    assert AlertCreate.model_validate(_alert_data(threshold=threshold)).threshold == threshold


@pytest.mark.parametrize("threshold", [-1, 101, "60", 60.5, 60.0, True, None, [], "abc"])
def test_alert_create_rejects_invalid_thresholds(threshold: object) -> None:
    with pytest.raises(ValidationError):
        AlertCreate.model_validate(_alert_data(threshold=threshold))


@pytest.mark.parametrize("field", ["farm_id", "event_id", "threshold"])
def test_alert_create_requires_every_field(field: str) -> None:
    data = _alert_data()
    del data[field]

    with pytest.raises(ValidationError):
        AlertCreate.model_validate(data)


@pytest.mark.parametrize("field", ["farm_id", "event_id"])
def test_alert_create_rejects_invalid_ids(field: str) -> None:
    with pytest.raises(ValidationError):
        AlertCreate.model_validate(_alert_data(**{field: "no-es-un-uuid"}))


def test_alert_create_has_no_id_field() -> None:
    assert "id" not in AlertCreate.model_fields


def test_alert_update_only_accepts_the_threshold() -> None:
    assert AlertUpdate(threshold=80).threshold == 80
    assert set(AlertUpdate.model_fields) == {"threshold"}


@pytest.mark.parametrize("data", [{}, {"threshold": None}, {"threshold": 101}, {"threshold": "80"}])
def test_alert_update_rejects_invalid_payloads(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AlertUpdate.model_validate(data)


@pytest.mark.parametrize("extra", ["farm_id", "event_id", "id", "desconocido"])
def test_alert_update_rejects_fields_that_cannot_be_changed(extra: str) -> None:
    with pytest.raises(ValidationError):
        AlertUpdate.model_validate({"threshold": 80, extra: str(uuid.uuid4())})


def test_alert_read_is_built_from_a_model_object() -> None:
    obj = SimpleNamespace(id=uuid.uuid4(), farm_id=uuid.uuid4(), event_id=uuid.uuid4(), threshold=70)

    alert = AlertRead.model_validate(obj)

    assert set(alert.model_dump()) == {"id", "farm_id", "event_id", "threshold"}
    assert alert.threshold == 70


def test_event_read_is_built_from_a_model_object() -> None:
    obj = SimpleNamespace(id=uuid.uuid4(), name="lluvia")

    event = EventRead.model_validate(obj)

    assert (event.id, event.name) == (obj.id, "lluvia")
    assert set(event.model_dump()) == {"id", "name"}


def _notification_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": uuid.uuid4(),
        "alert_id": uuid.uuid4(),
        "farm_name": "La Esperanza",
        "event": "lluvia",
        "forecast_date": date(2026, 3, 5),
        "probability": 80,
        "read_at": None,
        "created_at": datetime(2026, 3, 1, 6, 0, tzinfo=timezone.utc),
    }
    return data | overrides


def test_notification_read_builds_a_readable_message() -> None:
    notification = NotificationRead.model_validate(_notification_data())

    assert notification.message == (
        "Alerta de lluvia en La Esperanza: 80% de probabilidad el 05/03/2026"
    )


@pytest.mark.parametrize(
    ("event", "farm", "probability", "forecast_date", "expected"),
    [
        ("helada", "Campo Sur", 100, date(2026, 12, 25), "Alerta de helada en Campo Sur: 100% de probabilidad el 25/12/2026"),
        ("tormenta", "El Ombu", 0, date(2026, 1, 9), "Alerta de tormenta en El Ombu: 0% de probabilidad el 09/01/2026"),
        ("calor extremo", "Los Alamos", 60, date(2026, 2, 28), "Alerta de calor extremo en Los Alamos: 60% de probabilidad el 28/02/2026"),
    ],
)
def test_notification_message_uses_day_month_year_and_the_event_and_farm_names(
    event: str, farm: str, probability: int, forecast_date: date, expected: str
) -> None:
    data = _notification_data(
        event=event, farm_name=farm, probability=probability, forecast_date=forecast_date
    )

    assert NotificationRead.model_validate(data).message == expected


def test_notification_message_does_not_mention_the_threshold() -> None:
    message = NotificationRead.model_validate(_notification_data()).message

    assert "umbral" not in message.lower()


def test_notification_is_unread_without_read_at_and_read_with_it() -> None:
    unread = NotificationRead.model_validate(_notification_data())
    read = NotificationRead.model_validate(
        _notification_data(read_at=datetime(2026, 3, 2, tzinfo=timezone.utc))
    )

    assert unread.read is False
    assert read.read is True


def test_notification_dump_includes_the_computed_fields() -> None:
    dumped = NotificationRead.model_validate(_notification_data()).model_dump()

    assert set(dumped) == {
        "id",
        "alert_id",
        "farm_name",
        "event",
        "forecast_date",
        "probability",
        "read_at",
        "created_at",
        "read",
        "message",
    }


def test_notification_read_is_built_from_a_row_like_object() -> None:
    row = SimpleNamespace(**_notification_data())

    notification = NotificationRead.model_validate(row)

    assert notification.farm_name == "La Esperanza"
