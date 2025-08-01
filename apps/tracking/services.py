from django.contrib.gis.measure import Distance
from django.contrib.gis.geos import Point
from django.utils import timezone
from django.db.models import Q
from decimal import Decimal
import logging
from apps.campaigns.models import CampaignGeofence
from .models import (
    LocationRecord, GeofenceEntry, RiderSession, 
    EarningsCalculation, DailyTrackingSummary
)

logger = logging.getLogger(__name__)


class LocationProcessor:
    """
    Processes location records to detect geofence events and manage rider sessions
    """
    
    def __init__(self, rider, sync_batch=None):
        self.rider = rider
        self.sync_batch = sync_batch
        self.geofence_tolerance = 50  # meters tolerance for geofence detection
    
    def process_location(self, location_record):
        """
        Process a single location record for geofence events
        """
        try:
            # Get all active geofences for rider's active campaigns
            active_geofences = self._get_active_geofences()
            
            # Check for geofence entry/exit events
            for geofence in active_geofences:
                self._check_geofence_event(location_record, geofence)
            
            # Update daily summary
            self._update_daily_summary(location_record)
            
        except Exception as e:
            logger.error(f"Error processing location {location_record.mobile_id}: {e}")
            location_record.mark_error(str(e))
    
    def _get_active_geofences(self):
        """
        Get all active geofences that the rider is assigned to
        """
        rider_assignments = self.rider.geofence_assignments.filter(
            status='active',
            campaign_geofence__status='active'
        )
        
        return [assignment.campaign_geofence for assignment in rider_assignments]
    
    def _check_geofence_event(self, location_record, geofence):
        """
        Check if location triggers a geofence entry or exit event
        """
        # Calculate distance from location to geofence center
        geofence_center = Point(geofence.center_longitude, geofence.center_latitude)
        distance = location_record.location.distance(geofence_center)
        
        # Check if within geofence (including tolerance)
        is_inside = distance <= (geofence.radius_meters + self.geofence_tolerance)
        
        # Get rider's last geofence event for this geofence
        last_event = GeofenceEntry.objects.filter(
            rider=self.rider,
            geofence=geofence
        ).first()
        
        # Determine if this is an entry or exit event
        if is_inside and (not last_event or last_event.entry_type == 'exit'):
            # Rider entered geofence
            self._create_entry_event(location_record, geofence)
            
        elif not is_inside and last_event and last_event.entry_type == 'enter':
            # Rider exited geofence
            self._create_exit_event(location_record, geofence, last_event)
    
    def _create_entry_event(self, location_record, geofence):
        """
        Create geofence entry event and start new session
        """
        try:
            # Create entry event
            entry_event = GeofenceEntry.objects.create(
                rider=self.rider,
                geofence=geofence,
                entry_type='enter',
                location=location_record.location,
                recorded_at=location_record.recorded_at,
                source_location=location_record
            )
            
            # Start new session
            session = RiderSession.objects.create(
                rider=self.rider,
                geofence=geofence,
                start_entry=entry_event,
                started_at=location_record.recorded_at,
                status='active'
            )
            
            logger.info(f"Rider {self.rider.rider_id} entered geofence {geofence.name}")
            
        except Exception as e:
            logger.error(f"Error creating entry event: {e}")
    
    def _create_exit_event(self, location_record, geofence, entry_event):
        """
        Create geofence exit event and close active session
        """
        try:
            # Create exit event
            exit_event = GeofenceEntry.objects.create(
                rider=self.rider,
                geofence=geofence,
                entry_type='exit',
                location=location_record.location,
                recorded_at=location_record.recorded_at,
                source_location=location_record,
                entry_record=entry_event
            )
            
            # Close active session
            active_session = RiderSession.objects.filter(
                rider=self.rider,
                geofence=geofence,
                status='active'
            ).first()
            
            if active_session:
                active_session.close_session(exit_event)
                
                # Calculate distance covered during session
                session_distance = self._calculate_session_distance(active_session)
                active_session.distance_covered = session_distance
                active_session.save(update_fields=['distance_covered'])
                
                # Calculate earnings for the session
                earnings_calculator = EarningsCalculator(self.rider, geofence)
                earnings_calculator.calculate_session_earnings(active_session)
            
            logger.info(f"Rider {self.rider.rider_id} exited geofence {geofence.name}")
            
        except Exception as e:
            logger.error(f"Error creating exit event: {e}")
    
    def _calculate_session_distance(self, session):
        """
        Calculate total distance covered during a session
        """
        try:
            # Get all location records during the session
            session_locations = LocationRecord.objects.filter(
                rider=self.rider,
                recorded_at__gte=session.started_at,
                recorded_at__lte=session.ended_at or timezone.now(),
                sync_status='processed'
            ).order_by('recorded_at')
            
            total_distance = Decimal('0.00')
            previous_location = None
            
            for location in session_locations:
                if previous_location:
                    # Calculate distance between consecutive points
                    distance = previous_location.location.distance(location.location)
                    # Convert from meters to kilometers
                    total_distance += Decimal(str(distance / 1000))
                
                previous_location = location
            
            return total_distance
            
        except Exception as e:
            logger.error(f"Error calculating session distance: {e}")
            return Decimal('0.00')
    
    def _update_daily_summary(self, location_record):
        """
        Update or create daily tracking summary
        """
        try:
            date = location_record.recorded_at.date()
            
            summary, created = DailyTrackingSummary.objects.get_or_create(
                rider=self.rider,
                date=date,
                defaults={
                    'total_locations_recorded': 0,
                    'total_distance_km': Decimal('0.00'),
                    'working_hours': Decimal('0.00')
                }
            )
            
            # Increment location count
            summary.total_locations_recorded += 1
            
            # Calculate distance from previous location
            if summary.total_locations_recorded > 1:
                previous_location = LocationRecord.objects.filter(
                    rider=self.rider,
                    recorded_at__date=date,
                    recorded_at__lt=location_record.recorded_at,
                    sync_status='processed'
                ).order_by('-recorded_at').first()
                
                if previous_location:
                    distance = previous_location.location.distance(location_record.location)
                    summary.total_distance_km += Decimal(str(distance / 1000))
            
            summary.save()
            
        except Exception as e:
            logger.error(f"Error updating daily summary: {e}")


class EarningsCalculator:
    """
    Calculates earnings for riders based on geofence rates and session data
    """
    
    def __init__(self, rider, geofence):
        self.rider = rider
        self.geofence = geofence
    
    def calculate_session_earnings(self, session):
        """
        Calculate earnings for a completed session
        """
        try:
            earnings_type = self._determine_earnings_type()
            amount = self._calculate_amount(session, earnings_type)
            
            earnings = EarningsCalculation.objects.create(
                rider=self.rider,
                geofence=self.geofence,
                session=session,
                earnings_type=earnings_type,
                amount=amount,
                distance_km=session.distance_covered,
                duration_hours=Decimal(str(session.duration_minutes / 60)),
                rate_applied=self._get_applicable_rate(earnings_type),
                earned_at=session.ended_at or timezone.now(),
                verifications_completed=session.verification_count,
                calculation_metadata={
                    'session_id': session.id,
                    'geofence_rate_type': self.geofence.rate_type,
                    'calculated_at': timezone.now().isoformat()
                }
            )
            
            # Update session earnings
            session.earnings_calculated = amount
            session.save(update_fields=['earnings_calculated'])
            
            # Update daily summary
            self._update_daily_earnings(earnings)
            
            return earnings
            
        except Exception as e:
            logger.error(f"Error calculating session earnings: {e}")
            return None
    
    def calculate_earnings(self, earnings_type, distance_km, duration_hours, 
                         verifications_completed, earned_at, mobile_id=None, metadata=None):
        """
        Calculate earnings manually (called from API)
        """
        amount = self._calculate_amount_manual(
            earnings_type, distance_km, duration_hours
        )
        
        earnings = EarningsCalculation.objects.create(
            mobile_id=mobile_id,
            rider=self.rider,
            geofence=self.geofence,
            earnings_type=earnings_type,
            amount=amount,
            distance_km=Decimal(str(distance_km)),
            duration_hours=Decimal(str(duration_hours)),
            rate_applied=self._get_applicable_rate(earnings_type),
            earned_at=earned_at,
            verifications_completed=verifications_completed,
            calculation_metadata=metadata or {}
        )
        
        # Update daily summary
        self._update_daily_earnings(earnings)
        
        return earnings
    
    def _determine_earnings_type(self):
        """
        Determine earnings type based on geofence rate type
        """
        rate_type_mapping = {
            'per_km': 'distance',
            'per_hour': 'time', 
            'fixed_daily': 'fixed',
            'hybrid': 'hybrid'
        }
        
        return rate_type_mapping.get(self.geofence.rate_type, 'distance')
    
    def _calculate_amount(self, session, earnings_type):
        """
        Calculate earnings amount for a session
        """
        if earnings_type == 'distance':
            return session.distance_covered * self.geofence.rate_per_km
        
        elif earnings_type == 'time':
            duration_hours = Decimal(str(session.duration_minutes / 60))
            return duration_hours * self.geofence.rate_per_hour
        
        elif earnings_type == 'fixed':
            return self.geofence.fixed_daily_rate
        
        elif earnings_type == 'hybrid':
            distance_amount = session.distance_covered * self.geofence.rate_per_km
            duration_hours = Decimal(str(session.duration_minutes / 60))
            time_amount = duration_hours * self.geofence.rate_per_hour
            return distance_amount + time_amount
        
        return Decimal('0.00')
    
    def _calculate_amount_manual(self, earnings_type, distance_km, duration_hours):
        """
        Calculate earnings amount manually
        """
        distance = Decimal(str(distance_km))
        duration = Decimal(str(duration_hours))
        
        if earnings_type == 'distance':
            return distance * self.geofence.rate_per_km
        
        elif earnings_type == 'time':
            return duration * self.geofence.rate_per_hour
        
        elif earnings_type == 'fixed':
            return self.geofence.fixed_daily_rate
        
        elif earnings_type == 'hybrid':
            distance_amount = distance * self.geofence.rate_per_km
            time_amount = duration * self.geofence.rate_per_hour
            return distance_amount + time_amount
        
        return Decimal('0.00')
    
    def _get_applicable_rate(self, earnings_type):
        """
        Get the rate that was applied for calculation
        """
        if earnings_type == 'distance':
            return self.geofence.rate_per_km
        elif earnings_type == 'time':
            return self.geofence.rate_per_hour
        elif earnings_type == 'fixed':
            return self.geofence.fixed_daily_rate
        elif earnings_type == 'hybrid':
            # Return per_km rate for hybrid (both rates are in metadata)
            return self.geofence.rate_per_km
        
        return Decimal('0.00')
    
    def _update_daily_earnings(self, earnings):
        """
        Update daily summary with new earnings
        """
        try:
            date = earnings.earned_at.date()
            
            summary, created = DailyTrackingSummary.objects.get_or_create(
                rider=self.rider,
                date=date,
                defaults={
                    'total_earnings': Decimal('0.00'),
                    'distance_earnings': Decimal('0.00'),
                    'time_earnings': Decimal('0.00'),
                    'bonus_earnings': Decimal('0.00')
                }
            )
            
            # Add to total earnings
            summary.total_earnings += earnings.amount
            
            # Add to specific earnings type
            if earnings.earnings_type == 'distance':
                summary.distance_earnings += earnings.amount
            elif earnings.earnings_type == 'time':
                summary.time_earnings += earnings.amount
            elif earnings.earnings_type in ['bonus', 'correction']:
                summary.bonus_earnings += earnings.amount
            elif earnings.earnings_type == 'hybrid':
                # Split hybrid earnings between distance and time
                distance_portion = earnings.distance_km * self.geofence.rate_per_km
                time_portion = earnings.amount - distance_portion
                summary.distance_earnings += distance_portion
                summary.time_earnings += time_portion
            
            # Update verification count
            if earnings.verifications_completed > 0:
                summary.verifications_completed += earnings.verifications_completed
            
            summary.save()
            
        except Exception as e:
            logger.error(f"Error updating daily earnings: {e}")


class TrackingAnalytics:
    """
    Provides analytics and insights for tracking data
    """
    
    def __init__(self, rider=None, geofence=None):
        self.rider = rider
        self.geofence = geofence
    
    def get_rider_performance_metrics(self, start_date, end_date):
        """
        Get comprehensive performance metrics for a rider
        """
        summaries = DailyTrackingSummary.objects.filter(
            rider=self.rider,
            date__gte=start_date,
            date__lte=end_date
        )
        
        return {
            'total_distance': sum(s.total_distance_km for s in summaries),
            'total_earnings': sum(s.total_earnings for s in summaries),
            'total_sessions': sum(s.total_sessions for s in summaries),
            'average_daily_distance': sum(s.total_distance_km for s in summaries) / len(summaries) if summaries else 0,
            'average_daily_earnings': sum(s.total_earnings for s in summaries) / len(summaries) if summaries else 0,
            'days_active': len(summaries),
            'sync_success_rate': sum(s.sync_success_rate for s in summaries) / len(summaries) if summaries else 0
        }
    
    def get_geofence_activity_metrics(self, start_date, end_date):
        """
        Get activity metrics for a specific geofence
        """
        sessions = RiderSession.objects.filter(
            geofence=self.geofence,
            started_at__date__gte=start_date,
            started_at__date__lte=end_date
        )
        
        return {
            'total_sessions': sessions.count(),
            'completed_sessions': sessions.filter(status='completed').count(),
            'total_riders': sessions.values('rider').distinct().count(),
            'total_distance': sum(s.distance_covered for s in sessions),
            'total_earnings_paid': sum(s.earnings_calculated for s in sessions),
            'average_session_duration': sum(s.duration_minutes for s in sessions) / sessions.count() if sessions else 0
        }