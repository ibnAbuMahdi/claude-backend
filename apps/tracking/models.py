from django.db import models
from django.contrib.gis.db import models as gis_models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.core.models import BaseModel
import uuid

class LocationRecord(BaseModel):
    """
    Stores location data synced from mobile app
    Mirrors the mobile LocationRecord model
    """
    
    SYNC_STATUS_CHOICES = [
        ('pending', 'Pending Processing'),
        ('processed', 'Processed'),
        ('error', 'Processing Error'),
    ]
    
    # Identifiers
    mobile_id = models.CharField(
        max_length=36, 
        unique=True,
        help_text="UUID from mobile app"
    )
    rider = models.ForeignKey(
        'riders.Rider',
        on_delete=models.CASCADE,
        related_name='location_records'
    )
    campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.SET_NULL,
        related_name='location_records',
        null=True,
        blank=True
    )
    
    # Location Data
    location = gis_models.PointField(help_text="GPS coordinates")
    accuracy = models.FloatField(
        validators=[MinValueValidator(0)],
        help_text="GPS accuracy in meters"
    )
    speed = models.FloatField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Speed in km/h"
    )
    heading = models.FloatField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(360)],
        help_text="Heading in degrees"
    )
    altitude = models.FloatField(
        null=True, 
        blank=True,
        help_text="Altitude in meters"
    )
    
    # Timing
    recorded_at = models.DateTimeField(help_text="When location was recorded on mobile")
    synced_at = models.DateTimeField(auto_now_add=True, help_text="When synced to server")
    
    # Context
    is_working = models.BooleanField(default=True)
    
    # Processing
    sync_status = models.CharField(
        max_length=20,
        choices=SYNC_STATUS_CHOICES,
        default='pending'
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    # Metadata from mobile app
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional data from mobile app"
    )
    
    class Meta:
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['rider', 'recorded_at']),
            models.Index(fields=['campaign', 'recorded_at']),
            models.Index(fields=['sync_status']),
            models.Index(fields=['recorded_at']),
        ]
        # Partition by month for performance
        db_table = 'tracking_location_record'
    
    def __str__(self):
        return f"{self.rider.rider_id} - {self.recorded_at}"
    
    @property
    def latitude(self):
        return self.location.y if self.location else None
    
    @property
    def longitude(self):
        return self.location.x if self.location else None
    
    def mark_processed(self):
        """Mark location as processed"""
        self.sync_status = 'processed'
        self.processed_at = timezone.now()
        self.save(update_fields=['sync_status', 'processed_at'])
    
    def mark_error(self, error_message):
        """Mark location processing as failed"""
        self.sync_status = 'error'
        self.error_message = error_message
        self.processed_at = timezone.now()
        self.save(update_fields=['sync_status', 'error_message', 'processed_at'])


class GeofenceEntry(BaseModel):
    """
    Tracks when riders enter/exit geofences
    Generated from location data processing
    """
    
    ENTRY_TYPE_CHOICES = [
        ('enter', 'Entered Geofence'),
        ('exit', 'Exited Geofence'),
    ]
    
    rider = models.ForeignKey(
        'riders.Rider',
        on_delete=models.CASCADE,
        related_name='geofence_entries'
    )
    geofence = models.ForeignKey(
        'campaigns.CampaignGeofence',
        on_delete=models.CASCADE,
        related_name='entries'
    )
    entry_type = models.CharField(
        max_length=10,
        choices=ENTRY_TYPE_CHOICES
    )
    
    # Location where entry/exit occurred
    location = gis_models.PointField()
    recorded_at = models.DateTimeField()
    
    # Source location record
    source_location = models.ForeignKey(
        LocationRecord,
        on_delete=models.CASCADE,
        related_name='geofence_events'
    )
    
    # If this is an exit, link to the corresponding entry
    entry_record = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='exit_records'
    )
    
    class Meta:
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['rider', 'recorded_at']),
            models.Index(fields=['geofence', 'recorded_at']),
            models.Index(fields=['entry_type', 'recorded_at']),
        ]
    
    def __str__(self):
        return f"{self.rider.rider_id} {self.entry_type} {self.geofence.name} at {self.recorded_at}"


class RiderSession(BaseModel):
    """
    Tracks working sessions within geofences
    Created when rider enters a geofence and closed when they exit
    """
    
    SESSION_STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ]
    
    rider = models.ForeignKey(
        'riders.Rider',
        on_delete=models.CASCADE,
        related_name='tracking_sessions'
    )
    geofence = models.ForeignKey(
        'campaigns.CampaignGeofence',
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    
    # Session boundaries
    start_entry = models.OneToOneField(
        GeofenceEntry,
        on_delete=models.CASCADE,
        related_name='started_session'
    )
    end_entry = models.OneToOneField(
        GeofenceEntry,
        on_delete=models.CASCADE,
        related_name='ended_session',
        null=True,
        blank=True
    )
    
    # Timing
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    
    # Calculated metrics
    duration_minutes = models.PositiveIntegerField(default=0)
    distance_covered = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Distance covered in km during session"
    )
    
    # Performance
    verification_count = models.PositiveIntegerField(default=0)
    earnings_calculated = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    status = models.CharField(
        max_length=20,
        choices=SESSION_STATUS_CHOICES,
        default='active'
    )
    
    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['rider', 'started_at']),
            models.Index(fields=['geofence', 'started_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.rider.rider_id} session in {self.geofence.name}"
    
    def calculate_duration(self):
        """Calculate session duration in minutes"""
        if self.ended_at and self.started_at:
            delta = self.ended_at - self.started_at
            self.duration_minutes = int(delta.total_seconds() / 60)
            return self.duration_minutes
        return 0
    
    def close_session(self, end_entry):
        """Close an active session"""
        if self.status == 'active':
            self.end_entry = end_entry
            self.ended_at = end_entry.recorded_at
            self.status = 'completed'
            self.calculate_duration()
            self.save()


class EarningsCalculation(BaseModel):
    """
    Stores calculated earnings for riders based on location tracking
    Mirrors mobile EarningsRecord model
    """
    
    EARNINGS_TYPE_CHOICES = [
        ('distance', 'Distance-based'),
        ('time', 'Time-based'),
        ('fixed', 'Fixed Rate'),
        ('hybrid', 'Hybrid'),
        ('bonus', 'Bonus'),
        ('correction', 'Correction'),
    ]
    
    CALCULATION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('calculated', 'Calculated'),
        ('paid', 'Paid'),
        ('disputed', 'Disputed'),
    ]
    
    # Core identifiers
    mobile_id = models.CharField(
        max_length=36,
        unique=True,
        null=True,
        blank=True,
        help_text="UUID from mobile app if synced"
    )
    rider = models.ForeignKey(
        'riders.Rider',
        on_delete=models.CASCADE,
        related_name='earnings_calculations'
    )
    geofence = models.ForeignKey(
        'campaigns.CampaignGeofence',
        on_delete=models.CASCADE,
        related_name='earnings_calculations'
    )
    session = models.ForeignKey(
        RiderSession,
        on_delete=models.CASCADE,
        related_name='earnings',
        null=True,
        blank=True
    )
    
    # Calculation details
    earnings_type = models.CharField(
        max_length=20,
        choices=EARNINGS_TYPE_CHOICES
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    currency = models.CharField(max_length=3, default='NGN')
    
    # Calculation inputs
    distance_km = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    duration_hours = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0
    )
    rate_applied = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0
    )
    
    # Timing
    earned_at = models.DateTimeField()
    calculated_at = models.DateTimeField(auto_now_add=True)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=CALCULATION_STATUS_CHOICES,
        default='calculated'
    )
    
    # Verification count for the period
    verifications_completed = models.PositiveIntegerField(default=0)
    
    # Metadata
    calculation_metadata = models.JSONField(
        default=dict,
        help_text="Additional calculation details"
    )
    
    class Meta:
        ordering = ['-earned_at']
        indexes = [
            models.Index(fields=['rider', 'earned_at']),
            models.Index(fields=['geofence', 'earned_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.rider.rider_id} - ₦{self.amount} ({self.earnings_type})"


class LocationSyncBatch(BaseModel):
    """
    Tracks batches of location data synced from mobile apps
    Helps with debugging sync issues and monitoring performance
    """
    
    BATCH_STATUS_CHOICES = [
        ('received', 'Received'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partially Processed'),
    ]
    
    rider = models.ForeignKey(
        'riders.Rider',
        on_delete=models.CASCADE,
        related_name='sync_batches'
    )
    
    # Batch info
    batch_id = models.CharField(max_length=36, unique=True)  # UUID from mobile
    total_records = models.PositiveIntegerField()
    processed_records = models.PositiveIntegerField(default=0)
    failed_records = models.PositiveIntegerField(default=0)
    
    # Timing
    batch_created_at = models.DateTimeField()  # When batch was created on mobile
    received_at = models.DateTimeField(auto_now_add=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=BATCH_STATUS_CHOICES,
        default='received'
    )
    
    # Error tracking
    error_log = models.JSONField(default=list)
    
    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['rider', 'received_at']),
            models.Index(fields=['status']),
            models.Index(fields=['batch_id']),
        ]
    
    def __str__(self):
        return f"Batch {self.batch_id} - {self.rider.rider_id}"
    
    @property
    def success_rate(self):
        if self.total_records == 0:
            return 0
        return (self.processed_records / self.total_records) * 100
    
    def start_processing(self):
        """Mark batch as processing"""
        self.status = 'processing'
        self.processing_started_at = timezone.now()
        self.save(update_fields=['status', 'processing_started_at'])
    
    def complete_processing(self):
        """Mark batch as completed"""
        if self.failed_records > 0:
            self.status = 'partial'
        else:
            self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])
    
    def add_error(self, error_info):
        """Add error to batch log"""
        self.error_log.append({
            'timestamp': timezone.now().isoformat(),
            'error': str(error_info)
        })
        self.failed_records += 1
        self.save(update_fields=['error_log', 'failed_records'])


class DailyTrackingSummary(BaseModel):
    """
    Daily aggregated tracking data for performance monitoring
    """
    
    rider = models.ForeignKey(
        'riders.Rider',
        on_delete=models.CASCADE,
        related_name='daily_summaries'
    )
    date = models.DateField()
    
    # Location tracking stats
    total_locations_recorded = models.PositiveIntegerField(default=0)
    total_distance_km = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    working_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    
    # Geofence activity
    geofences_visited = models.PositiveIntegerField(default=0)
    geofence_entries = models.PositiveIntegerField(default=0)
    geofence_exits = models.PositiveIntegerField(default=0)
    
    # Sessions
    total_sessions = models.PositiveIntegerField(default=0)
    completed_sessions = models.PositiveIntegerField(default=0)
    abandoned_sessions = models.PositiveIntegerField(default=0)
    
    # Earnings
    total_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    distance_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    time_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bonus_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Verifications
    verifications_completed = models.PositiveIntegerField(default=0)
    
    # Sync stats
    sync_batches_count = models.PositiveIntegerField(default=0)
    sync_success_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00
    )
    
    class Meta:
        unique_together = ['rider', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['rider', 'date']),
            models.Index(fields=['date']),
        ]
    
    def __str__(self):
        return f"{self.rider.rider_id} - {self.date}"
