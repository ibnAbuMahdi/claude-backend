from django.urls import path, include
from . import views

urlpatterns = [
    path('earnings/', views.rider_earnings, name='rider_earnings'),
    path('payment-summary/', views.payment_summary, name='payment_summary'),
    path('activate/', views.activate_rider, name='activate_rider'),
    path('validate-plate/', views.validate_plate_number, name='validate_plate_number'),
    path('profile/', views.rider_profile, name='rider_profile'),
]
