# Random Verification Implementation Plan - Mobile-Initiated

## Overview

Move random verification triggering from server-side (Celery) to mobile app-initiated approach. The mobile app will use an algorithm to determine when to request verification, then call the backend to create and process the verification request.

## Current State Analysis

### Existing Mobile App Infrastructure
- **VerificationRequest model**: Complete with offline support
- **VerificationService**: API service with endpoints like `/verifications/submit/`
- **VerificationProvider**: Riverpod state management
- **VerificationScreen**: UI for camera and submission
- **Offline support**: Local storage and retry mechanisms

### Existing Backend Infrastructure
- **VerificationRequest model**: Supports different verification types (`random`, `geofence_join`, `manual`)
- **VerificationProcessor**: Processes and validates verification submissions
- **CooldownManager**: Manages verification attempt cooldowns
- **Basic verification endpoints**: Some endpoints exist but incomplete

## Proposed Architecture

### Mobile App Responsibilities
1. **Algorithm**: Determine when to trigger random verification
2. **Initiation**: Call backend API to create verification request
3. **Execution**: Use existing verification flow (camera, submit, etc.)
4. **Retry Logic**: Handle offline scenarios with existing infrastructure

### Backend Responsibilities
1. **Request Creation**: Create verification request when mobile app requests
2. **Validation**: Ensure rider is eligible for verification
3. **Processing**: Validate submitted verification using existing VerificationProcessor
4. **Response**: Return verification request details to mobile app

## Implementation Plan

### Phase 1: Backend API Endpoints

#### 1.1 Create Verification Request Endpoint
```
POST /api/v1/verifications/create-random/
```

**Purpose**: Mobile app calls this to initiate a random verification

**Request Data**:
```json
{
  "latitude": 6.5244,
  "longitude": 3.3792,
  "accuracy": 5.0,
  "campaign_id": "optional-uuid"  // If rider is in active campaign
}
```

**Response Success (201)**:
```json
{
  "success": true,
  "verification": {
    "id": "uuid",
    "campaign_id": "uuid",
    "campaign_name": "Campaign Name",
    "created_at": "2024-01-01T12:00:00Z",
    "deadline": "2024-01-01T12:10:00Z",
    "time_remaining_seconds": 600,
    "status": "pending"
  }
}
```

**Response Failure (400)**:
```json
{
  "success": false,
  "message": "Not eligible for verification",
  "reason": "cooldown_active|no_active_campaign|out_of_geofence",
  "retry_after_seconds": 300
}
```

#### 1.2 Submit Verification Endpoint (Update Existing)
```
POST /api/v1/verifications/submit/
```

**Update existing endpoint to handle both types**:
- `geofence_join` (existing)
- `random` (new)

#### 1.3 Check Pending Verifications Endpoint
```
GET /api/v1/verifications/pending/
```

**Purpose**: Mobile app checks for pending verifications on app start/resume

### Phase 2: Mobile App Algorithm

#### 2.1 Random Verification Trigger Algorithm

**Factors for Triggering**:
1. **Time-based**: Random intervals (30 min - 2 hours)
2. **Location-based**: Only when inside active campaign geofence
3. **Activity-based**: Only when rider is moving (not stationary)
4. **Cooldown respect**: Check last verification time
5. **Connection-based**: Only when online

**Algorithm Implementation**:
```dart
class RandomVerificationManager {
  static const int MIN_INTERVAL_MINUTES = 30;
  static const int MAX_INTERVAL_MINUTES = 120;
  static const int COOLDOWN_MINUTES = 5;
  
  // Calculate next verification time
  static DateTime calculateNextVerification() {
    final now = DateTime.now();
    final randomMinutes = Random().nextInt(
      MAX_INTERVAL_MINUTES - MIN_INTERVAL_MINUTES + 1
    ) + MIN_INTERVAL_MINUTES;
    
    return now.add(Duration(minutes: randomMinutes));
  }
  
  // Check if should trigger verification
  static bool shouldTriggerVerification() {
    // Check time since last verification
    // Check if in active campaign
    // Check if moving
    // Check if online
    return true/false;
  }
}
```

#### 2.2 Background Service Integration

**Timer-based Checking**:
- Check every 5-10 minutes if verification should be triggered
- Use Flutter's `Timer.periodic` or background service
- Respect app lifecycle (foreground/background)

### Phase 3: Integration Points

#### 3.1 Existing Verification Flow Integration

**No changes needed to**:
- VerificationScreen UI
- Image capture and submission
- Offline storage and retry
- Status checking and history

**Minor updates needed**:
- VerificationProvider: Add method to create random verification
- VerificationService: Add API call for creating verification

#### 3.2 Campaign Integration

**Active Campaign Detection**:
- Use existing campaign provider to get current campaign
- Only trigger random verification if rider is in active campaign
- Pass campaign_id when creating verification request

### Phase 4: Anti-Gaming Measures

#### 4.1 Mobile App Safeguards
- Minimum time between verifications (5 minutes)
- Only trigger when GPS indicates movement
- Validate rider is inside campaign geofence
- Respect server-side cooldowns

#### 4.2 Backend Validation
- Verify rider has active campaign assignment
- Check location is within campaign geofence
- Enforce cooldown periods
- Rate limiting on verification creation endpoint

## Detailed Implementation

### Backend Models (No Changes Needed)

Existing `VerificationRequest` model already supports:
- Different verification types (`random`)
- Campaign association
- Location data
- Status tracking

### Backend Services (Minor Updates)

**Update VerificationProcessor**:
```python
@staticmethod
def process_verification(verification_request):
    """Process verification for both geofence_join and random types"""
    if verification_request.verification_type == 'random':
        return VerificationProcessor.process_random_verification(verification_request)
    elif verification_request.verification_type == 'geofence_join':
        return VerificationProcessor.process_join_verification(verification_request)
    # ... etc
```

### Mobile App Updates

#### 3.1 VerificationService Updates
```dart
class VerificationService {
  // New method
  Future<VerificationResult> createRandomVerification({
    required double latitude,
    required double longitude,
    required double accuracy,
    String? campaignId,
  }) async {
    // Call POST /api/v1/verifications/create-random/
  }
  
  // Existing methods continue to work
  Future<VerificationResult> submitVerification(...) // No changes
  Future<List<VerificationRequest>> getVerificationRequests() // No changes
}
```

#### 3.2 VerificationProvider Updates
```dart
class VerificationNotifier extends StateNotifier<VerificationState> {
  // New method
  Future<VerificationRequest?> triggerRandomVerification() async {
    final location = await LocationService.getCurrentLocation();
    final campaign = ref.read(campaignProvider).currentCampaign;
    
    final result = await _verificationService.createRandomVerification(
      latitude: location.latitude,
      longitude: location.longitude,
      accuracy: location.accuracy,
      campaignId: campaign?.id,
    );
    
    if (result.success && result.request != null) {
      state = state.copyWith(currentRequest: result.request);
      return result.request;
    }
    
    return null;
  }
}
```

#### 3.3 Background Verification Manager
```dart
class BackgroundVerificationManager {
  static Timer? _verificationTimer;
  
  static void startRandomVerifications() {
    _verificationTimer = Timer.periodic(
      Duration(minutes: 10), // Check every 10 minutes
      (_) => _checkForRandomVerification(),
    );
  }
  
  static Future<void> _checkForRandomVerification() async {
    if (RandomVerificationManager.shouldTriggerVerification()) {
      final verificationNotifier = ProviderContainer().read(
        verificationProvider.notifier
      );
      
      final request = await verificationNotifier.triggerRandomVerification();
      
      if (request != null) {
        // Show verification screen or notification
        _showVerificationPrompt();
      }
    }
  }
}
```

## API Endpoints Summary

### New Endpoints to Implement
1. `POST /api/v1/verifications/create-random/` - Create random verification
2. `GET /api/v1/verifications/pending/` - Check pending verifications

### Existing Endpoints (Update if needed)
1. `POST /api/v1/verifications/submit/` - Submit verification (already exists)
2. `GET /api/v1/verifications/history/` - Get verification history (already exists)

## Benefits of This Approach

### 1. Simplicity
- No Celery tasks needed
- No complex server-side scheduling
- Leverages existing mobile app infrastructure

### 2. Reliability
- Mobile app controls timing
- Works offline (stores verification requests locally)
- No dependency on background job reliability

### 3. Flexibility
- Easy to adjust algorithm based on user behavior
- A/B test different verification frequencies
- Respond to device conditions (battery, connectivity)

### 4. User Experience
- Immediate response when verification is triggered
- Uses existing verification UI flow
- Respects user context (app state, location, etc.)

## Implementation Timeline

### Week 1: Backend API Endpoints
- Implement `create-random` endpoint
- Update `submit` endpoint for random verifications
- Add validation and cooldown logic
- Write tests

### Week 2: Mobile App Algorithm
- Implement RandomVerificationManager
- Add background checking service
- Update VerificationProvider and VerificationService
- Test integration

### Week 3: Testing & Refinement
- End-to-end testing
- Algorithm tuning
- Error handling
- Performance optimization

### Week 4: Deployment & Monitoring
- Deploy backend updates
- Release mobile app update
- Monitor verification frequency and success rates
- Gather user feedback

## Success Metrics

### Technical Metrics
- Verification completion rate > 90%
- Average response time < 2 minutes
- Offline success rate > 95%
- API error rate < 1%

### Business Metrics
- Random verification frequency: 3-5 per rider per day
- Anti-gaming detection: Flag suspicious patterns
- User retention: No significant drop due to verification fatigue

## Risk Mitigation

### 1. Over-verification Risk
- **Mitigation**: Implement maximum daily limits
- **Monitoring**: Track verification frequency per rider
- **Adjustment**: Dynamic algorithm based on user feedback

### 2. Gaming Risk
- **Mitigation**: Server-side validation of location and timing
- **Detection**: Monitor for unusual patterns
- **Response**: Increase verification frequency for suspicious accounts

### 3. Technical Failures
- **Mitigation**: Robust error handling and retry logic
- **Fallback**: Offline storage and sync when online
- **Monitoring**: Alert on high failure rates

## Future Enhancements

### 1. Machine Learning
- Optimize verification timing based on user behavior
- Predict optimal verification windows
- Personalized verification frequency

### 2. Advanced Anti-Gaming
- Movement pattern analysis
- Image similarity detection
- Behavioral biometrics

### 3. User Experience
- Smart notifications (when user is likely available)
- Gamification (verification streaks, bonuses)
- Context-aware triggering (traffic lights, stops)

This plan provides a comprehensive approach to implementing mobile-initiated random verification while leveraging existing infrastructure and maintaining system simplicity.