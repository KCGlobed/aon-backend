from django.urls import path , include
from users.views import *
from rest_framework_simplejwt.views import (
    TokenVerifyView,
    TokenRefreshView,
)

urlpatterns = [
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path('admin-login/', AdminLoginView.as_view(), name="admin-login"),
    path('admin-forgot-password/', AdminForgotPasswordView.as_view(), name="forgot-password"),
    path('reset-password/', UserResetPasswordView.as_view(), name="reset-password"),

    path('student-login/', StudentLoginView.as_view(), name="student-login"),

    path('get-organization-listing/', GetOrganizationListingView.as_view(), name="get-organization-listing"),
    
]