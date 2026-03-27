# Advanced Configuration

## SSL/TLS Encryption

For production brokers requiring encrypted connections:

**Profile configuration:**
```yaml
# profiles/production/config.yaml
logger:
  stomp:
    host: "secure-broker.example.com"
    port: 61614
    use_ssl: true
    cert_file: "/path/to/client.crt"
    key_file: "/path/to/client.key"
    queue: "/topic/snakemake.secure"
```

**Command line:**
```bash
snakemake --logger stomp \
  --logger-stomp-host secure-broker.example.com \
  --logger-stomp-port 61614 \
  --logger-stomp-use-ssl \
  --logger-stomp-cert-file /path/to/client.crt \
  --logger-stomp-key-file /path/to/client.key
```

## Event Filtering

Control which events generate messages to reduce noise or focus on specific workflow stages.

### Whitelist Approach

Only send specific events:

```bash
snakemake --logger stomp \
  --logger-stomp-include-events "WORKFLOW_STARTED,JOB_STARTED,JOB_FINISHED,WORKFLOW_FINISHED"
```

### Blacklist Approach

Exclude noisy events:

```bash
snakemake --logger stomp \
  --logger-stomp-exclude-events "DEBUG,PROGRESS,RESOURCES_INFO"
```

**Available events:** `WORKFLOW_STARTED`, `WORKFLOW_FINISHED`, `JOB_STARTED`, `JOB_FINISHED`, `JOB_ERROR`, `DEBUG`, `PROGRESS`, `RESOURCES_INFO`, and more.

## Built-in Formatters

### DefaultJSONFormatter (default)

Produces flat, easy-to-parse JSON:

```json
{
  "timestamp": "2024-01-15T14:30:00Z",
  "hostname": "compute-node-01",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "JOB_FINISHED",
  "level": "INFO",
  "message": "Job 5 completed successfully"
}
```

### JLabSWFFormatter

Nested schema compliant with JLab Scientific Workflow Facility standards:

```json
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
```

**To use JLabSWFFormatter:**

```bash
snakemake --logger stomp \
  --logger-stomp-formatter-class "snakemake_logger_plugin_stomp.formatters.JLabSWFFormatter"
```

The `SWF_RUN_NUMBER` environment variable can be set to populate the `correlation.run_number` field for tracking related workflow runs.

## Custom Formatters

Create your own formatter by implementing the `BaseFormatter` interface:

```python
# my_formatter.py
from snakemake_logger_plugin_stomp.formatters import BaseFormatter
from datetime import UTC, datetime

class MyFormatter(BaseFormatter):
    def format(self, record, workflow_metadata):
        return {
            "ts": datetime.now(UTC).isoformat(),
            "host": workflow_metadata.get("hostname"),
            "event": str(getattr(record, "event", "UNKNOWN")),
            "msg": record.getMessage() if hasattr(record, "getMessage") else str(record.msg),
            "custom_field": "my_value"
        }
```

Install your formatter in the same Python environment, then reference it:

```bash
snakemake --logger stomp \
  --logger-stomp-formatter-class "my_formatter.MyFormatter"
```

## Heartbeat Tuning

STOMP heartbeats keep the connection alive and detect network failures. Configure intervals in milliseconds:

```yaml
logger:
  stomp:
    host: "broker.example.com"
    heartbeat_send: 30000    # Client sends heartbeat every 30s (default: 10000ms = 10s)
    heartbeat_receive: 30000 # Client expects broker heartbeat every 30s (default: 10000ms = 10s)
```

**How it works:**
- `heartbeat_send`: How often the client sends heartbeat frames to the broker
- `heartbeat_receive`: How often the client expects to receive heartbeat frames from the broker
- Set to `0` to disable heartbeats entirely

**Do you need heartbeats for Snakemake?**

**YES, keep heartbeats enabled (default 10s)** if you have:
- Long-running jobs (hours) with infrequent events
- Workflows with idle periods waiting on external resources
- Unreliable networks (cloud, VPN, cross-datacenter connections)
- Enterprise firewalls/proxies that drop idle TCP connections
- Production workflows where silent connection loss is unacceptable

**NO, you can disable heartbeats (set to 0)** if you have:
- Short workflows (< 30 minutes) with frequent job events
- Localhost or same-datacenter broker (reliable network)
- Development/testing environment
- Jobs that start/finish frequently (events naturally keep connection alive)

**Tuning guidance:**
- **Default (10000ms = 10s)**: Good for most production workflows
- **Increase (30000-60000ms)**: For slow/congested networks to prevent false timeouts
- **Decrease (5000ms)**: For fast networks where you want quick failure detection
- **Disable (0)**: Only for local testing with reliable connections
- Both send and receive values should typically be the same
- Brokers may negotiate the actual interval based on their own configuration

**Example: Disable for local testing**
```yaml
logger:
  stomp:
    host: "localhost"
    heartbeat_send: 0
    heartbeat_receive: 0
```

## Queue vs Topic Destinations

STOMP supports both queue (point-to-point) and topic (publish-subscribe) semantics:

```yaml
# Queue - one consumer receives each message
queue: "/queue/snakemake.events"

# Topic - all subscribers receive each message
queue: "/topic/snakemake.broadcast"
```

Use **queues** when you want load balancing across multiple consumers. Use **topics** when multiple systems need to receive all events (e.g., monitoring + archival + alerting).

## RabbitMQ Streams

RabbitMQ streams are a queue type exposed by the RabbitMQ STOMP adapter. This plugin
supports stream publishing and stream declaration for queue destinations.

### Creating a Stream

Use a `/queue/<name>` destination together with `use_stream: true` to have RabbitMQ
declare the destination as a stream on first publish:

```yaml
logger:
  stomp:
    queue: "/queue/snakemake.stream"
    use_stream: true
```

### Publishing to an Existing Stream

Use `/amq/queue/<name>` when the stream already exists and should not be redeclared:

```yaml
logger:
  stomp:
    queue: "/amq/queue/snakemake.stream"
    use_stream: true
```

### Stream Filter Headers

RabbitMQ streams support outbound filter values on published messages. Use `stream_filter_value`
to set a static filter value applied to each published event:

```yaml
logger:
  stomp:
    queue: "/queue/snakemake.stream"
    use_stream: true
    stream_filter_value: "snakemake-workflow-logs"
```

### Constraints

- Stream support is publish-only in this plugin.
- RabbitMQ queue type is immutable, so an existing classic queue cannot be converted in place.

## Complete Production Example

A full production configuration combining SSL, event filtering, custom formatter, and heartbeat tuning:

```yaml
# profiles/production-stomp/config.yaml
logger:
  stomp:
    host: "activemq.prod.internal"
    port: 61614
    use_ssl: true
    cert_file: "/etc/certs/snakemake.crt"
    key_file: "/etc/certs/snakemake.key"
    queue: "/topic/snakemake.prod"
    formatter_class: "snakemake_logger_plugin_stomp.formatters.JLabSWFFormatter"
    include_events: "WORKFLOW_STARTED,JOB_STARTED,JOB_FINISHED,WORKFLOW_FINISHED,JOB_ERROR"
    heartbeat_send: 30000
    heartbeat_receive: 30000
```

**Usage:**
```bash
export STOMP_USER=workflow_user
export STOMP_PASSWORD=secure_password
export SWF_RUN_NUMBER=12345
snakemake --profile profiles/production-stomp
```

## Troubleshooting

### Connection Issues

If the plugin fails to connect:

1. Verify the broker is running and accessible: `telnet <host> <port>`
2. Check firewall rules allow the STOMP port
3. Confirm credentials are correct
4. Review broker logs for authentication errors

### SSL Certificate Errors

If SSL connections fail:

1. Verify certificate paths are correct and readable
2. Ensure certificates match the broker hostname
3. Check certificate expiration dates
4. Try with `use_ssl: false` first to isolate SSL-specific issues

### No Events Appearing

If events aren't reaching your consumer:

1. Check event filtering settings (`include_events`/`exclude_events`)
2. Verify the correct destination (queue vs topic)
3. Confirm consumers are connected to the same queue/topic
4. Review Snakemake logs for plugin connection errors

### Performance Considerations

For workflows with hundreds or thousands of jobs:

- Use event filtering to reduce message volume
- Consider using queues instead of topics if you don't need broadcast
- Increase heartbeat intervals if network latency is high
- Monitor broker memory usage and adjust configuration as needed