import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F, Q


def move_parent_to_links(apps, schema_editor):
    OrganizationUnit = apps.get_model("work", "OrganizationUnit")
    OrganizationUnitLink = apps.get_model("work", "OrganizationUnitLink")
    for unit in OrganizationUnit.objects.all().iterator():
        OrganizationUnit.objects.filter(pk=unit.pk).update(
            short_name=unit.long_name
        )
        if unit.parent_id is not None:
            OrganizationUnitLink.objects.get_or_create(
                supervisor_service_id=unit.parent_id,
                collaborator_service_id=unit.pk,
            )


def restore_parent_from_links(apps, schema_editor):
    OrganizationUnit = apps.get_model("work", "OrganizationUnit")
    OrganizationUnitLink = apps.get_model("work", "OrganizationUnitLink")
    for link in OrganizationUnitLink.objects.order_by("pk").iterator():
        OrganizationUnit.objects.filter(
            pk=link.collaborator_service_id,
            parent_id__isnull=True,
        ).update(parent_id=link.supervisor_service_id)


class Migration(migrations.Migration):
    dependencies = [("work", "0009_repair_inconsistent_completed_tasks")]

    operations = [
        migrations.RenameField(
            model_name="organizationunit",
            old_name="name",
            new_name="long_name",
        ),
        migrations.AlterField(
            model_name="organizationunit",
            name="long_name",
            field=models.CharField(max_length=180, verbose_name="nom long"),
        ),
        migrations.AddField(
            model_name="organizationunit",
            name="short_name",
            field=models.CharField(default="", max_length=80, verbose_name="nom court"),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name="organizationunit",
            options={"ordering": ["long_name"]},
        ),
        migrations.CreateModel(
            name="OrganizationUnitLink",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "collaborator_service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="supervisor_links",
                        to="work.organizationunit",
                    ),
                ),
                (
                    "supervisor_service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="collaborator_links",
                        to="work.organizationunit",
                    ),
                ),
            ],
            options={
                "ordering": [
                    "supervisor_service__code",
                    "collaborator_service__code",
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=~Q(
                            supervisor_service=F("collaborator_service")
                        ),
                        name="organization_unit_link_distinct_services",
                    ),
                    models.UniqueConstraint(
                        fields=(
                            "supervisor_service",
                            "collaborator_service",
                        ),
                        name="unique_organization_unit_link",
                    ),
                ],
            },
        ),
        migrations.RunPython(
            move_parent_to_links,
            reverse_code=restore_parent_from_links,
        ),
        migrations.RemoveField(
            model_name="organizationunit",
            name="parent",
        ),
    ]
