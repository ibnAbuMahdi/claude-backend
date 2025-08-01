from django.utils import timezone
from django.db import transaction
from django.contrib.gis.geos import Point
from datetime import timedelta
import logging

from .models import VerificationRequest, VerificationCooldown
from apps.campaigns.models import CampaignGeofenceAssignment, CampaignRiderAssignment

logger = logging.getLogger(__name__)


class VerificationProcessor:
    """Service class for processing verification requests"""
    
    @staticmethod
    def validate_image_basic(image_file):
        """Basic image validation - valid format, size, not corrupted"""
        try:
            # File size check
            if image_file.size > 5 * 1024 * 1024:  # 5MB
                return False, "Image too large (max 5MB)"
            
            # Format validation using file extension
            if hasattr(image_file, 'name') and image_file.name:
                file_extension = image_file.name.lower().split('.')[-1]
                valid_extensions = ['jpg', 'jpeg', 'png', 'webp']
                if file_extension not in valid_extensions:
                    return False, f"Invalid image format. Allowed: {', '.join(valid_extensions)}"
            
            # Try to open and validate image
            try:
                from PIL import Image
                # Reset file pointer to beginning
                image_file.seek(0)
                image = Image.open(image_file)
                image.verify()
                
                # Reset file pointer again for potential future use
                image_file.seek(0)
                image = Image.open(image_file)
                
                # Basic dimension check
                if image.width < 200 or image.height < 200:
                    return False, "Image resolution too low (minimum 200x200)"
                
                # Reset file pointer one more time
                image_file.seek(0)
                
            except ImportError:
                logger.warning("PIL not available for image validation")
                # Continue without PIL validation
            except Exception as e:
                return False, f"Invalid image: {str(e)}"
            
            return True, "Valid image"
            
        except Exception as e:
            return False, f"Image validation error: {str(e)}"
    
    @staticmethod
    def process_join_verification(verification_request):
        """Process verification for geofence joining"""
        logger.info(f"Processing join verification: {verification_request.id}")
        
        try:
            is_valid, message = VerificationProcessor.validate_image_basic(
                verification_request.image
            )
            
            if is_valid:
                verification_request.status = 'passed'
                verification_request.confidence_score = 95.0  # High confidence for valid images
                verification_request.ai_analysis = {
                    'validation_type': 'basic_image_check',
                    'is_valid_image': True,
                    'processed_at': timezone.now().isoformat(),
                    'message': message,
                    'image_size': verification_request.image.size,
                    'image_format': verification_request.image.name.split('.')[-1].lower()
                }
                logger.info(f"Verification {verification_request.id} passed")
            else:
                verification_request.status = 'failed'
                verification_request.confidence_score = 0.0
                verification_request.ai_analysis = {
                    'validation_type': 'basic_image_check',
                    'is_valid_image': False,
                    'failure_reason': message,
                    'processed_at': timezone.now().isoformat()
                }
                logger.warning(f"Verification {verification_request.id} failed: {message}")
            
            verification_request.save()
            return verification_request.status == 'passed'
            
        except Exception as e:
            logger.error(f"Error processing verification {verification_request.id}: {str(e)}")
            verification_request.status = 'failed'
            verification_request.confidence_score = 0.0
            verification_request.ai_analysis = {
                'validation_type': 'basic_image_check',
                'is_valid_image': False,
                'failure_reason': f"Processing error: {str(e)}",
                'processed_at': timezone.now().isoformat()
            }
            verification_request.save()
            return False

    @staticmethod
    def process_random_verification(verification_request):
        """Process verification for random compliance checks"""
        logger.info(f"Processing random verification: {verification_request.id}")
        
        try:
            is_valid, message = VerificationProcessor.validate_image_basic(
                verification_request.image
            )
            
            if is_valid:
                verification_request.status = 'passed'
                verification_request.confidence_score = 90.0  # Slightly lower confidence for random verification
                verification_request.ai_analysis = {
                    'validation_type': 'random_compliance_check',
                    'is_valid_image': True,
                    'processed_at': timezone.now().isoformat(),
                    'message': message,
                    'image_size': verification_request.image.size,
                    'image_format': verification_request.image.name.split('.')[-1].lower(),
                    'verification_context': 'random_check'
                }
                logger.info(f"Random verification {verification_request.id} passed")
            else:
                verification_request.status = 'failed'
                verification_request.confidence_score = 0.0
                verification_request.ai_analysis = {
                    'validation_type': 'random_compliance_check',
                    'is_valid_image': False,
                    'failure_reason': message,
                    'processed_at': timezone.now().isoformat(),
                    'verification_context': 'random_check'
                }
                logger.warning(f"Random verification {verification_request.id} failed: {message}")
            
            verification_request.save()
            return verification_request.status == 'passed'
            
        except Exception as e:
            logger.error(f"Error processing random verification {verification_request.id}: {str(e)}")
            verification_request.status = 'failed'
            verification_request.confidence_score = 0.0
            verification_request.ai_analysis = {
                'validation_type': 'random_compliance_check',
                'is_valid_image': False,
                'failure_reason': f"Processing error: {str(e)}",
                'processed_at': timezone.now().isoformat(),
                'verification_context': 'random_check'
            }
            verification_request.save()
            return False


class CooldownManager:
    """Service class for managing verification cooldowns"""
    
    @classmethod
    def check_cooldown(cls, rider, verification_type):
        """
        Check if rider is in cooldown period for verification type
        Returns: (can_verify: bool, cooldown_remaining: int)
        """
        return VerificationCooldown.check_cooldown(rider, verification_type)
    
    @classmethod
    def set_cooldown(cls, rider, verification_type, additional_seconds=0):
        """Set cooldown after verification attempt"""
        return VerificationCooldown.set_cooldown(rider, verification_type, additional_seconds)


class GeofenceJoinService:
    """Service class for handling geofence join operations with verification"""
    
    @staticmethod
    def handle_duplicate_join_attempt(rider, geofence):
        """
        Handle cases where rider might already be joined
        Returns: (is_duplicate, existing_assignment, should_return_success)
        """
        logger.info(f"Checking for duplicate join: rider {rider.rider_id} to geofence {geofence.name}")
        
        # Check for existing active assignment
        existing_assignment = CampaignGeofenceAssignment.objects.filter(
            rider=rider,
            campaign_geofence=geofence,
            status__in=['assigned', 'active']
        ).first()
        
        if existing_assignment:
            logger.info(f"Found existing assignment: {existing_assignment.id}")
            
            # Check if there's a recent successful verification
            recent_verification = VerificationRequest.objects.filter(
                rider=rider,
                geofence=geofence,
                verification_type='geofence_join',
                status='passed',
                created_at__gte=timezone.now() - timedelta(hours=1)
            ).first()
            
            if recent_verification:
                # Rider already joined with valid verification recently
                logger.info(f"Recent verification found: {recent_verification.id}")
                return True, existing_assignment, True
            else:
                # Existing assignment but no recent verification
                logger.warning(f"Existing assignment without recent verification")
                return True, existing_assignment, False
        
        logger.info("No duplicate join attempt detected")
        return False, None, False
    
    @staticmethod
    def create_join_with_verification(rider, geofence, verification_request, assigned_by=None):
        """Create geofence assignment after successful verification"""
        logger.info(f"Creating join with verification: rider {rider.rider_id} to geofence {geofence.name}")
        
        try:
            with transaction.atomic():
                # Create campaign assignment
                campaign_assignment, created = CampaignRiderAssignment.objects.get_or_create(
                    campaign=geofence.campaign,
                    rider=rider,
                    defaults={
                        'status': 'active',
                        'assigned_by': assigned_by or rider.user,
                        'started_at': timezone.now(),
                    }
                )
                
                if created:
                    logger.info(f"Created new campaign assignment: {campaign_assignment.id}")
                else:
                    logger.info(f"Using existing campaign assignment: {campaign_assignment.id}")
                    # Update status if it was previously cancelled
                    if campaign_assignment.status in ['cancelled', 'completed']:
                        campaign_assignment.status = 'active'
                        campaign_assignment.started_at = timezone.now()
                        campaign_assignment.save()
                
                # Create geofence assignment
                geofence_assignment, geo_created = CampaignGeofenceAssignment.objects.get_or_create(
                    campaign_geofence=geofence,
                    rider=rider,
                    defaults={
                        'campaign_rider_assignment': campaign_assignment,
                        'status': 'active',
                        'started_at': timezone.now(),
                    }
                )
                
                if geo_created:
                    logger.info(f"Created new geofence assignment: {geofence_assignment.id}")
                    
                    # Update geofence rider count only if new assignment
                    geofence.current_riders += 1
                    geofence.save(update_fields=['current_riders'])
                    logger.info(f"Updated geofence {geofence.name} current_riders to {geofence.current_riders}")
                else:
                    logger.info(f"Using existing geofence assignment: {geofence_assignment.id}")
                    # Update status if it was previously cancelled
                    if geofence_assignment.status in ['cancelled', 'completed']:
                        geofence_assignment.status = 'active'
                        geofence_assignment.started_at = timezone.now()
                        geofence_assignment.save()
                
                # Link verification to assignment
                if verification_request.ai_analysis is None:
                    verification_request.ai_analysis = {}
                
                verification_request.ai_analysis.update({
                    'geofence_assignment_id': str(geofence_assignment.id),
                    'campaign_assignment_id': str(campaign_assignment.id),
                    'join_completed_at': timezone.now().isoformat()
                })
                verification_request.save()
                
                logger.info(f"Successfully created join with verification")
                return campaign_assignment, geofence_assignment
                
        except Exception as e:
            logger.error(f"Error creating join with verification: {str(e)}")
            raise
    
    @staticmethod
    def validate_geofence_eligibility(rider, geofence, latitude, longitude):
        """
        Validate if rider is eligible to join a geofence
        Returns: (is_eligible: bool, error_message: str)
        """
        logger.info(f"Validating geofence eligibility: rider {rider.rider_id} for geofence {geofence.name}")
        
        # Check rider status
        if rider.status != 'active':
            return False, 'Rider account must be active'
        
        if not rider.is_available:
            return False, 'Rider is not available'
        
        # Check if rider can accept more campaigns
        if hasattr(rider, 'can_accept_campaign') and not rider.can_accept_campaign:
            return False, 'Rider has reached maximum concurrent campaigns'
        
        # Check if geofence can accept more riders
        if not geofence.can_assign_rider():
            if geofence.is_full:
                return False, 'This geofence is at capacity'
            elif not geofence.is_active:
                return False, 'This geofence is not currently active'
            elif geofence.remaining_budget <= 0:
                return False, 'This geofence has no remaining budget'
            else:
                return False, 'This geofence cannot accept new riders'
        
        # Validate location is within geofence
        rider_location = Point(float(longitude), float(latitude))
        geofence_center = Point(float(geofence.center_longitude), float(geofence.center_latitude))
        
        # Check if rider is within geofence radius
        distance_to_center = rider_location.distance(geofence_center) * 111320  # Convert degrees to meters
        
        if distance_to_center > geofence.radius_meters:
            return False, (
                f"You must be within the {geofence.name} area to join this geofence. "
                f"You are {int(distance_to_center - geofence.radius_meters)}m away from the boundary."
            )
        
        # Check if rider is already assigned to this specific geofence
        existing_geofence_assignment = CampaignGeofenceAssignment.objects.filter(
            campaign_geofence=geofence,
            rider=rider,
            status__in=['assigned', 'active']
        ).exists()
        
        if existing_geofence_assignment:
            return False, 'You are already assigned to this geofence'
        
        # Check if rider is already in this campaign (any geofence)
        existing_assignment = CampaignRiderAssignment.objects.filter(
            campaign=geofence.campaign,
            rider=rider,
            status__in=['assigned', 'accepted', 'active']
        ).exists()
        
        if existing_assignment:
            return False, 'You are already assigned to a geofence in this campaign'
        
        logger.info(f"Geofence eligibility validation passed")
        return True, ''