# apps/accounts/views.py
import random
import hashlib
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from celery import shared_task
import requests

from .models import User, OTPVerification
from apps.riders.models import Rider
from .serializers import RiderProfileSerializer

logger = logging.getLogger(__name__)

class AuthErrorCodes:
    INVALID_PHONE = 'INVALID_PHONE'
    RATE_LIMITED = 'RATE_LIMITED'
    SMS_FAILED = 'SMS_FAILED'
    INVALID_OTP = 'INVALID_OTP'
    OTP_EXPIRED = 'OTP_EXPIRED'
    TOO_MANY_ATTEMPTS = 'TOO_MANY_ATTEMPTS'
    SERVER_ERROR = 'SERVER_ERROR'

@api_view(['POST'])
@permission_classes([AllowAny])
def send_otp(request):
    """
    Send OTP to rider's phone number using Kudisms
    Endpoint: POST /api/v1/auth/send-otp/
    """
    try:
        phone_number = request.data.get('phone_number')
        if not phone_number:
            return Response({
                'success': False,
                'message': 'Phone number is required',
                'code': AuthErrorCodes.INVALID_PHONE
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Clean and validate phone number
        cleaned_phone = clean_phone_number(phone_number)
        if not is_valid_nigerian_phone(cleaned_phone):
            return Response({
                'success': False,
                'message': 'Please enter a valid Nigerian phone number (e.g., 08031234567)',
                'code': AuthErrorCodes.INVALID_PHONE
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check rate limiting (1 OTP per minute per phone)
        rate_limit_key = f'otp_rate_limit_{cleaned_phone}'
        if cache.get(rate_limit_key):
            return Response({
                'success': False,
                'message': 'Please wait 60 seconds before requesting another code',
                'code': AuthErrorCodes.RATE_LIMITED
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Set rate limit (1 minute)
        cache.set(rate_limit_key, True, timeout=60)
        
        # Test Redis connection first
        try:
            cache_test_key = f"otp_test_{cleaned_phone}"
            cache.set(cache_test_key, "test", timeout=10)
            cache_test_result = cache.get(cache_test_key)
            logger.info(f"Redis cache test: {cache_test_result}")
        except Exception as cache_error:
            logger.error(f"Redis cache test failed: {str(cache_error)}")
        
        # Test Celery broker connection
        try:
            from celery import current_app
            from django.conf import settings
            
            # Log the Redis URLs being used
            redis_url = getattr(settings, 'CELERY_BROKER_URL', 'NOT_SET')
            logger.info(f"Django CELERY_BROKER_URL: {redis_url}")
            logger.info(f"Celery app broker: {current_app.conf.broker_url}")
            
            inspect = current_app.control.inspect()
            stats = inspect.stats()
            logger.info(f"Celery broker connection test: {bool(stats)}")
        except Exception as broker_error:
            logger.error(f"Celery broker connection test failed: {str(broker_error)}")
        
        # Log before calling Celery task
        logger.info(f"About to send OTP task for {cleaned_phone}")
        
        # Send OTP via Kudisms OTP service (async)
        try:
            result = send_otp_kudisms.delay(cleaned_phone)
            logger.info(f"Celery task submitted successfully: {result.id}")
        except Exception as task_error:
            logger.error(f"Failed to submit Celery task: {str(task_error)}")
            return Response({
                'success': False,
                'message': 'Failed to queue OTP request. Please try again.',
                'code': AuthErrorCodes.SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Check if task completed immediately (for development)
        if hasattr(result, 'get'):
            try:
                logger.info(f"Waiting for task result...")
                task_result = result.get(timeout=5)  # Wait max 5 seconds
                logger.info(f"Task result: {task_result}")
                if not task_result.get('success'):
                    return Response({
                        'success': False,
                        'message': f"Failed to send OTP: {task_result.get('error', 'Unknown error')}",
                        'code': AuthErrorCodes.SMS_FAILED
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as timeout_error:
                # Task is running async, continue
                logger.info(f"Task running async (timeout): {str(timeout_error)}")
                pass
        
        # Log OTP attempt
        logger.info(f"OTP sent to {cleaned_phone}")
        
        return Response({
            'success': True,
            'message': 'Verification code sent to your phone',
            'expires_in_minutes': 5,
            'phone_number': cleaned_phone  # Return formatted phone for UI
        })
        
    except Exception as e:
        logger.error(f"Send OTP error: {str(e)}")
        return Response({
            'success': False,
            'message': 'Failed to send verification code. Please try again.',
            'code': AuthErrorCodes.SERVER_ERROR
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    """
    Verify OTP and authenticate/register rider
    Endpoint: POST /api/v1/auth/verify-otp/
    """
    try:
        phone_number = request.data.get('phone_number')
        otp_code = request.data.get('otp')
        device_info = request.data.get('device_info', {})
        
        if not phone_number or not otp_code:
            return Response({
                'success': False,
                'message': 'Phone number and verification code are required',
                'code': AuthErrorCodes.INVALID_OTP
            }, status=status.HTTP_400_BAD_REQUEST)
        
        cleaned_phone = clean_phone_number(phone_number)
        
        # Validate OTP format (4 digits for Kudisms)
        if len(otp_code) != 4 or not otp_code.isdigit():
            return Response({
                'success': False,
                'message': 'Please enter a valid 4-digit verification code',
                'code': AuthErrorCodes.INVALID_OTP
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # TEMPORARY: Skip OTP record lookup in development mode
        # TODO: Uncomment when KudiSMS issue is resolved
        
        # # Get the most recent OTP verification for this phone
        # try:
        #     otp_verification = OTPVerification.objects.filter(
        #         phone_number=cleaned_phone,
        #         status='sent',
        #         expires_at__gt=timezone.now()
        #     ).latest('created_at')
        # except OTPVerification.DoesNotExist:
        #     return Response({
        #         'success': False,
        #         'message': 'No valid verification code found. Please request a new one.',
        #         'code': AuthErrorCodes.OTP_EXPIRED
        #     }, status=status.HTTP_400_BAD_REQUEST)
        # 
        # # Check if max attempts reached
        # if otp_verification.attempts_used >= otp_verification.max_attempts:
        #     otp_verification.status = 'failed'
        #     otp_verification.save()
        #     return Response({
        #         'success': False,
        #         'message': 'Too many failed attempts. Please request a new code.',
        #         'code': AuthErrorCodes.TOO_MANY_ATTEMPTS
        #     }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create a temporary OTP verification record for development mode
        # Use get_or_create to avoid duplicate key errors
        otp_verification, created = OTPVerification.objects.get_or_create(
            phone_number=cleaned_phone,
            defaults={
                'verification_id': f'dev-mode-{cleaned_phone}-{timezone.now().timestamp()}',
                'status': 'sent',
                'expires_at': timezone.now() + timedelta(minutes=5)
            }
        )
        
        # TEMPORARY: Accept any 4-digit code while KudiSMS API issue is being resolved
        # TODO: Uncomment the lines below once KudiSMS "missing channel" issue is fixed
        logger.info(f"DEVELOPMENT MODE: Accepting any 4-digit OTP code for {cleaned_phone}")
        
        # # Verify OTP with Kudisms
        # verification_result = verify_otp_kudisms.delay(
        #     otp_verification.verification_id, 
        #     otp_code
        # )
        # 
        # # Wait for verification result
        # try:
        #     result = verification_result.get(timeout=10)  # Wait max 10 seconds
        #     
        #     if not result.get('success'):
        #         # Update local attempts counter
        #         otp_verification.attempts_used += 1
        #         if otp_verification.attempts_used >= otp_verification.max_attempts:
        #             otp_verification.status = 'failed'
        #         otp_verification.save()
        #         
        #         attempts_remaining = otp_verification.max_attempts - otp_verification.attempts_used
        #         return Response({
        #             'success': False,
        #             'message': f'Invalid verification code. {max(0, attempts_remaining)} attempts remaining.',
        #             'code': AuthErrorCodes.INVALID_OTP,
        #             'attempts_remaining': max(0, attempts_remaining)
        #         }, status=status.HTTP_400_BAD_REQUEST)
        #         
        # except Exception as e:
        #     logger.error(f"OTP verification task failed: {str(e)}")
        #     return Response({
        #         'success': False,
        #         'message': 'Verification service temporarily unavailable. Please try again.',
        #         'code': AuthErrorCodes.SERVER_ERROR
        #     }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Mark OTP as verified (development mode)
        otp_verification.status = 'verified'
        otp_verification.save()
        
        # Log successful verification (development mode)
        logger.info(f"OTP verified successfully (DEV MODE) for {cleaned_phone}")
        
        # Get or create user and rider
        user, rider, is_new_user = get_or_create_rider(cleaned_phone, device_info)
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token
        
        # Update last login
        user.last_login = timezone.now()
        user.save()
        
        # Log successful authentication
        logger.info(f"Rider authenticated: {cleaned_phone}, new_user: {is_new_user}")
        
        return Response({
            'success': True,
            'access_token': str(access_token),
            'refresh_token': str(refresh),
            'rider': RiderProfileSerializer(rider).data,
            'is_new_user': is_new_user,
            'message': 'Welcome to Stika!' if is_new_user else 'Welcome back!'
        })
        
    except Exception as e:
        logger.error(f"Verify OTP error: {str(e)}")
        return Response({
            'success': False,
            'message': 'Authentication failed. Please try again.',
            'code': AuthErrorCodes.SERVER_ERROR
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token(request):
    """
    Refresh JWT access token
    Endpoint: POST /api/v1/auth/refresh/
    """
    try:
        refresh_token = request.data.get('refresh_token')
        device_info = request.data.get('device_info', {})
        
        if not refresh_token:
            return Response({
                'success': False,
                'message': 'Refresh token is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            refresh = RefreshToken(refresh_token)
            user_id = refresh.payload.get('user_id')
            
            # Get user and update device info
            user = User.objects.get(id=user_id)
            
            # Update rider's last seen if they have a rider profile
            if hasattr(user, 'rider_profile'):
                rider = user.rider_profile
                rider.user.last_login = timezone.now()
                rider.user.save()
                
                # Update device info if provided
                if device_info and hasattr(rider, 'devices'):
                    # Update or create device record
                    device_id = device_info.get('device_id')
                    if device_id:
                        from apps.riders.models import RiderDevice
                        device, created = RiderDevice.objects.get_or_create(
                            rider=rider,
                            device_id=device_id,
                            defaults={
                                'device_name': device_info.get('device_name', 'Unknown'),
                                'platform': device_info.get('platform', 'unknown'),
                                'os_version': device_info.get('os_version', ''),
                                'app_version': device_info.get('app_version', ''),
                            }
                        )
                        device.last_login = timezone.now()
                        device.save()
            
            # Generate new access token
            access_token = refresh.access_token
            
            response_data = {
                'success': True,
                'access_token': str(access_token),
            }
            
            # Include rider data if available
            if hasattr(user, 'rider_profile'):
                response_data['rider'] = RiderProfileSerializer(user.rider_profile).data
            
            return Response(response_data)
            
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Invalid or expired refresh token'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
    except Exception as e:
        logger.error(f"Refresh token error: {str(e)}")
        return Response({
            'success': False,
            'message': 'Token refresh failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    Logout rider and blacklist refresh token
    Endpoint: POST /api/v1/auth/logout/
    """
    try:
        refresh_token = request.data.get('refresh_token')
        
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass  # Token might already be invalid
        
        # Update rider last seen
        if hasattr(request.user, 'rider_profile'):
            rider = request.user.rider_profile
            # Mark as offline or update status as needed
            
        logger.info(f"User logged out: {request.user.email}")
        
        return Response({
            'success': True,
            'message': 'Logged out successfully'
        })
        
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return Response({
            'success': True,  # Always return success for logout
            'message': 'Logged out'
        })

# Utility functions
def clean_phone_number(phone_number):
    """Clean and format Nigerian phone number"""
    # Remove any non-digit characters except +
    cleaned = ''.join(char for char in phone_number if char.isdigit() or char == '+')
    
    # Handle different formats
    if cleaned.startswith('+234'):
        return cleaned
    elif cleaned.startswith('234'):
        return f'+{cleaned}'
    elif cleaned.startswith('0') and len(cleaned) == 11:
        return f'+234{cleaned[1:]}'
    elif len(cleaned) == 10:
        return f'+234{cleaned}'
    
    return cleaned

def is_valid_nigerian_phone(phone_number):
    """Validate Nigerian phone number format"""
    if not phone_number.startswith('+234'):
        return False
    
    number = phone_number[4:]  # Remove +234
    if len(number) != 10:
        return False
    
    # Valid Nigerian mobile prefixes
    valid_prefixes = [
        '803', '806', '813', '814', '816', '903', '906',  # MTN
        '802', '808', '812', '701', '902', '904', '907', '912',  # Airtel
        '805', '807', '815', '811', '905',  # Glo
        '809', '818', '817', '908', '909',  # 9mobile
    ]
    
    prefix = number[:3]
    return prefix in valid_prefixes

def generate_otp():
    """Generate 6-digit OTP"""
    return f"{random.randint(100000, 999999)}"

def get_or_create_rider(phone_number, device_info):
    """Get or create user and rider profile"""
    from datetime import date
    
    # Try to find existing user by phone
    try:
        user = User.objects.get(phone_number=phone_number, user_type='rider')
        # Check if user has a rider profile
        try:
            rider = user.rider_profile
            is_new_user = False
        except Rider.DoesNotExist:
            # User exists but no rider profile, create one
            rider = Rider.objects.create(
                user=user,
                phone_number=phone_number,
                date_of_birth=date(1990, 1, 1),  # Default date, user can update later
                gender='male',  # Default gender, user can update later
                emergency_contact_name='',
                emergency_contact_phone=phone_number,  # Use same phone as emergency
                address='',
                city='',
                state='',
                tricycle_registration='',
                status='pending'
            )
            is_new_user = False  # User existed, just missing rider profile
    except User.DoesNotExist:
        # Create new user and rider
        user = User.objects.create(
            username=phone_number,  # Use phone as username initially
            email=f"{phone_number.replace('+', '')}@temp.stika.ng",  # Temporary email
            phone_number=phone_number,
            user_type='rider',
            is_verified=True  # Phone is verified via OTP
        )
        
        # Create rider profile
        rider = Rider.objects.create(
            user=user,
            phone_number=phone_number,
            date_of_birth=date(1990, 1, 1),  # Default date, user can update later
            gender='male',  # Default gender, user can update later
            emergency_contact_name='',
            emergency_contact_phone=phone_number,  # Use same phone as emergency
            address='',
            city='',
            state='',
            tricycle_registration='',
            status='pending'  # Will need to complete verification
        )
        
        is_new_user = True
    
    return user, rider, is_new_user


# Celery task for sending OTP via Kudisms
@shared_task(bind=True, max_retries=3)
def send_otp_kudisms(self, phone_number):
    """
    Send OTP using Kudisms OTP endpoint
    """
    try:
        logger.info(f"=== Starting OTP task for {phone_number} ===")
        
        # Get Kudisms configuration from settings
        token = getattr(settings, 'KUDISMS_TOKEN', '')
        sender_id = getattr(settings, 'KUDISMS_SENDER_ID', '')
        appname_code = getattr(settings, 'KUDISMS_APPNAME_CODE', '')
        template_code = getattr(settings, 'KUDISMS_TEMPLATE_CODE', '')
        
        logger.info(f"Kudisms config - Token present: {bool(token)}, Sender ID: {sender_id}, AppName: {appname_code}, Template: {template_code}")
        
        if not all([token, sender_id, appname_code, template_code]):
            logger.error("Kudisms credentials not configured properly")
            return {'success': False, 'error': 'OTP service not configured'}
        
        # Prepare form data for Kudisms OTP endpoint
        form_data = {
            'token': token,
            'senderID': sender_id,
            'recipients': phone_number,
            'appnamecode': appname_code,
            'templatecode': template_code,
            'otp_type': 'NUMERIC',
            'otp_length': '4',
            'otp_duration': '5',  # 5 minutes
            'channel': 'sms'
        }
        
        logger.info(f"Sending request to KudiSMS with data: {form_data}")
        
        # Send request to Kudisms OTP endpoint (multipart/form-data)
        # Use the exact format from KudiSMS documentation
        response = requests.post(
            'https://my.kudisms.net/api/sendotp',
            headers={},
            data=form_data,
            files=[],
            timeout=30
        )
        
        logger.info(f"KudiSMS response status: {response.status_code}")
        logger.info(f"KudiSMS response text: {response.text}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                
                if data.get('status') == 'success' and data.get('error_code') == '000':
                    # Success response
                    verification_id = data.get('verification_id')
                    cost = float(data.get('cost', 0))
                    balance = data.get('balance', '0')
                    
                    # Store verification record
                    otp_verification = OTPVerification.objects.create(
                        phone_number=phone_number,
                        verification_id=verification_id,
                        cost=cost,
                        expires_at=timezone.now() + timedelta(minutes=5)
                    )
                    
                    logger.info(f"OTP sent successfully to {phone_number}, verification_id: {verification_id}")
                    
                    return {
                        'success': True,
                        'verification_id': verification_id,
                        'cost': cost,
                        'balance': balance,
                        'expires_in_minutes': 5
                    }
                else:
                    # Error response
                    error_code = data.get('error_code', 'unknown')
                    error_msg = data.get('msg', 'Unknown error')
                    logger.error(f"Kudisms OTP API error: {error_code} - {error_msg}")
                    
                    # Handle specific error codes
                    if error_code == '109':
                        raise Exception("Insufficient balance for OTP service")
                    elif error_code == '107':
                        raise Exception("Invalid phone number format")
                    else:
                        raise Exception(f"OTP send failed: {error_msg}")
                        
            except ValueError as e:
                logger.error(f"Invalid JSON response from Kudisms: {response.text}")
                raise Exception("Invalid response from OTP service")
        else:
            raise Exception(f"OTP API returned status {response.status_code}")
            
    except Exception as exc:
        logger.error(f"Kudisms OTP task failed: {str(exc)}")
        
        if self.request.retries < self.max_retries:
            # Exponential backoff: 60s, 120s, 240s
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(countdown=countdown, exc=exc)
        else:
            # Final failure - log critical error
            logger.critical(f"Kudisms OTP failed permanently for {phone_number}")
            return {'success': False, 'error': str(exc)}

# Celery task for verifying OTP via Kudisms
@shared_task(bind=True, max_retries=2)
def verify_otp_kudisms(self, verification_id, otp_code):
    """
    Verify OTP using Kudisms verification endpoint
    """
    try:
        token = getattr(settings, 'KUDISMS_TOKEN', '')
        
        if not token:
            logger.error("Kudisms token not configured")
            return {'success': False, 'error': 'OTP service not configured'}
        
        # Prepare form data for verification
        form_data = {
            'token': token,
            'verification_id': verification_id,
            'otp': otp_code
        }
        
        # Send verification request
        response = requests.post(
            'https://my.kudisms.net/api/verifyotp',
            data=form_data,
            timeout=30
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                
                if data.get('status') == 'success' and data.get('error_code') == '000':
                    # OTP verified successfully
                    logger.info(f"OTP verified successfully for verification_id: {verification_id}")
                    
                    # Update verification record
                    try:
                        otp_verification = OTPVerification.objects.get(verification_id=verification_id)
                        otp_verification.status = 'verified'
                        otp_verification.save()
                    except OTPVerification.DoesNotExist:
                        logger.warning(f"OTP verification record not found: {verification_id}")
                    
                    return {
                        'success': True,
                        'message': 'OTP verified successfully'
                    }
                else:
                    # Verification failed
                    error_code = data.get('error_code', 'unknown')
                    error_msg = data.get('msg', 'Invalid OTP')
                    
                    # Update attempts
                    try:
                        otp_verification = OTPVerification.objects.get(verification_id=verification_id)
                        otp_verification.attempts_used += 1
                        if otp_verification.attempts_used >= otp_verification.max_attempts:
                            otp_verification.status = 'failed'
                        otp_verification.save()
                    except OTPVerification.DoesNotExist:
                        pass
                    
                    logger.warning(f"OTP verification failed: {error_code} - {error_msg}")
                    
                    return {
                        'success': False,
                        'error_code': error_code,
                        'error': error_msg
                    }
                    
            except ValueError:
                logger.error(f"Invalid JSON response from Kudisms verify: {response.text}")
                return {'success': False, 'error': 'Invalid response from verification service'}
        else:
            return {'success': False, 'error': f'Verification service returned status {response.status_code}'}
            
    except Exception as exc:
        logger.error(f"Kudisms OTP verification failed: {str(exc)}")
        return {'success': False, 'error': str(exc)}

