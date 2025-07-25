from django.urls import path, include
from . import views

urlpatterns = [
    path('available/', views.available_campaigns, name='available_campaigns'),
    path('my-campaigns/', views.my_campaigns, name='my_campaigns'),  # Match mobile app
    path('<uuid:campaign_id>/join/', views.join_campaign_by_id, name='join_campaign_by_id'),  # Mobile app format
    path('<uuid:campaign_id>/leave/', views.leave_campaign_by_id, name='leave_campaign_by_id'),  # Mobile app format
    path('join/', views.join_campaign, name='join_campaign'),  # Keep backward compatibility
    path('leave/', views.leave_campaign, name='leave_campaign'),  # Keep backward compatibility
    path('<uuid:campaign_id>/', views.campaign_details, name='campaign_details'),
]