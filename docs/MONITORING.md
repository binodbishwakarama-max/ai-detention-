# Monitoring and Alerting Guide

This document provides an overview of the monitoring and alerting setup for the AI Evaluation Engine, which uses Prometheus and Grafana.

## Overview

Our monitoring stack is designed to provide deep visibility into the application's performance and health. It consists of:

- **Prometheus:** A time-series database that scrapes and stores metrics from our application components.
- **Alertmanager:** Handles alerts sent by Prometheus and routes them to the appropriate notification channels.
- **Grafana:** A visualization tool that allows us to create dashboards to monitor our metrics.

## Prometheus Configuration

The main Prometheus configuration is located at `infra/prometheus/prometheus.yml`. It is configured to scrape metrics from the following targets:

- **FastAPI Application:** The main API server exposes metrics at the `/metrics` endpoint.
- **Celery Workers:** The Celery workers expose metrics that are scraped by Prometheus.

### Alerting Rules

Our alerting rules are defined in `infra/prometheus/alert_rules.yml`. These rules are designed to notify us of potential issues before they become critical. We have alerts for:

- **High HTTP Error Rate:** Triggers a warning if the error rate exceeds 1% and a critical alert if it exceeds 5%.
- **High P99 Latency:** Triggers a warning if the 99th percentile response time exceeds 500ms.
- **Celery Queue Backlog:** Triggers a warning if any Celery queue has more than 1000 pending messages.
- **Celery Worker Offline:** Triggers a critical alert if a Celery worker is offline for more than 2 minutes.

## Alertmanager Configuration

The Alertmanager configuration is located at `infra/prometheus/alertmanager.yml`. It is responsible for routing alerts to different notification channels based on their severity.

- **Warning Alerts:** Sent to the `#alerts` Slack channel.
- **Critical Alerts:** Sent to PagerDuty and the `#oncall` Slack channel to ensure immediate attention.

## Grafana Dashboards

While the configuration for Grafana is not included in this repository, we recommend creating the following dashboards to visualize the metrics collected by Prometheus:

- **API Performance:**
  - Request rate, error rate, and latency (average, p95, p99).
  - Breakdowns by endpoint, method, and status code.
- **Celery Workers:**
  - Queue depth and task execution times.
  - Worker status and resource utilization.
- **System Metrics:**
  - CPU, memory, and disk usage for all application components.

## Setup

To set up the monitoring stack locally, you can use the provided `docker-compose.yml` file, which includes services for Prometheus and Grafana. For a production deployment, you will need to deploy these components to your Kubernetes cluster.
