from decimal import Decimal, ROUND_HALF_UP

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def normalize_workloads_and_clear_caches(apps, schema_editor):
    """Round persisted workloads to one decimal before reducing database scale."""
    quantum = Decimal("0.1")
    for model_name in (
        "TaskAssignment",
        "TaskProposal",
        "HistoricalTaskAssignment",
        "HistoricalTaskProposal",
    ):
        model = apps.get_model("work", model_name)
        for item in model.objects.all().iterator():
            normalized = item.estimated_work_days.quantize(
                quantum, rounding=ROUND_HALF_UP
            )
            if normalized != item.estimated_work_days:
                model.objects.filter(pk=item.pk).update(
                    estimated_work_days=normalized
                )
    apps.get_model("work", "ProgressSeriesCache").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("work", "0011_compact_service_short_names")]

    operations = [
        migrations.RemoveConstraint(
            model_name="taskcodesequence",
            name="one_task_sequence_per_action_year",
        ),
        migrations.AlterField(
            model_name="taskcodesequence",
            name="action",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="code_sequences",
                to="work.institutionalaction",
            ),
        ),
        migrations.AddConstraint(
            model_name="taskcodesequence",
            constraint=models.UniqueConstraint(
                condition=models.Q(("action__isnull", False)),
                fields=("action", "year"),
                name="one_task_sequence_per_action_year",
            ),
        ),
        migrations.AddConstraint(
            model_name="taskcodesequence",
            constraint=models.UniqueConstraint(
                condition=models.Q(("action__isnull", True)),
                fields=("year",),
                name="one_unclassified_task_sequence_per_year",
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="action",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tasks",
                to="work.institutionalaction",
            ),
        ),
        migrations.AlterField(
            model_name="taskproposal",
            name="action",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="work.institutionalaction",
            ),
        ),
        migrations.RunPython(
            normalize_workloads_and_clear_caches,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="historicaltaskassignment",
            name="estimated_work_days",
            field=models.DecimalField(
                decimal_places=1,
                max_digits=7,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.1"))
                ],
                verbose_name="charge estimee en jours",
            ),
        ),
        migrations.AlterField(
            model_name="historicaltaskproposal",
            name="estimated_work_days",
            field=models.DecimalField(
                decimal_places=1,
                max_digits=7,
                verbose_name="charge estimee en jours",
            ),
        ),
        migrations.AlterField(
            model_name="taskassignment",
            name="estimated_work_days",
            field=models.DecimalField(
                decimal_places=1,
                max_digits=7,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.1"))
                ],
                verbose_name="charge estimee en jours",
            ),
        ),
        migrations.AlterField(
            model_name="taskproposal",
            name="estimated_work_days",
            field=models.DecimalField(
                decimal_places=1,
                max_digits=7,
                verbose_name="charge estimee en jours",
            ),
        ),
    ]
