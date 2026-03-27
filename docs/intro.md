# Snakemake Logger Plugin for STOMP

Stream Snakemake workflow events to STOMP message brokers (ActiveMQ, RabbitMQ, Apollo) in real-time for monitoring, audit trails, and event-driven system integration.

## Key Features

- **Real-time event streaming** to STOMP-compatible message brokers
- **RabbitMQ stream queue support** for append-only log style destinations
- **SSL/TLS encryption** for secure production deployments
- **Flexible formatters** - default flat JSON, JLab Scientific Workflow schema, or comprehensive Snakemake logs
- **Event filtering** - include/exclude specific event types to reduce noise
- **Custom formatters** - plugin your own formatter classes
- **Environment variable support** for credentials and sensitive configuration

## Installation

```bash
pip install snakemake-logger-plugin-stomp
```

## Quick Start

### Command Line

```bash
snakemake --logger stomp \
  --logger-stomp-host localhost \
  --logger-stomp-port 61613 \
  --logger-stomp-user admin \
  --logger-stomp-password admin \
  --logger-stomp-queue /queue/snakemake.events
```

### Profile Configuration

```yaml
# profiles/stomp/config.yaml
logger:
  stomp:
    host: "activemq.example.com"
    port: 61613
    user: "${STOMP_USER}"
    password: "${STOMP_PASSWORD}"
    queue: "/topic/snakemake.events"
```

Then run:
```bash
snakemake --profile profiles/stomp
```

### RabbitMQ Stream Destinations

When using RabbitMQ's STOMP adapter, the plugin can publish to stream queues.

```yaml
logger:
  stomp:
    host: "rabbitmq.example.com"
    port: 61613
    user: "${STOMP_USER}"
    password: "${STOMP_PASSWORD}"
    queue: "/queue/snakemake.stream"
    use_stream: true
    stream_filter_value: "snakemake-events"
```

Use `/queue/<name>` to create a new stream on first publish. Use `/amq/queue/<name>`
to publish to an existing stream without redeclaring it.

### Environment Variables

Secure credentials using environment variables:

```bash
export SNAKEMAKE_LOGGER_STOMP_HOST=activemq.example.com
export SNAKEMAKE_LOGGER_STOMP_USER=admin
export SNAKEMAKE_LOGGER_STOMP_PASSWORD=secret
snakemake --logger stomp
```

## Use Cases

- **External monitoring** - Send workflow events to centralized monitoring systems
- **Audit trails** - Create permanent records of workflow execution in message queues
- **Event-driven automation** - Trigger downstream processes based on workflow events
- **Team dashboards** - Build real-time dashboards showing workflow status across teams
- **Integration** - Connect Snakemake to enterprise message bus architectures