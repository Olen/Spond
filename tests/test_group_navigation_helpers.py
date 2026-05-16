"""Tests for the new Group navigation helpers and typed `FieldDef`.

Adapted from the patterns in elliot-100/Spond-classes
(`member_by_uid`, `role_by_uid`, `subgroup_by_uid`,
`members_by_subgroup`, `members_by_role`) — they encode common
"membership graph navigation" queries that every caller would
otherwise write inline.
"""

from __future__ import annotations

from spond.field_def import FieldDef
from spond.group import Group
from spond.role import Role
from spond.subgroup import Subgroup

_GROUP_PAYLOAD = {
    "id": "GID",
    "name": "Test Group",
    "members": [
        {
            "id": "M1",
            "firstName": "Alice",
            "lastName": "A",
            "roles": ["R1"],
            "subGroups": ["S1", "S2"],
        },
        {
            "id": "M2",
            "firstName": "Bob",
            "lastName": "B",
            "roles": ["R2"],
            "subGroups": ["S1"],
        },
        {
            "id": "M3",
            "firstName": "Carol",
            "lastName": "C",
            "roles": [],
            "subGroups": ["S2"],
        },
    ],
    "roles": [
        {"id": "R1", "name": "Coach"},
        {"id": "R2", "name": "Treasurer"},
    ],
    "subGroups": [
        {"id": "S1", "name": "Team A"},
        {"id": "S2", "name": "Team B"},
    ],
    "fieldDefs": [
        {"id": "F1", "name": "Shirt size"},
        {"id": "F2", "name": "Emergency contact"},
    ],
}


class TestRoleByUid:
    def test_returns_role_when_present(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        r = g.role_by_uid("R1")
        assert isinstance(r, Role)
        assert r.name == "Coach"

    def test_returns_none_when_missing(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        assert g.role_by_uid("NOSUCH") is None

    def test_returns_none_on_empty_group(self) -> None:
        g = Group.model_validate({"id": "X", "name": "Empty"})
        assert g.role_by_uid("ANY") is None


class TestSubgroupByUid:
    def test_returns_subgroup_when_present(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        sg = g.subgroup_by_uid("S2")
        assert isinstance(sg, Subgroup)
        assert sg.name == "Team B"

    def test_returns_none_when_missing(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        assert g.subgroup_by_uid("NOSUCH") is None


class TestMemberByUid:
    def test_returns_member_when_present(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        m = g.member_by_uid("M2")
        assert m is not None
        assert m.full_name == "Bob B"

    def test_returns_none_when_missing(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        assert g.member_by_uid("NOSUCH") is None

    def test_matches_find_member_uid_shape(self) -> None:
        """`member_by_uid(x)` is documented as a shorthand for
        `find_member(uid=x)` — verify they return the same result."""
        g = Group.model_validate(_GROUP_PAYLOAD)
        assert g.member_by_uid("M1") is g.find_member(uid="M1")


class TestMembersBySubgroup:
    def test_filters_by_subgroup_object(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        s1 = g.subgroup_by_uid("S1")
        members = g.members_by_subgroup(s1)
        assert [m.uid for m in members] == ["M1", "M2"]

    def test_filters_by_subgroup_uid_string(self) -> None:
        """Either a Subgroup instance OR its uid string works — for
        callers who only have a uid (e.g. from `member.subgroup_uids`)."""
        g = Group.model_validate(_GROUP_PAYLOAD)
        members = g.members_by_subgroup("S2")
        assert [m.uid for m in members] == ["M1", "M3"]

    def test_empty_when_no_members_match(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        assert g.members_by_subgroup("UNKNOWN") == []

    def test_empty_when_no_subgroups_at_all(self) -> None:
        g = Group.model_validate({"id": "X", "name": "Empty"})
        assert g.members_by_subgroup("ANY") == []


class TestMembersByRole:
    def test_filters_by_role_object(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        coach = g.role_by_uid("R1")
        coaches = g.members_by_role(coach)
        assert [m.uid for m in coaches] == ["M1"]

    def test_filters_by_role_uid_string(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        members = g.members_by_role("R2")
        assert [m.uid for m in members] == ["M2"]

    def test_empty_when_no_members_match(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        assert g.members_by_role("UNKNOWN") == []


class TestFieldDef:
    def test_field_defs_materialise_as_typed(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        assert len(g.field_defs) == 2
        assert all(isinstance(fd, FieldDef) for fd in g.field_defs)
        assert g.field_defs[0].uid == "F1"
        assert g.field_defs[0].name == "Shirt size"
        assert g.field_defs[1].name == "Emergency contact"

    def test_empty_when_no_field_defs(self) -> None:
        g = Group.model_validate({"id": "X", "name": "No FDs"})
        assert g.field_defs == []

    def test_field_def_str_contains_uid_and_name(self) -> None:
        fd = FieldDef.model_validate({"id": "F1", "name": "Shirt size"})
        s = str(fd)
        assert "F1" in s
        assert "Shirt size" in s

    def test_field_def_natural_key_uid_based(self) -> None:
        a = FieldDef.model_validate({"id": "F1", "name": "Different"})
        b = FieldDef.model_validate({"id": "F1", "name": "Names"})
        assert a == b  # same uid → equal
        assert hash(a) == hash(b)

    def test_field_def_minimal_only_uid_required(self) -> None:
        """Resilience: only `id` required; `name` defaults to empty."""
        fd = FieldDef.model_validate({"id": "F1"})
        assert fd.uid == "F1"
        assert fd.name == ""

    def test_field_defs_pair_with_member_custom_fields(self) -> None:
        """The motivating use case: render label/value pairs by joining
        `group.field_defs` (label) with `member.custom_fields` (value)."""
        g = Group.model_validate(
            {
                **_GROUP_PAYLOAD,
                "members": [
                    {
                        "id": "M1",
                        "firstName": "Alice",
                        "lastName": "A",
                        "fields": {"F1": "Medium", "F2": "555-1234"},
                    }
                ],
            }
        )
        member = g.member_by_uid("M1")
        rendered = {fd.name: member.custom_fields.get(fd.uid) for fd in g.field_defs}
        assert rendered == {"Shirt size": "Medium", "Emergency contact": "555-1234"}


class TestNavigationHelpersCompositeFlow:
    """End-to-end: walk subgroups → list members → check their roles.
    The motivating use case for the helpers landing together."""

    def test_walk_subgroups_with_role_lookup(self) -> None:
        g = Group.model_validate(_GROUP_PAYLOAD)
        results: dict[str, list[str]] = {}
        for sg in g.subgroups:
            for m in g.members_by_subgroup(sg):
                # For each member of this subgroup, what role names do they hold?
                role_names = [
                    r.name
                    for r_uid in m.role_uids
                    if (r := g.role_by_uid(r_uid)) is not None
                ]
                results.setdefault(sg.name, []).append(f"{m.full_name}: {role_names}")
        # Team A (S1) has Alice (Coach) and Bob (Treasurer)
        assert "Team A" in results
        assert any(
            "Alice A" in entry and "Coach" in entry for entry in results["Team A"]
        )
        assert any(
            "Bob B" in entry and "Treasurer" in entry for entry in results["Team A"]
        )
        # Team B (S2) has Alice (Coach) and Carol (no roles)
        assert "Team B" in results
        assert any("Carol C" in entry and "[]" in entry for entry in results["Team B"])
