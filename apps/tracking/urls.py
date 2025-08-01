from django.urls import path
from . import views

app_name = 'tracking'

urlpatterns = [
    # Location sync endpoints
    path('sync/', views.sync_locations, name='sync_locations'),
    path('earnings/calculate/', views.calculate_earnings, name='calculate_earnings'),
    path('stats/', views.rider_tracking_stats, name='rider_stats'),
    
    # Location records
    path('locations/', views.LocationRecordListView.as_view(), name='location_records'),
    
    # Geofence events
    path('geofence-events/', views.GeofenceEntryListView.as_view(), name='geofence_events'),
    
    # Sessions
    path('sessions/', views.RiderSessionListView.as_view(), name='rider_sessions'),
    
    # Earnings
    path('earnings/', views.EarningsCalculationListView.as_view(), name='earnings_calculations'),
    
    # Daily summaries
    path('summaries/', views.DailyTrackingSummaryListView.as_view(), name='daily_summaries'),
    
    # Sync batches (for debugging)
    path('sync-batches/', views.LocationSyncBatchListView.as_view(), name='sync_batches'),
]