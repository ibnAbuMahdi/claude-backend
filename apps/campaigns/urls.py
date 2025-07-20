from django.urls import path, include
from . import views

urlpatterns = [
    path('available/', views.available_campaigns, name='available_campaigns'),
]