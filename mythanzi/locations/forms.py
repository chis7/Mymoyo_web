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
    class Meta:
        model = Facility
        fields = ['name', 'district', 'services', 'code', 'level', 'latitude', 'longitude']
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
