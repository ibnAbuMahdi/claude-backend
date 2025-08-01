from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from . import views

urlpatterns = [
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
]

# OTP Authentication (for riders)
urlpatterns += [
   
    path('send-otp/', views.send_otp, name='send_otp'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    
    # Test endpoint for Kudi SMS service
    path('test-termii-sms/', views.test_termii_sms, name='test_kudisms_sms'),
    
    # JWT Token Management
    path('refresh/', views.refresh_token, name='token_refresh'),
    path('logout/', views.logout, name='logout'),
]