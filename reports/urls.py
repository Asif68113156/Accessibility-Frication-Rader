from django.urls import path
from .views import (
    map_view,
    report_create_view,
    report_resolve_view,
    report_pdf_export_view,
    upvote_report_view,
    csv_export_view,
    assign_officer_view,
    governance_audit_view,
)

urlpatterns = [
    path('map/', map_view, name='map'),
    path('reports/create/', report_create_view, name='report_create'),
    path('reports/resolve/<int:report_id>/', report_resolve_view, name='report_resolve'),
    path('reports/export-pdf/<int:report_id>/', report_pdf_export_view, name='report_pdf_export'),
    path('reports/upvote/<int:report_id>/', upvote_report_view, name='report_upvote'),
    path('reports/export-csv/', csv_export_view, name='reports_csv_export'),
    path('reports/assign-officer/<int:report_id>/', assign_officer_view, name='assign_officer'),
    path('governance/audit/', governance_audit_view, name='governance_audit'),
]
