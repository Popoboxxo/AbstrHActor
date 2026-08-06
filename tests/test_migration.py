"""Test Abstractor config entry migration (REQ-NFA-004)."""

from unittest.mock import Mock

from custom_components.abstractor import async_migrate_entry
from custom_components.abstractor.const import CONFIG_ENTRY_VERSION


async def test_current_version_entry_needs_no_migration() -> None:
    """An entry already on the current version passes through untouched."""
    entry = Mock(entry_id="entry-1", version=CONFIG_ENTRY_VERSION)

    result = await async_migrate_entry(Mock(), entry)

    assert result is True


async def test_future_version_entry_is_refused() -> None:
    """An entry from a newer integration version must not be guessed at."""
    entry = Mock(entry_id="entry-1", version=CONFIG_ENTRY_VERSION + 1)

    result = await async_migrate_entry(Mock(), entry)

    assert result is False
