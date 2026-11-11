from django.urls import path

from .auth_views import login_session, logout_session, session_info

urlpatterns = [
    path("session/", session_info, name="auth-session"),
    path("login/", login_session, name="auth-login"),
    path("logout/", logout_session, name="auth-logout"),
]
