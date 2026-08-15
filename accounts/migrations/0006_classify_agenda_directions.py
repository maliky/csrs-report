from django.db import migrations
from django.utils import timezone


CLASSIFICATION_REASON = "Classement initial selon l'unite principale"
PROGRAM_KINDS = {"programme", "laboratory", "station"}
ADMINISTRATION_KINDS = {"cell", "service"}


def _classify(unit, parent_by_unit_id, unit_by_id):
    ancestors = set()
    current_id = unit.pk
    while current_id is not None and current_id not in ancestors:
        ancestors.add(current_id)
        current_id = parent_by_unit_id.get(current_id)

    ancestor_codes = {
        unit_by_id[unit_id].code.strip().upper()
        for unit_id in ancestors
        if unit_id in unit_by_id
    }
    if "DP" in ancestor_codes:
        return "programs"
    if "DAF" in ancestor_codes:
        return "administration"

    kind = unit.kind.strip().lower()
    if kind in PROGRAM_KINDS:
        return "programs"
    if kind in ADMINISTRATION_KINDS:
        return "administration"
    return ""


def classify_agenda_directions(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    HistoricalUser = apps.get_model("accounts", "HistoricalUser")
    HistoricalUserGroups = apps.get_model("accounts", "HistoricalUser_groups")
    HistoricalUserPermissions = apps.get_model(
        "accounts", "HistoricalUser_user_permissions"
    )
    OrganizationUnit = apps.get_model("work", "OrganizationUnit")
    OrganizationUnitLink = apps.get_model("work", "OrganizationUnitLink")
    OrganizationMembership = apps.get_model("work", "OrganizationMembership")
    GroupThrough = User.groups.through
    PermissionThrough = User.user_permissions.through
    database = schema_editor.connection.alias

    unit_by_id = {
        unit.pk: unit
        for unit in OrganizationUnit.objects.using(database).order_by("pk").iterator()
    }
    parent_by_unit_id = dict(
        OrganizationUnitLink.objects.using(database).values_list(
            "collaborator_service_id", "supervisor_service_id"
        )
    )
    primary_unit_by_user_id = dict(
        OrganizationMembership.objects.using(database)
        .filter(is_primary=True, end_date__isnull=True)
        .values_list("user_id", "unit_id")
    )
    stamp = timezone.now()

    users = User.objects.using(database).filter(agenda_direction="").order_by("pk")
    for user in users.iterator():
        unit = unit_by_id.get(primary_unit_by_user_id.get(user.pk))
        if unit is None:
            continue
        direction = _classify(unit, parent_by_unit_id, unit_by_id)
        if not direction:
            continue

        User.objects.using(database).filter(pk=user.pk, agenda_direction="").update(
            agenda_direction=direction
        )
        history = HistoricalUser.objects.using(database).create(
            id=user.pk,
            is_superuser=user.is_superuser,
            first_name=user.first_name,
            last_name=user.last_name,
            is_staff=user.is_staff,
            is_active=user.is_active,
            date_joined=user.date_joined,
            email=user.email,
            login_alias=user.login_alias,
            position=user.position,
            phone=user.phone,
            phone_verified_at=user.phone_verified_at,
            is_it_admin=user.is_it_admin,
            agenda_direction=direction,
            history_date=stamp,
            history_change_reason=CLASSIFICATION_REASON,
            history_type="~",
        )
        HistoricalUserGroups.objects.using(database).bulk_create(
            [
                HistoricalUserGroups(
                    id=relation.pk,
                    user_id=user.pk,
                    group_id=relation.group_id,
                    history_id=history.history_id,
                )
                for relation in GroupThrough.objects.using(database).filter(
                    user_id=user.pk
                )
            ]
        )
        HistoricalUserPermissions.objects.using(database).bulk_create(
            [
                HistoricalUserPermissions(
                    id=relation.pk,
                    user_id=user.pk,
                    permission_id=relation.permission_id,
                    history_id=history.history_id,
                )
                for relation in PermissionThrough.objects.using(database).filter(
                    user_id=user.pk
                )
            ]
        )


def remove_initial_agenda_classification(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    HistoricalUser = apps.get_model("accounts", "HistoricalUser")
    HistoricalUserGroups = apps.get_model("accounts", "HistoricalUser_groups")
    HistoricalUserPermissions = apps.get_model(
        "accounts", "HistoricalUser_user_permissions"
    )
    database = schema_editor.connection.alias
    histories = list(
        HistoricalUser.objects.using(database)
        .filter(history_change_reason=CLASSIFICATION_REASON)
        .order_by("history_id")
    )
    for history in histories:
        newer_history_exists = (
            HistoricalUser.objects.using(database)
            .filter(id=history.id, history_id__gt=history.history_id)
            .exists()
        )
        if not newer_history_exists:
            User.objects.using(database).filter(
                pk=history.id, agenda_direction=history.agenda_direction
            ).update(agenda_direction="")

    history_ids = [history.history_id for history in histories]
    HistoricalUserGroups.objects.using(database).filter(
        history_id__in=history_ids
    ).delete()
    HistoricalUserPermissions.objects.using(database).filter(
        history_id__in=history_ids
    ).delete()
    HistoricalUser.objects.using(database).filter(history_id__in=history_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_historicaluser_agenda_direction_and_more"),
        ("work", "0019_populate_organization_history"),
    ]

    operations = [
        migrations.RunPython(
            classify_agenda_directions,
            remove_initial_agenda_classification,
        )
    ]
