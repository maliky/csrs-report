from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("work", "0003_taskproposal_accepted_assignment")]

    operations = [
        migrations.AlterField(
            model_name="historicaltaskproposal",
            name="status",
            field=models.CharField(
                choices=[
                    ("submitted", "Soumise"),
                    ("accepted", "Validee"),
                    ("rejected", "Rejetee"),
                ],
                default="submitted",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="taskproposal",
            name="status",
            field=models.CharField(
                choices=[
                    ("submitted", "Soumise"),
                    ("accepted", "Validee"),
                    ("rejected", "Rejetee"),
                ],
                default="submitted",
                max_length=16,
            ),
        ),
    ]
