from django.contrib import admin
from .models import Province, District, Facility, Service


class DistrictInline(admin.TabularInline):
    model = District
    extra = 1
    fields = ('name',)
    show_change_link = True


class FacilityInline(admin.TabularInline):
    model = Facility
    extra = 1
    fields = ('name', 'code', 'level', 'latitude', 'longitude')
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
    list_display = ('name', 'district', 'code', 'level', 'latitude', 'longitude')
    list_filter = ('district__province', 'district', 'services')
    search_fields = ('name', 'code', 'district__name', 'district__province__name', 'services__name')
    filter_horizontal = ('services',)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'description')
