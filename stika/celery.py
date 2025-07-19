import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stika.settings')

app = Celery('stika')

app.config_from_object('django.conf:settings', namespace='CELERY')

# Task routing (as per plan)
app.conf.task_routes = {
    'verification.*': {'queue': 'verification'},
    'payments.*': {'queue': 'payments'},
    'analytics.*': {'queue': 'analytics'},
    'notifications.*': {'queue': 'notifications'},
}

# Beat schedule for periodic tasks (as per plan)
app.conf.beat_schedule = {
    'process-pending-payments': {
        'task': 'payments.tasks.process_pending_payments',
        'schedule': crontab(hour=10, minute=0),  # Daily at 10 AM
        'options': {'queue': 'payments'}
    },
    'calculate-rider-scores': {
        'task': 'analytics.tasks.calculate_rider_scores',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
        'options': {'queue': 'analytics'}
    },
    'detect-suspicious-activity': {
        'task': 'fraud.tasks.detect_suspicious_activity',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
        'options': {'queue': 'fraud'}
    },
    'trigger-random-verifications': {
        'task': 'verification.tasks.trigger_random_verifications',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
        'options': {'queue': 'verification'}
    },
    'update-competitive-intelligence': {
        'task': 'analytics.tasks.update_competitive_intelligence',
        'schedule': crontab(hour=1, minute=0),  # Daily at 1 AM
        'options': {'queue': 'analytics'}
    },
}

app.autodiscover_tasks()