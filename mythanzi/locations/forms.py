from django import forms

from .models import District, Facility, Province, Service


class ProvinceForm(forms.ModelForm):
    class Meta:
        model = Province
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Province name',
            }),
        }


class DistrictForm(forms.ModelForm):
    class Meta:
        model = District
        fields = ['name', 'province']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'District name',
            }),
            'province': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['province'].queryset = Province.objects.order_by('name')


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['name', 'code', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Service name',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Service code',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional service description',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class FacilityForm(forms.ModelForm):
    spokes = forms.ModelMultipleChoiceField(
        queryset=Facility.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-select js-spokes-multiselect',
            'size': 8,
        }),
        help_text='Select facilities to assign as spokes for this hub.',
    )

    class Meta:
        model = Facility
        fields = ['name', 'district', 'services', 'code', 'level', 'facility_type', 'hub', 'spokes', 'latitude', 'longitude']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Facility name',
            }),
            'district': forms.Select(attrs={'class': 'form-select'}),
            'services': forms.CheckboxSelectMultiple(),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'MFL code',
            }),
            'level': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Facility level',
            }),
            'facility_type': forms.Select(attrs={'class': 'form-select'}),
            'hub': forms.Select(attrs={'class': 'form-select'}),
            'latitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Latitude',
                'step': '0.0000001',
            }),
            'longitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Longitude',
                'step': '0.0000001',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['district'].queryset = District.objects.select_related('province').order_by(
            'province__name',
            'name',
        )
        self.fields['services'].queryset = Service.objects.filter(is_active=True).order_by('name')
        self.fields['hub'].queryset = Facility.objects.filter(
            facility_type=Facility.FACILITY_TYPE_HUB,
        ).select_related('district__province').order_by(
            'district__province__name',
            'district__name',
            'name',
        )
        if self.instance.pk:
            self.fields['hub'].queryset = self.fields['hub'].queryset.exclude(pk=self.instance.pk)
        self.fields['spokes'].queryset = Facility.objects.exclude(
            facility_type=Facility.FACILITY_TYPE_HUB,
        ).select_related('district__province').order_by(
            'district__province__name',
            'district__name',
            'name',
        )
        if self.instance.pk:
            self.fields['spokes'].queryset = self.fields['spokes'].queryset.exclude(pk=self.instance.pk)
            self.fields['spokes'].initial = self.instance.spokes.all()

    def clean(self):
        cleaned_data = super().clean()
        facility_type = cleaned_data.get('facility_type')
        spokes = cleaned_data.get('spokes')
        if facility_type != Facility.FACILITY_TYPE_SPOKE:
            cleaned_data['hub'] = None
        if facility_type != Facility.FACILITY_TYPE_HUB:
            cleaned_data['spokes'] = Facility.objects.none()
        elif spokes and spokes.filter(facility_type=Facility.FACILITY_TYPE_HUB).exists():
            self.add_error('spokes', 'Hub facilities cannot be assigned as spokes.')
        return cleaned_data

    def save(self, commit=True):
        selected_spokes = list(self.cleaned_data.get('spokes') or [])
        facility = super().save(commit=False)
        if facility.facility_type != Facility.FACILITY_TYPE_SPOKE:
            facility.hub = None
        if commit:
            facility.save()
            self.save_m2m()
            if facility.facility_type == Facility.FACILITY_TYPE_HUB:
                selected_spoke_ids = [spoke.pk for spoke in selected_spokes]
                facility.spokes.exclude(pk__in=selected_spoke_ids).update(hub=None)
                Facility.objects.filter(pk__in=selected_spoke_ids).exclude(
                    facility_type=Facility.FACILITY_TYPE_HUB,
                ).update(
                    facility_type=Facility.FACILITY_TYPE_SPOKE,
                    hub_id=facility.pk,
                )
                for spoke in Facility.objects.filter(pk__in=selected_spoke_ids):
                    spoke.apply_hub_spoke_services()
            facility.apply_hub_spoke_services()
        return facility
