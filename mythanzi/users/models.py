from datetime import datetime, timedelta

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.crypto import get_random_string


class PersonIdentity(models.Model):
    """A real person that may have more than one login persona."""
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['full_name', 'id']
        verbose_name_plural = 'Person identities'

    def __str__(self):
        return self.full_name or f'Person #{self.pk}'

    @classmethod
    def for_user_defaults(cls, user, phone='', date_of_birth=None):
        full_name = user.get_full_name().strip() or user.username
        return cls.objects.create(
            full_name=full_name,
            phone=phone or None,
            date_of_birth=date_of_birth,
        )


class PopulationGroup(models.Model):
    """Reference data for client population group assignment."""
    SEX_ELIGIBILITY_CHOICES = [
        ('all', 'All sexes'),
        ('female', 'Female only'),
        ('male', 'Male only'),
    ]

    name = models.CharField(max_length=120, unique=True)
    code = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    sex_eligibility = models.CharField(max_length=12, choices=SEX_ELIGIBILITY_CHOICES, default='all')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """Extended user profile for additional information"""
    SEX_CHOICES = [
        ('female', 'Female'),
        ('male', 'Male'),
        ('other', 'Other / Not specified'),
    ]
    THEME_CHOICES = [
        ('slate', 'Slate'),
        ('teal', 'Teal'),
        ('indigo', 'Indigo'),
        ('rose', 'Rose'),
        ('amber', 'Amber'),
        ('sky', 'Sky'),
        ('light', 'Light'),
        ('dark', 'Dark'),
    ]
    ROLE_CHOICES = [
        ('client', 'Client'),
        ('mobiliser', 'Mobiliser / Outreach Worker'),
        ('chw', 'CHW / Case Manager'),
        ('provider', 'Provider / Clinician'),
        ('supervisor', 'Supervisor'),
        ('admin', 'Admin'),
    ]
    ROLE_RESPONSIBILITIES = {
        'client': [
            'View personal profile, stage, next appointment, and prevention status.',
            'Check upcoming appointments, missed visits, and follow-up obligations.',
            'See a simplified history of key events and actions.',
            'Complete self-service actions like assessments and appointment confirmations.',
        ],
        'mobiliser': [
            'Capture leads, contacts, and self-referrals in the field.',
            'Update lead status, contact attempts, and follow-up priorities.',
            'Convert qualified leads into formal client records.',
            'Support service linkage, referrals, and escalation of at-risk leads.',
        ],
        'chw': [
            'Review assigned clients, due visits, and overdue cases.',
            'Support risk assessment, referrals, and continuity across services.',
            'Record follow-up outcomes and adherence support interventions.',
            'Coordinate tracing and re-engagement for missed clients.',
        ],
        'provider': [
            'Open client cases and review referral and risk data.',
            'Record clinical assessments, LEN initiation, and eligibility decisions.',
            'Manage follow-up outcomes, adverse events, and next visit plans.',
            'Make case decisions around continuation, referral, or exit.',
        ],
        'supervisor': [
            'Monitor active work summaries, overdue follow-ups, and tracing queues.',
            'Review provider, follow-up, and tracing workloads for bottlenecks.',
            'Perform supportive supervision through selected client journeys.',
            'Confirm escalations and closure of high-risk or stuck cases.',
        ],
        'admin': [
            'Create and maintain users, roles, and access assignments.',
            'Manage core reference data, configurations, and workflow settings.',
            'Review audit logs, access patterns, and privacy controls.',
            'Monitor sync status and support system continuity.',
        ],
    }
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    person_identity = models.ForeignKey(
        PersonIdentity,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='profiles',
    )
    facility = models.ForeignKey(
        'locations.Facility',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='workers',
    )
    population_group = models.ForeignKey(
        PopulationGroup,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='client_profiles',
    )
    reference_number = models.CharField(max_length=20, unique=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='client')
    sex = models.CharField(max_length=12, choices=SEX_CHOICES, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_phone_verified = models.BooleanField(default=False)
    otp_code_hash = models.CharField(max_length=128, blank=True)
    otp_expires_at = models.DateTimeField(blank=True, null=True)
    must_change_password = models.BooleanField(default=False)
    temporary_password_expires_at = models.DateTimeField(blank=True, null=True)
    theme_color = models.CharField(max_length=20, choices=THEME_CHOICES, default='slate')
    last_logout = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    @staticmethod
    def build_reference_number(user_id):
        return f"MM-{user_id:06d}"

    def save(self, *args, **kwargs):
        if not self.reference_number and self.user_id:
            self.reference_number = self.build_reference_number(self.user_id)
        super().save(*args, **kwargs)

    def get_role_responsibilities(self):
        return self.ROLE_RESPONSIBILITIES.get(self.role, [])


class Appointment(models.Model):
    VISIT_PURPOSE_CHOICES = [
        ('clinical_review', 'Clinical Review (Checkup)'),
        ('lab_collection', 'Lab Collection'),
        ('medication_refill', 'Medication Refill'),
        ('follow_up', 'Follow-up Visit'),
    ]
    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('completed', 'Completed'),
        ('missed', 'Missed'),
    ]

    beneficiary = models.ForeignKey(User, on_delete=models.CASCADE, related_name='appointments')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='created_appointments',
    )
    visit_purpose = models.CharField(max_length=50, choices=VISIT_PURPOSE_CHOICES)
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    province = models.ForeignKey('locations.Province', on_delete=models.PROTECT, related_name='appointments')
    district = models.ForeignKey('locations.District', on_delete=models.PROTECT, related_name='appointments')
    facility = models.ForeignKey('locations.Facility', on_delete=models.PROTECT, related_name='appointments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='upcoming')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-appointment_date', '-appointment_time']
        verbose_name_plural = 'Appointments'

    def __str__(self):
        return f"{self.beneficiary.username} appointment on {self.appointment_date} at {self.appointment_time}"

    def clean(self):
        errors = {}

        if self.district_id and self.province_id and self.district.province_id != self.province_id:
            errors['district'] = 'Select a district within the chosen province.'

        if self.facility_id and self.district_id and self.facility.district_id != self.district_id:
            errors['facility'] = 'Select a facility within the chosen district.'

        if self.pk is None and self.appointment_date and self.appointment_time:
            appointment_datetime = timezone.make_aware(
                datetime.combine(self.appointment_date, self.appointment_time),
                timezone.get_current_timezone(),
            )
            if appointment_datetime <= timezone.now():
                errors['appointment_date'] = 'Appointments cannot be booked in the past.'
                errors['appointment_time'] = 'Choose a future appointment time.'

        if errors:
            raise ValidationError(errors)


class Notification(models.Model):
    NOTIFICATION_TYPE_CHOICES = [
        ('appointment', 'Appointment'),
        ('general', 'General'),
    ]
    CHANNEL_CHOICES = [
        ('portal', 'Portal'),
        ('email', 'Email'),
    ]
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('read', 'Read'),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='sent_notifications',
    )
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='notifications',
    )
    notification_type = models.CharField(max_length=40, choices=NOTIFICATION_TYPE_CHOICES, default='general')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    title = models.CharField(max_length=160)
    message = models.TextField()
    error_message = models.TextField(blank=True)
    read_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'status', '-created_at']),
            models.Index(fields=['recipient', 'channel', '-created_at']),
        ]

    def __str__(self):
        return f'{self.get_channel_display()} notification for {self.recipient}'

    @property
    def is_unread(self):
        return self.channel == 'portal' and not self.read_at

    def mark_read(self):
        if not self.read_at:
            self.read_at = timezone.now()
            self.status = 'read'
            self.save(update_fields=['read_at', 'status', 'updated_at'])


class NotificationTypeSetting(models.Model):
    CHANNEL_CHOICES = [
        ('portal', 'Portal'),
        ('email', 'Email'),
        ('portal_email', 'Portal + Email'),
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
    ]
    CADENCE_CHOICES = [
        ('daily', 'Daily'),
        ('before_event', 'Before event'),
        ('after_event', 'After event'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    key = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    cadence = models.CharField(max_length=30, choices=CADENCE_CHOICES, default='daily')
    channel = models.CharField(max_length=30, choices=CHANNEL_CHOICES, default='portal')
    timing = models.CharField(max_length=30, default='08:00')
    enabled = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def portal_enabled(self):
        return self.enabled and self.channel in {'portal', 'portal_email'}

    @property
    def email_enabled(self):
        return self.enabled and self.channel in {'email', 'portal_email'}


class ClientLocator(models.Model):
    CONTACT_METHOD_CHOICES = [
        ('phone', 'Phone call'),
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('clinic', 'Clinic visit'),
        ('mobiliser', 'Mobiliser follow-up'),
    ]

    client = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client_locator')
    location_notes = models.TextField(blank=True)
    preferred_visit_time = models.CharField(max_length=120, blank=True)
    mobiliser_zone = models.CharField(max_length=120, blank=True)
    service_point = models.ForeignKey(
        'locations.Facility',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='client_locators',
    )
    preferred_contact_method = models.CharField(max_length=20, choices=CONTACT_METHOD_CHOICES, blank=True)
    outreach_follow_up_details = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='updated_client_locators',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['client__username']

    def __str__(self):
        return f'Locator for {self.client.username}'


class ClientJourneyEvent(models.Model):
    STAGE_CHOICES = [
        ('contact', 'Contact'),
        ('risk_assessment', 'Risk assessment'),
        ('referral', 'Referral'),
        ('hivst', 'HIVST'),
        ('prep_len_initiation', 'PrEP/LEN initiation'),
        ('follow_up', 'Follow-up'),
        ('continuation', 'Continuation'),
    ]
    OUTCOME_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('missed', 'Missed'),
        ('referred', 'Referred'),
        ('continued', 'Continued'),
        ('stopped', 'Stopped'),
    ]

    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='journey_events')
    stage = models.CharField(max_length=40, choices=STAGE_CHOICES)
    event_date = models.DateField(default=timezone.localdate)
    outcome = models.CharField(max_length=30, choices=OUTCOME_CHOICES, default='pending')
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='recorded_journey_events',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-event_date', '-created_at']

    def __str__(self):
        return f'{self.client.username} - {self.get_stage_display()}'


class ReferralRecord(models.Model):
    STATUS_CHOICES = [
        ('generated', 'Generated'),
        ('sent', 'Sent'),
        ('received', 'Received'),
        ('attended', 'Attended'),
        ('initiated', 'Initiated'),
        ('not_attended', 'Not attended'),
        ('closed', 'Closed'),
    ]
    OUTCOME_CHOICES = [
        ('pending', 'Pending'),
        ('len_prep_initiated', 'LEN/PrEP initiated'),
        ('hivst_received', 'HIVST received'),
        ('referred_elsewhere', 'Referred elsewhere'),
        ('declined', 'Declined'),
    ]
    COMPLETED_STATUSES = {'attended', 'initiated', 'closed'}
    FOLLOW_UP_STATUSES = {'not_attended'}

    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referral_records')
    referral_code = models.CharField(max_length=40, unique=True, blank=True)
    receiving_facility = models.ForeignKey(
        'locations.Facility',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='referrals_received',
    )
    receiving_hub = models.CharField(max_length=180, blank=True)
    assigned_mobiliser = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='assigned_referrals',
    )
    confirmation_status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='generated')
    initiation_outcome = models.CharField(max_length=30, choices=OUTCOME_CHOICES, default='pending')
    referred_on = models.DateField(default=timezone.localdate)
    confirmed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='confirmed_referrals',
    )
    confirmed_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    received_at = models.DateTimeField(blank=True, null=True)
    attended_at = models.DateTimeField(blank=True, null=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='recorded_referrals',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-referred_on', '-created_at']

    def __str__(self):
        destination = self.receiving_facility or self.receiving_hub or 'service point'
        return f'{self.referral_code or "Referral"} to {destination}'

    @property
    def is_complete(self):
        return self.confirmation_status in self.COMPLETED_STATUSES

    @property
    def receiving_point_name(self):
        if self.receiving_facility:
            return self.receiving_facility.name
        return self.receiving_hub

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self.generate_referral_code()
        if self.receiving_facility_id:
            self.receiving_hub = self.receiving_facility.name

        now = timezone.now()
        if self.confirmation_status == 'sent' and not self.sent_at:
            self.sent_at = now
        if self.confirmation_status == 'received' and not self.received_at:
            self.received_at = now
        if self.confirmation_status in {'attended', 'initiated'} and not self.attended_at:
            self.attended_at = now
        if self.confirmation_status == 'closed' and not self.closed_at:
            self.closed_at = now
        if self.confirmed_by_id and not self.confirmed_at:
            self.confirmed_at = now

        super().save(*args, **kwargs)
        if self.confirmation_status in self.FOLLOW_UP_STATUSES:
            self.ensure_follow_up_task()

    @classmethod
    def generate_referral_code(cls):
        while True:
            code = f'REF-{get_random_string(10, allowed_chars="ABCDEFGHJKLMNPQRSTUVWXYZ23456789")}'
            if not cls.objects.filter(referral_code=code).exists():
                return code

    def ensure_follow_up_task(self):
        marker = f'Referral code: {self.referral_code}'
        duplicate = self.client.follow_up_tasks.filter(
            reason='referral_confirmation',
            status__in=['open', 'in_progress'],
            notes__icontains=marker,
        ).exists()
        if duplicate:
            return
        FollowUpTask.objects.create(
            client=self.client,
            assigned_to=self.assigned_mobiliser or self.recorded_by,
            reason='referral_confirmation',
            status='open',
            priority='high',
            due_date=timezone.localdate() + timedelta(days=2),
            notes=f'{marker}\nFollow up because referral status is Not attended.',
            created_by=self.recorded_by,
        )


class FollowUpTask(models.Model):
    REASON_CHOICES = [
        ('missed_appointment', 'Missed appointment'),
        ('tracing', 'Tracing'),
        ('re_engagement', 'Re-engagement'),
        ('referral_confirmation', 'Referral confirmation'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='follow_up_tasks')
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='assigned_follow_up_tasks',
    )
    reason = models.CharField(max_length=40, choices=REASON_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    due_date = models.DateField()
    notes = models.TextField(blank=True)
    outcome_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='created_follow_up_tasks',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', 'due_date', '-priority']

    def __str__(self):
        return f'{self.get_reason_display()} for {self.client.username}'


class ClientConsent(models.Model):
    client = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client_consent')
    code_based_management = models.BooleanField(default=True)
    consent_to_follow_up = models.BooleanField(default=False)
    consent_to_sms = models.BooleanField(default=False)
    consent_to_whatsapp = models.BooleanField(default=False)
    share_with_facility = models.BooleanField(default=False)
    privacy_notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='recorded_client_consents',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['client__username']

    def __str__(self):
        return f'Consent for {self.client.username}'


class AnonymousOrUserSubmission(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='%(class)ss',
    )
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    answers = models.JSONField(default=dict, blank=True)
    guidance = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['-submitted_at']


class SafeguardingCase(AnonymousOrUserSubmission):
    INCIDENT_TYPE_CHOICES = [
        ('abuse', 'Abuse or exploitation'),
        ('harassment', 'Harassment'),
        ('coercion', 'Coercion or pressure'),
        ('privacy_breach', 'Privacy breach'),
        ('unsafe_service', 'Unsafe service environment'),
        ('other', 'Other concern'),
    ]
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('received', 'Received'),
        ('under_review', 'Under review'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    reference_number = models.CharField(max_length=24, unique=True, blank=True)
    incident_type = models.CharField(max_length=40, choices=INCIDENT_TYPE_CHOICES, blank=True)
    incident_date = models.DateField(blank=True, null=True)
    location = models.CharField(max_length=180, blank=True)
    location_facility = models.ForeignKey(
        'locations.Facility',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='safeguarding_cases',
    )
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    involved_parties = models.TextField(blank=True)
    incident_details = models.TextField(blank=True)
    focal_point = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='assigned_safeguarding_cases',
    )
    confidentiality_locked = models.BooleanField(default=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='received')
    sla_deadline = models.DateField(blank=True, null=True)
    risk_trigger_flag = models.BooleanField(default=False)
    cab_oversight_ready = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', 'sla_deadline', '-submitted_at']

    def __str__(self):
        return self.reference_number or f'Safeguarding case #{self.pk}'

    def save(self, *args, **kwargs):
        if not self.sla_deadline:
            self.sla_deadline = timezone.localdate() + timedelta(days=30)
        super().save(*args, **kwargs)
        if not self.reference_number:
            self.reference_number = f'SG-{self.pk:06d}'
            super().save(update_fields=['reference_number'])

    @property
    def is_overdue(self):
        return self.status not in {'resolved', 'closed'} and self.sla_deadline and self.sla_deadline < timezone.localdate()


class GrievanceCase(AnonymousOrUserSubmission):
    CHANNEL_CHOICES = [
        ('in_app', 'In-app form'),
        ('qr_box', 'QR suggestion box'),
        ('verbal_log', 'Verbal log'),
        ('peer_navigator', 'Peer navigator entry'),
    ]
    CATEGORY_CHOICES = [
        ('service', 'Service'),
        ('staff', 'Staff'),
        ('access', 'Access'),
        ('stigma', 'Stigma'),
        ('discrimination', 'Discrimination'),
        ('quality', 'Programme quality'),
        ('other', 'Other'),
    ]
    PRIORITY_CHOICES = [
        ('standard', 'Standard'),
        ('urgent', 'Urgent'),
    ]
    STATUS_CHOICES = [
        ('received', 'Received'),
        ('assigned', 'Assigned'),
        ('under_review', 'Under review'),
        ('escalated', 'Escalated'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    ESCALATION_CHOICES = [
        ('', 'Not escalated'),
        ('programme_manager', 'Programme Manager'),
        ('psc', 'PSC'),
        ('governance_structure', 'Other governance structure'),
    ]

    reference_number = models.CharField(max_length=24, unique=True, blank=True)
    submission_channel = models.CharField(max_length=30, choices=CHANNEL_CHOICES, default='in_app')
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='standard')
    complaint_details = models.TextField()
    district = models.ForeignKey(
        'locations.District',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='grievance_cases',
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='assigned_grievance_cases',
    )
    response_provided = models.BooleanField(default=False)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='received')
    escalation_target = models.CharField(max_length=40, choices=ESCALATION_CHOICES, blank=True)
    sla_deadline = models.DateField(blank=True, null=True)
    resolution_notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', 'sla_deadline', '-submitted_at']

    def __str__(self):
        return self.reference_number or f'Grievance #{self.pk}'

    def save(self, *args, **kwargs):
        if not self.sla_deadline:
            self.sla_deadline = timezone.localdate() + timedelta(days=30)
        super().save(*args, **kwargs)
        if not self.reference_number:
            self.reference_number = f'GV-{self.pk:06d}'
            super().save(update_fields=['reference_number'])

    @property
    def is_overdue(self):
        return self.status not in {'resolved', 'closed'} and self.sla_deadline and self.sla_deadline < timezone.localdate()


class ClientExitInterview(AnonymousOrUserSubmission):
    SERVICE_POINT_CHOICES = [
        ('hub', 'Hub'),
        ('spoke', 'Spoke'),
        ('other', 'Other service point'),
    ]
    RATING_CHOICES = [
        (1, '1 - Very poor'),
        (2, '2 - Poor'),
        (3, '3 - Fair'),
        (4, '4 - Good'),
        (5, '5 - Excellent'),
    ]
    YES_NO_CHOICES = [
        ('yes', 'Yes'),
        ('no', 'No'),
        ('unsure', 'Not sure'),
    ]

    client_code = models.CharField(max_length=80, blank=True)
    service_point_type = models.CharField(max_length=20, choices=SERVICE_POINT_CHOICES)
    service_point = models.ForeignKey(
        'locations.Facility',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='exit_interviews',
    )
    population_group = models.ForeignKey(
        PopulationGroup,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='exit_interviews',
    )
    waiting_time_rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    staff_attitude_rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    privacy_respected = models.CharField(max_length=10, choices=YES_NO_CHOICES)
    information_clarity_score = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    len_questions_understood = models.CharField(max_length=10, choices=YES_NO_CHOICES)
    net_promoter_score = models.PositiveSmallIntegerField()
    comments = models.TextField(blank=True)
    dashboard_ready = models.BooleanField(default=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        owner = self.client_code or (self.user.username if self.user_id else 'Anonymous')
        return f'Exit interview - {owner}'


class SelfRiskAssessmentSubmission(AnonymousOrUserSubmission):
    score = models.PositiveSmallIntegerField(default=0)
    level = models.CharField(max_length=20, blank=True)

    def __str__(self):
        owner = self.user.username if self.user_id else 'Anonymous'
        return f'{owner} risk assessment ({self.level or "unscored"})'


class SelfTestReportSubmission(AnonymousOrUserSubmission):
    test_date = models.DateField()
    result = models.CharField(max_length=30)

    def __str__(self):
        owner = self.user.username if self.user_id else 'Anonymous'
        return f'{owner} self-test report ({self.result})'


class SideEffectReportSubmission(AnonymousOrUserSubmission):
    symptom_start_date = models.DateField()
    severity = models.CharField(max_length=30)
    follow_up_requested = models.BooleanField(default=False)

    def __str__(self):
        owner = self.user.username if self.user_id else 'Anonymous'
        return f'{owner} side-effect report ({self.severity})'


class ClinicFeedbackSubmission(AnonymousOrUserSubmission):
    facility = models.ForeignKey(
        'locations.Facility',
        on_delete=models.PROTECT,
        related_name='feedback_submissions',
    )
    visit_date = models.DateField()
    average_rating = models.DecimalField(max_digits=3, decimal_places=1)
    follow_up_requested = models.BooleanField(default=False)

    def __str__(self):
        owner = self.user.username if self.user_id else 'Anonymous'
        return f'{owner} clinic feedback for {self.facility}'


class AuditLog(models.Model):
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_CHOICES = [
        (ACTION_CREATE, 'Create'),
        (ACTION_UPDATE, 'Update'),
        (ACTION_DELETE, 'Delete'),
    ]

    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    app_label = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    object_pk = models.CharField(max_length=255)
    object_repr = models.CharField(max_length=255)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='audit_events',
    )
    changes = models.JSONField(default=dict, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['app_label', 'model_name', 'object_pk']),
            models.Index(fields=['action', 'created_at']),
            models.Index(fields=['actor', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} {self.app_label}.{self.model_name} {self.object_pk}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile when a new User is created"""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save the UserProfile when the User is saved"""
    profile, _ = UserProfile.objects.get_or_create(user=instance)
    profile.save()


@receiver(post_save, sender=UserProfile)
def sync_user_active_status(sender, instance, **kwargs):
    """Keep Django authentication status aligned with the profile status."""
    if instance.user.is_active != instance.is_active:
        instance.user.is_active = instance.is_active
        instance.user.save(update_fields=['is_active'])
