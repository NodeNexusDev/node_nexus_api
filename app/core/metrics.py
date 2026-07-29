"""Application-specific Prometheus metrics."""

from prometheus_client import Counter, Gauge, Histogram

AUDIT_DELIVERIES = Counter(
    "node_nexus_audit_deliveries_total", "Successfully delivered audit events"
)
AUDIT_FAILURES = Counter(
    "node_nexus_audit_delivery_failures_total", "Failed audit delivery attempts"
)
AUDIT_RETRIES = Counter(
    "node_nexus_audit_delivery_retries_total", "Retried audit deliveries"
)
AUDIT_PENDING = Gauge("node_nexus_audit_pending", "Audit events awaiting delivery")
AUDIT_OLDEST_PENDING = Gauge(
    "node_nexus_audit_oldest_pending_seconds",
    "Age of the oldest pending audit event",
)

SCHEDULER_OWNER = Gauge(
    "node_nexus_scheduler_owner", "Whether this replica owns scheduled execution"
)
SCHEDULER_READY = Gauge(
    "node_nexus_scheduler_ready", "Whether initial schedule restoration completed"
)
SCHEDULER_RESTORED = Counter(
    "node_nexus_scheduler_restored_total", "Runtime schedules restored from storage"
)
SCHEDULER_REGISTRATION_FAILURES = Counter(
    "node_nexus_scheduler_registration_failures_total",
    "Runtime schedule registration failures",
)
SCHEDULER_ACTIVE = Gauge(
    "node_nexus_scheduler_active_schedules",
    "Number of enabled persistent schedules",
)
SCHEDULER_MISFIRES = Counter(
    "node_nexus_scheduler_misfires_total", "Scheduled runs missed beyond grace time"
)
SCHEDULER_SKIPPED_OVERLAP = Counter(
    "node_nexus_scheduler_skipped_overlap_total",
    "Scheduled runs skipped because max instances was reached",
)
SCHEDULER_START_LAG = Histogram(
    "node_nexus_scheduler_start_lag_seconds",
    "Difference between planned and observed scheduler event time",
)
SCHEDULER_JOBS = Counter(
    "node_nexus_scheduler_jobs_total",
    "Scheduled execution outcomes",
    ["outcome"],
)
SCHEDULER_JOB_DURATION = Histogram(
    "node_nexus_scheduler_job_duration_seconds",
    "Scheduled execution duration",
)
