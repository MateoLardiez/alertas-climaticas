"""Validacion de los nombres (usuarios y campos): largo maximo y sin caracteres nulos.

Un NUL en un texto lo rechaza PostgreSQL: sin validar antes, la API respondia 500.
"""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import Farm, User
from alertas_climaticas.schemas.farm import FarmCreate, FarmUpdate
from alertas_climaticas.schemas.user import UserCreate, UserUpdate
from tests import factories

# El limite es parte del contrato de la API (se documenta en el README): se fija aca a proposito.
MAX_LENGTH = 100
TOO_LONG = "x" * (MAX_LENGTH + 1)
LONGEST = "x" * MAX_LENGTH
INVALID_NAMES = ["a\x00b", "\x00", TOO_LONG, "x" * 1_000_000]

ID = uuid.uuid4()
SCHEMAS = [
    pytest.param(lambda name: UserCreate(name=name), id="UserCreate"),
    pytest.param(lambda name: UserUpdate(name=name), id="UserUpdate"),
    pytest.param(lambda name: FarmCreate(name=name, user_id=ID, region_id=ID), id="FarmCreate"),
    pytest.param(lambda name: FarmUpdate(name=name), id="FarmUpdate"),
]


@pytest.mark.parametrize("build", SCHEMAS)
@pytest.mark.parametrize("name", INVALID_NAMES)
def test_schemas_reject_invalid_names(build: Callable[[str], object], name: str) -> None:
    with pytest.raises(ValidationError):
        build(name)


@pytest.mark.parametrize("build", SCHEMAS)
def test_schemas_accept_a_name_of_exactly_the_maximum_length(
    build: Callable[[str], object],
) -> None:
    assert build(LONGEST).name == LONGEST  # type: ignore[attr-defined]


@pytest.mark.parametrize("build", SCHEMAS)
def test_the_length_is_measured_after_stripping_whitespace(
    build: Callable[[str], object],
) -> None:
    assert build(f"  {LONGEST}  ").name == LONGEST  # type: ignore[attr-defined]


@pytest.mark.parametrize("build", SCHEMAS)
def test_the_error_says_what_is_wrong_with_a_null_character(
    build: Callable[[str], object],
) -> None:
    with pytest.raises(ValidationError, match="null characters"):
        build("a\x00b")


class TestThroughTheApi:
    """Cada endpoint que recibe un nombre responde 422 (no 500) y no guarda nada."""

    @pytest.fixture
    async def user(self, session: AsyncSession) -> User:
        return await factories.create_user(session, "Original")

    @pytest.fixture
    async def farm(self, session: AsyncSession, user: User) -> Farm:
        region = await factories.create_region(session)
        return await factories.create_farm(session, user, region, "Original")

    @pytest.mark.parametrize("name", INVALID_NAMES)
    async def test_post_users(
        self, client: AsyncClient, session: AsyncSession, name: str
    ) -> None:
        response = await client.post("/users", json={"name": name})

        assert response.status_code == 422
        assert await session.scalar(select(func.count()).select_from(User)) == 0

    @pytest.mark.parametrize("name", INVALID_NAMES)
    async def test_patch_users(
        self, client: AsyncClient, session: AsyncSession, user: User, name: str
    ) -> None:
        response = await client.patch(f"/users/{user.id}", json={"name": name})

        assert response.status_code == 422
        await session.refresh(user)
        assert user.name == "Original"

    @pytest.mark.parametrize("name", INVALID_NAMES)
    async def test_post_farms(
        self, client: AsyncClient, session: AsyncSession, user: User, name: str
    ) -> None:
        region = await factories.create_region(session)

        response = await client.post(
            "/farms", json={"user_id": str(user.id), "region_id": str(region.id), "name": name}
        )

        assert response.status_code == 422
        assert await session.scalar(select(func.count()).select_from(Farm)) == 0

    @pytest.mark.parametrize("name", INVALID_NAMES)
    async def test_patch_farms(
        self, client: AsyncClient, session: AsyncSession, farm: Farm, name: str
    ) -> None:
        response = await client.patch(f"/farms/{farm.id}", json={"name": name})

        assert response.status_code == 422
        await session.refresh(farm)
        assert farm.name == "Original"

    async def test_the_longest_name_is_accepted_everywhere(
        self, client: AsyncClient, session: AsyncSession, user: User, farm: Farm
    ) -> None:
        region = await factories.create_region(session, "Otra")
        sends: list[Awaitable[Response]] = [
            client.post("/users", json={"name": LONGEST}),
            client.patch(f"/users/{user.id}", json={"name": LONGEST}),
            client.post(
                "/farms",
                json={"user_id": str(user.id), "region_id": str(region.id), "name": LONGEST},
            ),
            client.patch(f"/farms/{farm.id}", json={"name": LONGEST}),
        ]

        statuses = [(await send).status_code for send in sends]

        assert statuses == [201, 200, 201, 200]
