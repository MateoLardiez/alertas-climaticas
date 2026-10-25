"""Tests de los schemas Pydantic: validacion de entrada y lectura desde objetos del modelo."""

import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from alertas_climaticas.schemas.farm import FarmCreate, FarmRead, FarmUpdate
from alertas_climaticas.schemas.region import RegionRead
from alertas_climaticas.schemas.user import UserCreate, UserDetailRead, UserRead


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
