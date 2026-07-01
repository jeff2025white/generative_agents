from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("translator", "0006_simpendingaction_simstate"),
    ]

    operations = [
        migrations.AddField(
            model_name="simpendingaction",
            name="message_mode",
            field=models.CharField(db_index=True, default="query", max_length=32),
        ),
        migrations.AddField(
            model_name="simpendingaction",
            name="conversation_history",
            field=models.TextField(default="[]"),
        ),
        migrations.AddField(
            model_name="simpendingaction",
            name="status",
            field=models.CharField(db_index=True, default="queued", max_length=32),
        ),
    ]
