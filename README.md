# Snakemake Logger Plugin for STOMP

[![PyPI version](https://img.shields.io/pypi/v/snakemake-logger-plugin-stomp.svg)](https://pypi.org/project/snakemake-logger-plugin-stomp/) [![CI](https://github.com/jeffersonlab/snakemake-logger-plugin-stomp/actions/workflows/ci.yml/badge.svg)](https://github.com/jeffersonlab/snakemake-logger-plugin-stomp/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Send Snakemake workflow events monitoring to a STOMP message broker (ActiveMQ, RabbitMQ, etc.) in real-time.

## Installation

```bash
pip install snakemake-logger-plugin-stomp
```

## Quick Start
```bash
snakemake --logger stomp \
  --logger-stomp-host localhost \
  --logger-stomp-port 61613 \
  --logger-stomp-user admin \
  --logger-stomp-password admin \
  --logger-stomp-queue /queue/snakemake.events
```

Or use a profile:
```yaml
# profiles/stomp/config.yaml
logger:
  stomp:
    host: "activemq.example.com"
    port: 61613
    user: "${STOMP_USER}"
    password: "${STOMP_PASSWORD}"
    queue: "/topic/snakemake.prod"
```

## Features

  - JSON event streaming to message brokers
  - SSL/TLS support
  - Configurable formatters (default + JLab SWF schema)
  - Event filtering (include/exclude)
  - Heartbeat management
  - Environment variable support for secrets