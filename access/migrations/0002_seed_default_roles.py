from django.db import migrations


ROLE_SPECS = (
    (
        "UNIT_VIEWER",
        "Lecture d'un service",
        "Consulter l'activite et les historiques dans un perimetre organisationnel.",
        "CSRS - Lecture service",
        ("view_unit_scope", "export_unit_data"),
    ),
    (
        "UNIT_MANAGER",
        "Gestion d'un service",
        "Gerer les taches, progressions et propositions dans un perimetre.",
        "CSRS - Gestion service",
        (
            "view_unit_scope",
            "manage_unit_assignments",
            "correct_unit_progress",
            "review_unit_proposals",
            "export_unit_data",
        ),
    ),
)


def seed_roles(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ScopedRole = apps.get_model("access", "ScopedRole")

    content_type, _created = ContentType.objects.get_or_create(
        app_label="access", model="scopedrole"
    )
    permission_names = {
        "view_unit_scope": "Consulter les donnees d'un service",
        "manage_unit_assignments": "Gerer les taches d'un service",
        "correct_unit_progress": "Corriger la progression d'un service",
        "review_unit_proposals": "Decider les propositions d'un service",
        "export_unit_data": "Exporter les donnees d'un service",
    }
    permissions = {}
    for codename, name in permission_names.items():
        permission, _created = Permission.objects.update_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        permissions[codename] = permission

    for code, name, description, group_name, codenames in ROLE_SPECS:
        group, _created = Group.objects.get_or_create(name=group_name)
        group.permissions.set([permissions[codename] for codename in codenames])
        ScopedRole.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "active": True,
                "group": group,
            },
        )


def remove_roles(apps, schema_editor):
    ScopedRole = apps.get_model("access", "ScopedRole")
    Group = apps.get_model("auth", "Group")
    codes = [spec[0] for spec in ROLE_SPECS]
    groups = [spec[3] for spec in ROLE_SPECS]
    ScopedRole.objects.filter(code__in=codes).delete()
    Group.objects.filter(name__in=groups).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("access", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_roles, reverse_code=remove_roles),
    ]
