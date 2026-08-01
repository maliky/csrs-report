from django.db import migrations


PERMISSIONS = {
    "view_process_scope": "Consulter les dossiers d'un service",
    "work_mission_assistance": "Preparer les ordres de mission",
    "sign_mission_order": "Signer les ordres de mission",
    "work_mission_distribution": "Distribuer les ordres de mission",
    "work_mission_fleet": "Preparer les vehicules de mission",
    "export_process": "Exporter un dossier de processus",
}

ROLE_SPECS = (
    (
        "MISSION_ASSISTANCE",
        "Assistance des missions",
        "Prepare les projets d'ordre de mission dans une file de service.",
        "CSRS - Assistance missions",
        ("view_process_scope", "work_mission_assistance"),
    ),
    (
        "MISSION_SIGNER",
        "Signature des missions",
        "Decide et signe les ordres de mission dans le perimetre delegue.",
        "CSRS - Signature missions",
        ("view_process_scope", "sign_mission_order", "export_process"),
    ),
    (
        "MISSION_SECRETARIAT",
        "Distribution des missions",
        "Enregistre la distribution et l'archivage des ordres de mission.",
        "CSRS - Distribution missions",
        ("view_process_scope", "work_mission_distribution"),
    ),
    (
        "MISSION_FLEET",
        "Parc automobile des missions",
        "Confirme la preparation d'un vehicule demande pour une mission.",
        "CSRS - Parc missions",
        ("view_process_scope", "work_mission_fleet"),
    ),
)


def seed_process_roles(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ScopedRole = apps.get_model("access", "ScopedRole")
    content_type, _created = ContentType.objects.get_or_create(
        app_label="access", model="scopedrole"
    )
    permissions = {}
    for codename, name in PERMISSIONS.items():
        permission, _created = Permission.objects.update_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        permissions[codename] = permission
    for code, name, description, group_name, codenames in ROLE_SPECS:
        group, _created = Group.objects.get_or_create(name=group_name)
        group.permissions.add(*(permissions[codename] for codename in codenames))
        ScopedRole.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "active": True,
                "group": group,
            },
        )
    for code in ("UNIT_VIEWER", "UNIT_MANAGER"):
        role = ScopedRole.objects.filter(code=code).select_related("group").first()
        if role is not None:
            role.group.permissions.add(permissions["view_process_scope"])
    manager = ScopedRole.objects.filter(code="UNIT_MANAGER").select_related("group").first()
    if manager is not None:
        manager.group.permissions.add(permissions["export_process"])


def remove_process_roles(apps, schema_editor):
    ScopedRole = apps.get_model("access", "ScopedRole")
    Group = apps.get_model("auth", "Group")
    codes = [spec[0] for spec in ROLE_SPECS]
    group_names = [spec[3] for spec in ROLE_SPECS]
    ScopedRole.objects.filter(code__in=codes).delete()
    Group.objects.filter(name__in=group_names).delete()


class Migration(migrations.Migration):
    dependencies = [("access", "0002_seed_default_roles")]

    operations = [
        migrations.AlterModelOptions(
            name="scopedrole",
            options={
                "ordering": ["code"],
                "permissions": [
                    ("view_unit_scope", "Consulter les donnees d'un service"),
                    ("manage_unit_assignments", "Gerer les taches d'un service"),
                    ("correct_unit_progress", "Corriger la progression d'un service"),
                    ("review_unit_proposals", "Decider les propositions d'un service"),
                    ("export_unit_data", "Exporter les donnees d'un service"),
                    ("view_process_scope", "Consulter les dossiers d'un service"),
                    ("work_mission_assistance", "Preparer les ordres de mission"),
                    ("sign_mission_order", "Signer les ordres de mission"),
                    (
                        "work_mission_distribution",
                        "Distribuer les ordres de mission",
                    ),
                    ("work_mission_fleet", "Preparer les vehicules de mission"),
                    ("export_process", "Exporter un dossier de processus"),
                ],
            },
        ),
        migrations.RunPython(seed_process_roles, remove_process_roles),
    ]
