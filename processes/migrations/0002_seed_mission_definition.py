from django.db import migrations


def seed_definition(apps, schema_editor):
    ProcessDefinition = apps.get_model("processes", "ProcessDefinition")
    ProcessDefinition.objects.update_or_create(
        code="MISSION_ORDER",
        version=1,
        defaults={"name": "Ordre de mission", "active": True},
    )


def remove_definition(apps, schema_editor):
    ProcessDefinition = apps.get_model("processes", "ProcessDefinition")
    ProcessDefinition.objects.filter(code="MISSION_ORDER", version=1).delete()


class Migration(migrations.Migration):
    dependencies = [("processes", "0001_initial")]
    operations = [migrations.RunPython(seed_definition, remove_definition)]
