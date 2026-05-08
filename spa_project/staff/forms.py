from django import forms
from .models import StaffProfile


class StaffProfileForm(forms.ModelForm):
    class Meta:
        model = StaffProfile
        fields = ['user', 'phone', 'full_name', 'gender', 'dob', 'address', 'notes']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-select'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'dob': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }