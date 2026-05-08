"""
Forms cho Complaint Management

File này chứa các forms cho:
- Tạo khiếu nại (customer, guest)
- Phản hồi khiếu nại
- Cập nhật trạng thái khiếu nại
- Phân công khiếu nại

Author: Spa ANA Team
"""

from django import forms
from django.contrib.auth.models import User

# Tạm import từ spa.models (CHƯA chuyển model trong phase này)
from .models import Complaint, ComplaintReply
from spa_services.models import Service


# =====================================================
# COMPLAINT FORMS
# =====================================================

class CustomerComplaintForm(forms.ModelForm):
    """Form khách hàng gửi khiếu nại"""

    class Meta:
        model = Complaint
        fields = ['title', 'content',
                  'incident_date', 'appointment_code', 'related_service',
                  'expected_solution']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tiêu đề khiếu nại'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Mô tả chi tiết vấn đề của bạn...'
            }),
            'incident_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'appointment_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Mã lịch hẹn (nếu có)'
            }),
            'expected_solution': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Bạn mong muốn được giải quyết như thế nào?'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['related_service'].queryset = Service.objects.filter(status='ACTIVE')
        self.fields['related_service'].required = False
        self.fields['related_service'].empty_label = "-- Chọn dịch vụ liên quan (nếu có) --"
        self.fields['related_service'].widget.attrs.update({'class': 'form-select'})

    def clean_title(self):
        title = self.cleaned_data.get('title', '').strip()
        if not title or len(title) < 5:
            raise forms.ValidationError('Tiêu đề phải có ít nhất 5 ký tự.')
        return title

    def clean_content(self):
        content = self.cleaned_data.get('content', '').strip()
        if not content or len(content) < 10:
            raise forms.ValidationError('Nội dung phải có ít nhất 10 ký tự.')
        return content


class GuestComplaintForm(forms.ModelForm):
    """Form khách chưa đăng nhập gửi khiếu nại"""

    class Meta:
        model = Complaint
        fields = ['customer_name_snapshot', 'customer_phone_snapshot', 'customer_email_snapshot',
                  'title', 'content', 'incident_date',
                  'appointment_code', 'related_service', 'expected_solution']
        widgets = {
            'customer_name_snapshot': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Họ và tên của bạn'
            }),
            'customer_phone_snapshot': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Số điện thoại',
                'pattern': '[0-9]{10,11}'
            }),
            'customer_email_snapshot': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email (không bắt buộc)'
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tiêu đề khiếu nại'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Mô tả chi tiết vấn đề của bạn...'
            }),
            'incident_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'appointment_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Mã lịch hẹn (nếu có)'
            }),
            'expected_solution': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Bạn mong muốn được giải quyết như thế nào?'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['related_service'].queryset = Service.objects.filter(status='ACTIVE')
        self.fields['related_service'].required = False
        self.fields['related_service'].empty_label = "-- Chọn dịch vụ liên quan (nếu có) --"
        self.fields['related_service'].widget.attrs.update({'class': 'form-select'})

    def clean_title(self):
        title = self.cleaned_data.get('title', '').strip()
        if not title or len(title) < 5:
            raise forms.ValidationError('Tiêu đề phải có ít nhất 5 ký tự.')
        return title

    def clean_content(self):
        content = self.cleaned_data.get('content', '').strip()
        if not content or len(content) < 10:
            raise forms.ValidationError('Nội dung phải có ít nhất 10 ký tự.')
        return content

    def clean_customer_phone_snapshot(self):
        import re
        phone = self.cleaned_data.get('customer_phone_snapshot', '').strip()
        if not phone:
            raise forms.ValidationError('Vui lòng nhập số điện thoại.')
        digits = ''.join(filter(str.isdigit, phone))
        if not re.match(r'^0\d{9}$', digits):
            raise forms.ValidationError('Số điện thoại không hợp lệ (phải có 10 số và bắt đầu bằng 0).')
        return digits


class ComplaintReplyForm(forms.ModelForm):
    """Form phản hồi khiếu nại"""

    class Meta:
        model = ComplaintReply
        fields = ['message', 'is_internal']
        widgets = {
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Nhập nội dung phản hồi...'
            }),
            'is_internal': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def clean_message(self):
        message = self.cleaned_data.get('message', '').strip()
        if not message:
            raise forms.ValidationError('Vui lòng nhập nội dung phản hồi.')
        return message


class ComplaintStatusForm(forms.ModelForm):
    """Form cập nhật trạng thái khiếu nại"""

    class Meta:
        model = Complaint
        fields = ['status', 'resolution']
        widgets = {
            'status': forms.Select(attrs={
                'class': 'form-select'
            }),
            'resolution': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Kết quả xử lý (nếu hoàn thành)'
            }),
        }


class ComplaintAssignForm(forms.ModelForm):
    """Form phân công người phụ trách"""

    class Meta:
        model = Complaint
        fields = ['assigned_to']
        widgets = {
            'assigned_to': forms.Select(attrs={
                'class': 'form-select'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Chỉ lấy staff users
        self.fields['assigned_to'].queryset = User.objects.filter(
            is_staff=True, is_active=True
        ).order_by('first_name', 'last_name')
        self.fields['assigned_to'].empty_label = "-- Chọn nhân viên --"
        self.fields['assigned_to'].required = True
