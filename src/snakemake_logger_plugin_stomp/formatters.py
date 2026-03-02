"""
Formatter classes for STOMP logger plugin.

This module provides formatter implementations that convert Snakemake log records
into structured JSON messages for STOMP brokers.
"""

import os
import socket
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any


class BaseFormatter(ABC):
    """Abstract base class for STOMP message formatters.

    Custom formatters should extend this class and implement the format() method
    to define their own message structure.
    """

    @abstractmethod
    def format(self, record: Any, workflow_metadata: dict) -> dict:
        """Format a log record into a dictionary for JSON serialization.

        Args:
            record: Python logging.LogRecord object with Snakemake event data
            workflow_metadata: Dict containing workflow_id, hostname, etc.

        Returns:
            Dictionary that will be JSON-serialized and sent to STOMP broker
        """
        pass


class DefaultJSONFormatter(BaseFormatter):
    """Standard flat JSON formatter for general logging.

    Produces simple, flat JSON structure that's easy to parse and index.
    Suitable for most monitoring and logging use cases.

    Example output:
        {
            "timestamp": "2024-01-15T14:30:00Z",
            "hostname": "compute-node-01",
            "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
            "event_type": "JOB_FINISHED",
            "level": "INFO",
            "message": "Job 5 completed successfully"
        }
    """

    def format(self, record, workflow_metadata):
        """Format record as flat JSON structure.

        Args:
            record: Log record containing event attribute and standard logging fields
            workflow_metadata: Dict with workflow_id and hostname

        Returns:
            Flat dictionary with timestamp, hostname, event info, and message
        """
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "hostname": workflow_metadata.get("hostname"),
            "workflow_id": workflow_metadata.get("workflow_id"),
            "event_type": str(getattr(record, "event", "UNKNOWN")),
            "level": getattr(record, "levelname", "INFO"),
            "message": (
                record.getMessage()
                if hasattr(record, "getMessage")
                else str(record.msg)
            ),
        }


class JLabSWFFormatter(BaseFormatter):
    """JLab Scientific Workflow Facility compliant formatter.

    Produces nested JSON schema following JLab SWF event standards.
    Suitable for integration with Jefferson Lab's Scientific Workflow Facility
    and similar enterprise workflow management systems.

    The formatter reads the SWF_RUN_NUMBER environment variable to populate
    correlation metadata for tracking related workflow runs.

    Example output:
        {
            "schema_ref": "org.jlab.swf.event",
            "schema_version": "1.0.0",
            "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "event_type": "SNAKEMAKE_JOB_FINISHED",
            "event_time": "2024-01-15T14:30:00Z",
            "source": {
                "agent_id": "snakemake-compute-node-01",
                "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
                "hostname": "compute-node-01"
            },
            "correlation": {
                "run_number": "12345"
            },
            "payload": {
                "msg": "Job 5 completed successfully",
                "level": "INFO",
                "name": "align_reads",
                "jobid": 5,
                "wildcards": {"sample": "A"},
                "threads": 4,
                "resources": {"mem_mb": 16000}
            }
        }
    """

    def format(self, record, workflow_metadata):
        """Format record following JLab SWF schema.

        Args:
            record: Log record with Snakemake-specific attributes (name, jobid,
                   wildcards, threads, resources) in addition to standard logging fields
            workflow_metadata: Dict with workflow_id and hostname

        Returns:
            Nested dictionary conforming to JLab SWF event schema
        """
        snakemake_event = str(getattr(record, "event", "UNKNOWN"))

        # Build the payload with message and log level
        payload = {
            "msg": (
                record.getMessage()
                if hasattr(record, "getMessage")
                else str(record.msg)
            ),
            "level": getattr(record, "levelname", "INFO"),
        }

        # Extract Snakemake-specific attributes if present
        # These vary by event type (e.g., JOB_STARTED vs WORKFLOW_FINISHED)
        for attr in ["name", "jobid", "wildcards", "threads", "resources"]:
            if hasattr(record, attr):
                val = getattr(record, attr)
                # Convert wildcards object to dictionary
                if attr == "wildcards" and hasattr(val, "items"):
                    val = dict(val.items())
                payload[attr] = val

        return {
            "schema_ref": "org.jlab.swf.event",
            "schema_version": "1.0.0",
            "event_id": str(uuid.uuid4()),
            "event_type": f"SNAKEMAKE_{snakemake_event}",
            "event_time": datetime.now(UTC).isoformat(),
            "source": {
                "agent_id": f"snakemake-{socket.gethostname()}",
                "workflow_id": workflow_metadata.get("workflow_id"),
                "hostname": workflow_metadata.get("hostname"),
            },
            "correlation": {"run_number": os.getenv("SWF_RUN_NUMBER")},
            "payload": payload,
        }
