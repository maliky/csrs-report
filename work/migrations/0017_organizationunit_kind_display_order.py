from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("work", "0016_historicaltaskassignment_revision_and_more")]

    operations = [
        migrations.AddField(
            model_name="organizationunit",
            name="display_order",
            field=models.PositiveIntegerField(default=0, verbose_name="ordre d'affichage"),
        ),
        migrations.AddField(
            model_name="organizationunit",
            name="kind",
            field=models.CharField(default="unit", max_length=32, verbose_name="type d'unite"),
        ),
        migrations.AlterModelOptions(
            name="organizationunit",
            options={"ordering": ["display_order", "long_name"]},
        ),
    ]
