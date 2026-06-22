from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='facility',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='facility',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True),
        ),
    ]
