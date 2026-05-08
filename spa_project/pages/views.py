"""
Views cho trang tĩnh (Static Pages)

File này chứa các views cho:
- Trang chủ (home)
- Giới thiệu (about)

Author: Spa ANA Team
"""

from django.shortcuts import render
from django.db.models import Min, Max, Count, Q
from spa_services.models import Service


def home(request):
    """
    Trang chủ - Hiển thị 6 dịch vụ active
    """
    services = (
        Service.objects
        .filter(status='ACTIVE')
        .select_related('category')
        .prefetch_related('variants')
        .annotate(
            min_price=Min('variants__price'),
            max_price=Max('variants__price'),
            min_duration=Min('variants__duration_minutes'),
            max_duration=Max('variants__duration_minutes'),
            variant_count=Count('variants'),
        )
        [:6]
    )

    return render(request, 'spa/pages/home.html', {'services': services})


def about(request):
    """
    Trang giới thiệu về Spa ANA

    Args:
        request: HttpRequest

    Returns:
        HttpResponse: Render template spa/pages/about.html
    """
    return render(request, 'spa/pages/about.html')
