"""Tests for Group surface — read APIs and the inter-dependency navigation
(Group → Member → Guardian)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from spond.group import Group
from spond.spond import Spond

from .conftest import MOCK_PASSWORD, MOCK_USERNAME


class TestGroupMethods:
    @pytest.fixture
    def mock_groups(self) -> list[Group]:
        """Two typed Group instances with placeholder data."""
        return [
            Group.model_validate({"id": "ID1", "name": "Group One"}),
            Group.model_validate({"id": "ID2", "name": "Group Two"}),
        ]

    @pytest.mark.asyncio
    async def test_get_group__happy_path(
        self, mock_groups: list[Group], mock_token
    ) -> None:
        """Test that a valid `id` returns the matching group."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.groups = mock_groups
        s.token = mock_token
        g = await s.get_group("ID2")

        assert isinstance(g, Group)
        assert g.uid == "ID2"
        assert g.name == "Group Two"

    @pytest.mark.asyncio
    async def test_get_group__no_match_raises_exception(
        self, mock_groups: list[Group], mock_token
    ) -> None:
        """Test that a non-matched `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.groups = mock_groups
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_group("ID3")

    @pytest.mark.asyncio
    async def test_get_group__blank_id_raises_exception(
        self, mock_groups: list[Group], mock_token
    ) -> None:
        """Test that a blank `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.groups = mock_groups
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_group("")

    @pytest.mark.asyncio
    async def test_get_group__no_groups_available_raises_keyerror(
        self, mock_token
    ) -> None:
        """`get_groups()` is documented to return None when no groups exist;
        `get_group()` should surface this as KeyError, not TypeError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.groups = None
        s.get_groups = AsyncMock()  # leaves self.groups as None

        with pytest.raises(KeyError):
            await s.get_group("ID1")


class TestGroupNavigation:
    """Group → Member → Guardian wiring."""

    def test_group_materializes_typed_members_and_guardians(self) -> None:
        raw = {
            "id": "GID",
            "name": "Test Group",
            "members": [
                {
                    "id": "M1",
                    "firstName": "Alice",
                    "lastName": "Smith",
                    "email": "alice@example.invalid",
                    "guardians": [
                        {
                            "id": "G1",
                            "firstName": "Bob",
                            "lastName": "Smith",
                            "phoneNumber": "+1",
                        }
                    ],
                },
            ],
        }
        from spond.person import Guardian, Member

        group = Group.model_validate(raw)
        assert isinstance(group.members[0], Member)
        assert group.members[0].full_name == "Alice Smith"
        assert isinstance(group.members[0].guardians[0], Guardian)
        assert group.members[0].guardians[0].full_name == "Bob Smith"

    def test_find_member_by_email(self) -> None:
        group = Group.model_validate(
            {
                "id": "GID",
                "name": "G",
                "members": [
                    {
                        "id": "M1",
                        "firstName": "A",
                        "lastName": "B",
                        "email": "a@b.invalid",
                    },
                ],
            }
        )
        found = group.find_member(email="a@b.invalid")
        assert found is not None
        assert found.uid == "M1"

    def test_find_member_returns_none_when_no_match(self) -> None:
        group = Group.model_validate({"id": "GID", "name": "G", "members": []})
        assert group.find_member(uid="missing") is None

    def test_find_member_requires_exactly_one_criterion(self) -> None:
        group = Group.model_validate({"id": "GID", "name": "G", "members": []})
        with pytest.raises(ValueError, match="exactly one"):
            group.find_member()
        with pytest.raises(ValueError, match="exactly one"):
            group.find_member(uid="X", email="a@b.invalid")

    def test_member_custom_fields_alias_works_via_either_name(self) -> None:
        """`Member.custom_fields` aliases the API's `"fields"` key — both
        forms must populate the attribute identically."""
        from spond.person import Member

        # API-style (via alias):
        m1 = Member.model_validate(
            {"id": "M1", "firstName": "A", "lastName": "B", "fields": {"height": "175"}}
        )
        # Python-style (via name):
        m2 = Member.model_validate(
            {
                "id": "M2",
                "firstName": "C",
                "lastName": "D",
                "custom_fields": {"height": "180"},
            }
        )
        assert m1.custom_fields == {"height": "175"}
        assert m2.custom_fields == {"height": "180"}
