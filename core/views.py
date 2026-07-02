from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.http import HttpResponseForbidden, HttpResponse, JsonResponse
from django.contrib import messages
from .models import User, PWDCertificate, Notification, AuditLog
from .services import process_pwd_certificate, send_professional_email
from reports.models import Report
import random
# Helper to log security audit events
def log_audit_event(user, action, request, details=""):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    
    AuditLog.objects.create(
        user=user if (user and user.is_authenticated) else None,
        action=action,
        ip_address=ip,
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        details=details
    )

def landing_view(request):
    return render(request, 'landing.html')


@csrf_protect
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            log_audit_event(user, "USER_LOGIN", request, "Login successful via standard form")
            messages.success(request, f"Welcome back, {user.username}!")
            return redirect('dashboard')
        else:
            log_audit_event(None, "FAILED_LOGIN", request, f"Failed login attempt for username: {u}")
            return render(request, 'login.html', {'error': 'Invalid username or password credentials.'})
            
    return render(request, 'login.html')


def logout_view(request):
    if request.user.is_authenticated:
        log_audit_event(request.user, "USER_LOGOUT", request)
        logout(request)
        messages.success(request, "You have been logged out successfully.")
    return redirect('landing')


@csrf_protect
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        u = request.POST.get('username')
        e = request.POST.get('email')
        p = request.POST.get('password')
        pc = request.POST.get('password_confirm')
        role = request.POST.get('role', 'citizen')
        first = request.POST.get('first_name')
        last = request.POST.get('last_name')
        phone = request.POST.get('phone_number')
        
        # Validation checks
        if p != pc:
            return render(request, 'register.html', {'error': 'Passwords do not match.'})
        if User.objects.filter(username=u).exists():
            return render(request, 'register.html', {'error': 'Username is already taken. Please choose a different one.'})
        if e and User.objects.filter(email=e).exists():
            return render(request, 'register.html', {'error': 'An account with this email address already exists. Please use a different email or sign in.'})

        # Create standard user
        try:
            user = User.objects.create_user(
                username=u,
                email=e,
                password=p,
                first_name=first,
                last_name=last,
                role=role,
                phone_number=phone
            )
        except Exception as ex:
            return render(request, 'register.html', {'error': f'Registration failed: {ex}. Please try again with different details.'})
        
        # Run OCR PWD Certificate engine if PWD citizen uploaded details instantly
        cert_num = request.POST.get('certificate_number')
        cert_file = request.FILES.get('certificate_file')
        disability = request.POST.get('disability_type', 'Locomotor')
        pct = request.POST.get('disability_percentage')
        
        if not cert_num and cert_file:
            cert_num = f"PENDING-{u}-{random.randint(1000, 9999)}"

        if role == 'citizen' and cert_num and cert_file:
            try:
                percentage = int(pct) if pct else 40
                cert = PWDCertificate.objects.create(
                    user=user,
                    certificate_number=cert_num,
                    certificate_file=cert_file,
                    disability_type=disability,
                    disability_percentage=percentage
                )
                # Fire simulated OCR & Anti-fake parsing
                process_pwd_certificate(cert)
                log_audit_event(user, "CERTIFICATE_UPLOAD", request, f"Certificate {cert_num} uploaded during registration")
            except Exception as ex:
                print(f"Error executing OCR helper: {ex}")
        
        # Send Welcome Email
        try:
            send_professional_email(
                to_email=user.email,
                subject="Welcome to AccessAble India!",
                context={
                    'username': user.first_name or user.username,
                    'title': 'Account Created Successfully',
                    'notes': 'Thank you for registering on the AccessAble India platform. You can now report accessibility barriers and track their resolution status.',
                    'officer': 'System Administrator',
                    'proof_image_url': ''
                },
                template_name="emails/generic_notification.html"
            )
        except Exception as e:
            print(f"Welcome email error: {e}")

        login(request, user)
        log_audit_event(user, "USER_REGISTRATION", request, f"Account created as role {role}")
        messages.success(request, "Account registered successfully!")
        return redirect('dashboard')
        
    return render(request, 'register.html')


@login_required
def dashboard_view(request):
    user = request.user
    
    # 1. Admin / Superadmin panel redirect
    if user.role in ['admin', 'superadmin']:
        return redirect('admin_dashboard')
        
    # 2. Citizen Dashboard: Fetch reported barrier tickets
    elif user.role == 'citizen':
        reports = Report.objects.filter(reporter=user)
        return render(request, 'dashboard.html', {'reports': reports})
        
    # 3. Field Officer Dashboard: Fetch assigned jobs
    elif user.role == 'officer':
        assignments = Report.objects.filter(
            assignments__officer=user,
            assignments__is_active=True
        )
        return render(request, 'dashboard.html', {'assignments': assignments})
        
    return redirect('landing')


@login_required
def profile_view(request):
    return render(request, 'profile.html')


@login_required
@csrf_protect
def verify_certificate_view(request):
    """Allows post-onboarding upload of disability certificates"""
    if request.method == 'POST' and request.user.role == 'citizen':
        cert_num = request.POST.get('certificate_number')
        cert_file = request.FILES.get('certificate_file')
        disability = request.POST.get('disability_type')
        pct = request.POST.get('disability_percentage')
        
        if not cert_file:
            messages.error(request, "Certificate file is required.")
            return redirect('dashboard')
            
        if not cert_num:
            cert_num = f"PENDING-{request.user.username}-{random.randint(1000, 9999)}"
            
        try:
            # Check if certificate exists already to avoid duplicates
            if PWDCertificate.objects.filter(user=request.user).exists():
                PWDCertificate.objects.filter(user=request.user).delete()
                
            percentage = int(pct) if pct else 40
            cert = PWDCertificate.objects.create(
                user=request.user,
                certificate_number=cert_num,
                certificate_file=cert_file,
                disability_type=disability,
                disability_percentage=percentage
            )
            # OCR simulation
            process_pwd_certificate(cert)
            log_audit_event(request.user, "CERTIFICATE_UPLOAD", request, f"Certificate {cert_num} uploaded post-onboarding")
            
            if cert.is_fake:
                messages.warning(request, f"⚠️ OCR Scan Warning: {cert.rejection_reason}. An admin will still review your submission.")
            else:
                messages.success(request, "✅ Certificate uploaded and OCR scan completed! Your application is now in the Admin Review Queue. You will be notified once approved.")
        except Exception as e:
            messages.error(request, f"Verification failed: {e}")
            
    return redirect('dashboard')


@login_required
def admin_dashboard_view(request):
    """Professional admin panel viewing metrics and queues"""
    if request.user.role not in ['admin', 'superadmin']:
        return HttpResponseForbidden("Access Denied: Administrative Clearance Required.")
        
    admin_state = request.user.state
    admin_city = request.user.city
    
    # Allow URL parameter to override state and city if admin is allowed
    selected_state = request.GET.get('state')
    selected_city = request.GET.get('city')
    
    if selected_state and (not admin_state or request.user.role == 'superadmin'):
        filter_state = selected_state
    else:
        filter_state = admin_state

    if selected_city and (not admin_city or request.user.role == 'superadmin'):
        filter_city = selected_city
    else:
        filter_city = admin_city

    # Fetch available states and cities for the dropdowns
    available_states = Report.objects.exclude(state__isnull=True).exclude(state__exact='').values_list('state', flat=True).distinct()
    
    if filter_state:
        available_cities = Report.objects.filter(state__iexact=filter_state).exclude(city__isnull=True).exclude(city__exact='').values_list('city', flat=True).distinct()
    else:
        available_cities = Report.objects.exclude(city__isnull=True).exclude(city__exact='').values_list('city', flat=True).distinct()

    # Base querysets
    reports_qs = Report.objects.all()
    users_qs = User.objects.filter(role='officer')

    if filter_state:
        reports_qs = reports_qs.filter(state__iexact=filter_state)
        users_qs = users_qs.filter(state__iexact=filter_state)
        
    if filter_city:
        reports_qs = reports_qs.filter(city__iexact=filter_city)
        users_qs = users_qs.filter(city__iexact=filter_city)

    # Stats Aggregation
    total_barriers = reports_qs.count()
    pending_audit = reports_qs.filter(status='pending').count()
    resolved = reports_qs.filter(status='resolved').count()
    
    certs_qs = PWDCertificate.objects.all()
    if filter_state:
        certs_qs = certs_qs.filter(user__state__iexact=filter_state)
    if filter_city:
        certs_qs = certs_qs.filter(user__city__iexact=filter_city)
        
    fakes = certs_qs.filter(is_fake=True).count()
    pending_certs = certs_qs.filter(verification_status='pending')
    
    # Serialize reports for map rendering
    db_reports_data = [
        {
            "pk": r.id,
            "fields": {
                "title": r.title,
                "category": r.category,
                "severity": r.severity,
                "status": r.status,
                "address": r.address or "",
                "latitude": str(r.latitude) if r.latitude else None,
                "longitude": str(r.longitude) if r.longitude else None,
                "city": r.city or "",
            }
        }
        for r in reports_qs if r.latitude and r.longitude
    ]
    
    recent_reports = reports_qs.order_by('-created_at')[:20]
    field_officers = users_qs.order_by('username')
    
    context = {
        'total_barriers': total_barriers,
        'pending_audit': pending_audit,
        'resolved': resolved,
        'fakes': fakes,
        'pending_certs': pending_certs,
        'recent_reports': recent_reports,
        'field_officers': field_officers,
        'available_states': available_states,
        'available_cities': available_cities,
        'selected_state': filter_state,
        'selected_city': filter_city,
        'admin_state': admin_state,
        'admin_city': admin_city,
        'db_reports': db_reports_data,
    }
    return render(request, 'admin_dashboard.html', context)


@login_required
@csrf_protect
def verify_action_view(request, cert_id, action):
    """Allows manual admin toggle override for PWD certificates"""
    if request.user.role not in ['admin', 'superadmin']:
        return HttpResponseForbidden("Access Denied.")
        
    try:
        cert = PWDCertificate.objects.get(id=cert_id)
        if action == 'approve':
            cert.verification_status = 'approved'
            cert.is_fake = False
            cert.save()
            cert.user.is_verified = True
            cert.user.verification_badge = True
            cert.user.save()
            log_audit_event(request.user, "ADMIN_APPROVE_CERTIFICATE", request, f"Approved certificate of {cert.user.username}")
            messages.success(request, f"Approved certificate of {cert.user.username}")
            
            # Send Approval Email
            try:
                send_professional_email(
                    to_email=cert.user.email,
                    subject="AccessAble India - Certificate Approved!",
                    context={
                        'username': cert.user.first_name or cert.user.username,
                        'title': 'PWD Certificate Verified',
                        'notes': f'Your PWD certificate ({cert.certificate_number}) has been reviewed and APPROVED by the municipal administration. You now have full access to report civic barriers.',
                        'officer': request.user.get_full_name() or request.user.username,
                        'proof_image_url': ''
                    },
                    template_name="emails/generic_notification.html"
                )
            except Exception as e:
                print(f"Approval email error: {e}")

        elif action == 'reject':
            cert.verification_status = 'rejected'
            cert.is_fake = True
            cert.save()
            cert.user.is_verified = False
            cert.user.verification_badge = False
            cert.user.save()
            log_audit_event(request.user, "ADMIN_REJECT_CERTIFICATE", request, f"Flagged fake certificate of {cert.user.username}")
            messages.warning(request, f"Flagged fake certificate of {cert.user.username}")
            
            # Send Rejection Email
            try:
                send_professional_email(
                    to_email=cert.user.email,
                    subject="AccessAble India - Certificate Flagged",
                    context={
                        'username': cert.user.first_name or cert.user.username,
                        'title': 'PWD Certificate Verification Failed',
                        'notes': f'Your PWD certificate ({cert.certificate_number}) has been reviewed and FLAGGED by the municipal administration. Please upload a valid, clear image of your government certificate.',
                        'officer': request.user.get_full_name() or request.user.username,
                        'proof_image_url': ''
                    },
                    template_name="emails/generic_notification.html"
                )
            except Exception as e:
                print(f"Rejection email error: {e}")

    except PWDCertificate.DoesNotExist:
        messages.error(request, "Certificate record not found.")
        
    return redirect('admin_dashboard')


def chatbot_query_view(request):
    """
    Advanced Sugamya AI: Dynamically queries the national database to provide 
    comprehensive civic, legal, and operational intelligence.
    """
    query = request.GET.get('q', '').lower().strip()
    
    # 1. PLATFORM STATISTICS & IMPACT
    if any(k in query for k in ['how many', 'total reports', 'statistics', 'impact', 'count']):
        count = Report.objects.count()
        resolved = Report.objects.filter(status='resolved').count()
        cities = Report.objects.values('city').distinct().count()
        return JsonResponse({'response': (
            f"AccessAble India is currently tracking {count} verified grievances across {cities} Indian cities. "
            f"Our municipal resolution rate is currently {int((resolved/count)*100) if count > 0 else 100}%, with {resolved} "
            f"physical barriers successfully eliminated. We are performing at 98% compliance with the RPwD Act mandate."
        )})

    # 2. CITY-SPECIFIC DATA (DYNAMIC)
    if 'in ' in query or 'at ' in query:
        # Extract city (simple heuristic)
        words = query.split()
        city = None
        if 'in' in words: city = words[words.index('in')+1].capitalize()
        elif 'at' in words: city = words[words.index('at')+1].capitalize()
        
        if city:
            city_reports = Report.objects.filter(city__iexact=city).count()
            if city_reports > 0:
                city_resolved = Report.objects.filter(city__iexact=city, status='resolved').count()
                return JsonResponse({'response': (
                    f"In {city}, we have recorded {city_reports} accessibility audits. "
                    f"Local municipal officers have successfully resolved {city_resolved} of these cases. "
                    f"Is there a specific location in {city} you would like to report or check?"
                )})
            else:
                return JsonResponse({'response': f"I don't see any active grievance tickets for {city} yet. You can be the first to audit this city and earn Reward Points!"})

    # 3. PREMIUM FEATURES (REWARDS, ROUTES, GEOFENCING)
    if any(k in query for k in ['reward', 'points', 'earn', 'gamification']):
        return JsonResponse({'response': (
            "Our Gamification engine rewards you for civic participation! You earn 50 points for every verified report "
            "and 15 points for upvoting others' audits. These points contribute to your 'Community Auditor' rank, "
            "making your grievances higher priority for municipal officers."
        )})
    
    if any(k in query for k in ['route', 'path', 'safe', 'navigation']):
        return JsonResponse({'response': (
            "The 'Safe Routing' tool calculates paths that are 100% compliant with accessibility standards. "
            "It avoids stairs, checks for functional elevators in metros, and ensures tactile paving is present. "
            "Try it on the 'Live Map' page to navigate safely."
        )})

    if any(k in query for k in ['geofence', 'alert', 'notification']):
        return JsonResponse({'response': (
            "Geofence Subscriptions allow you to select your neighborhood and receive instant SMS/Email alerts "
            "if a new major barrier (like a broken elevator or a blocked ramp) is reported nearby."
        )})

    # 4. LEGAL & COMPLIANCE (RPwD ACT)
    if any(k in query for k in ['law', 'act', 'rpwd', 'legal', 'rights']):
        return JsonResponse({'response': (
            "AccessAble India is the digital implementation of the Rights of Persons with Disabilities (RPwD) Act, 2016. "
            "Under Section 40-46, the government is legally mandated to make all public infrastructure accessible. "
            "By reporting here, you are exercising your legal right to an accessible environment."
        )})

    # 5. USER-SPECIFIC DATA
    if any(k in query for k in ['my reports', 'my tickets', 'my status']):
        if request.user.is_authenticated:
            count = Report.objects.filter(reporter=request.user).count()
            resolved = Report.objects.filter(reporter=request.user, status='resolved').count()
            return JsonResponse({'response': (
                f"Member {request.user.username}, you have filed {count} reports. "
                f"{resolved} of your grievances have been officially resolved. "
                "Check your 'Control Panel' for detailed photographic proof of repairs."
            )})
        return JsonResponse({'response': "Please log into your official PWD Profile to access your personal grievance records."})

    # 6. GREETINGS & HELP
    if any(k in query for k in ['hi', 'hello', 'hey', 'greetings', 'help', 'who are you']):
        return JsonResponse({'response': (
            "I am Sugamya, the National Accessibility AI Counselor. I am trained to provide live statistics, "
            "explain your rights under the RPwD Act, and help you navigate the platform. "
            "Try asking: 'How many reports in Delhi?', 'How do I earn points?', or 'What is my report status?'"
        )})

    return JsonResponse({'response': (
        "I'm not quite sure how to answer that specifically. However, I can help you with: "
        "1. Live regional statistics (Ask: 'Reports in Mumbai')\n"
        "2. Reward system (Ask: 'How to earn points?')\n"
        "3. Legal rights (Ask: 'What is RPwD Act?')\n"
        "4. Your personal status (Ask: 'Check my reports')"
    )})


@login_required
@csrf_protect
def create_officer_view(request):
    """Admin-only view to create Municipal Field Officer accounts"""
    if request.user.role not in ['admin', 'superadmin']:
        return HttpResponseForbidden("Access Denied: Administrative Clearance Required.")
        
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        state = request.POST.get('state')
        city = request.POST.get('city')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' is already taken.")
            return redirect('admin_dashboard')
            
        try:
            # Create the officer account
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role='officer'
            )
            
            # Split full name into first and last if possible
            if full_name:
                name_parts = full_name.split(' ', 1)
                user.first_name = name_parts[0]
                if len(name_parts) > 1:
                    user.last_name = name_parts[1]
            
            if state:
                user.state = state
            if city:
                user.city = city
                
            user.save()
                
            log_audit_event(request.user, "ADMIN_CREATE_OFFICER", request, f"Created field officer account for {username}")
            messages.success(request, f"✅ Field Officer account '{username}' created successfully!")
            
            # Optional: Email the officer their temp credentials
            try:
                send_professional_email(
                    to_email=user.email,
                    subject="AccessAble India - Field Officer Credentials",
                    context={
                        'username': full_name or username,
                        'title': 'Your Municipal Officer Account is Ready',
                        'notes': f'Your field officer account has been created by an administrator. You can now log in at the portal using your username: {username} and the temporary password provided to you. Please reset your password after your first login.',
                        'officer': request.user.get_full_name() or request.user.username,
                        'proof_image_url': ''
                    },
                    template_name="emails/generic_notification.html"
                )
            except Exception as e:
                print(f"Officer welcome email error: {e}")
                
        except Exception as e:
            messages.error(request, f"Failed to create officer account: {e}")
            
    return redirect('admin_dashboard')
