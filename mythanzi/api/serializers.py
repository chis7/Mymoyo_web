from django.contrib.auth.models import User
from rest_framework import serializers

from locations.models import District, Facility, Province, Service
from users.access import visible_appointment_filter
from users.models import (
    Appointment,
    ClientConsent,
    ClientJourneyEvent,
    ClientLocator,
    FollowUpTask,
    Notification,
    ReferralRecord,
    UserProfile,
)
from .models import FHIRResourceVersion


class UserProfileSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    responsibilities = serializers.SerializerMethodField()
    facility_name = serializers.CharField(source='facility.name', read_only=True)
    person_identity_name = serializers.CharField(source='person_identity.full_name', read_only=True)
    population_group_name = serializers.CharField(source='population_group.name', read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'role',
            'role_display',
            'person_identity',
            'person_identity_name',
            'facility',
            'facility_name',
            'population_group',
            'population_group_name',
            'responsibilities',
            'bio',
            'phone',
            'date_of_birth',
            'theme_color',
            'is_active',
            'must_change_password',
        ]

    def get_responsibilities(self, profile):
        return profile.get_role_responsibilities()


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'display_name',
            'email',
            'is_staff',
            'is_superuser',
            'is_active',
            'profile',
        ]

    def get_display_name(self, user):
        full_name = user.get_full_name().strip()
        return full_name or user.username


class ProvinceSerializer(serializers.ModelSerializer):
    facility_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Province
        fields = ['id', 'name', 'facility_count']


class DistrictSerializer(serializers.ModelSerializer):
    province_name = serializers.CharField(source='province.name', read_only=True)

    class Meta:
        model = District
        fields = ['id', 'name', 'province', 'province_name']


class ServiceSerializer(serializers.ModelSerializer):
    facility_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Service
        fields = ['id', 'name', 'code', 'description', 'is_active', 'facility_count']


class FacilitySerializer(serializers.ModelSerializer):
    district_name = serializers.CharField(source='district.name', read_only=True)
    province = serializers.IntegerField(source='district.province_id', read_only=True)
    province_name = serializers.CharField(source='district.province.name', read_only=True)
    hub_name = serializers.CharField(source='hub.name', read_only=True)
    spoke_count = serializers.IntegerField(read_only=True)
    service_names = serializers.SerializerMethodField()

    class Meta:
        model = Facility
        fields = [
            'id',
            'name',
            'code',
            'level',
            'facility_type',
            'hub',
            'hub_name',
            'spoke_count',
            'district',
            'district_name',
            'province',
            'province_name',
            'services',
            'service_names',
            'latitude',
            'longitude',
        ]

    def get_service_names(self, facility):
        return [service.name for service in facility.services.all()]


class AppointmentSerializer(serializers.ModelSerializer):
    beneficiary_detail = UserSerializer(source='beneficiary', read_only=True)
    beneficiary_reference = serializers.CharField(write_only=True, required=False, allow_blank=True)
    created_by_detail = UserSerializer(source='created_by', read_only=True)
    visit_purpose_display = serializers.CharField(source='get_visit_purpose_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    province_name = serializers.CharField(source='province.name', read_only=True)
    district_name = serializers.CharField(source='district.name', read_only=True)
    facility_name = serializers.CharField(source='facility.name', read_only=True)

    class Meta:
        model = Appointment
        fields = [
            'id',
            'beneficiary',
            'beneficiary_reference',
            'beneficiary_detail',
            'created_by',
            'created_by_detail',
            'visit_purpose',
            'visit_purpose_display',
            'appointment_date',
            'appointment_time',
            'province',
            'province_name',
            'district',
            'district_name',
            'facility',
            'facility_name',
            'status',
            'status_display',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']
        extra_kwargs = {
            'beneficiary': {'required': False},
        }

    def validate(self, attrs):
        reference_number = attrs.pop('beneficiary_reference', '').strip()
        if reference_number:
            try:
                attrs['beneficiary'] = User.objects.select_related('profile').get(
                    profile__reference_number__iexact=reference_number,
                    profile__role='client',
                    profile__is_active=True,
                    is_active=True,
                )
            except User.DoesNotExist:
                raise serializers.ValidationError({
                    'beneficiary_reference': 'No active client was found with this reference number.',
                })

        if self.instance is None and 'beneficiary' not in attrs:
            request = self.context.get('request')
            if not request or not request.user or not request.user.is_authenticated:
                raise serializers.ValidationError({'beneficiary': 'This field is required.'})
            attrs['beneficiary'] = request.user

        instance = self.instance or Appointment()
        for field_name, value in attrs.items():
            setattr(instance, field_name, value)
        if instance.facility_id:
            instance.district = instance.facility.district
            instance.province = instance.facility.district.province
            if instance.visit_purpose and not instance.facility.services.filter(
                code=instance.visit_purpose,
                is_active=True,
            ).exists():
                raise serializers.ValidationError({
                    'facility': 'Select a facility that provides this appointment service.',
                })

        try:
            instance.clean()
        except Exception as error:
            raise serializers.ValidationError(getattr(error, 'message_dict', str(error)))

        return attrs

    def create(self, validated_data):
        facility = validated_data.get('facility')
        if facility:
            validated_data['district'] = facility.district
            validated_data['province'] = facility.district.province
        return super().create(validated_data)

    def update(self, instance, validated_data):
        facility = validated_data.get('facility', instance.facility)
        if facility:
            validated_data['district'] = facility.district
            validated_data['province'] = facility.district.province
        return super().update(instance, validated_data)


class ClientSummarySerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    reference_number = serializers.CharField(source='profile.reference_number', read_only=True)
    phone = serializers.CharField(source='profile.phone', read_only=True)
    population_group = serializers.CharField(source='profile.population_group.name', read_only=True)
    facility_name = serializers.CharField(source='profile.facility.name', read_only=True)
    journey_count = serializers.IntegerField(read_only=True)
    referral_count = serializers.IntegerField(read_only=True)
    follow_up_count = serializers.IntegerField(read_only=True)
    appointment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'display_name',
            'reference_number',
            'phone',
            'population_group',
            'facility_name',
            'journey_count',
            'referral_count',
            'follow_up_count',
            'appointment_count',
        ]

    def get_display_name(self, user):
        full_name = user.get_full_name().strip()
        return full_name or user.username


class ClientLocatorSerializer(serializers.ModelSerializer):
    service_point_name = serializers.CharField(source='service_point.name', read_only=True)
    preferred_contact_method_display = serializers.CharField(source='get_preferred_contact_method_display', read_only=True)

    class Meta:
        model = ClientLocator
        fields = [
            'location_notes',
            'preferred_visit_time',
            'mobiliser_zone',
            'service_point',
            'service_point_name',
            'preferred_contact_method',
            'preferred_contact_method_display',
            'outreach_follow_up_details',
            'updated_at',
        ]
        read_only_fields = ['updated_at']


class ClientConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientConsent
        fields = [
            'code_based_management',
            'consent_to_follow_up',
            'consent_to_sms',
            'consent_to_whatsapp',
            'share_with_facility',
            'privacy_notes',
            'updated_at',
        ]
        read_only_fields = ['updated_at']


class ClientJourneyEventSerializer(serializers.ModelSerializer):
    stage_display = serializers.CharField(source='get_stage_display', read_only=True)
    outcome_display = serializers.CharField(source='get_outcome_display', read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)

    class Meta:
        model = ClientJourneyEvent
        fields = [
            'id',
            'stage',
            'stage_display',
            'event_date',
            'outcome',
            'outcome_display',
            'notes',
            'recorded_by',
            'recorded_by_name',
            'created_at',
        ]
        read_only_fields = ['recorded_by', 'created_at']


class ReferralRecordSerializer(serializers.ModelSerializer):
    receiving_facility_name = serializers.CharField(source='receiving_facility.name', read_only=True)
    assigned_mobiliser_name = serializers.CharField(source='assigned_mobiliser.get_full_name', read_only=True)
    confirmation_status_display = serializers.CharField(source='get_confirmation_status_display', read_only=True)
    initiation_outcome_display = serializers.CharField(source='get_initiation_outcome_display', read_only=True)

    class Meta:
        model = ReferralRecord
        fields = [
            'id',
            'referral_code',
            'receiving_facility',
            'receiving_facility_name',
            'receiving_hub',
            'assigned_mobiliser',
            'assigned_mobiliser_name',
            'confirmation_status',
            'confirmation_status_display',
            'initiation_outcome',
            'initiation_outcome_display',
            'referred_on',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['referral_code', 'receiving_hub', 'created_at', 'updated_at']


class FollowUpTaskSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    reason_display = serializers.CharField(source='get_reason_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)

    class Meta:
        model = FollowUpTask
        fields = [
            'id',
            'assigned_to',
            'assigned_to_name',
            'reason',
            'reason_display',
            'status',
            'status_display',
            'priority',
            'priority_display',
            'due_date',
            'notes',
            'outcome_notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class ClientDetailSerializer(ClientSummarySerializer):
    locator = serializers.SerializerMethodField()
    consent = serializers.SerializerMethodField()
    journey_events = ClientJourneyEventSerializer(many=True, read_only=True)
    referral_records = ReferralRecordSerializer(many=True, read_only=True)
    follow_up_tasks = FollowUpTaskSerializer(many=True, read_only=True)
    appointments = serializers.SerializerMethodField()

    class Meta(ClientSummarySerializer.Meta):
        fields = ClientSummarySerializer.Meta.fields + [
            'locator',
            'consent',
            'journey_events',
            'referral_records',
            'follow_up_tasks',
            'appointments',
        ]

    def get_locator(self, user):
        locator = getattr(user, 'client_locator', None)
        if not locator:
            return None
        return ClientLocatorSerializer(locator).data

    def get_consent(self, user):
        consent = getattr(user, 'client_consent', None)
        if not consent:
            return None
        return ClientConsentSerializer(consent).data

    def get_appointments(self, user):
        request = self.context.get('request')
        queryset = user.appointments.select_related(
            'beneficiary__profile',
            'created_by__profile',
            'province',
            'district',
            'facility',
        )
        if request and request.user.is_authenticated:
            queryset = queryset.filter(visible_appointment_filter(request.user))
        return AppointmentSerializer(queryset, many=True, context=self.context).data


class NotificationSerializer(serializers.ModelSerializer):
    appointment_detail = AppointmentSerializer(source='appointment', read_only=True)
    is_unread = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id',
            'notification_type',
            'channel',
            'status',
            'title',
            'message',
            'appointment',
            'appointment_detail',
            'is_unread',
            'read_at',
            'sent_at',
            'created_at',
        ]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class FHIRResourceVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FHIRResourceVersion
        fields = [
            'resource_type',
            'logical_id',
            'version_id',
            'action',
            'recorded_at',
            'source_app',
            'source_model',
            'source_pk',
            'resource',
        ]
