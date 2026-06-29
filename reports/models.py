from django.db import models
from django.conf import settings

class Report(models.Model):
    CATEGORY_CHOICES = [
        ('ramp', 'Ramp issue'),
        ('toilet', 'Toilet inaccessible'),
        ('tactile', 'Tactile paving missing'),
        ('elevator', 'Elevator not working'),
        ('parking', 'Parking accessibility'),
        ('transport', 'Public transport accessibility'),
        ('footpath', 'Footpath obstruction'),
        ('railway', 'Railway accessibility'),
    ]

    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('verified', 'Verified Barrier'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected'),
    ]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports'
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    
    # Location details
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    address = models.TextField(blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True, help_text="State where the issue was reported")
    city = models.CharField(max_length=100, blank=True, null=True, help_text="City where the issue was reported")
    
    is_anonymous = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Escalation tracking
    escalation_level = models.IntegerField(default=0)
    next_escalation_at = models.DateTimeField(blank=True, null=True)
    
    # Advanced AI-Driven scores and summaries
    priority_score = models.IntegerField(default=0)
    ai_summary = models.TextField(blank=True, null=True)
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sla_deadline = models.DateTimeField(null=True, blank=True)
    is_escalated = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.get_category_display()} ({self.get_status_display()})"

    def calculate_priority_score(self):
        # Calculate a priority score between 0 and 100 based on severity, status, and local report duplicates
        severity_weights = {'low': 10, 'medium': 30, 'high': 60, 'critical': 95}
        base_score = severity_weights.get(self.severity, 30)
        
        # Boost priority if there are other reports in the same location (crowd urgency)
        surrounding_reports = Report.objects.filter(
            category=self.category,
            status='verified'
        ).exclude(id=self.id)
        
        # Simple proximity check if coordinates exist
        proximity_boost = 0
        if self.latitude and self.longitude:
            for rep in surrounding_reports:
                if rep.latitude and rep.longitude:
                    dist = abs(self.latitude - rep.latitude) + abs(self.longitude - rep.longitude)
                    if dist < 0.005:  # within ~500m
                        proximity_boost += 5
        
        self.priority_score = min(base_score + proximity_boost, 100)
        return self.priority_score

    def save(self, *args, **kwargs):
        # Calculate the score prior to saving
        self.calculate_priority_score()
        super().save(*args, **kwargs)


class ReportMedia(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='media')
    file = models.FileField(upload_to='reports/')
    media_type = models.CharField(
        max_length=10,
        choices=[('image', 'Image'), ('video', 'Video')],
        default='image'
    )
    exif_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    exif_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_duplicate = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Media for {self.report.title} ({self.media_type})"


class OfficerAssignment(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='assignments')
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assigned_reports'
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_assignments'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.officer.username} assigned to {self.report.title}"


class ResolutionUpdate(models.Model):
    report = models.OneToOneField(Report, on_delete=models.CASCADE, related_name='resolution')
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='resolutions'
    )
    resolution_notes = models.TextField()
    resolved_proof_image = models.ImageField(upload_to='resolutions/', blank=True, null=True)
    resolved_at = models.DateTimeField(auto_now_add=True)
    
    # Accountability Peer-Review
    citizen_rating = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)], null=True, blank=True)
    citizen_feedback = models.TextField(blank=True, null=True)
    is_verified_by_citizen = models.BooleanField(default=False)

    def __str__(self):
        return f"Resolution for {self.report.title} by {self.officer.username if self.officer else 'Unknown'}"

class InfrastructureQRCode(models.Model):
    location_name = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=100, choices=[
        ('station', 'Railway/Metro Station'),
        ('mall', 'Shopping Mall'),
        ('hospital', 'Hospital'),
        ('government', 'Government Building'),
        ('college', 'College/University'),
    ])
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    qr_code_image = models.ImageField(upload_to='infrastructure_qr/', blank=True, null=True)
    health_score = models.IntegerField(default=100) # Out of 100
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.location_name} QR Node"

class CommunityVerification(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='verifications')
    verifier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_valid = models.BooleanField(default=True)
    comments = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Verification by {self.verifier.username} for {self.report.title}"

class AccessibilityCertification(models.Model):
    infrastructure = models.ForeignKey(InfrastructureQRCode, on_delete=models.CASCADE, related_name='certifications')
    auditor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    compliance_score = models.IntegerField(default=0)
    certificate_pdf = models.FileField(upload_to='certifications/', blank=True, null=True)
    issued_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Certification for {self.infrastructure.location_name}"

class InfrastructureReview(models.Model):
    infrastructure = models.ForeignKey(InfrastructureQRCode, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    wheelchair_rating = models.IntegerField(default=5) # 1 to 5
    tactile_rating = models.IntegerField(default=5)
    elevator_rating = models.IntegerField(default=5)
    restroom_rating = models.IntegerField(default=5)
    review_text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review for {self.infrastructure.location_name} by {self.user.username}"

class AccessibilityIndex(models.Model):
    region_type = models.CharField(max_length=50, choices=[('state', 'State'), ('city', 'City'), ('district', 'District')])
    region_name = models.CharField(max_length=255)
    infrastructure_score = models.FloatField(default=0.0)
    resolution_speed_score = models.FloatField(default=0.0)
    citizen_satisfaction_score = models.FloatField(default=0.0)
    overall_index = models.FloatField(default=0.0)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.region_name} - {self.overall_index}"

class RouteAccessibility(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    start_location = models.CharField(max_length=255)
    end_location = models.CharField(max_length=255)
    is_fully_accessible = models.BooleanField(default=False)
    obstacles_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Route for {self.user.username}: {self.start_location} to {self.end_location}"

class GeofenceAlertSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    radius_meters = models.IntegerField(default=1000)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Geofence Alert for {self.user.username}"

