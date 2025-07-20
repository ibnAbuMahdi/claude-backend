from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from graphene_django.views import GraphQLView

# API v1 patterns (as per plan)
api_v1_patterns = [
    path('auth/', include('apps.accounts.urls')),
    path('agencies/', include('apps.agencies.urls')),
    path('campaigns/', include('apps.campaigns.urls')),
    path('riders/', include('apps.riders.urls')),
    path('rider/', include('apps.riders.urls')),  # Support both singular and plural
    path('fleets/', include('apps.fleets.urls')),
    path('verification/', include('apps.verification.urls')),
    path('payments/', include('apps.payments.urls')),
    path('analytics/', include('apps.analytics.urls')),
    path('webhooks/', include('apps.webhooks.urls')),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(api_v1_patterns)),
    
    # API Documentation (as per plan)
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    
    # GraphQL endpoint (as per plan)
    path('api/v1/graphql/', GraphQLView.as_view(graphiql=settings.DEBUG)),
    
    # Health checks
    path('health/', include('health_check.urls')),
]

# Serve media files in both development and production
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)