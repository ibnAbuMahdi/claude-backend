from django.urls import path
from . import views

urlpatterns = [
    # Random verification endpoints (mobile-initiated)
    path('create-random/', views.create_random_verification, name='create_random_verification'),
    path('pending/', views.check_pending_verifications, name='check_pending_verifications'),
    path('submit/', views.submit_verification, name='submit_verification'),
    
    # Verification history and stats
    path('history/', views.verification_history, name='verification_history'),
    path('stats/', views.verification_stats, name='verification_stats'),
]