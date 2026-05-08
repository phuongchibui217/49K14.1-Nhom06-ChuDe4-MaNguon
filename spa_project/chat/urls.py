from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("manage/live-chat/", views.admin_live_chat, name="admin_live_chat"),
]
