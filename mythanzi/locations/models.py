from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Province(models.Model):
    name = models.CharField(max_length=200, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class District(models.Model):
    name = models.CharField(max_length=200)
    province = models.ForeignKey(Province, on_delete=models.CASCADE, related_name='districts')

    class Meta:
        unique_together = ('name', 'province')
        ordering = ['province__name', 'name']

    def __str__(self):
        return f"{self.name} ({self.province.name})"


class Service(models.Model):
    name = models.CharField(max_length=200, unique=True)
    code = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Facility(models.Model):
    FACILITY_TYPE_HUB = 'hub'
    FACILITY_TYPE_SPOKE = 'spoke'
    FACILITY_TYPE_NA = 'na'
    FACILITY_TYPE_CHOICES = [
        (FACILITY_TYPE_HUB, 'Hub'),
        (FACILITY_TYPE_SPOKE, 'Spoke'),
        (FACILITY_TYPE_NA, 'N/A'),
    ]
    HUB_SPOKE_SERVICE_CODES = [
        'clinical-follow-up',
        'clinical_review',
        'follow_up',
        'hiv-testing',
        'lab_collection',
        'medication_refill',
        'prep-len',
    ]

    name = models.CharField(max_length=255)
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='facilities')
    services = models.ManyToManyField(Service, blank=True, related_name='facilities')
    code = models.CharField(max_length=64, blank=True, null=True)
    level = models.CharField(max_length=100, blank=True, null=True)
    facility_type = models.CharField(max_length=10, choices=FACILITY_TYPE_CHOICES, default=FACILITY_TYPE_NA)
    hub = models.ForeignKey(
        'self',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='spokes',
        limit_choices_to={'facility_type': FACILITY_TYPE_HUB},
    )
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('name', 'district')
        ordering = ['district__province__name', 'district__name', 'name']

    def __str__(self):
        return f"{self.name} ({self.district.name})"

    def clean(self):
        super().clean()
        if self.hub_id and self.hub_id == self.pk:
            raise ValidationError({'hub': 'A facility cannot be its own hub.'})
        if self.facility_type != self.FACILITY_TYPE_SPOKE and self.hub_id:
            raise ValidationError({'hub': 'Only spoke facilities can be assigned to a hub.'})
        if self.hub and self.hub.facility_type != self.FACILITY_TYPE_HUB:
            raise ValidationError({'hub': 'Select a facility marked as a hub.'})

    def apply_hub_spoke_services(self):
        if self.facility_type not in {self.FACILITY_TYPE_HUB, self.FACILITY_TYPE_SPOKE}:
            return
        services = Service.objects.filter(code__in=self.HUB_SPOKE_SERVICE_CODES)
        if services:
            self.services.add(*services)


@receiver(post_save, sender=Facility)
def apply_hub_spoke_services(sender, instance, **kwargs):
    instance.apply_hub_spoke_services()
