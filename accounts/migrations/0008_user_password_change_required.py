from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_user_include_in_direction_agendas")]

    operations = [
        migrations.AddField(
            model_name="historicaluser",
            name="password_change_required",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Impose le remplacement du mot de passe temporaire lors de la "
                    "prochaine connexion."
                ),
                verbose_name="changement de mot de passe obligatoire",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="password_change_required",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Impose le remplacement du mot de passe temporaire lors de la "
                    "prochaine connexion."
                ),
                verbose_name="changement de mot de passe obligatoire",
            ),
        ),
    ]
