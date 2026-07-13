from datetime import date

from django.db import migrations


def add_holiday(apps, schema_editor):
    WorkCalendar = apps.get_model("work", "WorkCalendar")
    WorkCalendarDay = apps.get_model("work", "WorkCalendarDay")
    calendar = WorkCalendar.objects.filter(is_default=True).first()
    if calendar is not None:
        WorkCalendarDay.objects.get_or_create(
            calendar=calendar,
            day=date(2026, 3, 16),
            defaults={
                "name": "Lendemain de la Nuit du Destin",
                "is_working_day": False,
            },
        )


def remove_holiday(apps, schema_editor):
    apps.get_model("work", "WorkCalendarDay").objects.filter(
        day=date(2026, 3, 16), name="Lendemain de la Nuit du Destin"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("work", "0006_delete_taskcomment")]
    operations = [migrations.RunPython(add_holiday, remove_holiday)]
