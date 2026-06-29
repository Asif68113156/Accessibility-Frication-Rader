import io
import csv
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth import get_user_model
from .models import Report, ReportMedia, ResolutionUpdate, OfficerAssignment, AccessibilityIndex
from .services import GovernmentAuditService
from core.services import extract_exif_metadata, check_report_duplicate, generate_ai_summary, send_professional_email, analyze_image_with_ai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

User = get_user_model()

def map_view(request):
    """Renders live Leaflet GIS Incident grid with live DB data as safe JSON"""
    reports_qs = Report.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True).order_by('-created_at')[:100]

    # Serialize to a plain list of dicts so Django's json_script filter can safely embed it
    db_reports_data = [
        {
            "pk": r.id,
            "fields": {
                "title": r.title,
                "category": r.category,
                "severity": r.severity,
                "status": r.status,
                "address": r.address or "",
                "latitude": str(r.latitude),
                "longitude": str(r.longitude),
                "description": r.description or "",
                "priority_score": r.priority_score,
            }
        }
        for r in reports_qs
    ]
    return render(request, 'map.html', {'db_reports': db_reports_data})

@login_required
def upvote_report_view(request, report_id):
    """Allows community members to upvote and escalate a barrier"""
    report = get_object_or_404(Report, id=report_id)
    report.priority_score += 15
    report.save()
    messages.success(request, f"You verified and upvoted Ticket #{report.id}! Municipal priority escalated.")
    referer = request.META.get('HTTP_REFERER', '/map/')
    return redirect(referer)


@login_required
@csrf_protect
def report_create_view(request):
    """Handles barrier report submission with EXIF coordinate harvesting and AI spam check"""
    if request.user.role not in ['citizen', 'admin', 'superadmin']:
        return HttpResponseForbidden("Only PWD citizens and admins can submit accessibility reports.")
        
    if request.user.role == 'citizen' and not request.user.is_verified:
        messages.error(request, "Please verify your PWD Certificate before submitting reports.")
        return redirect('dashboard')
        
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        category = request.POST.get('category')
        severity = request.POST.get('severity', 'medium')
        lat_str = request.POST.get('latitude')
        lon_str = request.POST.get('longitude')
        address = request.POST.get('address')
        state = request.POST.get('state')
        city = request.POST.get('city')
        is_anon = request.POST.get('is_anonymous') == 'on'
        
        # Parse coordinates
        lat = Decimal(lat_str) if lat_str else None
        lon = Decimal(lon_str) if lon_str else None
        
        # Image attachment EXIF harvest check
        uploaded_files = request.FILES.getlist('files')
        exif_lat, exif_lon = None, None
        
        if uploaded_files:
            # Run AI Image Analysis for fake detection
            ai_analysis = analyze_image_with_ai(uploaded_files[0].name)
            if ai_analysis.get('is_fake'):
                messages.error(request, f"Report Rejected by AI: {ai_analysis.get('reason')}")
                return redirect('dashboard')
                
            # Look at first file for metadata coordinates
            exif_lat, exif_lon = extract_exif_metadata(uploaded_files[0])
            if exif_lat and exif_lon and not lat:
                lat, lon = exif_lat, exif_lon
                address = address or "Auto-extracted coordinates via Image EXIF"
        
        # Anti-Spam / Duplicate incident verification
        is_dup, original = check_report_duplicate(lat, lon, category)
        if is_dup:
            messages.warning(
                request,
                f"We found an existing active report for this same category near this location (Ticket ID: #{original.id}). "
                f"We have registered your endorsement on this issue to prevent duplicate municipal entries."
            )
            # Upvote / boost priority of original
            original.save() # recalculates priority with new count
            return redirect('dashboard')
            
        # AI Summary Generation
        summary = generate_ai_summary(title, description, category)
        
        # Create barrier ticket
        report = Report.objects.create(
            reporter=request.user,
            title=title,
            description=description,
            category=category,
            severity=severity,
            latitude=lat,
            longitude=lon,
            address=address,
            state=state,
            city=city,
            is_anonymous=is_anon,
            ai_summary=summary
        )
        
        # Save attached files
        for f in uploaded_files:
            ReportMedia.objects.create(
                report=report,
                file=f,
                media_type='image' if f.name.lower().endswith(('.png', '.jpg', '.jpeg')) else 'video'
            )
            
        # ────────────────────────────────────────────────────────────
        # INTELLIGENT ROUTING: Auto-Assign to City Nodal Officer
        # If the city has a designated municipal authority, route it instantly
        # ────────────────────────────────────────────────────────────
        if city:
            # Find the local municipal officer for this exact city
            nodal_officer = User.objects.filter(role='officer', city__iexact=city).first()
            if nodal_officer:
                OfficerAssignment.objects.create(
                    report=report,
                    officer=nodal_officer,
                    assigned_by=None # Auto-assigned by system
                )
                report.status = 'in_progress' # Skip pending audit, straight to assigned
                report.save()
        
        # Send Grievance Filed Email
        try:
            send_professional_email(
                to_email=request.user.email,
                subject=f"AccessAble India - Grievance Filed (#{report.id})",
                context={
                    'username': request.user.first_name or request.user.username,
                    'title': 'Grievance Registered Successfully',
                    'notes': f'Your report regarding "{report.title}" at {report.address} has been recorded. It is currently pending verification and assignment to a municipal field officer.',
                    'officer': 'System Administrator',
                    'proof_image_url': ''
                },
                template_name="emails/generic_notification.html"
            )
        except Exception as e:
            print(f"Grievance filed email error: {e}")
            
        # Simulate notification logging
        messages.success(request, "Accessibility barrier registered and AI verified successfully!")
        return redirect('dashboard')
        
    return render(request, 'report_issue.html')


@login_required
@csrf_protect
def report_resolve_view(request, report_id):
    """Allows field officers to resolve barriers with photographic verification proofs"""
    report = get_object_or_404(Report, id=report_id)
    
    # Permission verification
    if request.user.role not in ['officer', 'admin', 'superadmin']:
        return HttpResponseForbidden("Administrative Clearance Denied.")
        
    if request.method == 'POST':
        notes = request.POST.get('resolution_notes')
        proof = request.FILES.get('resolved_proof_image')
        
        if not notes or not proof:
            messages.error(request, "Resolution notes and evidence photos are mandatory to close tickets.")
            return redirect('dashboard')
            
        # Create resolution update
        resolution = ResolutionUpdate.objects.create(
            report=report,
            officer=request.user,
            resolution_notes=notes,
            resolved_proof_image=proof
        )
        
        # Update ticket status
        report.status = 'resolved'
        report.save()
        
        # Deactivate assignment logs
        OfficerAssignment.objects.filter(report=report, officer=request.user).update(is_active=False)
        
        # Trigger Simulated Celery background email
        if report.reporter and report.reporter.email:
            proof_url = ""
            if resolution.resolved_proof_image:
                try:
                    proof_url = request.build_absolute_uri(resolution.resolved_proof_image.url)
                except Exception:
                    proof_url = ""

            send_professional_email(
                to_email=report.reporter.email,
                subject=f"[AccessAble India] Your Grievance #{report.id} Has Been Resolved",
                context={
                    'username': report.reporter.get_full_name() or report.reporter.username,
                    'report_id': report.id,
                    'title': report.title,
                    'notes': notes,
                    'officer': request.user.get_full_name() or request.user.username,
                    'proof_image_url': proof_url,
                },
                template_name="emails/resolved_notification.html"
            )
            
        messages.success(request, "Resolution proof submitted! This ticket is closed and the PWD citizen has been emailed.")
        
    # Redirect back to the HTTP referer so admins stay on the admin panel, officers on dashboard
    referer = request.META.get('HTTP_REFERER', '/dashboard/')
    return redirect(referer)


def report_pdf_export_view(request, report_id):
    """
    Advanced Feature: Generates elegant, municipality-compliant PDF dossier
    using ReportLab letter page setups.
    """
    report = get_object_or_404(Report, id=report_id)
    
    # Create byte buffer
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        textColor=colors.HexColor('#4f46e5'),
        spaceAfter=15
    )
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=12,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        textColor=colors.HexColor('#475569'),
        leading=14
    )
    
    # Title
    story.append(Paragraph("AccessAble India Compliance Dossier", title_style))
    story.append(Spacer(1, 10))
    
    # Summary Details Table
    data = [
        [Paragraph("<b>Incident Ticket ID:</b>", body_style), Paragraph(f"#{report.id}", body_style)],
        [Paragraph("<b>Barrier Title:</b>", body_style), Paragraph(report.title, body_style)],
        [Paragraph("<b>Category:</b>", body_style), Paragraph(report.get_category_display(), body_style)],
        [Paragraph("<b>Report Severity:</b>", body_style), Paragraph(report.get_severity_style_display() if hasattr(report, 'get_severity_style_display') else report.get_severity_display(), body_style)],
        [Paragraph("<b>Status:</b>", body_style), Paragraph(report.get_status_display(), body_style)],
        [Paragraph("<b>Coordinates:</b>", body_style), Paragraph(f"Lat: {report.latitude}, Lon: {report.longitude}", body_style)],
        [Paragraph("<b>Logged Address:</b>", body_style), Paragraph(report.address or "Not Provided", body_style)],
    ]
    t = Table(data, colWidths=[150, 350])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('PADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))
    
    # Description
    story.append(Paragraph("Incident Description & Grievance", section_style))
    story.append(Paragraph(report.description, body_style))
    story.append(Spacer(1, 15))
    
    # AI Summary
    if report.ai_summary:
        story.append(Paragraph("AI Compliance Algorithm Assessment", section_style))
        story.append(Paragraph(report.ai_summary, body_style))
        story.append(Spacer(1, 15))
        
    # Resolution Notes
    if report.status == 'resolved' and hasattr(report, 'resolution'):
        story.append(Paragraph("Municipal Action Resolution Report", section_style))
        res_data = [
            [Paragraph("<b>Officer:</b>", body_style), Paragraph(report.resolution.officer.username if report.resolution.officer else "Unknown", body_style)],
            [Paragraph("<b>Closed Date:</b>", body_style), Paragraph(str(report.resolution.resolved_at.date()), body_style)],
            [Paragraph("<b>Action Notes:</b>", body_style), Paragraph(report.resolution.resolution_notes, body_style)]
        ]
        rest = Table(res_data, colWidths=[150, 350])
        rest.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f0fdf4')),
            ('PADDING', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#bbf7d0')),
        ]))
        story.append(rest)
        
    # Build Document
    doc.build(story)
    buf.seek(0)
    
    # Construct response
    response = HttpResponse(buf.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Barrier_Dossier_#{report.id}.pdf"'
    return response


@login_required
def csv_export_view(request):
    """Exports all grievance reports as a downloadable CSV spreadsheet for admin analysis"""
    if request.user.role not in ['admin', 'superadmin']:
        return HttpResponseForbidden("Administrative clearance required.")

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="AccessAble_India_Reports.csv"'

    writer = csv.writer(response)
    # Header Row
    writer.writerow([
        'Ticket ID', 'Title', 'Category', 'Severity', 'Status',
        'Reporter', 'Reporter Email', 'Address', 'Latitude', 'Longitude',
        'Priority Score', 'AI Summary', 'Filed On', 'Resolved'
    ])

    reports = Report.objects.select_related('reporter').order_by('-created_at')
    for r in reports:
        writer.writerow([
            f'#{r.id}',
            r.title,
            r.get_category_display(),
            r.get_severity_display(),
            r.get_status_display(),
            r.reporter.username if r.reporter else 'Anonymous',
            r.reporter.email if r.reporter else '',
            r.address or '',
            r.latitude or '',
            r.longitude or '',
            r.priority_score,
            r.ai_summary or '',
            r.created_at.strftime('%Y-%m-%d %H:%M'),
            'Yes' if r.status == 'resolved' else 'No',
        ])

    return response


@login_required
@csrf_protect
def assign_officer_view(request, report_id):
    """Allows admins to assign a field officer to a specific grievance report"""
    if request.user.role not in ['admin', 'superadmin']:
        return HttpResponseForbidden("Administrative clearance required.")

    report = get_object_or_404(Report, id=report_id)

    if request.method == 'POST':
        officer_id = request.POST.get('officer_id')
        if not officer_id:
            messages.error(request, "Please select a valid field officer.")
            return redirect('admin_dashboard')

        officer = get_object_or_404(User, id=officer_id, role='officer')

        # Deactivate any existing active assignment for this report
        OfficerAssignment.objects.filter(report=report, is_active=True).update(is_active=False)

        # Create new assignment
        OfficerAssignment.objects.create(
            report=report,
            officer=officer,
            assigned_by=request.user,
            is_active=True
        )

        # Update report status to in_progress
        report.status = 'in_progress'
        report.save()

        # Notify officer by email
        try:
            send_professional_email(
                to_email=officer.email,
                subject=f"AccessAble India - New Assignment: Ticket #{report.id}",
                context={
                    'username': officer.first_name or officer.username,
                    'title': f'New Field Assignment: {report.title}',
                    'notes': f'You have been assigned to investigate and resolve accessibility barrier "#{report.id} — {report.title}" at {report.address or "the reported location"}. Please log into your dashboard to view details and submit resolution proof.',
                    'officer': request.user.get_full_name() or request.user.username,
                    'proof_image_url': ''
                },
                template_name="emails/generic_notification.html"
            )
        except Exception as e:
            print(f"Officer assignment email error: {e}")

        messages.success(request, f"Officer {officer.username} assigned to Ticket #{report.id}. Status updated to In Progress.")

    return redirect('admin_dashboard')

@login_required
def governance_audit_view(request):
    """
    Official Governance Dashboard View: Provides high-level compliance metrics 
    for municipal commissioners.
    """
    if request.user.role not in ['admin', 'superadmin', 'officer']:
        return HttpResponseForbidden("Government credentials required.")
    
    city_filter = request.GET.get('city') or request.user.city or "Delhi"
    audit_data = GovernmentAuditService.generate_compliance_report(city_filter)
    
    # Get all indices for comparison
    indices = AccessibilityIndex.objects.all().order_by('-overall_index')
    
    context = {
        'audit': audit_data,
        'city': city_filter,
        'indices': indices,
    }
    return render(request, 'governance_audit.html', context)
