"""Tests de los services, sin pasar por HTTP."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.database.session import async_session_factory
from alertas_climaticas.exceptions import NotFoundError
from alertas_climaticas.models import Alert, Farm, User
from alertas_climaticas.schemas.farm import FarmCreate, FarmUpdate
from alertas_climaticas.schemas.user import UserCreate
from alertas_climaticas.services import farms as farm_service
from alertas_climaticas.services import regions as region_service
from alertas_climaticas.services import users as user_service
from tests import factories


class TestUserService:
    async def test_create_user_returns_the_saved_user(self, session: AsyncSession) -> None:
        user = await user_service.create_user(session, UserCreate(name="Mateo"))

        assert isinstance(user.id, uuid.UUID)
        assert user.name == "Mateo"

    async def test_create_user_commits_the_user(self, session: AsyncSession) -> None:
        user = await user_service.create_user(session, UserCreate(name="Mateo"))

        async with async_session_factory() as other_session:
            assert await other_session.get(User, user.id) is not None

    async def test_create_user_creates_a_new_row_each_time(self, session: AsyncSession) -> None:
        first = await user_service.create_user(session, UserCreate(name="Mateo"))
        second = await user_service.create_user(session, UserCreate(name="Mateo"))

        assert first.id != second.id


class TestRegionService:
    async def test_list_regions_is_empty_without_regions(self, session: AsyncSession) -> None:
        assert list(await region_service.list_regions(session)) == []

    async def test_list_regions_is_sorted_by_name(self, session: AsyncSession) -> None:
        for name in ["Zeta", "Alfa", "Mitad"]:
            await factories.create_region(session, name)

        regions = await region_service.list_regions(session)

        assert [region.name for region in regions] == ["Alfa", "Mitad", "Zeta"]


class TestFarmService:
    async def _count_farms(self, session: AsyncSession) -> int:
        return await session.scalar(select(func.count()).select_from(Farm)) or 0

    async def test_create_farm_returns_the_saved_farm(self, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)

        farm = await farm_service.create_farm(
            session, FarmCreate(user_id=user.id, region_id=region.id, name="La Esperanza")
        )

        assert isinstance(farm.id, uuid.UUID)
        assert (farm.user_id, farm.region_id, farm.name) == (user.id, region.id, "La Esperanza")

    async def test_create_farm_commits_the_farm(self, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)

        farm = await farm_service.create_farm(
            session, FarmCreate(user_id=user.id, region_id=region.id, name="Campo")
        )

        async with async_session_factory() as other_session:
            assert await other_session.get(Farm, farm.id) is not None

    async def test_create_farm_rejects_an_unknown_user(self, session: AsyncSession) -> None:
        region = await factories.create_region(session)
        unknown = uuid.uuid4()

        with pytest.raises(NotFoundError) as error:
            await farm_service.create_farm(
                session, FarmCreate(user_id=unknown, region_id=region.id, name="Campo")
            )

        assert (error.value.resource, error.value.resource_id) == ("User", unknown)
        assert await self._count_farms(session) == 0

    async def test_create_farm_rejects_an_unknown_region(self, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        unknown = uuid.uuid4()

        with pytest.raises(NotFoundError) as error:
            await farm_service.create_farm(
                session, FarmCreate(user_id=user.id, region_id=unknown, name="Campo")
            )

        assert (error.value.resource, error.value.resource_id) == ("Region", unknown)
        assert await self._count_farms(session) == 0

    async def test_get_farm_returns_the_farm(self, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        created = await factories.create_farm(session, user, region)

        farm = await farm_service.get_farm(session, created.id)

        assert farm.id == created.id

    async def test_get_farm_rejects_an_unknown_farm(self, session: AsyncSession) -> None:
        unknown = uuid.uuid4()

        with pytest.raises(NotFoundError) as error:
            await farm_service.get_farm(session, unknown)

        assert (error.value.resource, error.value.resource_id) == ("Farm", unknown)


class TestFarmServiceManagement:
    async def test_list_farms_returns_only_the_users_farms_sorted_by_name(
        self, session: AsyncSession
    ) -> None:
        mine = await factories.create_user(session, "Yo")
        other = await factories.create_user(session, "Otro")
        region = await factories.create_region(session)
        for name in ["Zeta", "Alfa"]:
            await factories.create_farm(session, mine, region, name)
        await factories.create_farm(session, other, region, "Ajeno")

        farms = await farm_service.list_farms(session, mine.id)

        assert [farm.name for farm in farms] == ["Alfa", "Zeta"]

    async def test_list_farms_is_empty_for_an_unknown_user(self, session: AsyncSession) -> None:
        assert list(await farm_service.list_farms(session, uuid.uuid4())) == []

    async def test_update_farm_changes_only_the_given_fields(self, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        farm = await factories.create_farm(session, user, region, "Original")

        updated = await farm_service.update_farm(session, farm.id, FarmUpdate(name="Nuevo"))

        assert updated.name == "Nuevo"
        assert updated.region_id == region.id
        assert updated.user_id == user.id

    async def test_update_farm_changes_the_region(self, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session, "Tandil")
        other_region = await factories.create_region(session, "Lobos")
        farm = await factories.create_farm(session, user, region)

        updated = await farm_service.update_farm(
            session, farm.id, FarmUpdate(region_id=other_region.id)
        )

        assert updated.region_id == other_region.id

    async def test_update_farm_commits_the_change(self, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        farm = await factories.create_farm(session, user, region, "Original")

        await farm_service.update_farm(session, farm.id, FarmUpdate(name="Nuevo"))

        async with async_session_factory() as other_session:
            saved = await other_session.get(Farm, farm.id)
            assert saved is not None
            assert saved.name == "Nuevo"

    async def test_update_farm_rejects_an_unknown_farm(self, session: AsyncSession) -> None:
        unknown = uuid.uuid4()

        with pytest.raises(NotFoundError) as error:
            await farm_service.update_farm(session, unknown, FarmUpdate(name="Nuevo"))

        assert (error.value.resource, error.value.resource_id) == ("Farm", unknown)

    async def test_update_farm_rejects_an_unknown_region_and_changes_nothing(
        self, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        farm = await factories.create_farm(session, user, region, "Original")
        unknown = uuid.uuid4()

        with pytest.raises(NotFoundError) as error:
            await farm_service.update_farm(
                session, farm.id, FarmUpdate(name="Nuevo", region_id=unknown)
            )

        assert (error.value.resource, error.value.resource_id) == ("Region", unknown)
        async with async_session_factory() as other_session:
            saved = await other_session.get(Farm, farm.id)
            assert saved is not None
            assert saved.name == "Original"

    async def test_delete_farm_removes_it(self, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        farm = await factories.create_farm(session, user, region)
        farm_id = farm.id

        await farm_service.delete_farm(session, farm_id)

        async with async_session_factory() as other_session:
            assert await other_session.get(Farm, farm_id) is None

    async def test_delete_farm_cascades_to_its_alerts(self, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        event = await factories.create_event(session)
        farm = await factories.create_farm(session, user, region)
        await factories.create_alert(session, farm, event)

        await farm_service.delete_farm(session, farm.id)

        assert await session.scalar(select(func.count()).select_from(Alert)) == 0

    async def test_delete_farm_rejects_an_unknown_farm(self, session: AsyncSession) -> None:
        unknown = uuid.uuid4()

        with pytest.raises(NotFoundError) as error:
            await farm_service.delete_farm(session, unknown)

        assert (error.value.resource, error.value.resource_id) == ("Farm", unknown)
