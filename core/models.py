from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = [
        ('citizen', 'Citizen / PWD User'),
        ('officer', 'Field Officer'),
        ('admin', 'System Admin'),
        ('superadmin', 'Super Admin'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='citizen')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    verification_badge = models.BooleanField(default=False)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True, help_text="State assignment for officers/admins")
    city = models.CharField(max_length=100, blank=True, null=True, help_text="City assignment for officers/admins")

    def save(self, *args, **kwargs):
        # Admins, officers, and superadmins are auto-verified
        if self.role in ['officer', 'admin', 'superadmin']:
            self.is_verified = True
            self.verification_badge = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class PWDCertificate(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='pwd_certificate')
    certificate_number = models.CharField(max_length=50, unique=True)
    certificate_file = models.FileField(upload_to='certificates/')
    disability_type = models.CharField(max_length=100)
    disability_percentage = models.PositiveIntegerField(default=40)
    
    # OCR Extracted Fields
    extracted_name = models.CharField(max_length=255, blank=True, null=True)
    extracted_disability_type = models.CharField(max_length=100, blank=True, null=True)
    extracted_certificate_number = models.CharField(max_length=50, blank=True, null=True)
    ocr_confidence = models.FloatField(default=0.0)
    ocr_raw_text = models.TextField(blank=True, null=True)
    
    # Verification Fields
    verification_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True, null=True)
    is_fake = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Certificate {self.certificate_number} for {self.user.username}"


class Notification(models.Model):
    TYPE_CHOICES = [
        ('info', 'Information'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('danger', 'Alert'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.username}: {self.title}"


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    details = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        actor = self.user.username if self.user else "Anonymous"
        return f"{actor} performed {self.action} at {self.timestamp}"

class RewardPoint(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reward_points')
    points = models.IntegerField(default=0)
    reason = models.CharField(max_length=255)
    awarded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.points} to {self.user.username} for {self.reason}"

class Announcement(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_critical = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
