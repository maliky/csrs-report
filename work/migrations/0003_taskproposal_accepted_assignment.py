from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("work", "0002_notificationdelivery")]

    operations = [
        migrations.AddField(
            model_name="historicaltaskproposal",
            name="accepted_assignment",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="work.taskassignment",
            ),
        ),
        migrations.AddField(
            model_name="taskproposal",
            name="accepted_assignment",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="source_proposal",
                to="work.taskassignment",
            ),
        ),
    ]
