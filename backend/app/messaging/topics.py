"""Canonical Kafka topic names."""

METRICS_EVENTS = "metrics-events"
DEPLOYMENT_EVENTS = "deployment-events"
INCIDENT_EVENTS = "incident-events"
DR_EVENTS = "dr-events"
SIMULATION_EVENTS = "simulation-events"

ALL_TOPICS = [
    METRICS_EVENTS,
    DEPLOYMENT_EVENTS,
    INCIDENT_EVENTS,
    DR_EVENTS,
    SIMULATION_EVENTS,
]

# Maps a UnifiedEvent.event_type to the topic it should be published on.
EVENT_TYPE_TO_TOPIC = {
    "metric": METRICS_EVENTS,
    "log": METRICS_EVENTS,
    "deployment": DEPLOYMENT_EVENTS,
    "incident": INCIDENT_EVENTS,
    "dr_event": DR_EVENTS,
    "backup": DR_EVENTS,
    "failover": DR_EVENTS,
    "replication": DR_EVENTS,
    "audit": INCIDENT_EVENTS,
}
