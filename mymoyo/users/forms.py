from django import forms
from django.contrib.auth.forms import UserCreationForm as DjangoUserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from .models import UserProfile, Appointment
from locations.models import Province, District, Facility


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
        fields = ['role', 'bio', 'phone', 'date_of_birth', 'is_active', 'must_change_password']
        widgets = {
            'role': forms.Select(attrs={
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

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']
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


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = [
            'beneficiary',
            'visit_purpose',
            'appointment_date',
            'appointment_time',
            'province',
            'district',
            'facility',
            'notes',
        ]
        widgets = {
            'beneficiary': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_beneficiary'
            }),
            'visit_purpose': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_visit_purpose'
            }),
            'appointment_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'id': 'id_appointment_date'
            }),
            'appointment_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time',
                'id': 'id_appointment_time'
            }),
            'province': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_province'
            }),
            'district': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_district'
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
        super().__init__(*args, **kwargs)
        self.fields['beneficiary'].queryset = User.objects.all().order_by('username')
        self.fields['province'].queryset = Province.objects.all().order_by('name')
        self.fields['district'].queryset = District.objects.all().order_by('province__name', 'name')
        self.fields['facility'].queryset = Facility.objects.all().order_by('district__province__name', 'district__name', 'name')
        self.fields['visit_purpose'].choices = Appointment.VISIT_PURPOSE_CHOICES
        self.fields['notes'].required = False
        for field in self.fields.values():
            if not field.widget.attrs.get('class'):
                field.widget.attrs['class'] = 'form-control'


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
