# Mobile App Logging Improvements

## Flutter App Logging Enhancements

### 1. Enhanced API Service Logging (`api_service.dart`)

Add comprehensive logging to the API service:

```dart
import 'package:flutter/foundation.dart';

class ApiService {
  // Add request logging before sending
  Future<Response> _loggedRequest(Future<Response> Function() request, String description) async {
    final stopwatch = Stopwatch()..start();
    
    try {
      if (kDebugMode) {
        print('🔵 API REQUEST START: $description');
        print('🔵 Timestamp: ${DateTime.now().toIso8601String()}');
      }
      
      final response = await request();
      
      stopwatch.stop();
      
      if (kDebugMode) {
        print('🟢 API REQUEST SUCCESS: $description');
        print('🟢 Status: ${response.statusCode}');
        print('🟢 Duration: ${stopwatch.elapsedMilliseconds}ms');
        print('🟢 Response Data: ${response.data}');
        print('🟢 Response Headers: ${response.headers}');
      }
      
      return response;
    } catch (e) {
      stopwatch.stop();
      
      if (kDebugMode) {
        print('🔴 API REQUEST ERROR: $description');
        print('🔴 Duration: ${stopwatch.elapsedMilliseconds}ms');
        print('🔴 Error: $e');
        print('🔴 Error Type: ${e.runtimeType}');
        
        if (e is DioException) {
          print('🔴 Dio Error Type: ${e.type}');
          print('🔴 Response Data: ${e.response?.data}');
          print('🔴 Status Code: ${e.response?.statusCode}');
        }
      }
      
      rethrow;
    }
  }
  
  // Wrap all API methods with logging
  Future<Response> get(String path, {Map<String, dynamic>? queryParameters}) {
    return _loggedRequest(
      () => _dio.get(path, queryParameters: queryParameters),
      'GET $path'
    );
  }
  
  Future<Response> post(String path, {dynamic data}) {
    return _loggedRequest(
      () => _dio.post(path, data: data),
      'POST $path'
    );
  }
}
```

### 2. Provider State Logging

Add state change logging to providers:

```dart
// In earnings_provider.dart
class EarningsNotifier extends StateNotifier<EarningsState> {
  @override
  set state(EarningsState newState) {
    if (kDebugMode) {
      print('📊 EARNINGS STATE CHANGE:');
      print('📊 Previous: isLoading=${state.isLoading}, error=${state.error}, earnings=${state.earnings.length}');
      print('📊 New: isLoading=${newState.isLoading}, error=${newState.error}, earnings=${newState.earnings.length}');
    }
    super.state = newState;
  }
  
  Future<void> fetchEarnings({bool refresh = false}) async {
    if (kDebugMode) {
      print('💰 FETCHING EARNINGS: refresh=$refresh, currentLoading=${state.isLoading}');
    }
    
    // Prevent concurrent calls
    if (state.isLoading && !refresh) {
      if (kDebugMode) {
        print('💰 EARNINGS FETCH BLOCKED: Already loading');
      }
      return;
    }
    
    // ... rest of implementation
  }
}
```

### 3. Home Screen Data Loading Logging

Add detailed logging to the home screen data loading:

```dart
// In home_screen.dart
Future<void> _loadInitialData() async {
  if (kDebugMode) {
    print('🏠 HOME SCREEN: Starting initial data load');
    print('🏠 Timestamp: ${DateTime.now().toIso8601String()}');
  }
  
  try {
    // Load data sequentially with logging
    if (kDebugMode) print('🏠 Step 1: Loading location data...');
    await _loadLocationData();
    
    if (kDebugMode) print('🏠 Step 2: Waiting 300ms before campaigns...');
    await Future.delayed(const Duration(milliseconds: 300));
    
    if (kDebugMode) print('🏠 Step 3: Loading campaign data...');
    await _loadCampaignData();
    
    if (kDebugMode) print('🏠 Step 4: Waiting 300ms before earnings...');
    await Future.delayed(const Duration(milliseconds: 300));
    
    if (kDebugMode) print('🏠 Step 5: Loading earnings data...');
    await _loadEarningsData();
    
    if (kDebugMode) print('🏠 Step 6: Updating map markers...');
    if (mounted) {
      _updateMapMarkers();
      setState(() {
        _isInitialLoading = false;
      });
    }
    
    if (kDebugMode) print('🏠 HOME SCREEN: Initial data load completed successfully');
  } catch (e) {
    if (kDebugMode) {
      print('🏠 HOME SCREEN ERROR: Initial data load failed');
      print('🏠 Error: $e');
      print('🏠 Error Type: ${e.runtimeType}');
      print('🏠 Stack Trace: ${StackTrace.current}');
    }
    
    // Handle errors gracefully
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Some data could not be loaded. Pull to refresh.'),
          backgroundColor: Colors.orange,
        ),
      );
      setState(() {
        _isInitialLoading = false;
      });
    }
  }
}
```

### 4. Campaign Service Enhanced Logging

```dart
// In campaign_service.dart
Future<List<Campaign>> getAvailableCampaigns() async {
  if (kDebugMode) {
    print('🎯 CAMPAIGN SERVICE: Getting available campaigns');
    print('🎯 Timestamp: ${DateTime.now().toIso8601String()}');
  }
  
  try {
    final response = await _apiService.get('/campaigns/available/');
    
    if (kDebugMode) {
      print('🎯 CAMPAIGN SERVICE: Response received');
      print('🎯 Status Code: ${response.statusCode}');
      print('🎯 Response Type: ${response.data.runtimeType}');
      print('🎯 Response Data: ${response.data}');
    }
    
    if (response.statusCode == 200) {
      final List<dynamic> campaignsJson = response.data['results'] ?? response.data;
      
      if (kDebugMode) {
        print('🎯 CAMPAIGN SERVICE: Parsing ${campaignsJson.length} campaigns');
      }
      
      final campaigns = campaignsJson
          .map((json) => Campaign.fromJson(json as Map<String, dynamic>))
          .toList();
      
      if (kDebugMode) {
        print('🎯 CAMPAIGN SERVICE: Successfully parsed campaigns');
      }
      
      return campaigns;
    } else {
      if (kDebugMode) {
        print('🎯 CAMPAIGN SERVICE ERROR: Unexpected status code ${response.statusCode}');
      }
      throw Exception('Failed to load campaigns');
    }
  } catch (e) {
    if (kDebugMode) {
      print('🎯 CAMPAIGN SERVICE ERROR: Exception occurred');
      print('🎯 Error: $e');
      print('🎯 Error Type: ${e.runtimeType}');
    }
    throw Exception('Failed to fetch campaigns: $e');
  }
}
```

### 5. Crash Reporting

Add crash reporting to main.dart:

```dart
// In main.dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // Set up error handling
  FlutterError.onError = (FlutterErrorDetails details) {
    if (kDebugMode) {
      print('🚨 FLUTTER ERROR:');
      print('🚨 Error: ${details.exception}');
      print('🚨 Stack: ${details.stack}');
      print('🚨 Library: ${details.library}');
      print('🚨 Context: ${details.context}');
    }
    
    // In production, send to crash reporting service
    FlutterError.presentError(details);
  };
  
  PlatformDispatcher.instance.onError = (error, stack) {
    if (kDebugMode) {
      print('🚨 PLATFORM ERROR:');
      print('🚨 Error: $error');
      print('🚨 Stack: $stack');
    }
    
    // In production, send to crash reporting service
    return true;
  };
  
  runApp(const MyApp());
}
```

## Implementation Priority

1. **High Priority**: API Service logging and Provider state logging
2. **Medium Priority**: Home screen data loading logging
3. **Low Priority**: Crash reporting and additional service logging

## Usage

These logging improvements will provide:
- Detailed API request/response information
- State change tracking in providers
- Sequential data loading visibility
- Error context and stack traces
- Performance timing information

All logs will only appear in debug mode and won't affect production performance.