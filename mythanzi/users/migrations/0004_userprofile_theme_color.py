from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_appointment'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='theme_color',
            field=models.CharField(
                choices=[
                    ('slate', 'Slate'),
                    ('teal', 'Teal'),
                    ('indigo', 'Indigo'),
                    ('rose', 'Rose'),
                ],
                default='slate',
                max_length=20,
            ),
        ),
    ]
