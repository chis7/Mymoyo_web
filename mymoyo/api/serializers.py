from django.contrib.auth.models import User
from rest_framework import serializers

from locations.models import District, Facility, Province
from users.models import Appointment, UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    responsibilities = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'role',
            'role_display',
            'responsibilities',
            'bio',
            'phone',
            'date_of_birth',
            'theme_color',
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


class FacilitySerializer(serializers.ModelSerializer):
    district_name = serializers.CharField(source='district.name', read_only=True)
    province = serializers.IntegerField(source='district.province_id', read_only=True)
    province_name = serializers.CharField(source='district.province.name', read_only=True)

    class Meta:
        model = Facility
        fields = [
            'id',
            'name',
            'code',
            'level',
            'district',
            'district_name',
            'province',
            'province_name',
            'latitude',
            'longitude',
        ]


class AppointmentSerializer(serializers.ModelSerializer):
    beneficiary_detail = UserSerializer(source='beneficiary', read_only=True)
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
            'beneficiary_detail',
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
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        instance = self.instance or Appointment()
        for field_name, value in attrs.items():
            setattr(instance, field_name, value)

        try:
            instance.clean()
        except Exception as error:
            raise serializers.ValidationError(getattr(error, 'message_dict', str(error)))

        return attrs


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
