from django.urls import path

from .auth_views import login_session, logout_session, session_info
from .merchant_auth_views import (
    register, resend_registration, confirm_registration,
    request_password_reset, confirm_password_reset,
)

urlpatterns = [
    path("session/", session_info, name="auth-session"),
    path("login/", login_session, name="auth-login"),
    path("logout/", logout_session, name="auth-logout"),
    path("register/", register, name="merchant-register"),
    path("register/resend/", resend_registration, name="merchant-resend"),
    path("register/confirm/", confirm_registration, name="merchant-confirm"),
    path("password-reset/request/", request_password_reset, name="merchant-reset-request"),
    path("password-reset/confirm/", confirm_password_reset, name="merchant-reset-confirm"),
]
