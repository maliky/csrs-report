from django.db import migrations
from django.utils import timezone


BASELINE_REASON = "Etat initial lors de l'activation de l'audit"


def populate_user_history(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    HistoricalUser = apps.get_model("accounts", "HistoricalUser")
    HistoricalUserGroups = apps.get_model("accounts", "HistoricalUser_groups")
    HistoricalUserPermissions = apps.get_model(
        "accounts", "HistoricalUser_user_permissions"
    )
    GroupThrough = User.groups.through
    PermissionThrough = User.user_permissions.through
    stamp = timezone.now()

    for user in User.objects.order_by("pk").iterator():
        history = HistoricalUser.objects.create(
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
            history_date=stamp,
            history_change_reason=BASELINE_REASON,
            history_type="+",
        )
        HistoricalUserGroups.objects.bulk_create(
            [
                HistoricalUserGroups(
                    id=relation.pk,
                    user_id=user.pk,
                    group_id=relation.group_id,
                    history_id=history.history_id,
                )
                for relation in GroupThrough.objects.filter(user_id=user.pk)
            ]
        )
        HistoricalUserPermissions.objects.bulk_create(
            [
                HistoricalUserPermissions(
                    id=relation.pk,
                    user_id=user.pk,
                    permission_id=relation.permission_id,
                    history_id=history.history_id,
                )
                for relation in PermissionThrough.objects.filter(user_id=user.pk)
            ]
        )


def remove_user_baseline(apps, schema_editor):
    HistoricalUser = apps.get_model("accounts", "HistoricalUser")
    HistoricalUserGroups = apps.get_model("accounts", "HistoricalUser_groups")
    HistoricalUserPermissions = apps.get_model(
        "accounts", "HistoricalUser_user_permissions"
    )
    history_ids = list(
        HistoricalUser.objects.filter(
            history_change_reason=BASELINE_REASON
        ).values_list("history_id", flat=True)
    )
    HistoricalUserGroups.objects.filter(history_id__in=history_ids).delete()
    HistoricalUserPermissions.objects.filter(history_id__in=history_ids).delete()
    HistoricalUser.objects.filter(history_id__in=history_ids).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_historicaluser_historicaluser_groups_and_more")]

    operations = [
        migrations.RunPython(populate_user_history, remove_user_baseline),
    ]
