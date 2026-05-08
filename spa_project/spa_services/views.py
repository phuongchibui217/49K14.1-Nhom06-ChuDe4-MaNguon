"""
Views cho Service Management

File này chứa các views cho:
- Trang danh sách dịch vụ (public)
- Trang chi tiết dịch vụ (public)
- Quản lý dịch vụ (admin)
- API endpoints cho services

Author: Spa ANA Team
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Min, Max, Count, Case, When, IntegerField
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
import json

# TẠM IMPORT từ spa.models (CHƯA chuyển model trong phase này)
from .models import Service

# Forms (sẽ tạo trong spa_services/forms.py)
from .forms import ServiceForm

# Service layer từ spa_services/service_services
from .service_services import (
    validate_service_data,
    create_service,
    update_service,
    get_service_by_id,
    serialize_service,
)

# Decorators, API response từ core
from core.api_response import staff_api, get_or_404


def _save_service_image(service, image_file):
    """
    Gán image_file vào ImageField của service và lưu.
    Django ImageField tự xử lý: sinh tên file, lưu vào MEDIA_ROOT/services/,
    và lưu relative path vào DB — không cần tự ghép path thủ công.
    """
    service.image = image_file
    service.save(update_fields=['image'])


# =====================================================
# PUBLIC SERVICE PAGES
# =====================================================

def service_list(request):
    """Danh sách dịch vụ - Lọc chỉ active, tính min/max price và duration từ variants"""
    from .models import ServiceCategory
    from django.db.models import Min, Max, Count

    load_error = False
    services = []
    categories = []

    try:
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
            .order_by('-created_at')
        )
        categories = ServiceCategory.objects.filter(status='ACTIVE').order_by('sort_order', 'name')
    except Exception:
        import traceback
        traceback.print_exc()
        load_error = True

    return render(request, 'spa_services/services.html', {
        'services': services,
        'categories': categories,
        'load_error': load_error,
    })


def service_detail(request, service_id):
    """Chi tiết dịch vụ - Lấy từ database"""
    # Case 1: Dịch vụ không tồn tại hoặc không active
    try:
        service = Service.objects.get(id=service_id, status='ACTIVE')
    except Service.DoesNotExist:
        return render(request, 'spa_services/service_detail.html', {
            'service': None,
            'not_found': True,
            'related_services': [],
        }, status=404)
    except Exception:
        # Case 2: Lỗi khi tải dữ liệu
        import traceback
        traceback.print_exc()
        return render(request, 'spa_services/service_detail.html', {
            'service': None,
            'load_error': True,
            'related_services': [],
        })

    # Lấy các dịch vụ liên quan (cùng category)
    try:
        related_services = (
            Service.objects
            .filter(category=service.category, status='ACTIVE')
            .exclude(id=service_id)
            .prefetch_related('variants')
            .annotate(
                min_price=Min('variants__price'),
                max_price=Max('variants__price'),
                min_duration=Min('variants__duration_minutes'),
                max_duration=Max('variants__duration_minutes'),
                variant_count=Count('variants'),
            )[:4]
        )
    except Exception:
        related_services = []

    return render(request, 'spa_services/service_detail.html', {
        'service': service,
        'related_services': related_services,
    })


# =====================================================
# ADMIN SERVICE MANAGEMENT
# =====================================================

@login_required(login_url='accounts:login')
def admin_services(request):
    """
    Quản lý dịch vụ

    GET: Hiển thị danh sách dịch vụ với pagination và filter
    POST: Xử lý thêm dịch vụ mới
    """
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('pages:home')

    # GET request - hiển thị danh sách
    if request.method == 'GET':
        # Search functionality
        search_query = request.GET.get('search', '').strip()
        category_filter = request.GET.get('category', '').strip()
        status_filter = request.GET.get('status', '').strip()
        is_filtered = bool(search_query or category_filter or status_filter)

        try:
            services_list = Service.objects.all().prefetch_related('variants')

            # BR-UC12-16: Tìm kiếm không phân biệt hoa thường (icontains)
            # Tìm trên name, code, short_description — hợp lý với màn quản lý
            if search_query:
                services_list = services_list.filter(
                    Q(name__icontains=search_query) |
                    Q(code__icontains=search_query) |
                    Q(short_description__icontains=search_query)
                )

            # BR-UC12-17: Kết hợp điều kiện AND
            if category_filter:
                services_list = services_list.filter(category__code=category_filter)

            if status_filter:
                services_list = services_list.filter(status=status_filter)

            # Sort: ACTIVE trước, INACTIVE sau (UC 12.4 step 9), rồi mới đến created_at
            services_list = services_list.order_by(
                Case(
                    When(status='ACTIVE', then=0),
                    default=1,
                    output_field=IntegerField(),
                ),
                '-created_at',
            )

            paginator = Paginator(services_list, 10)
            page_number = request.GET.get('page', 1)
            services = paginator.get_page(page_number)

        except Exception:
            import traceback
            traceback.print_exc()
            messages.error(request, 'Không thể tải danh sách dịch vụ, vui lòng thử lại.')
            services = []
            is_filtered = False

        # Get next service code
        next_code = Service._generate_code()

        # Get categories from DB for form dropdown — không hardcode
        from .models import ServiceCategory
        categories = ServiceCategory.objects.filter(status='ACTIVE').order_by('sort_order')

        context = {
            'services': services,
            'categories': categories,
            'next_service_code': next_code,
            'search_query': search_query,
            'category_filter': category_filter,
            'status_filter': status_filter,
            'is_filtered': is_filtered,   # UC 7a: phân biệt "không có dữ liệu" vs "không tìm thấy"
        }
        return render(request, 'manage/pages/admin_services.html', context)

    # POST request - xử lý thêm dịch vụ mới
    elif request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES)

        if form.is_valid():
            try:
                service = form.save(commit=False)
                service.created_by = request.user
                service.updated_by = request.user
                service.save()

                messages.success(
                    request,
                    f'Đã thêm dịch vụ mới: {service.name}'
                )
                return redirect('spa_services:admin_services')

            except Exception as e:
                messages.error(
                    request,
                    'Có lỗi khi lưu dữ liệu, vui lòng thử lại'
                )
        else:
            # Form có lỗi - hiển thị lỗi
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)

        # Redirect về trang danh sách (khi lỗi)
        return redirect('spa_services:admin_services')


@login_required(login_url='accounts:login')
def admin_service_edit(request, service_id):
    """
    Sửa dịch vụ
    """
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('pages:home')

    service = get_object_or_404(Service, id=service_id)

    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES, instance=service)

        if form.is_valid():
            try:
                updated_service = form.save(commit=False)
                updated_service.updated_by = request.user
                updated_service.save()

                messages.success(
                    request,
                    f'Đã cập nhật dịch vụ: {updated_service.name}'
                )
                return redirect('spa_services:admin_services')

            except Exception as e:
                messages.error(
                    request,
                    'Có lỗi khi lưu dữ liệu, vui lòng thử lại'
                )
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)

    return redirect('spa_services:admin_services')


@login_required(login_url='accounts:login')
def admin_service_delete(request, service_id):
    """Soft delete dịch vụ — UC 12.4"""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('pages:home')

    if request.method == 'POST':
        service = get_object_or_404(Service, id=service_id)
        try:
            service.status = 'INACTIVE'
            service.updated_by = request.user
            service.save(update_fields=['status', 'updated_by', 'updated_at'])
            messages.success(request, 'Xóa dịch vụ thành công')
        except Exception:
            messages.error(request, 'Có lỗi xảy ra, vui lòng thử lại')

    return redirect('spa_services:admin_services')


# =====================================================
# API ENDPOINTS FOR SERVICES
# =====================================================

@require_http_methods(["GET"])
def api_services_list(request):
    """API: Lấy danh sách dịch vụ kèm variants"""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'error': 'Không có quyền truy cập'}, status=403)

    from .models import ServiceVariant

    search_query = request.GET.get('search', '')
    service_id = request.GET.get('id', '')

    if service_id:
        services = Service.objects.filter(pk=service_id)
    elif search_query:
        services = Service.objects.filter(
            Q(name__icontains=search_query) | Q(code__icontains=search_query)
        )
    else:
        services = Service.objects.filter(status='ACTIVE').order_by('-created_at')

    services = services.prefetch_related('variants')

    services_data = [
        {
            'id': s.id,
            'code': s.code or '',
            'name': s.name,
            'categoryId': s.category_id,
            'categoryCode': s.category.code if s.category else '',
            'categoryName': s.get_category_name(),
            'description': s.short_description or (s.description[:100] if s.description else ''),
            'short_description': s.short_description or '',
            'detail_description': s.description or '',
            'status': s.status,
            'image': s.image.url if s.image else 'https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=100',
            'variants': [
                {
                    'id': v.id,
                    'label': v.label,
                    'duration_minutes': v.duration_minutes,
                    'price': float(v.price),
                    'sort_order': v.sort_order,
                }
                for v in s.variants.order_by('sort_order', 'duration_minutes')
            ],
        }
        for s in services
    ]
    return JsonResponse({'services': services_data})


@require_http_methods(["POST"])
@staff_api
def api_service_create(request):
    """API: Thêm dịch vụ mới"""
    from django.db import transaction as db_transaction
    from .models import ServiceCategory, ServiceVariant

    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            name = request.POST.get('name', '').strip()
            category = request.POST.get('category_number', '').strip()
            short_description = request.POST.get('short_description', '').strip()
            description = request.POST.get('description', '').strip()
            status = (request.POST.get('status', '') or '').strip().upper()
            code = request.POST.get('code', '').strip().upper()
            image_file = request.FILES.get('image')
        else:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            category = data.get('category_number', data.get('category', '')).strip()
            short_description = data.get('short_description', '').strip()
            description = data.get('description', '').strip()
            status = (data.get('status', '') or '').strip().upper()
            code = data.get('code', '').strip().upper()
            image_file = None

        # ── Validate Service fields ────────────────────────────────
        if not code:
            return JsonResponse({'error': 'Vui lòng nhập mã dịch vụ', 'field': 'code'}, status=400)
        if Service.objects.filter(code=code).exists():
            return JsonResponse({'error': 'Mã dịch vụ đã tồn tại', 'field': 'code'}, status=400)

        if not category:
            return JsonResponse({'error': 'Vui lòng chọn danh mục', 'field': 'category_number'}, status=400)

        if not name:
            return JsonResponse({'error': 'Tên dịch vụ không hợp lệ', 'field': 'name'}, status=400)
        if len(name) < 5 or len(name) > 200 or name.isdigit():
            return JsonResponse({'error': 'Tên dịch vụ không hợp lệ', 'field': 'name'}, status=400)
        if Service.objects.filter(name__iexact=name).exists():
            return JsonResponse({'error': 'Dịch vụ đã tồn tại', 'field': 'name'}, status=400)

        if not status:
            return JsonResponse({'error': 'Vui lòng chọn trạng thái dịch vụ', 'field': 'status'}, status=400)
        if status not in ('ACTIVE', 'INACTIVE'):
            return JsonResponse({'error': 'Vui lòng chọn trạng thái dịch vụ', 'field': 'status'}, status=400)

        if short_description and len(short_description) > 255:
            return JsonResponse({'error': 'Mô tả ngắn không được quá 255 ký tự', 'field': 'short_description'}, status=400)

        # ── Validate Image ─────────────────────────────────────────
        if not image_file:
            return JsonResponse({'error': 'Vui lòng chọn hình ảnh dịch vụ', 'field': 'image'}, status=400)
        if image_file.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'Hình ảnh không được quá 5MB', 'field': 'image'}, status=400)
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
        if image_file.content_type not in allowed_types:
            return JsonResponse({'error': 'Hình ảnh không đúng định dạng', 'field': 'image'}, status=400)

        # ── Validate Danh mục ──────────────────────────────────────
        try:
            category_obj = ServiceCategory.objects.get(code=str(category), status='ACTIVE')
        except ServiceCategory.DoesNotExist:
            return JsonResponse({'error': 'Vui lòng chọn danh mục', 'field': 'category_number'}, status=400)

        # ── Validate Variants ──────────────────────────────────────
        variants_json = request.POST.get('variants_json', '[]')
        try:
            variants_data = json.loads(variants_json)
        except (json.JSONDecodeError, TypeError):
            variants_data = []

        if not variants_data:
            return JsonResponse({'error': 'Vui lòng nhập đầy đủ thông tin gói', 'field': 'variants'}, status=400)

        # Validate từng variant trước khi lưu
        validated_variants = []
        for i, v in enumerate(variants_data):
            label = str(v.get('label', '')).strip()
            duration_raw = v.get('duration_minutes', '')
            price_raw = v.get('price', '')

            if duration_raw == '' or price_raw == '':
                return JsonResponse({'error': 'Vui lòng nhập đầy đủ thông tin gói', 'field': 'variants'}, status=400)

            try:
                duration = int(duration_raw)
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Thời lượng không hợp lệ', 'field': 'variants'}, status=400)
            try:
                price = float(price_raw)
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Giá dịch vụ không hợp lệ', 'field': 'variants'}, status=400)

            if duration <= 0:
                return JsonResponse({'error': 'Thời lượng không hợp lệ', 'field': 'variants'}, status=400)
            if price <= 0:
                return JsonResponse({'error': 'Giá dịch vụ không hợp lệ', 'field': 'variants'}, status=400)

            if not label:
                label = f'{duration} phút'
            validated_variants.append({'label': label, 'duration_minutes': duration, 'price': price, 'sort_order': i})

        # ── Lưu toàn bộ trong 1 transaction ───────────────────────
        try:
            with db_transaction.atomic():
                if not short_description:
                    short_description = description[:255] if description else ''

                service = Service.objects.create(
                    code=code,
                    name=name,
                    category=category_obj,
                    short_description=short_description,
                    description=description,
                    status=status,
                    image='',
                    created_by=request.user,
                    updated_by=None,
                )

                _save_service_image(service, image_file)

                for v in validated_variants:
                    ServiceVariant.objects.create(
                        service=service,
                        label=v['label'],
                        duration_minutes=v['duration_minutes'],
                        price=v['price'],
                        sort_order=v['sort_order'],
                    )

        except Exception:
            import traceback
            traceback.print_exc()
            return JsonResponse({'error': 'Có lỗi khi lưu dữ liệu, vui lòng thử lại'}, status=500)

        return JsonResponse({
            'success': True,
            'message': 'Thêm mới dịch vụ thành công',
            'service': {
                'id': service.id,
                'code': service.code,
                'name': service.name,
                'categoryName': service.get_category_name(),
                'image': service.image.url if service.image else '',
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': 'Có lỗi khi lưu dữ liệu, vui lòng thử lại'}, status=500)


@require_http_methods(["POST", "PUT"])
@staff_api
def api_service_update(request, service_id):
    """API: Cập nhật dịch vụ — UC 12.3"""
    service, error = get_or_404(Service, id=service_id)
    if error:
        return error

    from .models import ServiceCategory, ServiceVariant
    from django.db import transaction as db_transaction

    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            name = request.POST.get('name', '').strip()
            category = request.POST.get('category_number', '').strip()
            short_description = request.POST.get('short_description', '').strip()
            description = request.POST.get('description', '').strip()
            status = (request.POST.get('status', '') or '').strip().upper()
            code = request.POST.get('code', '').strip().upper()
            image_file = request.FILES.get('image')
        else:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            category = data.get('category_number', data.get('category', '')).strip()
            short_description = data.get('short_description', '').strip()
            description = data.get('description', '').strip()
            status = (data.get('status', '') or '').strip().upper()
            code = data.get('code', '').strip().upper()
            image_file = None

        # ── 5a: Mã dịch vụ ────────────────────────────────────────
        if not code:
            return JsonResponse({'error': 'Vui lòng nhập mã dịch vụ', 'field': 'code'}, status=400)
        # ── 5b: Mã trùng (trừ chính nó) ───────────────────────────
        if Service.objects.filter(code=code).exclude(id=service_id).exists():
            return JsonResponse({'error': 'Mã dịch vụ đã tồn tại', 'field': 'code'}, status=400)

        # ── 6a: Danh mục ──────────────────────────────────────────
        if not category:
            return JsonResponse({'error': 'Vui lòng chọn danh mục', 'field': 'category_number'}, status=400)
        try:
            category_obj = ServiceCategory.objects.get(code=category, status='ACTIVE')
        except ServiceCategory.DoesNotExist:
            return JsonResponse({'error': 'Vui lòng chọn danh mục', 'field': 'category_number'}, status=400)

        # ── 7a / 7b: Tên dịch vụ ──────────────────────────────────
        if not name or len(name) < 5 or len(name) > 200 or name.isdigit():
            return JsonResponse({'error': 'Tên dịch vụ không hợp lệ', 'field': 'name'}, status=400)
        if Service.objects.filter(name__iexact=name).exclude(id=service_id).exists():
            return JsonResponse({'error': 'Dịch vụ đã tồn tại', 'field': 'name'}, status=400)

        # ── 8a: Trạng thái ────────────────────────────────────────
        if not status or status not in ('ACTIVE', 'INACTIVE'):
            return JsonResponse({'error': 'Vui lòng chọn trạng thái dịch vụ', 'field': 'status'}, status=400)

        # ── 12a: Hình ảnh (chỉ validate nếu có upload mới) ────────
        if image_file:
            if image_file.size > 5 * 1024 * 1024:
                return JsonResponse({'error': 'Hình ảnh không đúng định dạng', 'field': 'image'}, status=400)
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
            if image_file.content_type not in allowed_types:
                return JsonResponse({'error': 'Hình ảnh không đúng định dạng', 'field': 'image'}, status=400)

        # ── 11a / 11b / 11c: Variants ─────────────────────────────
        variants_json = request.POST.get('variants_json', None)
        validated_variants = None
        if variants_json is not None:
            try:
                variants_data = json.loads(variants_json)
            except (json.JSONDecodeError, TypeError):
                variants_data = []

            if not variants_data:
                return JsonResponse({'error': 'Vui lòng nhập đầy đủ thông tin gói', 'field': 'variants'}, status=400)

            validated_variants = []
            for i, v in enumerate(variants_data):
                label = str(v.get('label', '')).strip()
                duration_raw = v.get('duration_minutes', '')
                price_raw = v.get('price', '')

                if duration_raw == '' or price_raw == '':
                    return JsonResponse({'error': 'Vui lòng nhập đầy đủ thông tin gói', 'field': 'variants'}, status=400)

                try:
                    duration = int(duration_raw)
                except (ValueError, TypeError):
                    return JsonResponse({'error': 'Thời lượng không hợp lệ', 'field': 'variants'}, status=400)
                try:
                    price = float(price_raw)
                except (ValueError, TypeError):
                    return JsonResponse({'error': 'Giá dịch vụ không hợp lệ', 'field': 'variants'}, status=400)

                if duration <= 0:
                    return JsonResponse({'error': 'Thời lượng không hợp lệ', 'field': 'variants'}, status=400)
                if price <= 0:
                    return JsonResponse({'error': 'Giá dịch vụ không hợp lệ', 'field': 'variants'}, status=400)

                if not label:
                    label = f'{duration} phút'
                validated_variants.append({'label': label, 'duration_minutes': duration, 'price': price, 'sort_order': i})

        # ── Fallback short_description ─────────────────────────────
        if not short_description:
            short_description = description[:255] if description else ''

        # ── 15a: Lưu toàn bộ trong 1 transaction ──────────────────
        try:
            with db_transaction.atomic():
                service.code = code
                service.name = name
                service.category = category_obj
                service.short_description = short_description
                service.description = description
                service.status = status
                service.updated_by = request.user
                service.save()

                if image_file:
                    _save_service_image(service, image_file)

                if validated_variants is not None:
                    service.variants.all().delete()
                    for v in validated_variants:
                        ServiceVariant.objects.create(
                            service=service,
                            label=v['label'],
                            duration_minutes=v['duration_minutes'],
                            price=v['price'],
                            sort_order=v['sort_order'],
                        )
        except Exception:
            import traceback
            traceback.print_exc()
            return JsonResponse({'error': 'Có lỗi khi lưu dữ liệu, vui lòng thử lại'}, status=500)

        # ── 16: Thành công ─────────────────────────────────────────
        return JsonResponse({'success': True, 'message': 'Cập nhật dịch vụ thành công'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': 'Có lỗi khi lưu dữ liệu, vui lòng thử lại'}, status=500)


@require_http_methods(["DELETE", "POST"])
@staff_api
def api_service_delete(request, service_id):
    """API: Soft delete dịch vụ — UC 12.4
    Không xóa vật lý, chỉ cập nhật status → INACTIVE (BR-UC12-13).
    Lịch sử appointment cũ giữ nguyên (BR-UC12-15).
    """
    service, error = get_or_404(Service, id=service_id)
    if error:
        return error

    try:
        service.status = 'INACTIVE'
        service.updated_by = request.user
        service.save(update_fields=['status', 'updated_by', 'updated_at'])
        return JsonResponse({'success': True, 'message': 'Xóa dịch vụ thành công'})
    except Exception:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': 'Có lỗi xảy ra, vui lòng thử lại'}, status=500)


# =====================================================
# API ENDPOINTS FOR SERVICE VARIANTS
# =====================================================

@require_http_methods(["GET"])
def api_variant_list(request, service_id):
    """API: Lấy danh sách variants của 1 service"""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'error': 'Không có quyền truy cập'}, status=403)

    from .models import ServiceVariant
    service, error = get_or_404(Service, id=service_id)
    if error:
        return error

    variants = ServiceVariant.objects.filter(service=service).order_by('sort_order', 'duration_minutes')
    data = [
        {
            'id': v.id,
            'label': v.label,
            'duration_minutes': v.duration_minutes,
            'price': float(v.price),
            'sort_order': v.sort_order,
        }
        for v in variants
    ]
    return JsonResponse({'success': True, 'variants': data})


@require_http_methods(["POST"])
@staff_api
def api_variant_create(request, service_id):
    """API: Tạo variant mới cho service"""
    from .models import ServiceVariant
    service, error = get_or_404(Service, id=service_id)
    if error:
        return error

    try:
        data = json.loads(request.body)
        label = data.get('label', '').strip()
        duration = data.get('duration_minutes')
        price = data.get('price')
        sort_order = data.get('sort_order', 0)

        if not label:
            return JsonResponse({'error': 'Vui lòng nhập tên gói'}, status=400)
        try:
            duration = int(duration)
            if duration <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Thời lượng không hợp lệ'}, status=400)
        try:
            price = float(price)
            if price < 0:
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Giá không hợp lệ'}, status=400)

        variant = ServiceVariant.objects.create(
            service=service,
            label=label,
            duration_minutes=duration,
            price=price,
            sort_order=sort_order,
        )
        return JsonResponse({
            'success': True,
            'message': f'Đã thêm gói: {variant.label}',
            'variant': {
                'id': variant.id,
                'label': variant.label,
                'duration_minutes': variant.duration_minutes,
                'price': float(variant.price),
                'sort_order': variant.sort_order,
            }
        })
    except Exception as e:
        return JsonResponse({'error': f'Lỗi: {str(e)}'}, status=400)


@require_http_methods(["POST", "PUT"])
@staff_api
def api_variant_update(request, service_id, variant_id):
    """API: Cập nhật variant"""
    from .models import ServiceVariant
    variant, error = get_or_404(ServiceVariant, id=variant_id, service_id=service_id)
    if error:
        return error

    try:
        data = json.loads(request.body)
        label = data.get('label', '').strip()
        duration = data.get('duration_minutes')
        price = data.get('price')
        sort_order = data.get('sort_order')

        if label:
            variant.label = label
        if duration is not None:
            try:
                duration = int(duration)
                if duration <= 0:
                    raise ValueError
                variant.duration_minutes = duration
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Thời lượng không hợp lệ'}, status=400)
        if price is not None:
            try:
                price = float(price)
                if price < 0:
                    raise ValueError
                variant.price = price
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Giá không hợp lệ'}, status=400)
        if sort_order is not None:
            variant.sort_order = int(sort_order)

        variant.save()
        return JsonResponse({'success': True, 'message': f'Đã cập nhật gói: {variant.label}'})
    except Exception as e:
        return JsonResponse({'error': f'Lỗi: {str(e)}'}, status=400)


@require_http_methods(["POST", "DELETE"])
@staff_api
def api_variant_delete(request, service_id, variant_id):
    """API: Xóa variant"""
    from .models import ServiceVariant
    variant, error = get_or_404(ServiceVariant, id=variant_id, service_id=service_id)
    if error:
        return error

    try:
        label = variant.label
        variant.delete()
        return JsonResponse({'success': True, 'message': f'Đã xóa gói: {label}'})
    except Exception as e:
        return JsonResponse({'error': f'Lỗi: {str(e)}'}, status=400)
