from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Appointment, AuditLog, UserProfile
from locations.models import Province, District, Facility

admin.site.site_header = 'My Moyo Admin'
admin.site.site_title = 'My Moyo Admin Portal'
admin.site.index_title = 'Manage users, locations and appointments'


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'


class CustomUserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_role')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'profile__phone')

    def get_role(self, obj):
        return obj.profile.role if hasattr(obj, 'profile') else ''
    get_role.short_description = 'Role'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone', 'is_active', 'must_change_password', 'created_at')
    list_filter = ('role', 'is_active', 'must_change_password', 'created_at')
    search_fields = ('user__username', 'user__email', 'phone')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Profile Information', {
            'fields': ('role', 'bio', 'phone', 'date_of_birth', 'is_active', 'must_change_password')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('beneficiary', 'visit_purpose', 'appointment_date', 'appointment_time', 'status', 'province', 'district', 'facility')
    list_filter = ('status', 'visit_purpose', 'province', 'district', 'facility')
    search_fields = ('beneficiary__username', 'beneficiary__email', 'notes')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Appointment Info', {
            'fields': ('beneficiary', 'visit_purpose', 'appointment_date', 'appointment_time', 'status')
        }),
        ('Location', {
            'fields': ('province', 'district', 'facility')
        }),
        ('Notes & Timestamps', {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'app_label', 'model_name', 'object_repr', 'actor')
    list_filter = ('action', 'app_label', 'model_name', 'created_at')
    search_fields = ('object_repr', 'object_pk', 'actor__username', 'actor__email')
    readonly_fields = (
        'action',
        'app_label',
        'model_name',
        'object_pk',
        'object_repr',
        'actor',
        'changes',
        'snapshot',
        'created_at',
    )
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
