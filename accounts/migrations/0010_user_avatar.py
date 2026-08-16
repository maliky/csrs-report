from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0009_user_terms_of_reference")]

    operations = [
        migrations.AddField(
            model_name="historicaluser",
            name="avatar",
            field=models.CharField(blank=True, default="", max_length=512, verbose_name="avatar"),
        ),
        migrations.AddField(
            model_name="user",
            name="avatar",
            field=models.CharField(blank=True, default="", max_length=512, verbose_name="avatar"),
        ),
    ]
