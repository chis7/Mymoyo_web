from django.contrib import admin

from .forms import FacilityForm
from .models import Province, District, Facility, Service


class DistrictInline(admin.TabularInline):
    model = District
    extra = 1
    fields = ('name',)
    show_change_link = True


class FacilityInline(admin.TabularInline):
    model = Facility
    extra = 1
    fields = ('name', 'code', 'level', 'facility_type', 'hub', 'latitude', 'longitude')
    show_change_link = True


class SpokeInline(admin.TabularInline):
    model = Facility
    fk_name = 'hub'
    extra = 0
    fields = ('name', 'district', 'code', 'level', 'facility_type')
    show_change_link = True


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    inlines = (DistrictInline,)


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ('name', 'province')
    list_filter = ('province',)
    search_fields = ('name', 'province__name')
    inlines = (FacilityInline,)


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    form = FacilityForm
    list_display = ('name', 'district', 'code', 'level', 'facility_type', 'hub', 'latitude', 'longitude')
    list_filter = ('facility_type', 'hub', 'district__province', 'district', 'services')
    search_fields = ('name', 'code', 'hub__name', 'district__name', 'district__province__name', 'services__name')
    filter_horizontal = ('services',)
    inlines = (SpokeInline,)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'description')
