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
    try:
        # Return empty list for now to prevent app crashes
        # Return empty list directly - campaign service expects response.data['results'] or response.data as list
        return Response([])
    except Exception as e:
        logger.error(f"Available campaigns error: {str(e)}")
        return Response([], status=status.HTTP_500_INTERNAL_SERVER_ERROR)