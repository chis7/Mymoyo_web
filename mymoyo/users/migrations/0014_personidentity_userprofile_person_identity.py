from django.db import migrations, models
import django.db.models.deletion


def create_person_identities(apps, schema_editor):
    UserProfile = apps.get_model('users', 'UserProfile')
    PersonIdentity = apps.get_model('users', 'PersonIdentity')
    for profile in UserProfile.objects.select_related('user').filter(person_identity__isnull=True):
        user = profile.user
        full_name = f'{user.first_name} {user.last_name}'.strip() or user.username
        person = PersonIdentity.objects.create(
            full_name=full_name,
            phone=profile.phone,
            date_of_birth=profile.date_of_birth,
        )
        profile.person_identity = person
        profile.save(update_fields=['person_identity'])


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0013_userprofile_facility'),
    ]

    operations = [
        migrations.CreateModel(
            name='PersonIdentity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=255)),
                ('phone', models.CharField(blank=True, max_length=20, null=True)),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name_plural': 'Person identities',
                'ordering': ['full_name', 'id'],
            },
        ),
        migrations.AddField(
            model_name='userprofile',
            name='person_identity',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='profiles', to='users.personidentity'),
        ),
        migrations.RunPython(create_person_identities, migrations.RunPython.noop),
    ]
