from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import User, PWDCertificate, Notification, AuditLog, RewardPoint, Announcement

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'role_badge', 'city', 'state', 'is_verified_badge', 'is_staff')
    list_filter = ('role', 'city', 'state', 'is_verified', 'is_staff')
    search_fields = ('username', 'email', 'phone_number')
    
    fieldsets = UserAdmin.fieldsets + (
        ('Professional Role & Verification', {
            'fields': (('role', 'is_verified', 'verification_badge'), 'phone_number'),
            'description': 'Manage identity and jurisdictional assignments.'
        }),
        ('Location Assignment', {
            'fields': (('state', 'city'),),
        }),
        ('Personal Assets', {
            'fields': ('avatar',),
        }),
    )
    
    def role_badge(self, obj):
        colors = {'citizen': '#4a148c', 'officer': '#006064', 'admin': '#bf360c', 'superadmin': '#b71c1c'}
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 10px; font-size: 10px; text-transform: uppercase;">{}</span>',
            colors.get(obj.role, '#757575'),
            obj.get_role_display()
        )
    role_badge.short_description = 'Designation'

    def is_verified_badge(self, obj):
        if obj.is_verified:
            return format_html('<span style="color: green;">✔ Verified</span>')
        return format_html('<span style="color: red;">✘ Unverified</span>')
    is_verified_badge.short_description = 'Verification'

@admin.register(PWDCertificate)
class PWDCertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_number', 'user', 'disability_type', 'verification_status', 'is_fake')
    list_filter = ('verification_status', 'is_fake', 'disability_type')
    search_fields = ('certificate_number', 'user__username', 'extracted_name')
    actions = ['approve_certificates', 'reject_certificates', 'flag_as_fake']
    readonly_fields = ('ocr_raw_text', 'ocr_confidence')

    def approve_certificates(self, request, queryset):
        for cert in queryset:
            cert.verification_status = 'approved'
            cert.is_fake = False
            cert.save()
            cert.user.is_verified = True
            cert.user.verification_badge = True
            cert.user.save()
        self.message_user(request, "Selected certificates have been approved.")
    approve_certificates.short_description = "Approve certificates & verify users"

    def reject_certificates(self, request, queryset):
        queryset.update(verification_status='rejected')
        for cert in queryset:
            cert.user.is_verified = False
            cert.user.save()
        self.message_user(request, "Selected certificates rejected.")
    reject_certificates.short_description = "Reject selected"

    def flag_as_fake(self, request, queryset):
        queryset.update(verification_status='rejected', is_fake=True)
        self.message_user(request, "Flagged as FAKE.")

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'ip_address')
    readonly_fields = ('user', 'action', 'ip_address', 'user_agent', 'details', 'timestamp')

@admin.register(RewardPoint)
class RewardPointAdmin(admin.ModelAdmin):
    list_display = ('user', 'points', 'reason', 'awarded_at')
    list_filter = ('awarded_at',)
    search_fields = ('user__username', 'reason')

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_critical', 'created_at')
    list_filter = ('is_critical',)

admin.site.register(User, CustomUserAdmin)
