"""
Snakemake logger plugin for STOMP message brokers.

This plugin streams Snakemake workflow events to STOMP-compatible message brokers
(ActiveMQ, RabbitMQ, Apollo) in real-time for monitoring, audit trails, and
event-driven integration.
"""

import importlib
import json
import logging as py_logging
import socket
import ssl
import uuid
from dataclasses import dataclass, field
from typing import Optional

import stomp
from snakemake_interface_logger_plugins.base import LogHandlerBase
from snakemake_interface_logger_plugins.common import LogEvent
from snakemake_interface_logger_plugins.settings import LogHandlerSettingsBase

from snakemake_logger_plugin_stomp.formatters import DefaultJSONFormatter


@dataclass
class LogHandlerSettings(LogHandlerSettingsBase):
    """Configuration settings for STOMP logger plugin.

    All settings can be provided via command line options (--stomp-*),
    profile configuration files, or environment variables where indicated.
    """

    host: str = field(
        default="localhost",
        metadata={"help": "STOMP broker hostname", "required": True},
    )
    port: int = field(
        default=61613,
        metadata={"help": "STOMP broker port", "required": True},
    )
    user: Optional[str] = field(
        default=None,
        metadata={
            "help": "STOMP broker username for authentication",
            "required": True,
            "env_var": True,  # Can be set via SNAKEMAKE_LOGGER_STOMP_USER
        },
    )
    password: Optional[str] = field(
        default=None,
        metadata={
            "help": "STOMP broker password for authentication",
            "required": True,
            "env_var": True,  # Can be set via SNAKEMAKE_LOGGER_STOMP_PASSWORD
        },
    )
    queue: str = field(
        default="/queue/snakemake.events",
        metadata={
            "help": "STOMP destination (queue or topic path, e.g., /queue/name or /topic/name)"
        },
    )
    formatter_class: str = field(
        default="snakemake_logger_plugin_stomp.formatters.DefaultJSONFormatter",
        metadata={
            "help": "Full Python path to formatter class (e.g., module.submodule.ClassName)",
            "env_var": False,
            "required": False,
        },
    )
    include_events: Optional[str] = field(
        default=None,
        metadata={
            "help": "Comma-separated list of events to include (e.g., 'WORKFLOW_STARTED,JOB_FINISHED')",
            "env_var": False,
        },
    )
    exclude_events: Optional[str] = field(
        default=None,
        metadata={
            "help": "Comma-separated list of events to exclude (e.g., 'DEBUG,PROGRESS')",
            "env_var": False,
        },
    )
    use_ssl: bool = field(
        default=False,
        metadata={
            "help": "Enable SSL/TLS encryption for broker connection",
            "env_var": False,
        },
    )
    cert_file: Optional[str] = field(
        default=None,
        metadata={
            "help": "Path to SSL certificate file for client authentication",
            "env_var": False,
        },
    )
    key_file: Optional[str] = field(
        default=None,
        metadata={
            "help": "Path to SSL private key file for client authentication",
            "env_var": False,
        },
    )
    heartbeat_send: int = field(
        default=10000,
        metadata={
            "help": "STOMP heartbeat send interval in milliseconds (0 to disable)",
            "env_var": False,
        },
    )
    heartbeat_receive: int = field(
        default=10000,
        metadata={
            "help": "STOMP heartbeat receive interval in milliseconds (0 to disable)",
            "env_var": False,
        },
    )
    fail_on_connection_error: bool = field(
        default=False,
        metadata={
            "help": "Fail workflow if initial connection to broker fails (strict audit mode)",
            "env_var": False,
        },
    )


class StompConnectionListener(stomp.ConnectionListener):
    """Listener for STOMP connection events.

    Handles connection errors and disconnections, logging them appropriately.
    """

    def __init__(self, logger):
        """Initialize listener with a logger instance.

        Args:
            logger: Python logger for outputting connection events
        """
        self.logger = logger

    def on_error(self, frame):
        """Handle STOMP error frames.

        Args:
            frame: STOMP error frame containing error details
        """
        self.logger.error(f"[STOMP] Broker error: {frame.body}")

    def on_disconnected(self):
        """Handle disconnection from STOMP broker."""
        self.logger.warning("[STOMP] Disconnected from broker")


class LogHandler(LogHandlerBase):
    """Snakemake logger handler for STOMP message broker integration.

    This handler intercepts Snakemake log events, formats them according to
    the configured formatter, and sends them to a STOMP message broker.

    Features:
    - Automatic connection management with heartbeats
    - SSL/TLS support for secure connections
    - Configurable event filtering (include/exclude lists)
    - Pluggable formatter system
    - Automatic workflow ID generation and tracking
    """

    def __post_init__(self) -> None:
        """Initialize the STOMP logger handler.

        This method is called after __init__ by the base class. It:
        - Sets up internal logging
        - Initializes workflow metadata tracking
        - Loads the configured formatter
        - Establishes connection to STOMP broker
        """
        super().__post_init__()

        # Internal logger for plugin diagnostics (separate from Snakemake logs)
        self._internal_logger = py_logging.getLogger(__name__)

        # STOMP connection handle
        self.connection = None

        # Workflow tracking metadata
        self.workflow_metadata = {
            "workflow_id": None,  # Generated on WORKFLOW_STARTED event
            "hostname": socket.gethostname(),
        }

        # Load and initialize the configured formatter
        self.formatter_instance = self._init_formatter()

        self.include_events_lower = (
            {e.lower() for e in self.settings.include_events.split(",")}
            if self.settings.include_events
            else None
        )
        self.exclude_events_lower = (
            {e.lower() for e in self.settings.exclude_events.split(",")}
            if self.settings.exclude_events
            else None
        )

        # Establish connection to STOMP broker
        self._connect_to_broker()

    def _init_formatter(self):
        """Load and instantiate the configured formatter class.

        Returns:
            Instance of the configured formatter class, or DefaultJSONFormatter
            if loading fails.
        """
        try:
            # Split module path from class name
            module_path, class_name = self.settings.formatter_class.rsplit(".", 1)

            # Dynamically import the module
            module = importlib.import_module(module_path)

            # Get the class and instantiate it
            formatter_class = getattr(module, class_name)
            return formatter_class()

        except (ImportError, AttributeError, ValueError) as e:
            self._internal_logger.error(
                f"[STOMP] Failed to load formatter '{self.settings.formatter_class}': {e}. "
                f"Falling back to DefaultJSONFormatter."
            )
            return DefaultJSONFormatter()

    def _connect_to_broker(self):
        """Establish connection to STOMP message broker.

        Configures SSL if enabled and sets up connection listener for
        error handling. Connection errors are logged but don't halt execution.
        """
        hosts = [(self.settings.host, self.settings.port)]

        try:
            # Create STOMP connection with heartbeat configuration
            self.connection = stomp.Connection(
                host_and_ports=hosts,
                heartbeats=(
                    self.settings.heartbeat_send,
                    self.settings.heartbeat_receive,
                ),
            )

            # Attach listener for error handling
            self.connection.set_listener(
                "logger", StompConnectionListener(self._internal_logger)
            )

            # Configure SSL if enabled
            if self.settings.use_ssl:
                self.connection.set_ssl(
                    for_hosts=hosts,
                    cert_file=self.settings.cert_file,
                    key_file=self.settings.key_file,
                    ssl_version=ssl.PROTOCOL_TLS_CLIENT,
                )

            # Establish connection to broker
            self.connection.connect(
                username=self.settings.user,
                passcode=self.settings.password,
                wait=True,
            )

            self._internal_logger.info(
                f"[STOMP] Connected to {self.settings.host}:{self.settings.port}"
            )

        except (ConnectionError, OSError, Exception) as e:
            self._internal_logger.error(
                f"[STOMP] Failed to connect to {self.settings.host}:{self.settings.port}: {e}"
            )
            if self.settings.fail_on_connection_error:
                raise RuntimeError(
                    f"STOMP logging required but broker unavailable: {e}"
                ) from e

    def _send_to_broker(self, event_data: dict):
        """Send formatted event data to STOMP broker.

        Args:
            event_data: Dictionary to be JSON-serialized and sent as message body
        """
        # Skip if not connected
        if not self.connection or not self.connection.is_connected():
            self._internal_logger.debug(
                "[STOMP] Skipping send - not connected to broker"
            )
            return

        try:
            # Send message with JSON body and appropriate headers
            self.connection.send(
                body=json.dumps(event_data, default=str),
                destination=self.settings.queue,
                headers={
                    "persistent": "true",  # Request broker persistence
                    "content-type": "application/json",
                },
            )

            self._internal_logger.debug(
                f"[STOMP] Sent event: {event_data.get('event_type', 'UNKNOWN')}"
            )

        except (ConnectionError, OSError, Exception) as e:
            self._internal_logger.error(f"[STOMP] Failed to send message: {e}")

    def _should_send_event(self, event_type: str) -> bool:
        """Check if event passes filter criteria.

        Events are filtered based on include_events and exclude_events settings.
        If include_events is set, only those events pass. If exclude_events is
        set, all events except those are sent. If both are set, include_events
        takes precedence.

        Args:
            event_type: String representation of the event type

        Returns:
            True if event should be sent, False otherwise
        """
        event_lower = event_type.lower()

        if self.include_events_lower:
            return event_lower in self.include_events_lower
        if self.exclude_events_lower:
            return event_lower not in self.exclude_events_lower

        return True

    def emit(self, record):
        """Process and emit a log record.

        This is the main entry point called by Python's logging system for each
        log event. It filters events, generates workflow IDs, formats messages,
        and sends them to the STOMP broker.

        Args:
            record: Python logging.LogRecord with Snakemake event data
        """
        # Skip records without event attribute (non-Snakemake logs)
        if not hasattr(record, "event"):
            return

        event_type = str(record.event)

        # Apply event filters
        if not self._should_send_event(event_type):
            self._internal_logger.debug(f"[STOMP] Filtered out event: {event_type}")
            return

        # Generate workflow ID on first WORKFLOW_STARTED event
        if (
            event_type == str(LogEvent.WORKFLOW_STARTED)
            and not self.workflow_metadata["workflow_id"]
        ):
            self.workflow_metadata["workflow_id"] = str(uuid.uuid4())
            self._internal_logger.info(
                f"[STOMP] Generated workflow ID: {self.workflow_metadata['workflow_id']}"
            )

        # Format event using configured formatter
        try:
            event_data = self.formatter_instance.format(record, self.workflow_metadata)
        except Exception as e:
            self._internal_logger.error(
                f"[STOMP] Formatter error for event {event_type}: {e}"
            )
            return

        # Send formatted event to broker
        self._send_to_broker(event_data)

    def close(self):
        """Clean up and close STOMP connection.

        Called when Snakemake workflow completes or logger is being shut down.
        """
        if self.connection and self.connection.is_connected():
            try:
                self.connection.disconnect()
                self._internal_logger.info("[STOMP] Disconnected from broker")
            except Exception as e:
                self._internal_logger.error(f"[STOMP] Error during disconnect: {e}")

    @property
    def writes_to_stream(self) -> bool:
        """Indicate this handler does not write to stdout/stderr.

        Returns:
            False - events are sent to STOMP broker, not console streams
        """
        return False

    @property
    def writes_to_file(self) -> bool:
        """Indicate this handler does not write to files.

        Returns:
            False - events are sent to STOMP broker, not written to files
        """
        return False

    @property
    def has_filter(self) -> bool:
        """Indicate this handler implements event filtering.

        Returns:
            True - handler filters events based on include/exclude settings
        """
        return True

    @property
    def has_formatter(self) -> bool:
        """Indicate this handler implements custom formatting.

        Returns:
            True - handler uses pluggable formatter system
        """
        return True

    @property
    def needs_rulegraph(self) -> bool:
        """Indicate whether handler needs workflow DAG information.

        Returns:
            False - this handler doesn't require the workflow rulegraph
        """
        return False
