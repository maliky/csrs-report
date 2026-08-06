from django.db import migrations


PERMISSIONS = {
    "manage_visitor_visits": "Enregistrer les visites",
    "manage_staff_availability": "Gérer les indisponibilités",
    "prepare_weekly_agenda": "Préparer l'agenda hebdomadaire",
    "view_weekly_agenda": "Consulter l'agenda hebdomadaire",
}

ROLE_SPECS = (
    (
        "AGENDA_SECRETARIAT",
        "Secrétariat de la Direction générale",
        "Enregistre les visiteurs et prépare les versions de l’agenda hebdomadaire.",
        "CSRS - Secrétariat agenda",
        ("manage_visitor_visits", "prepare_weekly_agenda", "view_weekly_agenda"),
    ),
    (
        "AGENDA_HR",
        "Ressources humaines — indisponibilités",
        "Enregistre les congés, absences et missions sans consulter le rapport complet.",
        "CSRS - RH agenda",
        ("manage_staff_availability",),
    ),
    (
        "AGENDA_VIEWER",
        "Lecture de l’agenda hebdomadaire",
        "Consulte et réimprime les versions générées.",
        "CSRS - Lecture agenda",
        ("view_weekly_agenda",),
    ),
)


def seed_agenda_roles(apps, schema_editor):
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


def remove_agenda_roles(apps, schema_editor):
    ScopedRole = apps.get_model("access", "ScopedRole")
    Group = apps.get_model("auth", "Group")
    ScopedRole.objects.filter(code__in=[spec[0] for spec in ROLE_SPECS]).delete()
    Group.objects.filter(name__in=[spec[3] for spec in ROLE_SPECS]).delete()


class Migration(migrations.Migration):
    dependencies = [("access", "0003_process_permissions")]
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
                    ("work_mission_distribution", "Distribuer les ordres de mission"),
                    ("work_mission_fleet", "Preparer les vehicules de mission"),
                    ("export_process", "Exporter un dossier de processus"),
                    ("manage_visitor_visits", "Enregistrer les visites"),
                    ("manage_staff_availability", "Gérer les indisponibilités"),
                    ("prepare_weekly_agenda", "Préparer l'agenda hebdomadaire"),
                    ("view_weekly_agenda", "Consulter l'agenda hebdomadaire"),
                ],
            },
        ),
        migrations.RunPython(seed_agenda_roles, remove_agenda_roles),
    ]
