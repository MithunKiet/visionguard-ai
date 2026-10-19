"""Real PostgreSQL user-list bounds, role batching and scope regressions."""
from datetime import datetime, timezone
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from src.modules.users.infrastructure.repositories import UserAdminRepository
from src.shared.database.models import Role, User, UserRole
from src.shared.database.session import AsyncSessionFactory, engine
from src.shared.security.scope import ScopeFilter
from tests.test_review_integration import headers, setup as setup

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL and Redis")


@pytest.fixture
async def directory(setup):
    s = setup
    async with AsyncSessionFactory() as db:
        roles = {role.code: role for role in (await db.scalars(select(Role))).all()}
        rows = []
        for place, count in ((s.places[0], 105), (s.places[1], 3), (s.places[2], 4)):
            rows += [User(enterprise_id=place.factory.enterprise_id, factory_id=place.factory.id,
                department_id=place.department.id, name="Same display name", email=f"{uuid4().hex}@example.com",
                password_hash="unused-test-only", is_first_login=False, status="Active") for _ in range(count)]
        deleted = User(enterprise_id=s.enterprise.id, factory_id=s.places[0].factory.id, name="Deleted",
            email=f"{uuid4().hex}@example.com", password_hash="unused-test-only", deleted_at=datetime.now(timezone.utc))
        no_factory = User(enterprise_id=s.enterprise.id, name="Unassigned", email=f"{uuid4().hex}@example.com",
                          password_hash="unused-test-only")
        db.add_all([*rows, deleted, no_factory])
        await db.flush()
        for row in rows:
            db.add(UserRole(user_public_id=row.public_id, role_public_id=roles["VIEWER"].public_id))
        db.add(UserRole(user_public_id=rows[0].public_id, role_public_id=roles["SUPERVISOR"].public_id))
        await db.commit()
    return SimpleNamespace(site=s, rows=rows, deleted=deleted, no_factory=no_factory,
                           total=112, factory_total=108, foreign_total=5)


async def test_users_are_bounded_by_default_and_metadata_is_scoped(directory):
    s = directory.site
    response = await s.client.get("/api/v1/users", headers=headers(s))
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["data"]) == 20
    assert payload["meta"] == {"page": 1, "page_size": 20, "total": directory.total, "total_pages": 6}
    assert all(row["enterprise_id"] == s.enterprise.public_id for row in payload["data"])
    assert all(isinstance(row["id"], str) and "password_hash" not in row for row in payload["data"])


async def test_equal_names_have_stable_nonoverlapping_pages_and_keep_all_roles(directory):
    s = directory.site
    seen = []
    for page in range(1, 8):
        response = await s.client.get("/api/v1/users", headers=headers(s), params={"page": page, "page_size": 17})
        assert response.status_code == 200
        payload = response.json()
        assert payload["meta"]["total"] == directory.total
        assert len(payload["data"]) <= 17
        seen.extend(payload["data"])
    assert len({row["id"] for row in seen}) == len(seen) == directory.total
    assert directory.deleted.public_id not in {row["id"] for row in seen}
    multi_role = next(row for row in seen if row["id"] == directory.rows[0].public_id)
    assert multi_role["roles"] == ["SUPERVISOR", "VIEWER"]
    unassigned = next(row for row in seen if row["id"] == directory.no_factory.public_id)
    assert unassigned["roles"] == [] and unassigned["factory_id"] is None
    repeat = await s.client.get("/api/v1/users", headers=headers(s), params={"page": 2, "page_size": 17})
    assert [row["id"] for row in repeat.json()["data"]] == [row["id"] for row in seen[17:34]]


async def test_factory_manager_and_other_tenant_have_independent_totals(directory):
    s = directory.site
    for caller, total, factory in (("manager", directory.factory_total, s.places[0].factory),
                                    ("foreign", directory.foreign_total, s.places[2].factory)):
        response = await s.client.get("/api/v1/users", headers=headers(s, caller), params={"page_size": 100})
        assert response.status_code == 200
        assert response.json()["meta"]["total"] == total
        assert all(row["factory_id"] == factory.public_id for row in response.json()["data"])
    blocked = await s.client.get("/api/v1/users", headers=headers(s, "viewer"))
    assert blocked.status_code == 403


async def test_empty_scope_and_beyond_last_page_keep_totals_without_leaking_rows(directory):
    s = directory.site
    async with AsyncSessionFactory() as db:
        rows, total = await UserAdminRepository(db).list(s.enterprise.public_id, ScopeFilter(unrestricted=False))
        assert rows == [] and total == 0
    response = await s.client.get("/api/v1/users", headers=headers(s), params={"page": 99})
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"]["total"] == directory.total


async def test_role_query_count_is_constant_between_one_and_one_hundred_users(directory):
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)
    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        counts = []
        for page_size in (1, 100):
            statements.clear()
            async with AsyncSessionFactory() as db:
                users, total = await UserAdminRepository(db).list(directory.site.enterprise.public_id, page_size=page_size)
                assert len(users) == page_size and total == directory.total
            counts.append(len(statements))
        assert counts == [4, 4]  # Tenant lookup, scoped count, bounded rows, one roles query.
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)


async def test_detail_uses_the_same_complete_role_mapping(directory):
    s = directory.site
    response = await s.client.get(f"/api/v1/users/{directory.rows[0].public_id}", headers=headers(s))
    assert response.status_code == 200
    assert response.json()["data"]["roles"] == ["SUPERVISOR", "VIEWER"]


async def test_invite_update_detail_and_deactivation_keep_role_mapping(setup, monkeypatch):
    from src.modules.users.application import services
    monkeypatch.setattr(services, "send_email", AsyncMock(return_value=False))
    s = setup
    created = await s.client.post("/api/v1/users", headers=headers(s), json={
        "name": "New user", "email": f"{uuid4().hex}@example.com", "roles": ["VIEWER"],
        "factory_id": s.places[0].factory.public_id, "department_id": s.places[0].department.public_id,
    })
    assert created.status_code == 200
    user_id = created.json()["data"]["id"]
    assert created.json()["data"]["roles"] == ["VIEWER"]
    updated = await s.client.put(f"/api/v1/users/{user_id}", headers=headers(s),
                                json={"roles": ["VIEWER", "SUPERVISOR"]})
    assert updated.status_code == 200
    assert updated.json()["data"]["roles"] == ["SUPERVISOR", "VIEWER"]
    listed = await s.client.get("/api/v1/users", headers=headers(s))
    record = next(row for row in listed.json()["data"] if row["id"] == user_id)
    assert record["roles"] == ["SUPERVISOR", "VIEWER"]
    assert "temp_password" not in record and listed.json()["meta"]["total"] == 4
    assert (await s.client.delete(f"/api/v1/users/{user_id}", headers=headers(s))).status_code == 200
    listed = await s.client.get("/api/v1/users", headers=headers(s))
    assert listed.json()["meta"]["total"] == 3
    assert user_id not in {row["id"] for row in listed.json()["data"]}


@pytest.mark.parametrize("params", [{"page": 0}, {"page": 1_000_001}, {"page_size": 0}, {"page_size": 101}])
async def test_invalid_api_bounds_are_rejected(setup, params):
    response = await setup.client.get("/api/v1/users", headers=headers(setup), params=params)
    assert response.status_code == 422
