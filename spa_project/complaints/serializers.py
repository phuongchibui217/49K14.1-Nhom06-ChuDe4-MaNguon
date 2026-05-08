"""
Serializers - Chuyển đổi Complaint models thành Dictionary (JSON)

Author: Spa ANA Team
"""

from .models import Complaint, ComplaintReply, ComplaintHistory


def serialize_complaint(complaint):
    """Chuyển 1 Complaint object thành dict"""
    return {
        'id': complaint.id,
        'code': complaint.code,
        'full_name': complaint.customer_name_snapshot or complaint.full_name,
        'phone': complaint.customer_phone_snapshot or complaint.phone,
        'email': complaint.customer_email_snapshot or complaint.email or '',
        'title': complaint.title,
        'content': complaint.content,
        'incident_date': complaint.incident_date.strftime('%Y-%m-%d') if complaint.incident_date else None,
        'appointment_code': complaint.appointment_code,
        'related_service': {
            'id': complaint.related_service.id,
            'name': complaint.related_service.name,
        } if complaint.related_service else None,
        'expected_solution': complaint.expected_solution,
        'status': complaint.status,
        'status_display': complaint.get_status_display(),
        'assigned_to': {
            'id': complaint.assigned_to.id,
            'name': complaint.assigned_to.get_full_name() or complaint.assigned_to.username,
        } if complaint.assigned_to else None,
        'resolution': complaint.resolution,
        'resolved_at': complaint.resolved_at.strftime('%Y-%m-%d %H:%M') if complaint.resolved_at else None,
        'created_at': complaint.created_at.strftime('%Y-%m-%d %H:%M'),
        'updated_at': complaint.updated_at.strftime('%Y-%m-%d %H:%M') if complaint.updated_at else None,
    }


def serialize_reply(reply):
    """Chuyển 1 ComplaintReply object thành dict"""
    return {
        'id': reply.id,
        'sender_name': reply.sender_name,
        'sender_role': reply.sender_role,
        'sender_role_display': reply.get_sender_role_display(),
        'message': reply.message,
        'is_internal': reply.is_internal,
        'created_at': reply.created_at.strftime('%Y-%m-%d %H:%M'),
    }


def serialize_history(item):
    """Chuyển 1 ComplaintHistory object thành dict"""
    return {
        'id': item.id,
        'action': item.action,
        'action_display': item.get_action_display(),
        'old_value': item.old_value,
        'new_value': item.new_value,
        'note': item.note,
        'performed_by': (item.performed_by.get_full_name() or item.performed_by.username) if item.performed_by else 'Hệ thống',
        'performed_at': item.performed_at.strftime('%Y-%m-%d %H:%M'),
    }
