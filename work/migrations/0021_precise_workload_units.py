from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("work", "0020_reportingdeletionaudit")]

    operations = [
        migrations.AlterField(
            model_name="historicaltaskassignment",
            name="estimated_work_days",
            field=models.DecimalField(
                decimal_places=4,
                max_digits=10,
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
                decimal_places=4,
                max_digits=10,
                verbose_name="charge estimee en jours",
            ),
        ),
        migrations.AlterField(
            model_name="taskassignment",
            name="estimated_work_days",
            field=models.DecimalField(
                decimal_places=4,
                max_digits=10,
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
                decimal_places=4,
                max_digits=10,
                verbose_name="charge estimee en jours",
            ),
        ),
    ]
