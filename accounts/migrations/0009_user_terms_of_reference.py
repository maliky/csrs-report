from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_user_password_change_required")]

    operations = [
        migrations.AddField(
            model_name="historicaluser",
            name="terms_of_reference",
            field=models.TextField(blank=True, default="", verbose_name="cahier des charges"),
        ),
        migrations.AddField(
            model_name="user",
            name="terms_of_reference",
            field=models.TextField(blank=True, default="", verbose_name="cahier des charges"),
        ),
    ]
