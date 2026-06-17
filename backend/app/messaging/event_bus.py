"""Event bus abstraction.

A single `EventBus` interface with two implementations:

* `KafkaEventBus`     — real Kafka producer/consumer (used when
                        KAFKA_BOOTSTRAP_SERVERS is configured).
* `InMemoryEventBus`  — process-local pub/sub used for local dev, tests and
                        demos so the platform runs with zero infrastructure.

The rest of the codebase depends only on the abstract interface, so swapping
transports never touches business logic.
"""
from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Callable, Dict, List

from app.config import settings
from app.core.logging import get_logger
from app.schemas.events import UnifiedEvent

logger = get_logger(__name__)

Subscriber = Callable[[UnifiedEvent], None]


class EventBus(ABC):
    @abstractmethod
    def publish(self, topic: str, event: UnifiedEvent) -> None: ...

    @abstractmethod
    def subscribe(self, topic: str, handler: Subscriber) -> None: ...

    def close(self) -> None:  # pragma: no cover - optional
        pass


class InMemoryEventBus(EventBus):
    """Thread-safe, synchronous in-process pub/sub."""

    def __init__(self) -> None:
        self._subs: Dict[str, List[Subscriber]] = defaultdict(list)
        self._lock = threading.Lock()
        self.published: List[dict] = []  # lightweight audit trail for demos

    def publish(self, topic: str, event: UnifiedEvent) -> None:
        with self._lock:
            handlers = list(self._subs.get(topic, []))
            self.published.append({"topic": topic, "event": event.model_dump(mode="json")})
            # Keep the demo trail bounded.
            if len(self.published) > 1000:
                self.published = self.published[-1000:]
        for handler in handlers:
            try:
                handler(event)
            except Exception:  # noqa: BLE001 - subscriber isolation
                logger.exception("subscriber failed for topic %s", topic)

    def subscribe(self, topic: str, handler: Subscriber) -> None:
        with self._lock:
            self._subs[topic].append(handler)


class KafkaEventBus(EventBus):
    """Kafka-backed bus. Imports kafka-python lazily so the dependency is only
    required when Kafka is actually enabled."""

    def __init__(self, bootstrap_servers: str) -> None:
        from kafka import KafkaProducer  # lazy import

        self._producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers.split(","),
            client_id=settings.KAFKA_CLIENT_ID,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            retries=5,
            acks="all",
            linger_ms=20,
        )
        self._bootstrap = bootstrap_servers
        self._consumer_threads: List[threading.Thread] = []
        logger.info("KafkaEventBus connected to %s", bootstrap_servers)

    def publish(self, topic: str, event: UnifiedEvent) -> None:
        self._producer.send(
            topic, key=event.key(), value=event.model_dump(mode="json")
        )

    def subscribe(self, topic: str, handler: Subscriber) -> None:
        from kafka import KafkaConsumer  # lazy import

        def _run() -> None:
            consumer = KafkaConsumer(
                topic,
                bootstrap_servers=self._bootstrap.split(","),
                group_id=f"deployhub-{topic}",
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest",
                enable_auto_commit=True,
            )
            for msg in consumer:
                try:
                    handler(UnifiedEvent(**msg.value))
                except Exception:  # noqa: BLE001
                    logger.exception("kafka subscriber failed on %s", topic)

        t = threading.Thread(target=_run, daemon=True, name=f"consumer-{topic}")
        t.start()
        self._consumer_threads.append(t)

    def close(self) -> None:
        try:
            self._producer.flush()
            self._producer.close()
        except Exception:  # noqa: BLE001
            pass


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Singleton accessor. Chooses transport based on configuration, and
    transparently degrades to the in-memory bus if Kafka is unreachable."""
    global _bus
    if _bus is not None:
        return _bus
    if settings.kafka_enabled:
        try:
            _bus = KafkaEventBus(settings.KAFKA_BOOTSTRAP_SERVERS)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Kafka unavailable (%s); falling back to in-memory event bus", exc
            )
            _bus = InMemoryEventBus()
    else:
        logger.info("Kafka not configured; using in-memory event bus")
        _bus = InMemoryEventBus()
    return _bus
