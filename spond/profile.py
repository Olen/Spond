"""Typed `Profile` model for the authenticated user's account.

`Profile` represents the rich user record returned by `Spond.get_profile()`.
It carries account-level details (email, phone, timezone, locale,
preferences) — strictly more than the `profile` dict referenced inside
Members and Guardians, which is a sparse subset.
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field

from ._compat import DictCompatModel, LenientDate


class Profile(DictCompatModel):
    """The authenticated user's full account profile.

    Returned by `Spond.get_profile()`. Not the same as the `profile` dict
    nested inside Member/Guardian — that's a sparse reference shape.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    uid: str = Field(alias="id")
    # Defaulted to "" so a missing field on the authenticated user's
    # profile response can't crash `get_profile()` outright.
    first_name: str = Field(default="", alias="firstName")
    last_name: str = Field(default="", alias="lastName")
    primary_email: str | None = Field(default=None, alias="primaryEmail")
    phone_number: str | None = Field(default=None, alias="phoneNumber")
    formatted_phone_number: str | None = Field(
        default=None, alias="formattedPhoneNumber"
    )
    image_url: str | None = Field(default=None, alias="imageUrl")
    date_of_birth: LenientDate = Field(default=None, alias="dateOfBirth")
    gender: str | None = None
    locale: str | None = None
    country_code: str | None = Field(default=None, alias="countryCode")
    timezone: str | None = None
    contact_method: str | None = Field(default=None, alias="contactMethod")
    deleted: bool = False
    internal: bool = False
    dummy: bool = False
    unable_to_reach: bool = Field(default=False, alias="unableToReach")
    preferences: dict[str, Any] | None = None
    """Nested preference settings (push, email, locale, etc.). Unmodelled."""

    # Fields observed in the live API but absent from the original Spond SDK's
    # reverse-engineered shape. All optional so a future field-drop doesn't
    # crash get_profile().
    tos_version: int | None = Field(default=None, alias="tosVersion")
    """Version of the Spond Terms of Service the user has accepted."""
    contact: bool = False
    """Whether the user can be listed as a group contact person."""

    # Internal/analytics fields — preserved for completeness but not part of
    # the user-meaningful API surface. Treat as opaque.
    tracking_id: str | None = Field(default=None, alias="trackingId")
    """Internal analytics identifier. Opaque; do not rely on the shape."""
    unsubscribe_code: str | None = Field(default=None, alias="unsubscribeCode")
    """Email-unsubscribe token. Internal."""

    @property
    def full_name(self) -> str:
        """Convenience: non-empty `first_name` and `last_name` joined by a
        single space. Returns `""` when both are missing (avoids the bare
        `" "` artefact when name fields default to empty strings)."""
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    def __str__(self) -> str:
        return f"Profile(uid={self.uid!r}, name={self.full_name!r})"
