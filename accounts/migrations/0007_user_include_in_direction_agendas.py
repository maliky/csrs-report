from django.db import migrations, models
from django.utils import timezone


EXCLUSION_REASON = "Exclusion initiale du DG des agendas"


def exclude_dg_from_direction_agendas(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    HistoricalUser = apps.get_model("accounts", "HistoricalUser")
    HistoricalUserGroups = apps.get_model("accounts", "HistoricalUser_groups")
    HistoricalUserPermissions = apps.get_model(
        "accounts", "HistoricalUser_user_permissions"
    )
    GroupThrough = User.groups.through
    PermissionThrough = User.user_permissions.through
    database = schema_editor.connection.alias
    stamp = timezone.now()

    users = (
        User.objects.using(database)
        .filter(login_alias__iexact="dg", include_in_direction_agendas=True)
        .order_by("pk")
    )
    for user in users.iterator():
        User.objects.using(database).filter(
            pk=user.pk, include_in_direction_agendas=True
        ).update(include_in_direction_agendas=False)
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
            agenda_direction=user.agenda_direction,
            include_in_direction_agendas=False,
            history_date=stamp,
            history_change_reason=EXCLUSION_REASON,
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


def restore_dg_to_direction_agendas(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    HistoricalUser = apps.get_model("accounts", "HistoricalUser")
    HistoricalUserGroups = apps.get_model("accounts", "HistoricalUser_groups")
    HistoricalUserPermissions = apps.get_model(
        "accounts", "HistoricalUser_user_permissions"
    )
    database = schema_editor.connection.alias
    histories = list(
        HistoricalUser.objects.using(database)
        .filter(history_change_reason=EXCLUSION_REASON)
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
                pk=history.id, include_in_direction_agendas=False
            ).update(include_in_direction_agendas=True)

    history_ids = [history.history_id for history in histories]
    HistoricalUserGroups.objects.using(database).filter(
        history_id__in=history_ids
    ).delete()
    HistoricalUserPermissions.objects.using(database).filter(
        history_id__in=history_ids
    ).delete()
    HistoricalUser.objects.using(database).filter(history_id__in=history_ids).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_classify_agenda_directions")]

    operations = [
        migrations.AddField(
            model_name="historicaluser",
            name="include_in_direction_agendas",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Désactivez ce réglage pour le DG ou une personne dont les "
                    "tâches ne doivent figurer dans aucun agenda de direction."
                ),
                verbose_name="inclure dans les agendas de direction",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="include_in_direction_agendas",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Désactivez ce réglage pour le DG ou une personne dont les "
                    "tâches ne doivent figurer dans aucun agenda de direction."
                ),
                verbose_name="inclure dans les agendas de direction",
            ),
        ),
        migrations.RunPython(
            exclude_dg_from_direction_agendas,
            restore_dg_to_direction_agendas,
        ),
    ]
