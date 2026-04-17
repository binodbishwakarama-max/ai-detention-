# CI/CD Pipeline Guide

This document provides an overview of the Continuous Integration and Continuous Deployment (CI/CD) pipeline for the AI Evaluation Engine, which is managed using GitHub Actions.

## Overview

Our CI/CD pipeline is designed to automate the process of testing, building, and deploying the application, ensuring that we can deliver new features and bug fixes rapidly and reliably. The pipeline is defined in two separate workflow files located in the `.github/workflows` directory:

- `pr-validation.yml`: Handles the validation of pull requests.
- `deploy.yml`: Manages the deployment of the application to production.

## Pull Request Validation (`pr-validation.yml`)

This workflow runs on every pull request targeting the `main` branch and is designed to ensure that all new code meets our quality standards before it is merged.

### Stages

1.  **Checkout Code:** The workflow begins by checking out the code from the pull request.
2.  **Set up Python:** It sets up the specified Python version and caches dependencies to speed up subsequent runs.
3.  **Install Dependencies:** It installs all the necessary Python packages required for linting and testing.
4.  **Lint with Ruff:** It runs `ruff` to check for code style violations and formatting issues.
5.  **Run PyTest:** It executes our test suite using `pytest`, including running tests in parallel (`-n 4`) and generating a code coverage report. The workflow will fail if code coverage is below 95%.
6.  **Upload Coverage to Codecov:** The coverage report is uploaded to Codecov to track our code coverage over time.

A pull request cannot be merged unless all these checks pass.

## Deployment (`deploy.yml`)

This workflow is triggered on every push to the `main` branch and is responsible for building and deploying the application to our Kubernetes cluster.

### Jobs

1.  **Build and Push (`build-and-push`):**
    - **Login to Registry:** It logs in to the GitHub Container Registry.
    - **Build and Push Image:** It builds the Docker image for the API and pushes it to the registry, tagged with the commit SHA.

2.  **Deploy to Kubernetes (`deploy-to-k8s`):**
    - This job runs after the `build-and-push` job has completed successfully.
    - **Note:** The current implementation is a placeholder and needs to be configured for your specific cloud provider and Kubernetes setup (e.g., using `aws-actions/amazon-eks-run-kubectl` for AWS EKS or a similar action for other providers).
    - The intended logic is to update the Kubernetes deployment with the new image tag and monitor the rollout status.

## Secrets and Configuration

The pipeline requires the following secrets to be configured in your GitHub repository settings:

- `CODECOV_TOKEN`: Required for uploading coverage reports to Codecov.
- `GITHUB_TOKEN`: Automatically provided by GitHub Actions.

For the deployment job, you will need to configure secrets for authenticating with your cloud provider and Kubernetes cluster.
