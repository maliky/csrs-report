from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("access", "0004_agenda_permissions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RoleSimulation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("administrator_label", models.CharField(max_length=255)),
                ("target_label", models.CharField(max_length=255)),
                ("role_snapshot", models.JSONField(default=list)),
                ("unit_snapshot", models.JSONField(default=list)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("end_reason", models.CharField(blank=True, max_length=80)),
                ("administrator", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="started_role_simulations", to=settings.AUTH_USER_MODEL)),
                ("target", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="received_role_simulations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-started_at", "-pk"]},
        ),
        migrations.CreateModel(
            name="RoleSimulationAction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("method", models.CharField(max_length=10)),
                ("path", models.CharField(max_length=512)),
                ("status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                ("simulation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="actions", to="access.rolesimulation")),
            ],
            options={"ordering": ["-occurred_at", "-pk"]},
        ),
    ]
