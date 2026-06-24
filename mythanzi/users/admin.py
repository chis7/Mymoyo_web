from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import (
    Appointment,
    AuditLog,
    ClientConsent,
    ClientExitInterview,
    ClinicFeedbackSubmission,
    ClientJourneyEvent,
    ClientLocator,
    FollowUpTask,
    GrievanceCase,
    PersonIdentity,
    PopulationGroup,
    ReferralRecord,
    SafeguardingCase,
    SelfRiskAssessmentSubmission,
    SelfTestReportSubmission,
    SideEffectReportSubmission,
    UserProfile,
)
from locations.models import Province, District, Facility

admin.site.site_header = 'My Moyo Admin'
admin.site.site_title = 'My Moyo Admin Portal'
admin.site.index_title = 'Manage users, locations and appointments'


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'


class CustomUserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_role', 'get_reference_number')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'profile__phone', 'profile__reference_number')

    def get_role(self, obj):
        return obj.profile.role if hasattr(obj, 'profile') else ''
    get_role.short_description = 'Role'

    def get_reference_number(self, obj):
        return obj.profile.reference_number if hasattr(obj, 'profile') else ''
    get_reference_number.short_description = 'Reference #'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'person_identity', 'reference_number', 'role', 'population_group', 'phone', 'is_active', 'is_phone_verified', 'must_change_password', 'created_at')
    list_filter = ('role', 'population_group', 'is_active', 'is_phone_verified', 'must_change_password', 'created_at')
    search_fields = ('reference_number', 'user__username', 'user__email', 'phone')
    readonly_fields = ('reference_number', 'created_at', 'updated_at')
    fieldsets = (
        ('User', {
            'fields': ('user', 'person_identity', 'reference_number')
        }),
        ('Profile Information', {
            'fields': ('role', 'population_group', 'bio', 'phone', 'date_of_birth', 'is_active', 'is_phone_verified', 'must_change_password')
        }),
        ('OTP Verification', {
            'fields': ('otp_expires_at',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PersonIdentity)
class PersonIdentityAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'date_of_birth', 'created_at')
    search_fields = ('full_name', 'phone')
    readonly_fields = ('created_at',)


@admin.register(PopulationGroup)
class PopulationGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created_at',)


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('beneficiary', 'created_by', 'visit_purpose', 'appointment_date', 'appointment_time', 'status', 'province', 'district', 'facility')
    list_filter = ('status', 'visit_purpose', 'province', 'district', 'facility')
    search_fields = ('beneficiary__username', 'beneficiary__email', 'beneficiary__profile__reference_number', 'created_by__username', 'notes')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Appointment Info', {
            'fields': ('beneficiary', 'created_by', 'visit_purpose', 'appointment_date', 'appointment_time', 'status')
        }),
        ('Location', {
            'fields': ('province', 'district', 'facility')
        }),
        ('Notes & Timestamps', {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ClientLocator)
class ClientLocatorAdmin(admin.ModelAdmin):
    list_display = ('client', 'service_point', 'mobiliser_zone', 'preferred_contact_method', 'updated_at')
    list_filter = ('preferred_contact_method', 'service_point')
    search_fields = ('client__username', 'client__profile__reference_number', 'mobiliser_zone', 'location_notes')
    readonly_fields = ('updated_at',)


@admin.register(ClientJourneyEvent)
class ClientJourneyEventAdmin(admin.ModelAdmin):
    list_display = ('client', 'stage', 'outcome', 'event_date', 'recorded_by')
    list_filter = ('stage', 'outcome', 'event_date')
    search_fields = ('client__username', 'client__profile__reference_number', 'notes')
    readonly_fields = ('created_at',)


@admin.register(ReferralRecord)
class ReferralRecordAdmin(admin.ModelAdmin):
    list_display = ('referral_code', 'client', 'receiving_facility', 'assigned_mobiliser', 'confirmation_status', 'initiation_outcome', 'referred_on')
    list_filter = ('confirmation_status', 'initiation_outcome', 'receiving_facility__district', 'referred_on')
    search_fields = ('client__username', 'client__profile__reference_number', 'referral_code', 'receiving_hub', 'receiving_facility__name')
    readonly_fields = ('referral_code', 'created_at', 'updated_at', 'confirmed_at', 'sent_at', 'received_at', 'attended_at', 'closed_at')


@admin.register(FollowUpTask)
class FollowUpTaskAdmin(admin.ModelAdmin):
    list_display = ('client', 'reason', 'status', 'priority', 'due_date', 'assigned_to')
    list_filter = ('reason', 'status', 'priority', 'due_date')
    search_fields = ('client__username', 'client__profile__reference_number', 'notes', 'outcome_notes')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ClientConsent)
class ClientConsentAdmin(admin.ModelAdmin):
    list_display = ('client', 'code_based_management', 'consent_to_follow_up', 'consent_to_sms', 'share_with_facility', 'updated_at')
    list_filter = ('code_based_management', 'consent_to_follow_up', 'consent_to_sms', 'consent_to_whatsapp', 'share_with_facility')
    search_fields = ('client__username', 'client__profile__reference_number', 'privacy_notes')
    readonly_fields = ('updated_at',)


@admin.register(SafeguardingCase)
class SafeguardingCaseAdmin(admin.ModelAdmin):
    list_display = ('reference_number', 'incident_type', 'severity', 'status', 'focal_point', 'sla_deadline', 'submitted_at')
    list_filter = ('incident_type', 'severity', 'status', 'confidentiality_locked', 'risk_trigger_flag', 'cab_oversight_ready')
    search_fields = ('reference_number', 'location', 'incident_details')
    readonly_fields = ('reference_number', 'submitted_at', 'updated_at')


@admin.register(GrievanceCase)
class GrievanceCaseAdmin(admin.ModelAdmin):
    list_display = ('reference_number', 'category', 'priority', 'status', 'assigned_to', 'district', 'sla_deadline', 'submitted_at')
    list_filter = ('category', 'priority', 'status', 'submission_channel', 'district')
    search_fields = ('reference_number', 'complaint_details', 'resolution_notes')
    readonly_fields = ('reference_number', 'submitted_at', 'updated_at')


@admin.register(ClientExitInterview)
class ClientExitInterviewAdmin(admin.ModelAdmin):
    list_display = ('submitted_at', 'service_point_type', 'service_point', 'population_group', 'waiting_time_rating', 'staff_attitude_rating', 'net_promoter_score')
    list_filter = ('service_point_type', 'population_group', 'privacy_respected', 'len_questions_understood')
    search_fields = ('client_code', 'comments', 'service_point__name')
    readonly_fields = ('submitted_at',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'app_label', 'model_name', 'object_repr', 'actor')
    list_filter = ('action', 'app_label', 'model_name', 'created_at')
    search_fields = ('object_repr', 'object_pk', 'actor__username', 'actor__email')
    readonly_fields = (
        'action',
        'app_label',
        'model_name',
        'object_pk',
        'object_repr',
        'actor',
        'changes',
        'snapshot',
        'created_at',
    )
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SelfRiskAssessmentSubmission)
class SelfRiskAssessmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ('submitted_at', 'user', 'session_key', 'level', 'score')
    list_filter = ('level', 'submitted_at')
    search_fields = ('user__username', 'user__email', 'session_key')
    readonly_fields = ('user', 'session_key', 'answers', 'guidance', 'score', 'level', 'submitted_at')

    def has_add_permission(self, request):
        return False


@admin.register(SelfTestReportSubmission)
class SelfTestReportSubmissionAdmin(admin.ModelAdmin):
    list_display = ('submitted_at', 'user', 'session_key', 'test_date', 'result')
    list_filter = ('result', 'test_date', 'submitted_at')
    search_fields = ('user__username', 'user__email', 'session_key')
    readonly_fields = ('user', 'session_key', 'answers', 'guidance', 'test_date', 'result', 'submitted_at')

    def has_add_permission(self, request):
        return False


@admin.register(SideEffectReportSubmission)
class SideEffectReportSubmissionAdmin(admin.ModelAdmin):
    list_display = ('submitted_at', 'user', 'session_key', 'severity', 'follow_up_requested')
    list_filter = ('severity', 'follow_up_requested', 'submitted_at')
    search_fields = ('user__username', 'user__email', 'session_key')
    readonly_fields = (
        'user',
        'session_key',
        'answers',
        'guidance',
        'symptom_start_date',
        'severity',
        'follow_up_requested',
        'submitted_at',
    )

    def has_add_permission(self, request):
        return False


@admin.register(ClinicFeedbackSubmission)
class ClinicFeedbackSubmissionAdmin(admin.ModelAdmin):
    list_display = ('submitted_at', 'user', 'session_key', 'facility', 'visit_date', 'average_rating', 'follow_up_requested')
    list_filter = ('facility', 'visit_date', 'follow_up_requested', 'submitted_at')
    search_fields = ('user__username', 'user__email', 'session_key', 'facility__name')
    readonly_fields = (
        'user',
        'session_key',
        'answers',
        'guidance',
        'facility',
        'visit_date',
        'average_rating',
        'follow_up_requested',
        'submitted_at',
    )

    def has_add_permission(self, request):
        return False


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
