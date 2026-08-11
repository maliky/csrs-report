from django.db import migrations
from django.utils import timezone


BASELINE_REASON = "Etat initial lors de l'activation de l'audit"


def populate_organization_history(apps, schema_editor):
    OrganizationUnit = apps.get_model("work", "OrganizationUnit")
    OrganizationUnitLink = apps.get_model("work", "OrganizationUnitLink")
    HistoricalOrganizationUnit = apps.get_model(
        "work", "HistoricalOrganizationUnit"
    )
    HistoricalOrganizationUnitLink = apps.get_model(
        "work", "HistoricalOrganizationUnitLink"
    )
    stamp = timezone.now()

    HistoricalOrganizationUnit.objects.bulk_create(
        [
            HistoricalOrganizationUnit(
                id=unit.pk,
                long_name=unit.long_name,
                short_name=unit.short_name,
                code=unit.code,
                kind=unit.kind,
                display_order=unit.display_order,
                active=unit.active,
                history_date=stamp,
                history_change_reason=BASELINE_REASON,
                history_type="+",
            )
            for unit in OrganizationUnit.objects.order_by("pk").iterator()
        ]
    )
    HistoricalOrganizationUnitLink.objects.bulk_create(
        [
            HistoricalOrganizationUnitLink(
                id=link.pk,
                supervisor_service_id=link.supervisor_service_id,
                collaborator_service_id=link.collaborator_service_id,
                history_date=stamp,
                history_change_reason=BASELINE_REASON,
                history_type="+",
            )
            for link in OrganizationUnitLink.objects.order_by("pk").iterator()
        ]
    )


def remove_organization_baseline(apps, schema_editor):
    apps.get_model("work", "HistoricalOrganizationUnitLink").objects.filter(
        history_change_reason=BASELINE_REASON
    ).delete()
    apps.get_model("work", "HistoricalOrganizationUnit").objects.filter(
        history_change_reason=BASELINE_REASON
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("work", "0018_historicalorganizationunit_and_more")]

    operations = [
        migrations.RunPython(
            populate_organization_history,
            remove_organization_baseline,
        )
    ]
