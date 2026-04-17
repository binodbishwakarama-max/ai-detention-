# Disaster Recovery Playbook

This document is the official runbook for handling critical failure scenarios in the AI Evaluation Engine. It provides step-by-step instructions for Site Reliability Engineers (SREs) to ensure swift and effective recovery.

## Guiding Principles

- **Fail-Safe by Design:** Many components are designed to fail open or gracefully degrade to minimize user impact.
- **Automated Recovery First:** Where possible, the system is configured for automatic recovery (e.g., exponential backoff, retries). Manual intervention should be a last resort.
- **Immutable Infrastructure:** We treat our infrastructure as code. Manual changes to production environments are strongly discouraged and should be codified and peer-reviewed.

---

## Scenario 1: Complete Database Failure

- **Symptoms:**
  - API returns `500 Internal Server Error` for all stateful requests.
  - Prometheus alert `PostgresDown` is firing.
  - Logs are flooded with `sqlalchemy.exc.OperationalError`.

- **Recovery Protocol:**
  1.  **Confirm Outage:** Verify the database is unreachable from the API and worker pods.
  2.  **Initiate Point-in-Time Recovery (PITR):**
      - Use your cloud provider's console or CLI to restore the database from the latest backup to a new instance.
      - **Example (AWS RDS):**
        ```bash
        aws rds restore-db-instance-to-point-in-time \
            --source-db-instance-identifier <source-instance-id> \
            --target-db-instance-identifier <new-instance-id> \
            --restore-time <timestamp>
        ```
  3.  **Update Application Configuration:** Update the `DATABASE_URL` secret in Kubernetes to point to the new database instance.
  4.  **Restart Application Pods:** Perform a rolling restart of the API and worker deployments to pick up the new database connection.
      ```bash
      kubectl rollout restart deployment/eval-engine-api
      kubectl rollout restart deployment/eval-engine-worker
      ```
  5.  **Post-Mortem:** Conduct a thorough post-mortem to determine the root cause of the failure and implement preventative measures.

---

## Scenario 2: Complete Redis Failure

- **Symptoms:**
  - Celery workers are idle and not processing tasks.
  - API latency may be normal due to fail-open design, but new evaluations will not be processed.
  - Prometheus alert `RedisDown` is firing.

- **Recovery Protocol:**
  1.  **Fail-Open Confirmation:** Note that the API is designed to fail-open. Rate limiting and caching will be bypassed, but the API will remain available for read-only operations.
  2.  **Reboot Redis Instance:**
      - **AWS ElastiCache:** `aws elasticache reboot-cache-cluster --cache-cluster-id <cluster-id>`
      - **Self-Hosted:** Restart the Redis pod or server.
  3.  **Purge Corrupted Celery State:** If tasks were in-flight, the Celery state may be corrupted. Purge it to allow workers to reconnect cleanly.
      ```bash
      # Exec into a worker pod to run this command
      celery -A src.workers.celery_app purge -f
      ```
  4.  **Re-queue Failed Tasks:** Manually inspect logs or the dead-letter queue for tasks that failed during the outage and re-queue them if necessary.

---

## Scenario 3: Dead Letter Queue (DLQ) Flood

- **Symptoms:**
  - Prometheus alert `QueueBacklog` is firing for the DLQ.
  - The `dlq:all` list in Redis grows rapidly.

- **Recovery Protocol:**
  1.  **Isolate the Poison Pill:** A flood in the DLQ often indicates a "poison pill" message—a malformed task that causes workers to crash repeatedly.
  2.  **Sample the DLQ:** Use `redis-cli` to inspect a message from the DLQ and identify the traceback.

      ```bash
      # Get the key of a message
      LINDEX dlq:all 0

      # Get the traceback for that message
      HGET <message-key> traceback
      ```

  3.  **Fix and Deploy:** Identify the underlying bug in the worker code, deploy a fix, and monitor the DLQ to ensure the issue is resolved.
  4.  **Drain the DLQ:** Once the fix is deployed, use a script to safely re-queue the messages from the DLQ.

---

## Scenario 4: High Latency / Saturation

- **Symptoms:**
  - Prometheus alert `HighP99Latency` is firing.
  - API response times are slow.
  - CPU or memory usage is high across API or worker pods.

- **Recovery Protocol:**
  1.  **Scale Out:** The first line of defense is to scale out the affected component.

      ```bash
      # Scale API pods
      kubectl scale deployment/eval-engine-api --replicas=5

      # Scale worker pods
      kubectl scale deployment/eval-engine-worker --replicas=10
      ```

  2.  **Investigate Bottlenecks:** While scaled out, investigate the root cause. Check for:
      - Slow database queries (`pg_stat_activity`).
      - Inefficient code paths (profiling).
      - Upstream service latency.
  3.  **Optimize and Scale In:** Once the bottleneck is identified and resolved, scale the application back to normal levels.
