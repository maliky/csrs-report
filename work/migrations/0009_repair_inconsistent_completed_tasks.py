from django.db import migrations


def repair_inconsistent_completed_tasks(apps, schema_editor):
    TaskAssignment = apps.get_model("work", "TaskAssignment")
    ProgressEntry = apps.get_model("work", "ProgressEntry")
    ProgressSeriesCache = apps.get_model("work", "ProgressSeriesCache")
    TaskActivity = apps.get_model("work", "TaskActivity")

    repaired_ids = []
    for assignment in TaskAssignment.objects.filter(status="completed").iterator():
        latest = (
            ProgressEntry.objects.filter(assignment_id=assignment.pk)
            .order_by("-entry_date", "-updated_at", "-pk")
            .first()
        )
        percentage = latest.percentage if latest is not None else 0
        if percentage >= 100:
            continue
        TaskAssignment.objects.filter(pk=assignment.pk).update(
            status="active",
            completed_at=None,
        )
        TaskActivity.objects.create(
            assignment_id=assignment.pk,
            actor_id=(
                latest.author_id if latest is not None else assignment.manager_id
            ),
            kind="reopened",
            message=(
                "Tache remise en cours automatiquement : sa derniere progression "
                f"connue est de {percentage} %."
            ),
            percentage_before=100,
            percentage_after=percentage,
            details={"reason": "inconsistent_completed_progress"},
        )
        repaired_ids.append(assignment.pk)

    if repaired_ids:
        ProgressSeriesCache.objects.filter(
            assignment_id__in=repaired_ids
        ).delete()


class Migration(migrations.Migration):
    dependencies = [("work", "0008_progressseriescache")]

    operations = [
        migrations.RunPython(
            repair_inconsistent_completed_tasks,
            reverse_code=migrations.RunPython.noop,
        )
    ]
