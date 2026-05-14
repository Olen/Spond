"""Tests for Group surface — read APIs and the inter-dependency navigation
(Group → Member → Guardian)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

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

    def test_group_str(self) -> None:
        """`Group.__str__` includes uid, name, and member count."""
        raw = {
            "id": "GID1",
            "name": "My Team",
            "members": [
                {"id": "M1", "firstName": "A", "lastName": "B"},
                {"id": "M2", "firstName": "C", "lastName": "D"},
            ],
        }
        g = Group.model_validate(raw)
        s = str(g)
        assert "GID1" in s
        assert "My Team" in s
        assert "2" in s  # member count

    @pytest.mark.asyncio
    async def test_group_from_api_wires_client_on_members_and_guardians(self) -> None:
        """`Group.from_api()` must set `_client` on the group, each member,
        and each nested guardian so per-instance HTTP methods work."""
        from spond.spond import Spond

        raw = {
            "id": "GID",
            "name": "G",
            "members": [
                {
                    "id": "M1",
                    "firstName": "A",
                    "lastName": "B",
                    "guardians": [{"id": "G1", "firstName": "C", "lastName": "D"}],
                }
            ],
        }
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        group = Group.from_api(raw, s)

        assert group._client is s
        assert group.members[0]._client is s
        assert group.members[0].guardians[0]._client is s

    def test_find_member_by_name(self) -> None:
        """`find_member(name=...)` matches against `member.full_name`."""
        group = Group.model_validate(
            {
                "id": "GID",
                "name": "G",
                "members": [
                    {"id": "M1", "firstName": "Charlie", "lastName": "Brown"},
                    {"id": "M2", "firstName": "Alice", "lastName": "Smith"},
                ],
            }
        )
        found = group.find_member(name="Alice Smith")
        assert found is not None
        assert found.uid == "M2"

    def test_find_member_by_uid(self) -> None:
        """`find_member(uid=...)` returns the member with the matching id."""
        group = Group.model_validate(
            {
                "id": "GID",
                "name": "G",
                "members": [
                    {"id": "M1", "firstName": "A", "lastName": "B"},
                    {"id": "M2", "firstName": "C", "lastName": "D"},
                ],
            }
        )
        found = group.find_member(uid="M1")
        assert found is not None
        assert found.uid == "M1"

    def test_person_str(self) -> None:
        """`Person.__str__` includes class name, uid, and full_name."""
        from spond.person import Member

        m = Member.model_validate({"id": "M99", "firstName": "Ola", "lastName": "N"})
        s = str(m)
        assert "Member" in s
        assert "M99" in s
        assert "Ola N" in s

    def test_role_str(self) -> None:
        """`Role.__str__` includes uid and name."""
        from spond.role import Role

        r = Role.model_validate({"id": "R1", "name": "Coach"})
        s = str(r)
        assert "R1" in s
        assert "Coach" in s

    def test_subgroup_str(self) -> None:
        """`Subgroup.__str__` includes uid and name."""
        from spond.subgroup import Subgroup

        sg = Subgroup.model_validate({"id": "SG1", "name": "Team A"})
        s = str(sg)
        assert "SG1" in s
        assert "Team A" in s


class TestGetPersonMethod:
    """Tests for `Spond.get_person()` — member/guardian lookup by various
    identifiers."""

    _MEMBER_WITH_GUARDIAN = {
        "id": "M1",
        "firstName": "Alice",
        "lastName": "Smith",
        "email": "alice@example.invalid",
        "profile": {"id": "PROF1"},
        "guardians": [
            {
                "id": "G1",
                "firstName": "Bob",
                "lastName": "Smith",
                "profile": {"id": "PROF_G1"},
            }
        ],
    }
    _GROUP_PAYLOAD = {
        "id": "GID1",
        "name": "Test Group",
        "members": [_MEMBER_WITH_GUARDIAN],
    }

    @pytest_asyncio.fixture
    async def spond_with_groups(self, mock_token):
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.groups = [Group.model_validate(self._GROUP_PAYLOAD)]
        return s

    @pytest.mark.asyncio
    async def test_get_person_by_uid(self, spond_with_groups) -> None:
        person = await spond_with_groups.get_person("M1")
        assert person.uid == "M1"

    @pytest.mark.asyncio
    async def test_get_person_by_email(self, spond_with_groups) -> None:
        person = await spond_with_groups.get_person("alice@example.invalid")
        assert person.uid == "M1"

    @pytest.mark.asyncio
    async def test_get_person_by_full_name(self, spond_with_groups) -> None:
        person = await spond_with_groups.get_person("Alice Smith")
        assert person.uid == "M1"

    @pytest.mark.asyncio
    async def test_get_person_by_profile_id(self, spond_with_groups) -> None:
        person = await spond_with_groups.get_person("PROF1")
        assert person.uid == "M1"

    @pytest.mark.asyncio
    async def test_get_person_returns_guardian(self, spond_with_groups) -> None:
        """When the uid matches a guardian (not a member), that guardian is
        returned."""
        from spond.person import Guardian

        person = await spond_with_groups.get_person("G1")
        assert isinstance(person, Guardian)
        assert person.uid == "G1"

    @pytest.mark.asyncio
    async def test_get_person_no_match_raises_keyerror(self, spond_with_groups) -> None:
        with pytest.raises(KeyError, match="scanned"):
            await spond_with_groups.get_person("NOBODY")

    @pytest.mark.asyncio
    async def test_get_person_no_groups_raises_keyerror(self, mock_token) -> None:
        """When the account has no groups, a distinct KeyError message is raised."""
        from unittest.mock import AsyncMock

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.groups = None
        # Mock get_groups to leave self.groups = None (simulates no groups)
        s.get_groups = AsyncMock(return_value=None)

        with pytest.raises(KeyError, match="no groups"):
            await s.get_person("ANYONE")

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_groups_http_path(self, mock_get, mock_token) -> None:
        """The HTTP-fetch path of `get_groups()` returns typed Group objects
        and caches them on `self.groups`."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        raw_groups = [
            {"id": "G1", "name": "Alpha"},
            {"id": "G2", "name": "Beta"},
        ]
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=raw_groups
        )

        groups = await s.get_groups()

        assert groups is not None
        assert len(groups) == 2
        assert all(isinstance(g, Group) for g in groups)
        assert groups[0].uid == "G1"
        assert groups[1].name == "Beta"
        assert s.groups is groups  # cache identity

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_groups_returns_none_when_api_returns_null(
        self, mock_get, mock_token
    ) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=None
        )

        groups = await s.get_groups()

        assert groups is None
        assert s.groups is None
