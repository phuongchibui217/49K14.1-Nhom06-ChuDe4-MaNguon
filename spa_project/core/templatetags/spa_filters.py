from django import template

register = template.Library()


@register.filter
def vnd(value):
    """Format số thành tiền VNĐ: 200000 → 200.000đ"""
    try:
        amount = int(float(value))
        return f"{amount:,}đ".replace(",", ".")
    except (ValueError, TypeError):
        return value
