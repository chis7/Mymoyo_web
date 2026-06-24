from datetime import datetime

from django import forms
from django.contrib.auth.forms import UserCreationForm as DjangoUserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from .models import (
    Appointment,
    ClientConsent,
    ClientExitInterview,
    ClientJourneyEvent,
    ClientLocator,
    FollowUpTask,
    GrievanceCase,
    PersonIdentity,
    PopulationGroup,
    ReferralRecord,
    SafeguardingCase,
    UserProfile,
)
from locations.models import District, Facility

FACILITY_REQUIRED_ROLES = {'supervisor', 'provider', 'chw', 'mobiliser'}
FACILITY_ASSIGNABLE_ROLES = {'admin', 'supervisor', 'provider', 'chw', 'mobiliser'}
FACILITY_USER_ROLES = FACILITY_REQUIRED_ROLES


class PopulationGroupForm(forms.ModelForm):
    class Meta:
        model = PopulationGroup
        fields = ['name', 'code', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Population group name',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'population-group-code',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Username'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First Name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last Name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email Address'
            }),
        }


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'role',
            'person_identity',
            'facility',
            'population_group',
            'bio',
            'phone',
            'date_of_birth',
            'is_active',
            'must_change_password',
        ]
        widgets = {
            'role': forms.Select(attrs={
                'class': 'form-control'
            }),
            'person_identity': forms.Select(attrs={
                'class': 'form-control'
            }),
            'facility': forms.Select(attrs={
                'class': 'form-control'
            }),
            'population_group': forms.Select(attrs={
                'class': 'form-control'
            }),
            'bio': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Biography',
                'rows': 4
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone Number'
            }),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'must_change_password': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['person_identity'].queryset = PersonIdentity.objects.order_by('full_name', 'id')
        self.fields['person_identity'].required = False
        self.fields['facility'].queryset = Facility.objects.select_related('district__province').order_by(
            'district__province__name',
            'district__name',
            'name',
        )
        self.fields['facility'].required = False
        self.fields['population_group'].queryset = PopulationGroup.objects.filter(is_active=True).order_by('name')
        self.fields['population_group'].required = False

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        facility = cleaned_data.get('facility')
        if role in FACILITY_REQUIRED_ROLES and not facility:
            self.add_error('facility', 'Select the facility where this user works.')
        if role not in FACILITY_ASSIGNABLE_ROLES:
            cleaned_data['facility'] = None
        if role != 'client':
            cleaned_data['population_group'] = None
        return cleaned_data


class SelfProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['bio', 'phone', 'date_of_birth']
        widgets = {
            'bio': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Biography',
                'rows': 4,
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone Number',
            }),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
        }


class UserCreationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm Password'
        }),
        label='Confirm Password'
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Username'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email Address'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First Name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last Name'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError('Passwords do not match.')

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class PublicRegistrationForm(DjangoUserCreationForm):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email Address'
        })
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mobile number for OTP'
        })
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Username'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First Name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last Name'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm Password'
        })

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean_phone(self):
        phone = self.cleaned_data['phone'].strip()
        if UserProfile.objects.filter(phone__iexact=phone).exists():
            raise forms.ValidationError('An account with this mobile number already exists.')
        return phone


class AppointmentForm(forms.ModelForm):
    client = forms.ModelChoiceField(
        label='Client name',
        queryset=User.objects.none(),
        widget=forms.HiddenInput(attrs={
            'id': 'id_client',
        }),
        error_messages={
            'required': 'Select an active client.',
            'invalid_choice': 'Select a valid active client.',
        },
    )

    class Meta:
        model = Appointment
        fields = [
            'visit_purpose',
            'appointment_date',
            'appointment_time',
            'facility',
            'notes',
        ]
        widgets = {
            'visit_purpose': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_visit_purpose'
            }),
            'appointment_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'id': 'id_appointment_date',
                'min': timezone.localdate().isoformat(),
            }),
            'appointment_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time',
                'id': 'id_appointment_time'
            }),
            'facility': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_facility'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Appointment notes (optional)'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.created_by = kwargs.pop('created_by', None)
        super().__init__(*args, **kwargs)
        self.fields['client'].queryset = User.objects.select_related('profile').filter(
            profile__role='client',
            profile__is_active=True,
            is_active=True,
        ).order_by('first_name', 'last_name', 'username')
        self.fields['facility'].queryset = Facility.objects.select_related('district__province').prefetch_related('services').order_by(
            'district__province__name',
            'district__name',
            'name',
        )
        self.fields['visit_purpose'].choices = Appointment.VISIT_PURPOSE_CHOICES
        self.fields['notes'].required = False
        self.fields['appointment_date'].widget = forms.HiddenInput(attrs={
            'id': 'id_appointment_date',
        })
        for field in self.fields.values():
            if not field.widget.attrs.get('class'):
                field.widget.attrs['class'] = 'form-control'

        if self.instance and self.instance.pk:
            self.fields['client'].initial = self.instance.beneficiary
        elif self.created_by and hasattr(self.created_by, 'profile') and self.created_by.profile.facility_id:
            facility = self.created_by.profile.facility
            self.fields['facility'].initial = facility.pk

    def clean(self):
        cleaned_data = super().clean()
        facility = cleaned_data.get('facility')
        visit_purpose = cleaned_data.get('visit_purpose')
        if facility and visit_purpose:
            active_services = facility.services.filter(is_active=True)
            if not active_services.filter(code=visit_purpose).exists():
                self.add_error('facility', 'Select a facility that provides this appointment service.')
        return cleaned_data

    def save(self, commit=True):
        appointment = super().save(commit=False)
        appointment.beneficiary = self.cleaned_data['client']
        appointment.district = appointment.facility.district
        appointment.province = appointment.facility.district.province
        if self.created_by and not appointment.created_by_id:
            appointment.created_by = self.created_by
        if commit:
            appointment.save()
            self.save_m2m()
        return appointment


class ClientAppointmentForm(AppointmentForm):
    class Meta(AppointmentForm.Meta):
        fields = [
            'visit_purpose',
            'appointment_date',
            'appointment_time',
            'facility',
            'notes',
        ]

    def __init__(self, *args, **kwargs):
        self.client = kwargs.pop('client')
        super().__init__(*args, **kwargs)
        self.fields.pop('client', None)
        self.fields['appointment_date'].widget = forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'min': timezone.localdate().isoformat(),
        })

    def save(self, commit=True):
        appointment = forms.ModelForm.save(self, commit=False)
        appointment.beneficiary = self.client
        appointment.district = appointment.facility.district
        appointment.province = appointment.facility.district.province
        if self.created_by and not appointment.created_by_id:
            appointment.created_by = self.created_by
        if commit:
            appointment.save()
            self.save_m2m()
        return appointment


class AppointmentEditForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['visit_purpose', 'appointment_date', 'appointment_time', 'status']
        widgets = {
            'visit_purpose': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_edit_visit_purpose',
            }),
            'appointment_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'id': 'id_edit_appointment_date',
                'min': timezone.localdate().isoformat(),
            }),
            'appointment_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time',
                'id': 'id_edit_appointment_time',
            }),
            'status': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_edit_status',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        appointment_date = cleaned_data.get('appointment_date')
        appointment_time = cleaned_data.get('appointment_time')
        visit_purpose = cleaned_data.get('visit_purpose')
        status = cleaned_data.get('status')
        facility = self.instance.facility
        if status == 'upcoming' and appointment_date and appointment_time:
            appointment_datetime = timezone.make_aware(
                datetime.combine(appointment_date, appointment_time),
                timezone.get_current_timezone(),
            )
            if appointment_datetime <= timezone.now():
                self.add_error('appointment_date', 'Appointments cannot be scheduled in the past.')
                self.add_error('appointment_time', 'Choose a future appointment time.')
        if facility and visit_purpose:
            active_services = facility.services.filter(is_active=True)
            if not active_services.filter(code=visit_purpose).exists():
                self.add_error('visit_purpose', 'This facility is not mapped to that service.')
        return cleaned_data


class ClientLocatorForm(forms.ModelForm):
    class Meta:
        model = ClientLocator
        fields = [
            'location_notes',
            'preferred_visit_time',
            'mobiliser_zone',
            'service_point',
            'preferred_contact_method',
            'outreach_follow_up_details',
        ]
        widgets = {
            'location_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'preferred_visit_time': forms.TextInput(attrs={'class': 'form-control'}),
            'mobiliser_zone': forms.TextInput(attrs={'class': 'form-control'}),
            'service_point': forms.Select(attrs={'class': 'form-select'}),
            'preferred_contact_method': forms.Select(attrs={'class': 'form-select'}),
            'outreach_follow_up_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['service_point'].queryset = Facility.objects.select_related('district__province').order_by(
            'district__province__name',
            'district__name',
            'name',
        )
        self.fields['service_point'].required = False


class ClientJourneyEventForm(forms.ModelForm):
    class Meta:
        model = ClientJourneyEvent
        fields = ['stage', 'event_date', 'outcome', 'notes']
        widgets = {
            'stage': forms.Select(attrs={'class': 'form-select'}),
            'event_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'outcome': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class ReferralRecordForm(forms.ModelForm):
    class Meta:
        model = ReferralRecord
        fields = [
            'receiving_facility',
            'assigned_mobiliser',
            'confirmation_status',
            'initiation_outcome',
            'referred_on',
            'notes',
        ]
        widgets = {
            'receiving_facility': forms.Select(attrs={'class': 'form-select'}),
            'assigned_mobiliser': forms.Select(attrs={'class': 'form-select'}),
            'confirmation_status': forms.Select(attrs={'class': 'form-select'}),
            'initiation_outcome': forms.Select(attrs={'class': 'form-select'}),
            'referred_on': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['receiving_facility'].queryset = Facility.objects.select_related(
            'district',
            'district__province',
        ).order_by('district__province__name', 'district__name', 'name')
        self.fields['receiving_facility'].required = True
        self.fields['receiving_facility'].label = 'Receiving facility / service point'
        self.fields['assigned_mobiliser'].queryset = User.objects.select_related('profile').filter(
            profile__role='mobiliser',
            profile__is_active=True,
            is_active=True,
        ).order_by('first_name', 'last_name', 'username')
        self.fields['assigned_mobiliser'].required = False


class ReferralConfirmationForm(forms.ModelForm):
    class Meta:
        model = ReferralRecord
        fields = ['confirmation_status', 'initiation_outcome', 'notes']
        widgets = {
            'confirmation_status': forms.Select(attrs={'class': 'form-select'}),
            'initiation_outcome': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }


class FollowUpTaskForm(forms.ModelForm):
    class Meta:
        model = FollowUpTask
        fields = ['assigned_to', 'reason', 'status', 'priority', 'due_date', 'notes', 'outcome_notes']
        widgets = {
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'outcome_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = User.objects.select_related('profile').filter(
            profile__role__in=FACILITY_USER_ROLES,
            profile__is_active=True,
            is_active=True,
        ).order_by('first_name', 'last_name', 'username')
        self.fields['assigned_to'].required = False


class ClientConsentForm(forms.ModelForm):
    class Meta:
        model = ClientConsent
        fields = [
            'code_based_management',
            'consent_to_follow_up',
            'consent_to_sms',
            'consent_to_whatsapp',
            'share_with_facility',
            'privacy_notes',
        ]
        widgets = {
            'code_based_management': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'consent_to_follow_up': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'consent_to_sms': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'consent_to_whatsapp': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'share_with_facility': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'privacy_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class SafeguardingReportForm(forms.ModelForm):
    class Meta:
        model = SafeguardingCase
        fields = [
            'incident_type',
            'incident_date',
            'location',
            'severity',
            'involved_parties',
            'incident_details',
        ]
        widgets = {
            'incident_type': forms.Select(attrs={'class': 'form-select'}),
            'incident_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional location or service point'}),
            'severity': forms.Select(attrs={'class': 'form-select'}),
            'involved_parties': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'incident_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def clean_incident_date(self):
        incident_date = self.cleaned_data.get('incident_date')
        if incident_date and incident_date > timezone.localdate():
            raise forms.ValidationError('Incident date cannot be in the future.')
        return incident_date


class SafeguardingCaseUpdateForm(forms.ModelForm):
    class Meta:
        model = SafeguardingCase
        fields = [
            'focal_point',
            'status',
            'severity',
            'confidentiality_locked',
            'risk_trigger_flag',
            'cab_oversight_ready',
            'resolution_notes',
        ]
        widgets = {
            'focal_point': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'severity': forms.Select(attrs={'class': 'form-select'}),
            'confidentiality_locked': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'risk_trigger_flag': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'cab_oversight_ready': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'resolution_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['focal_point'].queryset = User.objects.filter(
            profile__role__in=['admin', 'supervisor', 'provider', 'chw']
        ).order_by('first_name', 'last_name', 'username')
        self.fields['focal_point'].required = False


class GrievanceSubmissionForm(forms.ModelForm):
    class Meta:
        model = GrievanceCase
        fields = ['submission_channel', 'category', 'priority', 'complaint_details', 'district']
        widgets = {
            'submission_channel': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'complaint_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'district': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['district'].queryset = District.objects.select_related('province').order_by(
            'province__name',
            'name',
        )
        self.fields['district'].required = False


class GrievanceCaseUpdateForm(forms.ModelForm):
    class Meta:
        model = GrievanceCase
        fields = [
            'assigned_to',
            'status',
            'priority',
            'response_provided',
            'escalation_target',
            'resolution_notes',
        ]
        widgets = {
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'response_provided': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'escalation_target': forms.Select(attrs={'class': 'form-select'}),
            'resolution_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = User.objects.filter(
            profile__role__in=['admin', 'supervisor', 'provider', 'chw']
        ).order_by('first_name', 'last_name', 'username')
        self.fields['assigned_to'].required = False


class ClientExitInterviewForm(forms.ModelForm):
    class Meta:
        model = ClientExitInterview
        fields = [
            'client_code',
            'service_point_type',
            'service_point',
            'population_group',
            'waiting_time_rating',
            'staff_attitude_rating',
            'privacy_respected',
            'information_clarity_score',
            'len_questions_understood',
            'net_promoter_score',
            'comments',
        ]
        widgets = {
            'client_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional client code'}),
            'service_point_type': forms.Select(attrs={'class': 'form-select'}),
            'service_point': forms.Select(attrs={'class': 'form-select'}),
            'population_group': forms.Select(attrs={'class': 'form-select'}),
            'waiting_time_rating': forms.Select(attrs={'class': 'form-select'}),
            'staff_attitude_rating': forms.Select(attrs={'class': 'form-select'}),
            'privacy_respected': forms.Select(attrs={'class': 'form-select'}),
            'information_clarity_score': forms.Select(attrs={'class': 'form-select'}),
            'len_questions_understood': forms.Select(attrs={'class': 'form-select'}),
            'net_promoter_score': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '10'}),
            'comments': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['service_point'].queryset = Facility.objects.select_related('district__province').order_by(
            'district__province__name',
            'district__name',
            'name',
        )
        self.fields['service_point'].required = False
        self.fields['population_group'].queryset = PopulationGroup.objects.filter(is_active=True).order_by('name')
        self.fields['population_group'].required = False

    def clean_net_promoter_score(self):
        score = self.cleaned_data['net_promoter_score']
        if score < 0 or score > 10:
            raise forms.ValidationError('Net promoter score must be between 0 and 10.')
        return score


class SelfRiskAssessmentForm(forms.Form):
    YES_NO_CHOICES = (
        ('', 'Select an answer'),
        ('yes', 'Yes'),
        ('no', 'No'),
        ('unsure', 'Not sure'),
    )
    CONDOM_CHOICES = (
        ('', 'Select an answer'),
        ('always', 'Always'),
        ('sometimes', 'Sometimes'),
        ('rarely', 'Rarely or never'),
        ('not_active', 'Not sexually active'),
    )
    PARTNER_CHOICES = (
        ('', 'Select an answer'),
        ('0', 'None'),
        ('1', 'One'),
        ('2_4', 'Two to four'),
        ('5_plus', 'Five or more'),
    )
    TEST_CHOICES = (
        ('', 'Select an answer'),
        ('3_months', 'Within the last 3 months'),
        ('12_months', 'Within the last 12 months'),
        ('over_12_months', 'More than 12 months ago'),
        ('never', 'Never tested'),
    )
    PREP_CHOICES = (
        ('', 'Select an answer'),
        ('yes_current', 'Yes, I am currently using PrEP'),
        ('yes_past', 'I used PrEP before'),
        ('no', 'No'),
        ('unsure', 'Not sure'),
    )

    recent_test = forms.ChoiceField(
        label='When was your most recent HIV test?',
        choices=TEST_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    partners = forms.ChoiceField(
        label='How many sexual partners have you had in the last 6 months?',
        choices=PARTNER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    condom_use = forms.ChoiceField(
        label='How often do you use condoms during sex?',
        choices=CONDOM_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    partner_status = forms.ChoiceField(
        label='Do you have a partner whose HIV status is positive or unknown?',
        choices=YES_NO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    sti_symptoms = forms.ChoiceField(
        label='Have you had STI symptoms or treatment in the last 6 months?',
        choices=YES_NO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    prep_use = forms.ChoiceField(
        label='Are you currently using PrEP or another HIV prevention medicine?',
        choices=PREP_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    pregnancy_or_breastfeeding = forms.ChoiceField(
        label='Are you pregnant, trying to become pregnant, or breastfeeding?',
        choices=YES_NO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    safety_concerns = forms.ChoiceField(
        label='Do you feel unsafe discussing HIV prevention with a partner?',
        choices=YES_NO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class SelfTestReportForm(forms.Form):
    TEST_TYPE_CHOICES = (
        ('', 'Select test type'),
        ('oral_fluid', 'Oral fluid self-test'),
        ('finger_prick', 'Finger-prick blood self-test'),
        ('unknown', 'Not sure'),
    )
    RESULT_CHOICES = (
        ('', 'Select result'),
        ('negative', 'Negative'),
        ('positive', 'Positive / reactive'),
        ('invalid', 'Invalid / unclear'),
        ('not_read', 'I have not read it yet'),
    )
    YES_NO_CHOICES = (
        ('', 'Select an answer'),
        ('yes', 'Yes'),
        ('no', 'No'),
        ('unsure', 'Not sure'),
    )
    SOURCE_CHOICES = (
        ('', 'Select source'),
        ('clinic', 'Clinic or health facility'),
        ('chw', 'Community health worker'),
        ('pharmacy', 'Pharmacy'),
        ('friend_partner', 'Friend or partner'),
        ('other', 'Other'),
    )

    test_type = forms.ChoiceField(
        label='What type of self-test did you use?',
        choices=TEST_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    kit_source = forms.ChoiceField(
        label='Where did you get the self-test kit?',
        choices=SOURCE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    test_date = forms.DateField(
        label='When did you take the test?',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    result = forms.ChoiceField(
        label='What was the self-test result?',
        choices=RESULT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    followed_instructions = forms.ChoiceField(
        label='Did you follow the kit instructions and timing?',
        choices=YES_NO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    confirmatory_test = forms.ChoiceField(
        label='Have you had a confirmatory HIV test at a clinic?',
        choices=YES_NO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    support_needed = forms.ChoiceField(
        label='Would you like support from a health worker?',
        choices=YES_NO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    notes = forms.CharField(
        label='Notes',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Optional notes about the kit, timing, or support needed',
        }),
    )

    def clean_test_date(self):
        test_date = self.cleaned_data['test_date']
        if test_date > timezone.localdate():
            raise forms.ValidationError('Test date cannot be in the future.')
        return test_date


class SideEffectReportForm(forms.Form):
    PREVENTION_METHOD_CHOICES = (
        ('', 'Select method'),
        ('oral_prep', 'Oral PrEP'),
        ('cab_la', 'CAB-LA Injectable'),
        ('dapivirine_ring', 'Dapivirine Ring'),
        ('lenacapavir', 'Lenacapavir Injectable (LEN)'),
        ('pep', 'PEP'),
        ('other', 'Other HIV prevention medicine'),
        ('unsure', 'Not sure'),
    )
    SEVERITY_CHOICES = (
        ('', 'Select severity'),
        ('mild', 'Mild - I can continue normal activities'),
        ('moderate', 'Moderate - it affects my activities'),
        ('severe', 'Severe - I need urgent help'),
    )
    YES_NO_CHOICES = (
        ('', 'Select an answer'),
        ('yes', 'Yes'),
        ('no', 'No'),
        ('unsure', 'Not sure'),
    )
    OUTCOME_CHOICES = (
        ('', 'Select current status'),
        ('ongoing', 'Still happening'),
        ('improving', 'Improving'),
        ('resolved', 'Resolved'),
        ('worse', 'Getting worse'),
    )

    prevention_method = forms.ChoiceField(
        label='Which prevention medicine or product are you using?',
        choices=PREVENTION_METHOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    symptom_start_date = forms.DateField(
        label='When did the side effect start?',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    symptoms = forms.CharField(
        label='What side effects are you experiencing?',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Describe the symptoms, body area, and anything that makes them better or worse',
        }),
    )
    severity = forms.ChoiceField(
        label='How severe are the symptoms?',
        choices=SEVERITY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    status = forms.ChoiceField(
        label='What is the current status?',
        choices=OUTCOME_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    urgent_symptoms = forms.ChoiceField(
        label='Do you have trouble breathing, chest pain, fainting, swelling, or severe rash?',
        choices=YES_NO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    stopped_medicine = forms.ChoiceField(
        label='Have you stopped or missed the medicine because of this?',
        choices=YES_NO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    facility_visit = forms.ChoiceField(
        label='Have you visited a clinic or health worker about this?',
        choices=YES_NO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    support_needed = forms.ChoiceField(
        label='Would you like a health worker to follow up?',
        choices=YES_NO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    contact_preference = forms.CharField(
        label='Preferred contact method',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Phone, SMS, WhatsApp, or preferred clinic',
        }),
    )

    def clean_symptom_start_date(self):
        symptom_start_date = self.cleaned_data['symptom_start_date']
        if symptom_start_date > timezone.localdate():
            raise forms.ValidationError('Symptom start date cannot be in the future.')
        return symptom_start_date


class ClinicFeedbackForm(forms.Form):
    RATING_CHOICES = (
        ('', 'Select rating'),
        ('5', '5 - Excellent'),
        ('4', '4 - Good'),
        ('3', '3 - Fair'),
        ('2', '2 - Poor'),
        ('1', '1 - Very poor'),
    )
    YES_NO_CHOICES = (
        ('', 'Select an answer'),
        ('yes', 'Yes'),
        ('no', 'No'),
    )
    VISIT_REASON_CHOICES = (
        ('', 'Select visit reason'),
        ('testing', 'HIV testing'),
        ('prep', 'PrEP or prevention services'),
        ('follow_up', 'Follow-up visit'),
        ('side_effects', 'Side effects or urgent care'),
        ('other', 'Other service'),
    )

    facility = forms.ModelChoiceField(
        label='Which clinic did you visit?',
        queryset=Facility.objects.none(),
        empty_label='Select clinic',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    visit_date = forms.DateField(
        label='When did you visit?',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    visit_reason = forms.ChoiceField(
        label='What was the main reason for your visit?',
        choices=VISIT_REASON_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    overall_rating = forms.ChoiceField(
        label='Overall, how would you rate the clinic service?',
        choices=RATING_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    wait_time_rating = forms.ChoiceField(
        label='How would you rate the waiting time?',
        choices=RATING_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    staff_respect_rating = forms.ChoiceField(
        label='How would you rate staff respect and privacy?',
        choices=RATING_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    medicine_availability = forms.ChoiceField(
        label='Were the services or medicines you needed available?',
        choices=YES_NO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    would_recommend = forms.ChoiceField(
        label='Would you recommend this clinic to someone else?',
        choices=YES_NO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    follow_up_needed = forms.ChoiceField(
        label='Would you like a supervisor or health worker to follow up?',
        choices=YES_NO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    comments = forms.CharField(
        label='Comments',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Share what went well, what could improve, or what support you need',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['facility'].queryset = Facility.objects.all().order_by(
            'district__province__name',
            'district__name',
            'name',
        )

    def clean_visit_date(self):
        visit_date = self.cleaned_data['visit_date']
        if visit_date > timezone.localdate():
            raise forms.ValidationError('Visit date cannot be in the future.')
        return visit_date
