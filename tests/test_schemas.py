"""Tests de los schemas Pydantic: validacion de entrada y lectura desde objetos del modelo."""

import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from alertas_climaticas.schemas.farm import FarmCreate, FarmRead
from alertas_climaticas.schemas.region import RegionRead
from alertas_climaticas.schemas.user import UserCreate, UserRead


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
