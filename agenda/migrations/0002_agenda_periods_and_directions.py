from datetime import timedelta

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def preserve_legacy_agendas(apps, schema_editor):
    AgendaDraft = apps.get_model("agenda", "AgendaDraft")
    AgendaVersion = apps.get_model("agenda", "AgendaVersion")
    HistoricalAgendaDraft = apps.get_model("agenda", "HistoricalAgendaDraft")
    for draft in AgendaDraft.objects.order_by("pk").iterator():
        draft.period_end = draft.period_start + timedelta(days=6)
        draft.save(update_fields=["period_end"])
    for version in AgendaVersion.objects.order_by("pk").iterator():
        version.period_end = version.period_start + timedelta(days=6)
        version.agenda_direction = "legacy"
        version.save(update_fields=["period_end", "agenda_direction"])
    for history in HistoricalAgendaDraft.objects.all().iterator():
        history.period_end = history.period_start + timedelta(days=6)
        history.save(update_fields=["period_end"])


class Migration(migrations.Migration):

    dependencies = [
        ("agenda", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(
            old_name="WeeklyAgendaDraft",
            new_name="AgendaDraft",
        ),
        migrations.RenameModel(
            old_name="WeeklyAgendaVersion",
            new_name="AgendaVersion",
        ),
        migrations.RenameModel(
            old_name="HistoricalWeeklyAgendaDraft",
            new_name="HistoricalAgendaDraft",
        ),
        migrations.RenameField(
            model_name="agendadraft",
            old_name="week_start",
            new_name="period_start",
        ),
        migrations.RenameField(
            model_name="agendaversion",
            old_name="week_start",
            new_name="period_start",
        ),
        migrations.RenameField(
            model_name="historicalagendadraft",
            old_name="week_start",
            new_name="period_start",
        ),
        migrations.RemoveConstraint(
            model_name="agendaversion",
            name="unique_weekly_agenda_version",
        ),
        migrations.AlterField(
            model_name="agendadraft",
            name="period_start",
            field=models.DateField(verbose_name="début de période"),
        ),
        migrations.AlterField(
            model_name="agendaversion",
            name="period_start",
            field=models.DateField(verbose_name="début de période"),
        ),
        migrations.AlterField(
            model_name="historicalagendadraft",
            name="period_start",
            field=models.DateField(verbose_name="début de période"),
        ),
        migrations.AddField(
            model_name="agendadraft",
            name="period_end",
            field=models.DateField(null=True, verbose_name="fin de période"),
        ),
        migrations.AddField(
            model_name="agendaversion",
            name="period_end",
            field=models.DateField(null=True, verbose_name="fin de période"),
        ),
        migrations.AddField(
            model_name="historicalagendadraft",
            name="period_end",
            field=models.DateField(null=True, verbose_name="fin de période"),
        ),
        migrations.AddField(
            model_name="agendaversion",
            name="agenda_direction",
            field=models.CharField(
                choices=[
                    ("programs", "Direction des programmes"),
                    ("administration", "Direction administrative"),
                    ("legacy", "Agenda global historique"),
                ],
                max_length=16,
                null=True,
                verbose_name="direction",
            ),
        ),
        migrations.RunPython(preserve_legacy_agendas, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="agendadraft",
            name="period_end",
            field=models.DateField(verbose_name="fin de période"),
        ),
        migrations.AlterField(
            model_name="agendaversion",
            name="period_end",
            field=models.DateField(verbose_name="fin de période"),
        ),
        migrations.AlterField(
            model_name="historicalagendadraft",
            name="period_end",
            field=models.DateField(verbose_name="fin de période"),
        ),
        migrations.AlterField(
            model_name="agendaversion",
            name="agenda_direction",
            field=models.CharField(
                choices=[
                    ("programs", "Direction des programmes"),
                    ("administration", "Direction administrative"),
                    ("legacy", "Agenda global historique"),
                ],
                max_length=16,
                verbose_name="direction",
            ),
        ),
        migrations.AlterField(
            model_name="agendadraft",
            name="updated_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="updated_agenda_drafts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="agendaversion",
            name="generated_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="generated_agendas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterModelOptions(
            name="agendadraft",
            options={"ordering": ["-period_start", "-period_end"]},
        ),
        migrations.AlterModelOptions(
            name="agendaversion",
            options={
                "ordering": ["-period_start", "agenda_direction", "-version"]
            },
        ),
        migrations.AlterModelOptions(
            name="historicalagendadraft",
            options={
                "get_latest_by": ("history_date", "history_id"),
                "ordering": ("-history_date", "-history_id"),
                "verbose_name": "historical agenda draft",
                "verbose_name_plural": "historical agenda drafts",
            },
        ),
        migrations.AddConstraint(
            model_name="agendadraft",
            constraint=models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="agenda_draft_end_not_before_start",
            ),
        ),
        migrations.AddConstraint(
            model_name="agendadraft",
            constraint=models.UniqueConstraint(
                fields=("period_start", "period_end"),
                name="unique_agenda_draft_period",
            ),
        ),
        migrations.AddConstraint(
            model_name="agendaversion",
            constraint=models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="agenda_version_end_not_before_start",
            ),
        ),
        migrations.AddConstraint(
            model_name="agendaversion",
            constraint=models.UniqueConstraint(
                fields=(
                    "period_start",
                    "period_end",
                    "agenda_direction",
                    "version",
                ),
                name="unique_agenda_version",
            ),
        ),
    ]
