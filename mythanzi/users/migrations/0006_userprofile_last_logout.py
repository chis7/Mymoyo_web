from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_sync_userprofile_active_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='last_logout',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
