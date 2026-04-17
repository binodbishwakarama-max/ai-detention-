# Kubernetes Deployment Guide

This document provides instructions for deploying the AI Evaluation Engine to a Kubernetes cluster.

## Prerequisites

- A running Kubernetes cluster.
- `kubectl` configured to connect to your cluster.
- A container registry (e.g., Docker Hub, Google Container Registry) to store your Docker images.

## 1. Build and Push Docker Images

Before deploying to Kubernetes, you need to build and push the Docker images for the application components to your container registry.

```bash
# Authenticate with your container registry
docker login <your-registry>

# Build and push the API image
docker build -t <your-registry>/eval-engine-api:latest .
docker push <your-registry>/eval-engine-api:latest

# Build and push the worker image
docker build -t <your-registry>/eval-engine-worker:latest -f Dockerfile.worker .
docker push <your-registry>/eval-engine-worker:latest
```

**Note:** You will need to update the image names in the Kubernetes deployment files to match your registry and image names.

## 2. Configure Secrets

The application requires several secrets to be configured in the Kubernetes cluster. These include database credentials, Redis passwords, and other sensitive information.

Create a `secrets.yaml` file with the following content, replacing the placeholder values with your actual secrets:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: eval-engine-secrets
type: Opaque
data:
  DATABASE_URL: <base64-encoded-database-url>
  REDIS_URL: <base64-encoded-redis-url>
  MINIO_ACCESS_KEY: <base64-encoded-minio-access-key>
  MINIO_SECRET_KEY: <base64-encoded-minio-secret-key>
  JWT_SECRET_KEY: <base64-encoded-jwt-secret-key>
```

To encode your secrets in base64, you can use the following command:

```bash
echo -n "your-secret-value" | base64
```

Apply the secrets to your cluster:

```bash
kubectl apply -f secrets.yaml
```

## 3. Deploy Application Components

The Kubernetes manifests for deploying the application are located in the `infra/k8s` directory.

### Update Image Names

Before applying the manifests, you need to update the image names in the deployment files (`api-deployment.yaml` and `worker-deployments.yaml`) to point to the images you pushed to your container registry.

### Apply Manifests

Apply the manifests in the following order:

```bash
# Deploy the API
kubectl apply -f infra/k8s/api-deployment.yaml

# Deploy the workers
kubectl apply -f infra/k8s/worker-deployments.yaml

# Deploy the Horizontal Pod Autoscaler and Pod Disruption Budget
kubectl apply -f infra/k8s/hpa-and-pdb.yaml
```

## 4. Expose the Application

To expose the application to the internet, you will need to create a Service and an Ingress resource. The specifics of this will depend on your cluster's Ingress controller and networking setup.

Here is an example of a Service and Ingress resource that you can adapt to your needs:

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: eval-engine-api-service
spec:
  selector:
    app: eval-engine-api
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000
---
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: eval-engine-ingress
spec:
  rules:
    - host: eval-engine.your-domain.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: eval-engine-api-service
                port:
                  number: 80
```

Apply these resources to your cluster:

```bash
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml
```

After completing these steps, the AI Evaluation Engine should be running in your Kubernetes cluster and accessible at the domain you configured in the Ingress resource.
