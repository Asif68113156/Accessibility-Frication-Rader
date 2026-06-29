from django.urls import path
from .views import (
    landing_view,
    login_view,
    logout_view,
    register_view,
    verify_certificate_view,
    verify_action_view,
    dashboard_view,
    profile_view,
    admin_dashboard_view,
    chatbot_query_view,
    create_officer_view,
)

urlpatterns = [
    path('', landing_view, name='landing'),
    path('auth/login/', login_view, name='login'),
    path('auth/logout/', logout_view, name='logout'),
    path('auth/register/', register_view, name='register'),
    path('auth/verify-certificate/', verify_certificate_view, name='verify_certificate'),
    path('auth/verify-action/<int:cert_id>/<str:action>/', verify_action_view, name='verify_action'),
    path('auth/create-officer/', create_officer_view, name='create_officer'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('profile/', profile_view, name='profile'),
    path('admin-panel/', admin_dashboard_view, name='admin_dashboard'),
    path('api/chatbot/', chatbot_query_view, name='chatbot_query'),
]
