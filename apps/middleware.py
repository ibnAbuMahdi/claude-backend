# Custom middleware for API request logging
import logging
import json
import time
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('api_requests')

class APILoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log all API requests and responses for debugging
    """
    
    def process_request(self, request):
        # Start timing the request
        request.start_time = time.time()
        
        # Log incoming request details
        if request.path.startswith('/api/'):
            logger.info(f"=== INCOMING API REQUEST ===")
            logger.info(f"Method: {request.method}")
            logger.info(f"Path: {request.path}")
            logger.info(f"Query String: {request.META.get('QUERY_STRING', '')}")
            logger.info(f"Remote IP: {self.get_client_ip(request)}")
            logger.info(f"User Agent: {request.META.get('HTTP_USER_AGENT', 'Unknown')}")
            
            # Log authentication info
            if hasattr(request, 'user') and request.user.is_authenticated:
                logger.info(f"Authenticated User: {request.user.id} ({request.user.phone_number})")
            else:
                logger.info("User: Anonymous/Unauthenticated")
            
            # Log request headers (excluding sensitive ones)
            safe_headers = {}
            for key, value in request.META.items():
                if key.startswith('HTTP_') and key not in ['HTTP_AUTHORIZATION']:
                    header_name = key[5:].replace('_', '-').title()
                    safe_headers[header_name] = value
            logger.info(f"Headers: {safe_headers}")
            
            # Log request body for POST/PUT requests (limit size)
            if request.method in ['POST', 'PUT', 'PATCH'] and hasattr(request, 'body'):
                try:
                    body = request.body.decode('utf-8')
                    if len(body) > 1000:
                        body = body[:1000] + '... (truncated)'
                    logger.info(f"Request Body: {body}")
                except:
                    logger.info("Request Body: Unable to decode")
    
    def process_response(self, request, response):
        # Log API response details
        if request.path.startswith('/api/'):
            duration = time.time() - getattr(request, 'start_time', time.time())
            
            logger.info(f"=== API RESPONSE ===")
            logger.info(f"Path: {request.path}")
            logger.info(f"Status Code: {response.status_code}")
            logger.info(f"Duration: {duration:.3f}s")
            
            # Log response content for debugging (limit size)
            if hasattr(response, 'content'):
                try:
                    content = response.content.decode('utf-8')
                    if len(content) > 2000:
                        content = content[:2000] + '... (truncated)'
                    logger.info(f"Response Content: {content}")
                except:
                    logger.info("Response Content: Unable to decode")
            
            # Log response headers
            response_headers = dict(response.items())
            logger.info(f"Response Headers: {response_headers}")
            
            logger.info(f"=== END API REQUEST ===")
        
        return response
    
    def process_exception(self, request, exception):
        # Log API exceptions
        if request.path.startswith('/api/'):
            duration = time.time() - getattr(request, 'start_time', time.time())
            
            logger.error(f"=== API EXCEPTION ===")
            logger.error(f"Path: {request.path}")
            logger.error(f"Duration: {duration:.3f}s")
            logger.error(f"Exception: {str(exception)}")
            logger.error(f"Exception Type: {type(exception).__name__}")
            
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            logger.error(f"=== END API EXCEPTION ===")
        
        return None  # Allow normal exception handling to continue
    
    def get_client_ip(self, request):
        """Get the client's IP address from the request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip