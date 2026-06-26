from django.db import migrations, models


NEW_NOTIFICATION_TYPE_SETTINGS = [
    {
        'key': 'client_journey_event',
        'name': 'Client Journey Event',
        'description': 'Notify clients when journey events are recorded on their profile.',
        'cadence': 'after_event',
        'channel': 'portal',
        'timing': 'immediate',
    },
    {
        'key': 'client_referral',
        'name': 'Client Referral',
        'description': 'Notify clients when referrals are created or updated.',
        'cadence': 'after_event',
        'channel': 'portal',
        'timing': 'immediate',
    },
    {
        'key': 'client_follow_up_task',
        'name': 'Client Follow-Up Task',
        'description': 'Notify clients when follow-up tasks are created for their care journey.',
        'cadence': 'after_event',
        'channel': 'portal',
        'timing': 'immediate',
    },
    {
        'key': 'staff_follow_up_task',
        'name': 'Staff Follow-Up Task Assignment',
        'description': 'Notify staff members when follow-up tasks are assigned to them.',
        'cadence': 'after_event',
        'channel': 'portal',
        'timing': 'immediate',
    },
]


def seed_notification_event_types(apps, schema_editor):
    NotificationTypeSetting = apps.get_model('users', 'NotificationTypeSetting')
    for default in NEW_NOTIFICATION_TYPE_SETTINGS:
        NotificationTypeSetting.objects.get_or_create(
            key=default['key'],
            defaults={
                **default,
                'enabled': True,
                'is_system': True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0024_notificationtypesetting'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                choices=[
                    ('appointment', 'Appointment'),
                    ('client_journey_event', 'Client Journey Event'),
                    ('client_referral', 'Client Referral'),
                    ('client_follow_up_task', 'Client Follow-Up Task'),
                    ('staff_follow_up_task', 'Staff Follow-Up Task Assignment'),
                    ('general', 'General'),
                ],
                default='general',
                max_length=40,
            ),
        ),
        migrations.RunPython(seed_notification_event_types, migrations.RunPython.noop),
    ]
