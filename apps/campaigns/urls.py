from django.urls import path, include
from . import views

urlpatterns = [
    # Campaign endpoints
    path('available/', views.available_campaigns, name='available_campaigns'),
    path('my-campaigns/', views.my_campaigns, name='my_campaigns'),
    path('tracking-status/', views.get_tracking_status, name='tracking_status'),
    path('<uuid:campaign_id>/', views.campaign_details, name='campaign_details'),
    
    # New geofence-based joining (preferred)
    path('geofences/join/', views.join_geofence, name='join_geofence'),
    path('geofences/join-with-verification/', views.join_geofence_with_verification, name='join_geofence_verification'),
    path('geofences/check-join-eligibility/', views.check_geofence_join_eligibility, name='check_join_eligibility'),
    path('geofences/leave/', views.leave_geofence, name='leave_geofence'),
    path('geofences/<uuid:geofence_id>/', views.geofence_details, name='geofence_details'),
    
    # Legacy campaign joining (deprecated but backward compatible)
    path('<uuid:campaign_id>/join/', views.join_campaign_by_id, name='join_campaign_by_id'),
    path('<uuid:campaign_id>/leave/', views.leave_campaign_by_id, name='leave_campaign_by_id'),
    path('join/', views.join_campaign, name='join_campaign'),
    path('leave/', views.leave_campaign, name='leave_campaign'),
]