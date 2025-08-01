# Geofence Join with Verification Implementation Plan

## Overview
Update the join geofence flow to require successful verification as a prerequisite. This ensures riders are physically present and have valid stickers before joining any geofence.

## Current Implementation Analysis
After examining the existing codebase, I found:

### Existing Join Flow (`apps/campaigns/views.py:join_geofence`)
- Uses `CampaignJoinSerializer` with comprehensive validation
- Location validation: Checks rider is within geofence radius using PostGIS
- Creates `CampaignRiderAssignment` and `CampaignGeofenceAssignment` atomically
- Proper error handling and logging patterns
- Response format: `{'success': bool, 'message': str, 'assignment': dict, 'geofence_assignment': dict}`

### Existing Serializer Patterns (`apps/campaigns/serializers.py`)
- `CampaignJoinSerializer`: Handles geofence join validation
- Validates rider eligibility, campaign status, geofence availability
- Distance calculation: `rider_location.distance(geofence_center) * 111320` (degrees to meters)
- Comprehensive error messages with distance feedback

### Current Verification System (`apps/verification/models.py`)
- Basic `VerificationRequest` model exists
- Status flow: pending → processing → passed/failed/manual_review
- Links to rider and campaign

## Requirements Summary
1. **Verification Requirement**: Riders must complete verification (photo + location) before joining
2. **Valid Image Detection**: Basic image validation (for now, just detect valid image format/content)
3. **Cooldown Period**: 1-minute cooldown between verification attempts
4. **Offline Resilience**: Handle duplicate join attempts and network failures gracefully
5. **Client-side Validation**: Check rider status and geofence boundaries before API call

## Technical Architecture

### 1. Backend Implementation

#### 1.1 Database Changes

**Update VerificationRequest model:**
```python
# apps/verification/models.py
class VerificationRequest(BaseModel):
    # Existing fields...
    
    # New fields for geofence joining
    geofence = models.ForeignKey('campaigns.CampaignGeofence', on_delete=models.CASCADE, null=True, blank=True)
    verification_type = models.CharField(
        max_length=20,
        choices=[
            ('random', 'Random Verification'),
            ('geofence_join', 'Geofence Join Verification'),
            ('manual', 'Manual Verification'),
        ],
        default='random'
    )
    
    # Cooldown tracking
    attempted_at = models.DateTimeField(auto_now_add=True)
    can_retry_after = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        indexes = [
            models.Index(fields=['rider', 'verification_type', 'attempted_at']),
            models.Index(fields=['can_retry_after']),
        ]
```

**Add verification cooldown tracking:**
```python
# apps/verification/models.py
class VerificationCooldown(BaseModel):
    """Track verification attempt cooldowns per rider"""
    rider = models.ForeignKey('riders.Rider', on_delete=models.CASCADE)
    verification_type = models.CharField(max_length=20)
    last_attempt = models.DateTimeField()
    cooldown_until = models.DateTimeField()
    attempt_count = models.PositiveIntegerField(default=1)
    
    class Meta:
        unique_together = ['rider', 'verification_type']
```

#### 1.2 New API Endpoints

**Primary endpoint (builds on existing patterns):**
```python
# apps/campaigns/urls.py
urlpatterns = [
    # Existing URLs...
    path('geofences/join/', views.join_geofence, name='join_geofence'),  # Current endpoint
    path('geofences/join-with-verification/', views.join_geofence_with_verification, name='join_geofence_verification'),
    path('geofences/check-join-eligibility/', views.check_geofence_join_eligibility, name='check_join_eligibility'),
]
```

**New serializer (extends existing CampaignJoinSerializer):**
```python
# apps/campaigns/serializers.py
class CampaignJoinWithVerificationSerializer(CampaignJoinSerializer):
    """Extends CampaignJoinSerializer to include verification data"""
    
    # Image data (multipart upload)
    image = serializers.ImageField()
    accuracy = serializers.DecimalField(max_digits=8, decimal_places=2)
    timestamp = serializers.DateTimeField()
    
    class Meta(CampaignJoinSerializer.Meta):
        pass
    
    def validate_image(self, value):
        """Validate image file"""
        if value.size > 5 * 1024 * 1024:  # 5MB limit
            raise serializers.ValidationError("Image file too large (max 5MB)")
        
        if not value.content_type.startswith('image/'):
            raise serializers.ValidationError("Invalid image format")
        
        return value
    
    def validate(self, attrs):
        """Enhanced validation including cooldown checks"""
        # First run parent validation (all existing checks)
        attrs = super().validate(attrs)
        
        # Check verification cooldown
        rider = self.context['request'].user.rider_profile
        can_verify, cooldown_remaining = CooldownManager.check_cooldown(
            rider, 'geofence_join'
        )
        
        if not can_verify:
            raise serializers.ValidationError(
                f"Please wait {int(cooldown_remaining)} seconds before trying again"
            )
        
        # Check for recent duplicate attempts
        recent_attempt = VerificationRequest.objects.filter(
            rider=rider,
            geofence_id=attrs['geofence_id'],
            verification_type='geofence_join',
            created_at__gte=timezone.now() - timedelta(minutes=5)
        ).first()
        
        if recent_attempt and recent_attempt.status == 'passed':
            # Check if already joined successfully
            geofence = CampaignGeofence.objects.get(id=attrs['geofence_id'])
            existing_assignment = CampaignGeofenceAssignment.objects.filter(
                campaign_geofence=geofence,
                rider=rider,
                status__in=['assigned', 'active']
            ).first()
            
            if existing_assignment:
                attrs['_existing_assignment'] = existing_assignment
                attrs['_is_duplicate'] = True
        
        return attrs
```

**Implementation (follows existing join_geofence pattern):**
```python
# apps/campaigns/views.py
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def join_geofence_with_verification(request):
    """
    Join geofence with verification requirement
    Follows same pattern as existing join_geofence but adds verification step
    
    Expected data (multipart/form-data):
    - geofence_id: UUID
    - latitude: float
    - longitude: float
    - accuracy: float
    - image: file
    - timestamp: ISO string
    """
    logger.info(f"=== JOIN GEOFENCE WITH VERIFICATION REQUEST ===")
    logger.info(f"User: {request.user.id} ({request.user.phone_number})")
    logger.info(f"Data: {dict(request.data)}")
    
    try:
        # Get geofence first (same as existing join_geofence)
        geofence_id = request.data.get('geofence_id')
        if not geofence_id:
            return Response({
                'success': False,
                'message': 'geofence_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            geofence = CampaignGeofence.objects.select_related('campaign').get(id=geofence_id)
        except CampaignGeofence.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Geofence not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Create request data with campaign_id (same pattern)
        request_data = request.data.copy()
        request_data['campaign_id'] = str(geofence.campaign.id)
        
        # Use enhanced serializer for validation
        serializer = CampaignJoinWithVerificationSerializer(
            data=request_data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.warning(f"Invalid join with verification request: {serializer.errors}")
            return Response({
                'success': False,
                'message': 'Invalid request',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check for duplicate (handle offline resilience)
        if serializer.validated_data.get('_is_duplicate'):
            existing_assignment = serializer.validated_data['_existing_assignment']
            logger.info(f"Duplicate join attempt - returning existing assignment")
            
            # Return success with existing assignment data
            assignment_serializer = CampaignRiderAssignmentSerializer(
                existing_assignment.campaign_rider_assignment
            )
            geofence_serializer = CampaignGeofenceAssignmentSerializer(existing_assignment)
            
            return Response({
                'success': True,
                'message': f'Already joined {geofence.name}',
                'was_duplicate': True,
                'assignment': assignment_serializer.data,
                'geofence_assignment': geofence_serializer.data,
                'verification_id': 'existing'
            })
        
        # Process verification and join atomically
        with transaction.atomic():
            rider = request.user.rider_profile
            
            # 1. Create verification request
            verification = VerificationRequest.objects.create(
                rider=rider,
                campaign=geofence.campaign,
                geofence=geofence,  # New field
                verification_type='geofence_join',  # New field
                image=serializer.validated_data['image'],
                location=Point(
                    float(serializer.validated_data['longitude']),
                    float(serializer.validated_data['latitude'])
                ),
                accuracy=float(serializer.validated_data['accuracy']),
                timestamp=serializer.validated_data['timestamp'],
                image_metadata={
                    'geofence_join_attempt': True,
                    'geofence_id': str(geofence_id),
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                }
            )
            
            # 2. Process verification (basic image validation for now)
            verification_passed = VerificationProcessor.process_join_verification(verification)
            
            if not verification_passed:
                # Set cooldown and return failure
                CooldownManager.set_cooldown(rider, 'geofence_join')
                
                return Response({
                    'success': False,
                    'message': 'Verification failed: Invalid image or sticker not detected',
                    'verification_id': str(verification.id),
                    'verification_status': verification.status
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 3. Verification passed - proceed with join (reuse existing logic)
            campaign_assignment = CampaignRiderAssignment.objects.create(
                campaign=geofence.campaign,
                rider=rider,
                status='active',  # Active immediately after verification
                assigned_by=request.user
            )
            
            geofence_assignment = CampaignGeofenceAssignment.objects.create(
                campaign_geofence=geofence,
                rider=rider,
                campaign_rider_assignment=campaign_assignment,
                status='active',
                assigned_at=timezone.now(),
                started_at=timezone.now()  # Start immediately
            )
            
            # 4. Update geofence rider count
            geofence.current_riders += 1
            geofence.save(update_fields=['current_riders'])
            
            # 5. Update rider availability (same as existing)
            if hasattr(rider, 'current_campaign_count') and hasattr(rider, 'max_concurrent_campaigns'):
                if rider.current_campaign_count >= rider.max_concurrent_campaigns:
                    rider.is_available = False
                    rider.save()
            
            logger.info(f"Successfully assigned rider {rider.rider_id} to geofence {geofence.name} with verification")
            
            # Return response (same format as existing join_geofence)
            assignment_serializer = CampaignRiderAssignmentSerializer(campaign_assignment)
            geofence_serializer = CampaignGeofenceAssignmentSerializer(geofence_assignment)
            
            return Response({
                'success': True,
                'message': f'Successfully joined {geofence.name} with verification',
                'verification_id': str(verification.id),
                'assignment': assignment_serializer.data,
                'geofence_assignment': geofence_serializer.data,
                'assigned_geofence': {
                    'id': str(geofence.id),
                    'name': geofence.name,
                    'rate_type': geofence.rate_type,
                    'rate_per_km': float(geofence.rate_per_km),
                    'rate_per_hour': float(geofence.rate_per_hour),
                    'fixed_daily_rate': float(geofence.fixed_daily_rate),
                    'center_latitude': float(geofence.center_latitude),
                    'center_longitude': float(geofence.center_longitude),
                    'radius_meters': geofence.radius_meters,
                }
            }, status=status.HTTP_201_CREATED)
            
    except Exception as e:
        logger.error(f"=== JOIN GEOFENCE WITH VERIFICATION ERROR ===")
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return Response({
            'success': False,
            'message': 'Failed to join geofence with verification'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

**Eligibility check endpoint:**
```python
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_geofence_join_eligibility(request):
    """
    Check if rider can join a geofence without actually joining
    Query params: geofence_id, latitude, longitude
    """
    
    # Returns:
    # - can_join: boolean
    # - reasons: list of blocking reasons
    # - cooldown_remaining: seconds (if in cooldown)
    # - geofence_info: basic geofence details
```

#### 1.3 Verification Processing

**Simple image validation:**
```python
# apps/verification/services.py
class VerificationProcessor:
    @staticmethod
    def validate_image_basic(image_file):
        """Basic image validation - valid format, size, not corrupted"""
        try:
            # File size check
            if image_file.size > 5 * 1024 * 1024:  # 5MB
                return False, "Image too large (max 5MB)"
            
            # Format validation
            if not image_file.content_type.startswith('image/'):
                return False, "Invalid image format"
            
            # Try to open and validate image
            from PIL import Image
            image = Image.open(image_file)
            image.verify()
            
            # Basic dimension check
            if image.width < 200 or image.height < 200:
                return False, "Image resolution too low"
            
            return True, "Valid image"
            
        except Exception as e:
            return False, f"Invalid image: {str(e)}"
    
    @staticmethod
    def process_join_verification(verification_request):
        """Process verification for geofence joining"""
        is_valid, message = VerificationProcessor.validate_image_basic(
            verification_request.image
        )
        
        if is_valid:
            verification_request.status = 'passed'
            verification_request.confidence_score = 0.95  # High confidence for valid images
            verification_request.ai_analysis = {
                'validation_type': 'basic_image_check',
                'is_valid_image': True,
                'processed_at': timezone.now().isoformat(),
                'message': message
            }
        else:
            verification_request.status = 'failed'
            verification_request.confidence_score = 0.0
            verification_request.ai_analysis = {
                'validation_type': 'basic_image_check',
                'is_valid_image': False,
                'failure_reason': message,
                'processed_at': timezone.now().isoformat()
            }
        
        verification_request.save()
        return verification_request.status == 'passed'
```

#### 1.4 Cooldown Management

```python
# apps/verification/services.py
class CooldownManager:
    COOLDOWN_PERIODS = {
        'geofence_join': 60,  # 1 minute
        'random': 300,        # 5 minutes
        'manual': 0,          # No cooldown
    }
    
    @classmethod
    def check_cooldown(cls, rider, verification_type):
        """Check if rider is in cooldown period"""
        try:
            cooldown = VerificationCooldown.objects.get(
                rider=rider,
                verification_type=verification_type
            )
            
            if timezone.now() < cooldown.cooldown_until:
                remaining = (cooldown.cooldown_until - timezone.now()).total_seconds()
                return False, remaining
            else:
                # Cooldown expired, can proceed
                return True, 0
                
        except VerificationCooldown.DoesNotExist:
            # No cooldown record, can proceed
            return True, 0
    
    @classmethod
    def set_cooldown(cls, rider, verification_type, additional_seconds=0):
        """Set cooldown after verification attempt"""
        cooldown_seconds = cls.COOLDOWN_PERIODS.get(verification_type, 60)
        cooldown_seconds += additional_seconds
        
        cooldown_until = timezone.now() + timedelta(seconds=cooldown_seconds)
        
        cooldown, created = VerificationCooldown.objects.update_or_create(
            rider=rider,
            verification_type=verification_type,
            defaults={
                'last_attempt': timezone.now(),
                'cooldown_until': cooldown_until,
                'attempt_count': 1 if created else F('attempt_count') + 1
            }
        )
        return cooldown
```

#### 1.5 Duplicate Join Handling

```python
# apps/campaigns/services.py
class GeofenceJoinService:
    @staticmethod
    def handle_duplicate_join_attempt(rider, geofence):
        """
        Handle cases where rider might already be joined
        Returns: (is_duplicate, existing_assignment, should_return_success)
        """
        
        # Check for existing active assignment
        existing_assignment = CampaignGeofenceAssignment.objects.filter(
            rider=rider,
            campaign_geofence=geofence,
            status__in=['assigned', 'active']
        ).first()
        
        if existing_assignment:
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
                return True, existing_assignment, True
            else:
                # Existing assignment but no recent verification
                return True, existing_assignment, False
        
        return False, None, False
    
    @staticmethod
    def create_join_with_verification(rider, geofence, verification_request):
        """Create geofence assignment after successful verification"""
        
        with transaction.atomic():
            # Create campaign assignment
            campaign_assignment, created = CampaignRiderAssignment.objects.get_or_create(
                campaign=geofence.campaign,
                rider=rider,
                defaults={
                    'status': 'active',
                    'assigned_by': rider.user,
                    'started_at': timezone.now(),
                }
            )
            
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
            
            # Update geofence rider count only if new assignment
            if geo_created:
                geofence.current_riders += 1
                geofence.save(update_fields=['current_riders'])
            
            # Link verification to assignment
            verification_request.ai_analysis.update({
                'geofence_assignment_id': str(geofence_assignment.id),
                'campaign_assignment_id': str(campaign_assignment.id)
            })
            verification_request.save()
            
            return campaign_assignment, geofence_assignment
```

### 2. Mobile App Implementation

#### 2.1 Enhanced Campaign Service

```dart
// lib/src/core/services/campaign_service.dart

// New result class for comprehensive responses
class GeofenceJoinResult {
  final bool success;
  final String? error;
  final String? verificationId;
  final String? assignmentId;
  final bool wasDuplicate;
  final Map<String, dynamic>? data;
  
  const GeofenceJoinResult({
    required this.success,
    this.error,
    this.verificationId,
    this.assignmentId,
    this.wasDuplicate = false,
    this.data,
  });
}

// Enhanced geofence validation
class GeofenceValidator {
  static Future<ValidationResult> validateJoinEligibility({
    required Rider rider,
    required Geofence geofence,
    required double latitude,
    required double longitude,
  }) async {
    
    // Check rider status
    if (rider.status != RiderStatus.active) {
      return ValidationResult(
        isValid: false,
        reason: 'Rider must be active to join geofences',
      );
    }
    
    // Check if already in a campaign
    if (rider.currentCampaignId != null) {
      return ValidationResult(
        isValid: false,
        reason: 'You are already in a campaign. Leave current campaign first.',
      );
    }
    
    // Check geofence availability
    if (!geofence.hasAvailableSlots) {
      return ValidationResult(
        isValid: false,
        reason: 'This geofence is full. Try another area.',
      );
    }
    
    // Check location (client-side validation)
    bool isInGeofence = await _isRiderInGeofence(
      latitude, longitude, geofence
    );
    
    if (!isInGeofence) {
      return ValidationResult(
        isValid: false,
        reason: 'You must be within the ${geofence.name} area to join',
      );
    }
    
    return ValidationResult(isValid: true);
  }
}

// Main service methods
class CampaignService {
  // Check eligibility before showing verification UI
  Future<ValidationResult> checkGeofenceJoinEligibility(String geofenceId) async {
    try {
      final response = await _apiService.get(
        '/campaigns/geofences/check-join-eligibility/',
        queryParameters: {'geofence_id': geofenceId},
      );
      
      if (response.statusCode == 200) {
        final data = response.data;
        return ValidationResult(
          isValid: data['can_join'] ?? false,
          reason: data['reasons']?.join(', '),
          cooldownRemaining: data['cooldown_remaining'],
          data: data,
        );
      }
      
      return ValidationResult(
        isValid: false,
        reason: 'Failed to check eligibility',
      );
    } catch (e) {
      return ValidationResult(
        isValid: false,
        reason: 'Network error: $e',
      );
    }
  }
  
  // Combined join with verification
  Future<GeofenceJoinResult> joinGeofenceWithVerification({
    required String geofenceId,
    required String imagePath,
    required double latitude,
    required double longitude,
    required double accuracy,
  }) async {
    try {
      print('🎯 JOIN WITH VERIFICATION: Starting for $geofenceId');
      
      // Prepare multipart form data
      final formData = FormData.fromMap({
        'geofence_id': geofenceId,
        'latitude': latitude.toString(),
        'longitude': longitude.toString(),
        'accuracy': accuracy.toString(),
        'timestamp': DateTime.now().toIso8601String(),
        'image': await MultipartFile.fromFile(
          imagePath,
          filename: 'verification_join_${DateTime.now().millisecondsSinceEpoch}.jpg',
        ),
      });

      final response = await _apiService.post(
        '/campaigns/geofences/join-with-verification/',
        data: formData,
        options: Options(
          headers: {'Content-Type': 'multipart/form-data'},
          sendTimeout: const Duration(minutes: 2),
          receiveTimeout: const Duration(minutes: 2),
        ),
      );
      
      if (response.statusCode == 200 || response.statusCode == 201) {
        final data = response.data;
        return GeofenceJoinResult(
          success: true,
          verificationId: data['verification_id'],
          assignmentId: data['assignment_id'],
          wasDuplicate: data['was_duplicate'] ?? false,
          data: data,
        );
      } else {
        final errorMessage = _extractErrorMessage(response.data) ?? 'Join failed';
        return GeofenceJoinResult(success: false, error: errorMessage);
      }
    } catch (e) {
      print('🎯 JOIN WITH VERIFICATION ERROR: $e');
      
      // Check if it's a network error and we should retry
      if (_isNetworkError(e)) {
        return GeofenceJoinResult(
          success: false, 
          error: 'Network error. Please check your connection and try again.',
        );
      }
      
      return GeofenceJoinResult(success: false, error: 'Failed to join: $e');
    }
  }
}
```

#### 2.2 Offline Resilience Strategy

```dart
// lib/src/core/services/offline_sync_service.dart

class OfflineSyncService {
  static const String _pendingJoinsKey = 'pending_geofence_joins';
  
  // Store pending join attempts
  Future<void> storePendingJoin({
    required String geofenceId,
    required String imagePath,
    required double latitude,
    required double longitude,
    required double accuracy,
    required DateTime timestamp,
  }) async {
    final pendingJoin = {
      'geofence_id': geofenceId,
      'image_path': imagePath,
      'latitude': latitude,
      'longitude': longitude,
      'accuracy': accuracy,
      'timestamp': timestamp.toIso8601String(),
      'attempt_count': 0,
      'created_at': DateTime.now().toIso8601String(),
    };
    
    final existingJoins = await _getPendingJoins();
    existingJoins.add(pendingJoin);
    
    await HiveService.saveData(_pendingJoinsKey, existingJoins);
  }
  
  // Sync pending joins when network is available
  Future<void> syncPendingJoins() async {
    final pendingJoins = await _getPendingJoins();
    if (pendingJoins.isEmpty) return;
    
    final campaignService = CampaignService();
    final successfulJoins = <Map<String, dynamic>>[];
    
    for (final join in pendingJoins) {
      try {
        // Check if join is still relevant (not too old)
        final attemptTime = DateTime.parse(join['created_at']);
        if (DateTime.now().difference(attemptTime).inHours > 1) {
          successfulJoins.add(join); // Mark as processed (too old)
          continue;
        }
        
        final result = await campaignService.joinGeofenceWithVerification(
          geofenceId: join['geofence_id'],
          imagePath: join['image_path'],
          latitude: join['latitude'],
          longitude: join['longitude'],
          accuracy: join['accuracy'],
        );
        
        if (result.success || result.wasDuplicate) {
          successfulJoins.add(join);
          
          // Update local state if successful
          if (result.success) {
            await _updateLocalStateAfterJoin(join['geofence_id'], result.data);
          }
        } else if (join['attempt_count'] >= 3) {
          // Max retries reached, give up
          successfulJoins.add(join);
        } else {
          // Increment attempt count
          join['attempt_count'] = (join['attempt_count'] ?? 0) + 1;
        }
        
      } catch (e) {
        print('Error syncing pending join: $e');
        // Keep in pending list for next sync attempt
      }
    }
    
    // Remove successful joins from pending list
    final remainingJoins = pendingJoins
        .where((join) => !successfulJoins.contains(join))
        .toList();
    
    await HiveService.saveData(_pendingJoinsKey, remainingJoins);
  }
  
  Future<List<Map<String, dynamic>>> _getPendingJoins() async {
    final data = await HiveService.getData(_pendingJoinsKey);
    return List<Map<String, dynamic>>.from(data ?? []);
  }
  
  Future<void> _updateLocalStateAfterJoin(String geofenceId, Map<String, dynamic>? data) async {
    // Update local rider state
    final rider = HiveService.getRider();
    if (rider != null && data != null) {
      final campaignId = data['campaign_id'];
      if (campaignId != null) {
        final updatedRider = rider.copyWith(currentCampaignId: campaignId);
        await HiveService.saveRider(updatedRider);
      }
    }
  }
}

// Connectivity monitoring
class ConnectivityService {
  static Stream<bool> get connectivityStream => 
      Connectivity().onConnectivityChanged.map((result) => 
          result != ConnectivityResult.none);
  
  static Future<void> onConnectivityRestored() async {
    await OfflineSyncService().syncPendingJoins();
  }
}
```

#### 2.3 Enhanced Campaign Provider

```dart
// lib/src/core/providers/campaign_provider.dart

class CampaignNotifier extends StateNotifier<CampaignState> {
  
  // Updated join method with offline handling
  Future<bool> joinGeofenceWithVerification(String geofenceId, String imagePath) async {
    state = state.copyWith(isJoining: true, error: null);
    
    try {
      // Pre-flight validation
      final eligibilityResult = await _campaignService.checkGeofenceJoinEligibility(geofenceId);
      if (!eligibilityResult.isValid) {
        state = state.copyWith(
          isJoining: false, 
          error: eligibilityResult.reason,
        );
        return false;
      }
      
      // Check cooldown
      if (eligibilityResult.cooldownRemaining != null && eligibilityResult.cooldownRemaining! > 0) {
        state = state.copyWith(
          isJoining: false,
          error: 'Please wait ${eligibilityResult.cooldownRemaining} seconds before trying again',
        );
        return false;
      }
      
      // Get current location
      final locationResult = await _campaignService.getCurrentLocationForJoin();
      if (!locationResult.success) {
        state = state.copyWith(isJoining: false, error: locationResult.error);
        return false;
      }
      
      final locationData = locationResult.data!;
      final latitude = locationData['latitude'] as double;
      final longitude = locationData['longitude'] as double;
      final accuracy = locationData['accuracy'] as double;
      
      try {
        // Attempt join with verification
        final result = await _campaignService.joinGeofenceWithVerification(
          geofenceId: geofenceId,
          imagePath: imagePath,
          latitude: latitude,
          longitude: longitude,
          accuracy: accuracy,
        );
        
        if (result.success) {
          await _updateStateAfterSuccessfulJoin(geofenceId, result.data);
          state = state.copyWith(isJoining: false);
          return true;
        } else {
          state = state.copyWith(isJoining: false, error: result.error);
          return false;
        }
        
      } catch (e) {
        // Network error - store for offline sync
        if (_isNetworkError(e)) {
          await OfflineSyncService().storePendingJoin(
            geofenceId: geofenceId,
            imagePath: imagePath,
            latitude: latitude,
            longitude: longitude,
            accuracy: accuracy,
            timestamp: DateTime.now(),
          );
          
          state = state.copyWith(
            isJoining: false,
            error: 'Network error. Your join request has been saved and will be processed when connection is restored.',
          );
          return false;
        }
        
        rethrow;
      }
      
    } catch (e) {
      state = state.copyWith(isJoining: false, error: e.toString());
      return false;
    }
  }
  
  bool _isNetworkError(dynamic error) {
    return error.toString().contains('SocketException') ||
           error.toString().contains('NetworkException') ||
           error.toString().contains('Connection failed');
  }
}
```

### 3. UI Implementation

#### 3.1 New Geofence Join Verification Screen

```dart
// lib/src/features/campaigns/screens/geofence_join_verification_screen.dart

class GeofenceJoinVerificationScreen extends ConsumerStatefulWidget {
  final Geofence geofence;
  
  const GeofenceJoinVerificationScreen({
    super.key, 
    required this.geofence,
  });

  @override
  ConsumerState<GeofenceJoinVerificationScreen> createState() => 
      _GeofenceJoinVerificationScreenState();
}

class _GeofenceJoinVerificationScreenState 
    extends ConsumerState<GeofenceJoinVerificationScreen> {
  
  CameraController? _cameraController;
  String? _capturedImagePath;
  bool _isProcessing = false;
  bool _isCameraReady = false;
  Position? _currentLocation;
  Timer? _cooldownTimer;
  int _cooldownSeconds = 0;
  
  @override
  void initState() {
    super.initState();
    _initializeCamera();
    _getCurrentLocation();
    _checkCooldownStatus();
  }
  
  Future<void> _checkCooldownStatus() async {
    // Check if user is in cooldown period
    final eligibility = await ref
        .read(campaignServiceProvider)
        .checkGeofenceJoinEligibility(widget.geofence.id);
    
    if (eligibility.cooldownRemaining != null && eligibility.cooldownRemaining! > 0) {
      setState(() {
        _cooldownSeconds = eligibility.cooldownRemaining!.round();
      });
      _startCooldownTimer();
    }
  }
  
  void _startCooldownTimer() {
    _cooldownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      setState(() {
        _cooldownSeconds--;
      });
      
      if (_cooldownSeconds <= 0) {
        timer.cancel();
      }
    });
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: Text('Join ${widget.geofence.name}'),
        backgroundColor: Colors.black.withOpacity(0.3),
        elevation: 0,
      ),
      body: Stack(
        children: [
          // Camera preview or captured image
          if (_isCameraReady && _capturedImagePath == null)
            _buildCameraPreview()
          else if (_capturedImagePath != null)
            _buildImagePreview()
          else
            _buildCameraLoading(),
          
          // Geofence info overlay
          _buildGeofenceInfoOverlay(),
          
          // Cooldown overlay
          if (_cooldownSeconds > 0)
            _buildCooldownOverlay(),
          
          // Controls
          _buildControls(),
        ],
      ),
    );
  }
  
  Widget _buildCooldownOverlay() {
    return Container(
      color: Colors.black.withOpacity(0.8),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.timer,
              color: Colors.orange,
              size: 64,
            ),
            const SizedBox(height: 16),
            const Text(
              'Please wait before trying again',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '${_cooldownSeconds}s remaining',
              style: const TextStyle(
                color: Colors.orange,
                fontSize: 24,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
      ),
    );
  }
  
  Widget _buildControls() {
    if (_cooldownSeconds > 0) {
      return const SizedBox.shrink();
    }
    
    return Positioned(
      bottom: 50,
      left: 20,
      right: 20,
      child: _capturedImagePath == null
          ? _buildCaptureControls()
          : _buildSubmitControls(),
    );
  }
  
  Widget _buildSubmitControls() {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.green.withOpacity(0.9),
            borderRadius: BorderRadius.circular(12),
          ),
          child: const Row(
            children: [
              Icon(Icons.check_circle, color: Colors.white),
              SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Photo captured! Ready to join with verification.',
                  style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: _isProcessing ? null : _retakePhoto,
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: Colors.white, width: 2),
                  foregroundColor: Colors.white,
                ),
                child: const Text('RETAKE'),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              flex: 2,
              child: LoadingButton(
                onPressed: _submitJoinWithVerification,
                isLoading: _isProcessing,
                backgroundColor: AppColors.success,
                child: const Text('JOIN GEOFENCE'),
              ),
            ),
          ],
        ),
      ],
    );
  }
  
  Future<void> _submitJoinWithVerification() async {
    if (_capturedImagePath == null || _currentLocation == null) return;
    
    setState(() => _isProcessing = true);
    
    try {
      final success = await ref
          .read(campaignProvider.notifier)
          .joinGeofenceWithVerification(widget.geofence.id, _capturedImagePath!);
      
      if (mounted) {
        if (success) {
          _showSuccessDialog();
        } else {
          final error = ref.read(campaignProvider).error ?? 'Failed to join geofence';
          _showErrorDialog(error);
        }
      }
    } finally {
      if (mounted) {
        setState(() => _isProcessing = false);
      }
    }
  }
}
```

### 4. Testing Strategy

#### 4.1 Backend Tests

```python
# tests/test_geofence_join_verification.py

class GeofenceJoinVerificationTestCase(APITestCase):
    def setUp(self):
        self.rider = RiderFactory(status='active')
        self.geofence = CampaignGeofenceFactory()
        self.client.force_authenticate(self.rider.user)
    
    def test_successful_join_with_verification(self):
        """Test successful geofence join with valid verification"""
        
    def test_join_with_invalid_image(self):
        """Test join fails with invalid image"""
        
    def test_cooldown_prevents_rapid_attempts(self):
        """Test cooldown mechanism works"""
        
    def test_duplicate_join_handling(self):
        """Test handling of duplicate join attempts"""
        
    def test_offline_resilience(self):
        """Test offline join attempt storage and sync"""
```

#### 4.2 Mobile App Tests

```dart
// test/geofence_join_verification_test.dart

group('Geofence Join Verification', () {
  testWidgets('shows cooldown when in cooldown period', (tester) async {
    // Test UI shows cooldown overlay
  });
  
  testWidgets('successful join flow', (tester) async {
    // Test complete join flow
  });
  
  test('offline sync stores and retries failed joins', () async {
    // Test offline resilience
  });
});
```

### 5. Deployment Plan

#### 5.1 Database Migration

```python
# migrations/0005_verification_geofence_join.py

class Migration(migrations.Migration):
    dependencies = [
        ('verification', '0004_pickuplocation'),
    ]
    
    operations = [
        migrations.AddField(
            model_name='verificationrequest',
            name='geofence',
            field=models.ForeignKey(null=True, blank=True, to='campaigns.CampaignGeofence'),
        ),
        migrations.AddField(
            model_name='verificationrequest',
            name='verification_type',
            field=models.CharField(max_length=20, default='random'),
        ),
        migrations.CreateModel(
            name='VerificationCooldown',
            fields=[
                ('id', models.AutoField(primary_key=True)),
                ('rider', models.ForeignKey(to='riders.Rider')),
                ('verification_type', models.CharField(max_length=20)),
                ('last_attempt', models.DateTimeField()),
                ('cooldown_until', models.DateTimeField()),
                ('attempt_count', models.PositiveIntegerField(default=1)),
            ],
        ),
    ]
```

#### 5.2 Feature Flag Implementation

```python
# Feature flags for gradual rollout
GEOFENCE_JOIN_VERIFICATION_ENABLED = getattr(settings, 'GEOFENCE_JOIN_VERIFICATION_ENABLED', False)

@api_view(['POST'])
def join_geofence_with_verification(request):
    if not GEOFENCE_JOIN_VERIFICATION_ENABLED:
        return Response({
            'success': False,
            'message': 'Feature not available yet'
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    
    # ... rest of implementation
```

### 6. Monitoring and Analytics

#### 6.1 Key Metrics

- **Verification Success Rate**: % of verifications that pass
- **Join Success Rate**: % of join attempts that succeed after verification
- **Cooldown Violations**: Attempts blocked by cooldown
- **Offline Sync Success**: % of pending joins successfully synced
- **Average Join Time**: Time from verification to successful join

#### 6.2 Error Tracking

- **Verification Failures**: Track common failure reasons
- **Network Errors**: Monitor offline scenarios
- **Duplicate Attempts**: Track and optimize duplicate handling

### 7. Security Considerations

#### 7.1 Image Validation

- File size limits (5MB max)
- Format validation (JPEG, PNG only)
- Basic corruption checks
- Metadata sanitization

#### 7.2 Rate Limiting

- Cooldown enforcement
- IP-based rate limiting
- User-based attempt tracking

#### 7.3 Location Validation

- Server-side geofence validation
- Accuracy requirements
- Anti-spoofing measures

### 8. Performance Optimization

#### 8.1 Image Processing

- Async image processing for better UX
- Image compression before upload
- Progressive image quality fallback

#### 8.2 Database Optimization

- Indexed queries for geofence lookups
- Efficient cooldown checks
- Optimized duplicate detection

#### 8.3 Caching Strategy

- Geofence boundary caching
- User eligibility caching
- Network request optimization

This comprehensive plan provides a complete roadmap for implementing the geofence join verification feature with offline resilience, proper error handling, and a focus on user experience.