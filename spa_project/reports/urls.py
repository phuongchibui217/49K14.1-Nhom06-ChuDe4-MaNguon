from django.urls import path
from . import views
from . import api

app_name = 'reports'

urlpatterns = [
    # ── HTML view (server-side render) ───────────────────────────────
    path('manage/reports/', views.admin_reports, name='admin_reports'),

    # ── JSON API ──────────────────────────────────────────────────────
    path('api/reports/', api.api_reports, name='api_reports'),
]
