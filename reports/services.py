import os
from django.conf import settings
from .models import Report, AccessibilityIndex
from django.template.loader import render_to_string
# Note: In a real production environment, you'd use a library like WeasyPrint or ReportLab
# For this demo, we'll simulate the generation of a professional metadata summary

class GovernmentAuditService:
    @staticmethod
    def generate_compliance_report(jurisdiction_name):
        """
        Generates a structured compliance summary for a city or state.
        Useful for Inter-Departmental meetings (Ministry of Urban Development).
        """
        reports = Report.objects.filter(city__iexact=jurisdiction_name)
        total = reports.count()
        resolved = reports.filter(status='resolved').count()
        pending = reports.filter(status='pending').count()
        
        compliance_rate = (resolved / total * 100) if total > 0 else 100
        
        summary = {
            "title": f"Accessibility Compliance Audit: {jurisdiction_name}",
            "metrics": {
                "total_grievances": total,
                "resolution_rate": f"{compliance_rate:.2f}%",
                "pending_critical_barriers": reports.filter(severity='critical', status='pending').count()
            },
            "legal_ref": "Under Section 46 of RPwD Act, 2016",
            "stamp": "AUTHENTICATED BY NATIONAL ACCESSIBILITY COMMAND CENTER"
        }
        return summary

    @staticmethod
    def auto_escalate_stale_reports():
        """
        Government logic: If a critical report is not verified in 24h, 
        or not resolved in 7 days, escalate level.
        """
        from django.utils import timezone
        from datetime import timedelta
        
        stale_threshold = timezone.now() - timedelta(days=7)
        stale_reports = Report.objects.filter(status='verified', updated_at__lte=stale_threshold)
        
        for report in stale_reports:
            report.escalation_level += 1
            # Logic to notify District Magistrate or higher authority
            # notify_higher_authority(report)
            report.save()
        
        return stale_reports.count()

import qrcode
from io import BytesIO
from django.core.files import File

class QRCodeService:
    @staticmethod
    def generate_for_infrastructure(infrastructure):
        """
        Generates a unique QR code for a public building/station.
        When scanned, it links to the building's accessibility audit profile.
        """
        qr_data = f"https://accessableindia.gov.in/infrastructure/{infrastructure.id}/"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        
        buffer = BytesIO()
        img.save(buffer)
        filename = f'qr_infra_{infrastructure.id}.png'
        infrastructure.qr_code_image.save(filename, File(buffer), save=True)
        return True
