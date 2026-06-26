from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils.crypto import get_random_string


def generate_referral_code(ReferralRecord):
    while True:
        code = f'REF-{get_random_string(10, allowed_chars="ABCDEFGHJKLMNPQRSTUVWXYZ23456789")}'
        if not ReferralRecord.objects.filter(referral_code=code).exists():
            return code


def migrate_referrals(apps, schema_editor):
    ReferralRecord = apps.get_model('users', 'ReferralRecord')
    Facility = apps.get_model('locations', 'Facility')

    status_map = {
        'issued': 'generated',
        'received': 'received',
        'confirmed': 'attended',
        'completed': 'initiated',
        'cancelled': 'closed',
    }
    outcome_map = {
        'initiated': 'len_prep_initiated',
        'not_eligible': 'referred_elsewhere',
        'lost_to_follow_up': 'declined',
    }

    seen_codes = set()
    for referral in ReferralRecord.objects.order_by('pk'):
        changed = False
        if not referral.referral_code or referral.referral_code in seen_codes:
            referral.referral_code = generate_referral_code(ReferralRecord)
            changed = True
        seen_codes.add(referral.referral_code)
        if referral.confirmation_status in status_map:
            referral.confirmation_status = status_map[referral.confirmation_status]
            changed = True
        if referral.initiation_outcome in outcome_map:
            referral.initiation_outcome = outcome_map[referral.initiation_outcome]
            changed = True
        if referral.receiving_hub and not referral.receiving_facility_id:
            facility = Facility.objects.filter(name__iexact=referral.receiving_hub.strip()).first()
            if facility:
                referral.receiving_facility = facility
                changed = True
        if changed:
            referral.save(update_fields=[
                'referral_code',
                'confirmation_status',
                'initiation_outcome',
                'receiving_facility',
            ])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('locations', '0008_apply_services_to_hub_spoke_facilities'),
        ('users', '0018_clientexitinterview_grievancecase_safeguardingcase'),
    ]

    operations = [
        migrations.AddField(
            model_name='referralrecord',
            name='assigned_mobiliser',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_referrals', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='referralrecord',
            name='attended_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='referralrecord',
            name='closed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='referralrecord',
            name='confirmed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='referralrecord',
            name='confirmed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='confirmed_referrals', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='referralrecord',
            name='received_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='referralrecord',
            name='receiving_facility',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='referrals_received', to='locations.facility'),
        ),
        migrations.AddField(
            model_name='referralrecord',
            name='sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='referralrecord',
            name='confirmation_status',
            field=models.CharField(choices=[('generated', 'Generated'), ('sent', 'Sent'), ('received', 'Received'), ('attended', 'Attended'), ('initiated', 'Initiated'), ('not_attended', 'Not attended'), ('closed', 'Closed')], default='generated', max_length=30),
        ),
        migrations.AlterField(
            model_name='referralrecord',
            name='initiation_outcome',
            field=models.CharField(choices=[('pending', 'Pending'), ('len_prep_initiated', 'LEN/PrEP initiated'), ('hivst_received', 'HIVST received'), ('referred_elsewhere', 'Referred elsewhere'), ('declined', 'Declined')], default='pending', max_length=30),
        ),
        migrations.AlterField(
            model_name='referralrecord',
            name='receiving_hub',
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.RunPython(migrate_referrals, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='referralrecord',
            name='referral_code',
            field=models.CharField(blank=True, max_length=40, unique=True),
        ),
    ]
