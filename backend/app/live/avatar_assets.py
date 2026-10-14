"""Resolve the small, reviewed set of bundled avatar assets."""

DEFAULT_AVATAR_ASSET_ID = "arcana-local"
LEGACY_AVATAR_ASSET_ID = "avatar-sample-b"


def effective_avatar_asset_id(asset_id: str | None, character_name: str) -> str | None:
    """Upgrade only an uncustomized Kira at read time; never mutate saved settings."""
    if asset_id == LEGACY_AVATAR_ASSET_ID and character_name.casefold() == "kira":
        return DEFAULT_AVATAR_ASSET_ID
    if asset_id:
        return asset_id
    return DEFAULT_AVATAR_ASSET_ID if character_name.casefold() == "kira" else None
