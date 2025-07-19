from django.utils.deprecation import MiddlewareMixin
from django.http import Http404
from apps.agencies.models import Agency

class TenantMiddleware(MiddlewareMixin):
    """
    Middleware to handle multi-tenant architecture based on subdomain
    Sets the current agency based on subdomain for B2B2B model
    """
    
    def process_request(self, request):
        host = request.get_host()
        
        # Skip tenant detection for admin and API routes
        if (request.path.startswith('/admin/') or 
            request.path.startswith('/api/') or 
            host.startswith('api.')):
            request.tenant = None
            return None
            
        # Extract subdomain
        subdomain = self.get_subdomain(host)
        
        if subdomain:
            try:
                agency = Agency.objects.get(subdomain=subdomain, is_active=True)
                request.tenant = agency
            except Agency.DoesNotExist:
                raise Http404("Agency not found")
        else:
            request.tenant = None
            
        return None
    
    def get_subdomain(self, host):
        """Extract subdomain from host"""
        parts = host.split('.')
        if len(parts) > 2:
            return parts[0]
        return None