"""Base agent contract.

Each specialized agent implements `analyze(context) -> dict`. The base class
provides shared access to the DB session, infrastructure memory and the optional
LLM client, plus a helper to persist its output as an AgentOutput row.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.agents.llm import get_llm
from app.core.logging import get_logger
from app.db.models import AgentOutput
from app.memory.infrastructure_memory import get_memory


class BaseAgent(ABC):
    name: str = "base"

    def __init__(self, db: Optional[Session] = None) -> None:
        self.db = db
        self.memory = get_memory()
        self.llm = get_llm()
        self.log = get_logger(f"agent.{self.name}")

    @abstractmethod
    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run the agent over a context dict and return its structured output."""

    def persist(
        self, output: Dict[str, Any], incident_id: Optional[int] = None
    ) -> None:
        if self.db is None:
            return
        row = AgentOutput(
            incident_id=incident_id,
            agent_name=self.name,
            output=output,
            confidence=float(output.get("confidence", 0.0) or 0.0),
        )
        self.db.add(row)
        self.db.flush()
