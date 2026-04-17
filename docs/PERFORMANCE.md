# Performance and Scalability Guide

This document outlines the strategy for performance testing the AI Evaluation Engine to ensure it meets the demands of enterprise-scale workloads.

## Objectives

- **Identify Bottlenecks:** Proactively find and address performance bottlenecks in the API, database, and worker processes.
- **Establish Baselines:** Define performance baselines for key user flows to track regressions over time.
- **Determine Capacity:** Understand the system's limits and determine the hardware requirements for different levels of user load.
- **Ensure Reliability:** Verify that the system remains stable and reliable under sustained load.

## Tooling

- **Load Generation:** We use [Locust](https://locust.io/), a modern, Python-based load testing framework. The test scenarios are defined in `load_tests/locustfile.py`.
- **Monitoring:** During load tests, we will monitor the system using our [Prometheus and Grafana stack](./MONITORING.md) to get real-time insights into application and system performance.

## Key Scenarios

The `locustfile.py` simulates the following user behaviors:

1.  **Authentication:** Users log in to obtain a JWT access token.
2.  **Evaluation Workflow:**
    - Create an evaluation configuration.
    - Trigger an evaluation run.
    - Poll for the run status and results.
3.  **Dashboard Viewing:** Users list existing evaluation runs and datasets, simulating a dashboard view.

## Key Performance Indicators (KPIs)

We will measure the following KPIs to assess performance:

- **Requests Per Second (RPS):** The number of requests the system can handle per second.
- **Response Time:**
  - Average
  - 95th Percentile (p95)
  - 99th Percentile (p99)
- **Error Rate:** The percentage of requests that result in an error (5xx status codes).
- **CPU and Memory Utilization:** Resource usage of the API, worker, and database pods.

## Running Load Tests

To run the load tests locally against a development environment:

1.  **Start the Application:**
    ```bash
    docker compose up -d
    ```
2.  **Run Locust:**
    ```bash
    locust -f load_tests/locustfile.py --host=http://localhost:8000
    ```
3.  Open your browser to `http://localhost:8089` to start the test and view real-time results.

## Performance Benchmarks and Results

This section will be updated with the results of our performance tests.

| Date       | Test Duration | Concurrent Users | Total RPS | p99 Latency (ms) | Error Rate | Notes                             |
| :--------- | :------------ | :--------------- | :-------- | :--------------- | :--------- | :-------------------------------- |
| YYYY-MM-DD | 10 minutes    | 100              | TBD       | TBD              | TBD        | Initial baseline test.            |
| YYYY-MM-DD | 30 minutes    | 500              | TBD       | TBD              | TBD        | Stress test after optimization X. |

---

_This document is a living document and will be updated as our performance testing strategy evolves and new results become available._
