from django.urls import path, include
from . import views

urlpatterns = [
    path('earnings/', views.rider_earnings, name='rider_earnings'),
    path('payment-summary/', views.payment_summary, name='payment_summary'),
]
