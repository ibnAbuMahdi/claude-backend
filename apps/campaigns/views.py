# apps/campaigns/views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import logging

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def available_campaigns(request):
    """
    Get available campaigns for the authenticated rider
    TODO: Implement actual campaign logic
    """
    logger.info(f"=== AVAILABLE CAMPAIGNS REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Query params: {dict(request.GET)}")
    logger.info(f"Method: {request.method}")
    logger.info(f"Path: {request.path}")
    
    try:
        # Return empty list directly - campaign service expects response.data['results'] or response.data as list
        response_data = []
        
        logger.info(f"Successfully returning campaigns response: {response_data}")
        return Response(response_data)
    except Exception as e:
        logger.error(f"=== AVAILABLE CAMPAIGNS ERROR ===")
        logger.error(f"User: {request.user.id} ({request.user.phone_number})")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        error_response = []
        
        logger.error(f"Returning error response: {error_response}")
        return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)