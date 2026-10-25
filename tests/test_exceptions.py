"""Tests de los errores de dominio."""

import uuid

from alertas_climaticas.exceptions import NotFoundError


def test_not_found_error_keeps_the_resource_and_its_id() -> None:
    resource_id = uuid.uuid4()

    error = NotFoundError("Farm", resource_id)

    assert error.resource == "Farm"
    assert error.resource_id == resource_id


def test_not_found_error_message_names_the_resource_and_id() -> None:
    resource_id = uuid.uuid4()

    assert str(NotFoundError("Farm", resource_id)) == f"Farm {resource_id} not found"


def test_not_found_error_is_a_plain_exception_without_http_knowledge() -> None:
    assert issubclass(NotFoundError, Exception)
    assert not hasattr(NotFoundError, "status_code")
