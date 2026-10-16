# Security Guidelines

## Overview

This document outlines security best practices and guidelines for Campus Guide Kiosk.

---

## Security Considerations

### 1. Input Validation & Sanitization

**✅ Implemented:**
- All user queries are validated for length (max 500 chars)
- SQL injection prevention
- XSS attack prevention
- HTML/JavaScript injection prevention

**Usage:**
```python
from error_handlers import sanitize_input

query = sanitize_input(user_input, max_length=500)
```

### 2. API Key Management

**Best Practices:**

- ✅ Never commit `.env` file to version control
- ✅ Use `.env.example` for templates
- ✅ Rotate API keys regularly
- ✅ Implement key fallback/rotation in Gemini client
- ✅ Use environment variables for all secrets

**Example .env:**
```env
GEMINI_API_KEYS=key1,key2,key3
RELOAD_SECRET=your-strong-random-secret
```

**Key Rotation:**
```bash
# Update GEMINI_API_KEYS in .env
# Reload FAQ store to apply changes
curl -X POST http://localhost:5000/api/v1/reload \
  -H "X-Reload-Secret: your-secret"
```

### 3. Firebase Security

**Configuration:**

- ✅ Service account key stored securely
- ✅ Firestore security rules enforced
- ✅ Collection-level access control

**Firestore Security Rules Example:**
```firebase
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Only allow public read access to FAQs
    match /faqs/{document=**} {
      allow read: if true;
      allow write: if false;
    }
    
    // Restrict query logs to authenticated admin
    match /query_logs/{document=**} {
      allow read, write: if request.auth != null;
    }
    
    // Allow events read by anyone
    match /events/{document=**} {
      allow read: if true;
      allow write: if false;
    }
  }
}
```

### 4. Authentication & Authorization

**Admin Endpoints:**

All admin endpoints require authentication via `X-Reload-Secret` header:

```bash
# Reload FAQ store (requires secret)
curl -X POST http://localhost:5000/api/v1/reload \
  -H "X-Reload-Secret: $RELOAD_SECRET"

# Get analytics (requires secret)
curl "http://localhost:5000/api/v1/analytics?secret=$RELOAD_SECRET"
```

**Set strong secret:**
```bash
# Generate random secret
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 5. Rate Limiting

**✅ Implemented:**
- Per-minute limit: 60 requests (configurable)
- Per-hour limit: 1000 requests (configurable)
- IP-based rate limiting

**Configuration:**
```env
RATE_LIMIT_ENABLED=True
RATE_LIMIT_RPM=60
RATE_LIMIT_RPH=1000
```

**Response (HTTP 429):**
```json
{
  "status": "error",
  "error": "RateLimitExceeded",
  "message": "Rate limit exceeded. Please try again later."
}
```

### 6. CORS Configuration

**Recommended Configuration:**
```env
# Development (allow all)
CORS_ORIGINS=*

# Production (specific origins)
CORS_ORIGINS=https://yourdomain.com,https://map.yourdomain.com

# Docker
CORS_ORIGINS=http://localhost:5000
```

### 7. HTTPS/TLS

**Production Setup with nginx:**

```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;
    
    ssl_certificate /etc/ssl/certs/your_cert.crt;
    ssl_certificate_key /etc/ssl/private/your_key.key;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

### 8. Security Headers

**✅ Implemented by app.py:**
```python
response.headers['X-Content-Type-Options'] = 'nosniff'
response.headers['X-Frame-Options'] = 'SAMEORIGIN'
response.headers['X-XSS-Protection'] = '1; mode=block'
```

**Additional headers (via nginx):**
```
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### 9. Error Handling

**Security:**
- ✅ Never expose sensitive information in error messages
- ✅ Use generic error messages for users
- ✅ Log detailed errors server-side only

**Good:**
```json
{
  "status": "error",
  "message": "Failed to process query. Please try again."
}
```

**Bad (information disclosure):**
```json
{
  "status": "error",
  "message": "Firebase connection failed: Firestore client not initialized"
}
```

### 10. Logging & Monitoring

**✅ Implemented:**
- Structured logging to `logs/app.log`
- Rotating file handler (10MB max per file)
- Error tracking and classification

**Log Examples:**
```
2026-05-31 12:00:00 - campus_guide_kiosk - INFO - 🚀 Campus Guide Kiosk Starting Up
2026-05-31 12:00:05 - campus_guide_kiosk - WARNING - Unauthorized API attempt from 192.168.1.1
2026-05-31 12:00:10 - campus_guide_kiosk - ERROR - [Unauthorized]: Reload attempted with invalid secret
```

**Never log:**
- API keys or tokens
- User passwords
- Personally identifiable information (PII)
- Sensitive database contents

---

## Deployment Security Checklist

- [ ] Set strong `RELOAD_SECRET` (32+ random characters)
- [ ] Change default credentials
- [ ] Enable HTTPS/TLS
- [ ] Configure firewall rules
- [ ] Set restrictive CORS origins
- [ ] Enable rate limiting
- [ ] Configure security headers
- [ ] Set up monitoring and alerting
- [ ] Regular dependency updates
- [ ] Log rotation and archival
- [ ] Database backups
- [ ] Incident response plan

---

## Dependency Management

### Vulnerabilities

**Check for vulnerabilities:**

```bash
# Using pip-audit
pip install pip-audit
pip-audit

# Using safety
pip install safety
safety check
```

**Update dependencies:**

```bash
# Update specific package
pip install --upgrade flask

# Update all
pip install --upgrade -r requirements-dev.txt

# Update requirements.txt
pip freeze   # review the output, then update the pinned versions in requirements.txt by hand
```

### Pinned Versions

✅ All dependencies are pinned to specific versions in `requirements.txt`:

```
Flask==3.0.0
Flask-Limiter==3.5.0
```

**Why:**
- Ensures reproducible builds
- Prevents automatic breaking changes
- Easier security auditing

---

## Incident Response

### Steps if Security Breach Detected

1. **Immediate Actions:**
   - Disconnect affected systems
   - Preserve logs and evidence
   - Notify relevant parties

2. **Investigation:**
   - Review logs for unauthorized access
   - Check for data exfiltration
   - Identify vulnerability

3. **Remediation:**
   - Patch vulnerability
   - Rotate compromised credentials
   - Redeploy application
   - Monitor for re-compromise

4. **Communication:**
   - Notify users if data was accessed
   - Publish security advisory
   - Document lessons learned

---

## Security Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP Cheat Sheets](https://cheatsheetseries.owasp.org/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Python Security](https://python.readthedocs.io/en/latest/library/security_warnings.html)
- [Flask Security](https://flask.palletsprojects.com/en/latest/security/)

---

## Reporting Security Issues

**Do not open public GitHub issues for security vulnerabilities.**

Instead:
1. Email security concerns to: [maintainer-email]
2. Include: Description, affected versions, proof-of-concept
3. Allow time for patch before public disclosure (responsible disclosure)

---

## Version History

| Version | Release Date | Security Updates |
|---------|--------------|------------------|
| 1.0.0   | 2026-05-31   | Initial release  |

---

**Last Updated:** May 31, 2026  
**Maintained By:** Campus Guide Kiosk Team
