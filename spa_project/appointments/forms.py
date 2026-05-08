"""
Forms cho Appointments module.

BookingOnlineForm: Form đặt lịch online cho khách hàng.
Chỉ thu thập thông tin booker + dịch vụ + ngày giờ.
Thông tin khách (snapshot) được xử lý riêng trong view.

Author: Spa ANA Team
"""

import re
from django import forms
from spa_services.models import Service, ServiceVariant
from .services import validate_appointment_date, validate_appointment_time


class BookingOnlineForm(forms.Form):
    """
    Form đặt lịch hẹn cho khách hàng (booking online).

    Phân tách rõ:
    - booker_name / booker_phone: lấy từ account đang đăng nhập (hidden field)
    - service: chọn dịch vụ để lọc variant — không lưu vào DB
    - service_variant: gói dịch vụ
    - appointment_date / appointment_time: ngày giờ hẹn
    - booker_notes: ghi chú lần đặt lịch (lưu vào Booking)
    """

    booker_name = forms.CharField(
        widget=forms.HiddenInput(),
        required=True,
    )
    booker_phone = forms.CharField(
        widget=forms.HiddenInput(),
        required=True,
    )

    service = forms.ModelChoiceField(
        queryset=Service.objects.filter(status='ACTIVE'),
        required=True,
        empty_label='-- Chọn dịch vụ --',
        label='Dịch vụ',
        widget=forms.Select(attrs={'class': 'lux-select'})
    )

    service_variant = forms.ModelChoiceField(
        queryset=ServiceVariant.objects.none(),
        required=True,
        empty_label='-- Chọn gói dịch vụ --',
        label='Gói dịch vụ',
        widget=forms.Select(attrs={'class': 'lux-select'}),
    )

    appointment_date = forms.DateField(
        required=True,
        label='Ngày hẹn',
        widget=forms.DateInput(attrs={'class': 'lux-input', 'type': 'date'}),
    )

    appointment_time = forms.TimeField(
        required=True,
        label='Giờ hẹn',
        widget=forms.TimeInput(attrs={'class': 'lux-input', 'type': 'time'}),
    )

    booker_notes = forms.CharField(
        required=False,
        label='Ghi chú',
        widget=forms.Textarea(attrs={
            'class': 'lux-textarea',
            'rows': 4,
            'placeholder': 'Ghi chú thêm về yêu cầu đặc biệt, dị ứng, hoặc thông tin khác...',
        }),
    )

    def __init__(self, *args, **kwargs):
        self.customer_profile = kwargs.pop('customer_profile', None)
        super().__init__(*args, **kwargs)

        # Pre-fill booker info từ profile (user đang đăng nhập)
        if self.customer_profile:
            # Lấy tên/SĐT từ profile (fallback rỗng nếu không có)
            profile_name = self.customer_profile.full_name or ''
            profile_phone = self.customer_profile.phone or ''

            # Điền vào hidden fields (user không thấy, nhưng data có sẵn)
            self.initial['booker_name'] = profile_name
            self.initial['booker_phone'] = profile_phone

        # Load variants theo service đã chọn
        service_id = self.data.get('service') if self.data else None
        if service_id:
            self.fields['service_variant'].queryset = ServiceVariant.objects.filter(
                service_id=service_id
            ).order_by('sort_order', 'duration_minutes')
        else:
            # Chưa chọn service → rỗng (chờ JavaScript filter)
            self.fields['service_variant'].queryset = ServiceVariant.objects.none()

    def clean_booker_phone(self):
        phone = self.cleaned_data.get('booker_phone', '').strip()
        digits = re.sub(r'\D', '', phone)
        if not digits:
            raise forms.ValidationError('Không xác định được số điện thoại người đặt.')
        if not re.match(r'^0\d{9}$', digits):
            raise forms.ValidationError('Số điện thoại không hợp lệ (phải có 10 số và bắt đầu bằng 0).')
        return digits

    def clean_appointment_date(self):
        appointment_date = self.cleaned_data.get('appointment_date')
        if appointment_date:
            try:
                validate_appointment_date(appointment_date)
            except Exception as e:
                raise forms.ValidationError(str(e.message))
        return appointment_date

    def clean_appointment_time(self):
        appointment_time = self.cleaned_data.get('appointment_time')
        appointment_date = self.cleaned_data.get('appointment_date')
        if appointment_time and appointment_date:
            try:
                validate_appointment_time(appointment_time, appointment_date)
            except Exception as e:
                raise forms.ValidationError(str(e.message))
        return appointment_time

    def clean_service_variant(self):
        service_variant = self.cleaned_data.get('service_variant')
        if not service_variant:
            raise forms.ValidationError('Vui lòng chọn gói dịch vụ để đặt lịch.')
        return service_variant

    def clean(self):
        """Validate end time không vượt giờ đóng cửa (21:00)."""
        cleaned_data    = super().clean()
        appointment_time = cleaned_data.get('appointment_time')
        appointment_date = cleaned_data.get('appointment_date')
        service_variant  = cleaned_data.get('service_variant')

        if appointment_time and appointment_date and service_variant:
            from django.core.exceptions import ValidationError as DjangoValidationError
            duration_min = service_variant.duration_minutes if service_variant else 60
            try:
                validate_appointment_time(appointment_time, appointment_date, duration_min)
            except DjangoValidationError as e:
                self.add_error('appointment_time', e.message)

        return cleaned_data
