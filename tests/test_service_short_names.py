"""Data migration coverage for compact organization service labels."""

from importlib import import_module

import pytest
from django.apps import apps

from work.models import OrganizationUnit


@pytest.mark.django_db
def test_short_name_migration_updates_known_codes_and_preserves_unknown_units() -> None:
    daf = OrganizationUnit.objects.create(
        code="DAF",
        short_name="Direction administrative et financiere",
        long_name="Direction administrative et financiere",
    )
    custom = OrganizationUnit.objects.create(
        code="CUSTOM",
        short_name="Nom local",
        long_name="Service local",
    )
    migration = import_module("work.migrations.0011_compact_service_short_names")

    migration.set_compact_short_names(apps, None)

    daf.refresh_from_db()
    custom.refresh_from_db()
    assert daf.short_name == "daf"
    assert daf.long_name == "Direction administrative et financiere"
    assert custom.short_name == "Nom local"

    migration.restore_long_names(apps, None)
    daf.refresh_from_db()
    assert daf.short_name == daf.long_name
