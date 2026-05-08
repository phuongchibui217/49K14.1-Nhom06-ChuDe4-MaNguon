from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .services import get_attachment_accept_string


@login_required(login_url="accounts:login")
def admin_live_chat(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Bạn không có quyền truy cập trang này.")
        return redirect("pages:home")

    return render(
        request,
        "chat/admin_live_chat.html",
        {
            "chat_attachment_accept": get_attachment_accept_string(),
        },
    )
