from django.db import models


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
    name = models.CharField(max_length=255)
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='facilities')
    services = models.ManyToManyField(Service, blank=True, related_name='facilities')
    code = models.CharField(max_length=64, blank=True, null=True)
    level = models.CharField(max_length=100, blank=True, null=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('name', 'district')
        ordering = ['district__province__name', 'district__name', 'name']

    def __str__(self):
        return f"{self.name} ({self.district.name})"
