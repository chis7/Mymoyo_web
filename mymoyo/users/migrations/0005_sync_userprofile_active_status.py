from django.db import migrations


def sync_user_active_status(apps, schema_editor):
    UserProfile = apps.get_model('users', 'UserProfile')
    User = apps.get_model('auth', 'User')

    for profile in UserProfile.objects.all().only('user_id', 'is_active'):
        User.objects.filter(pk=profile.user_id).update(is_active=profile.is_active)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_userprofile_theme_color'),
    ]

    operations = [
        migrations.RunPython(sync_user_active_status, migrations.RunPython.noop),
    ]
