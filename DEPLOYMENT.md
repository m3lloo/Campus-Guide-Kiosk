# Campus Guide Kiosk - Deployment Guide

## Overview

This guide covers various deployment methods for Campus Guide Kiosk, from local development to production environments.

---

## Table of Contents

1. [Local Development](#local-development)
2. [Docker Deployment](#docker-deployment)
3. [Production Deployment](#production-deployment)
4. [Cloud Deployment](#cloud-deployment)
5. [Monitoring & Troubleshooting](#monitoring--troubleshooting)

---

## Local Development

### Prerequisites

- Python 3.8+
- pip or conda
- Git

### Setup

```bash
# Clone repository
git clone https://github.com/yourusername/CampusGuideKiosk.git
cd CampusGuideKiosk

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your configuration

# Run application
python app.py
```

Visit http://localhost:5000

---

## Docker Deployment

### Prerequisites

- Docker
- Docker Compose

### Quick Start

```bash
# Build and run with docker-compose
docker-compose up -d

# Check logs
docker-compose logs -f web

# Stop
docker-compose down
```

### Docker Build

```bash
# Build image
docker build -t campus-guide-kiosk:latest .

# Run container
docker run -d \
  --name campus_guide_kiosk \
  -p 5000:5000 \
  -v $(pwd)/firebase:/app/firebase:ro \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  campus-guide-kiosk:latest
```

### Health Check

```bash
curl http://localhost:5000/api/v1/health
```

---

## Production Deployment

### AWS EC2 Deployment

#### Step 1: Launch EC2 Instance

```bash
# SSH into instance
ssh -i your-key.pem ec2-user@your-instance-ip

# Update system
sudo yum update -y
sudo yum install -y python3 python3-pip git docker

# Start Docker
sudo systemctl start docker
sudo systemctl enable docker
```

#### Step 2: Clone and Deploy

```bash
# Clone repository
git clone https://github.com/yourusername/CampusGuideKiosk.git
cd CampusGuideKiosk

# Copy Firebase credentials (secure method recommended)
# Use AWS Secrets Manager or parameter store
scp -i your-key.pem firebase/campus_guide_kiosk.json ec2-user@your-instance:/home/ec2-user/CampusGuideKiosk/firebase/

# Create .env from template
cp .env.example .env
# Edit with production values

# Deploy with Docker
sudo docker-compose up -d
```

### Google Cloud Run Deployment

```bash
# Authenticate with GCP
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Build image
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/campus-guide-kiosk

# Deploy to Cloud Run
gcloud run deploy campus-guide-kiosk \
  --image gcr.io/YOUR_PROJECT_ID/campus-guide-kiosk \
  --platform managed \
  --region us-central1 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 120 \
  --set-env-vars ENVIRONMENT=production \
  --no-allow-unauthenticated
```

### Heroku Deployment

```bash
# Login to Heroku
heroku login

# Create app
heroku create your-app-name

# Add buildpack
heroku buildpacks:add heroku/python

# Set environment variables
heroku config:set ENVIRONMENT=production
heroku config:set GEMINI_API_KEYS=your_api_keys
# Add other environment variables...

# Deploy
git push heroku main

# Check logs
heroku logs -t
```

---

## Cloud Deployment

### Kubernetes (K8s) Deployment

Create `k8s-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: campus-guide-kiosk
spec:
  replicas: 2
  selector:
    matchLabels:
      app: campus-guide-kiosk
  template:
    metadata:
      labels:
        app: campus-guide-kiosk
    spec:
      containers:
      - name: web
        image: your-registry/campus-guide-kiosk:latest
        ports:
        - containerPort: 5000
        env:
        - name: ENVIRONMENT
          value: "production"
        - name: FLASK_ENV
          value: "production"
        envFrom:
        - configMapRef:
            name: app-config
        - secretRef:
            name: app-secrets
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /api/v1/health
            port: 5000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/v1/health
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 5

---
apiVersion: v1
kind: Service
metadata:
  name: campus-guide-kiosk-service
spec:
  selector:
    app: campus-guide-kiosk
  ports:
  - protocol: TCP
    port: 80
    targetPort: 5000
  type: LoadBalancer
```

Deploy:

```bash
kubectl apply -f k8s-deployment.yaml
```

---

## Monitoring & Troubleshooting

### Health Check

```bash
# Check application health
curl http://localhost:5000/api/v1/health
```

Expected response:
```json
{
  "status": "success",
  "message": "System is healthy",
  "data": {
    "status": "healthy",
    "environment": "production",
    "faq_count": 42,
    "model_loaded": true,
    "firebase_status": "connected",
    "api_keys_configured": 2,
    "rate_limiting_enabled": true
  }
}
```

### Viewing Logs

#### Docker Logs

```bash
# Real-time logs
docker-compose logs -f web

# Last 100 lines
docker-compose logs --tail 100 web
```

#### Application Logs

```bash
# View application logs
tail -f logs/app.log

# Search for errors
grep ERROR logs/app.log
```

### Performance Tuning

#### Worker Configuration

Edit `docker-compose.yml` or gunicorn command:

```bash
gunicorn --workers=8 --threads=4 --worker-class=gthread --timeout=120 app:app
```

#### Environment Variables for Performance

```env
# Caching
CACHE_MAX_SIZE=256

# Rate limiting
RATE_LIMIT_RPM=120
RATE_LIMIT_RPH=5000

# Log level (DEBUG is slower)
LOG_LEVEL=INFO
```

### Common Issues

#### 1. Firebase Connection Failed

```
ERROR: Firebase connection failed
```

**Solution:**
- Verify `firebase/campus_guide_kiosk.json` exists
- Check Firebase credentials are valid
- Ensure service account has Firestore permissions

#### 2. Embedding Model Not Loading

```
FATAL: Error loading Embedding Model
```

**Solution:**
- Check disk space (models are ~500MB)
- Verify internet connection for first download
- Check `EMBEDDING_MODEL` environment variable

#### 3. Gemini API Key Exhausted

```
API key [0] exhausted, rotating...
```

**Solution:**
- Add more API keys to `GEMINI_API_KEYS`
- Check API usage quota in Google Cloud Console
- Increase rate limiting thresholds if legitimate

#### 4. Out of Memory

```
MemoryError or Container killed
```

**Solution:**
```bash
# Increase memory limit in docker-compose.yml
# Or in Docker:
docker run -m 4g ...

# Or in K8s, increase resource limits
```

### Maintenance

#### Regular Updates

```bash
# Update dependencies
pip install --upgrade -r requirements.txt

# Test
pytest

# Rebuild Docker image
docker-compose build --no-cache
docker-compose up -d
```

#### Database Optimization

```bash
# Add Firestore indexes (in Firebase console)
# For optimal FAQ search:
# - Index: collection:faqs, fields: category (asc), created_at (desc)
```

#### Backup Strategy

```bash
# Backup Firebase data
gsutil -m cp -r gs://your-bucket/firestore-exports ./backups/

# Backup logs
tar -czf logs_backup_$(date +%Y%m%d).tar.gz logs/
```

---

## Security Checklist

- [ ] Set strong `RELOAD_SECRET` in production
- [ ] Use HTTPS in production (nginx reverse proxy)
- [ ] Restrict CORS origins (`CORS_ORIGINS`)
- [ ] Enable rate limiting (`RATE_LIMIT_ENABLED=True`)
- [ ] Rotate Gemini API keys regularly
- [ ] Monitor logs for suspicious activity
- [ ] Update dependencies regularly
- [ ] Use environment variables for all secrets
- [ ] Enable Firebase security rules
- [ ] Setup WAF (Web Application Firewall)

---

## Support

For issues and questions:
1. Check [Health Check](#health-check) status
2. Review logs for error messages
3. Consult troubleshooting section above
4. Open GitHub issue with logs and environment details
