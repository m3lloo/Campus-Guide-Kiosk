# Campus Guide Kiosk - API Documentation

## Base URL

```
http://localhost:5000
```

## Authentication

The API uses optional authentication via headers for admin endpoints:
- `X-Reload-Secret`: Required for `/api/v1/reload` endpoint in production

## Error Responses

All error responses follow this format:

```json
{
  "status": "error",
  "error": "ErrorType",
  "message": "Detailed error message"
}
```

### Common HTTP Status Codes

- `200` - Success
- `400` - Bad Request (validation error)
- `401` - Unauthorized (invalid credentials)
- `404` - Not Found
- `429` - Too Many Requests (rate limited)
- `500` - Internal Server Error

---

## Endpoints

### 1. Ask Question

**Endpoint:** `POST /api/v1/ask`

**Description:** Submit a question to get an AI-powered response with semantic search.

**Rate Limit:** 60 requests per minute, 1000 per hour

**Request Body:**

```json
{
  "query": "Where is the Registrar's Office?"
}
```

**Query Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| query | string | Yes | User question (max 500 characters) |

**Response (Success):**

```json
{
  "status": "success",
  "message": "Query processed successfully",
  "data": {
    "response": "The Registrar's Office is located on the first floor of the main building...",
    "match_score": "0.87",
    "suggested_questions": [
      "What are the office hours?",
      "How do I enroll?",
      "What documents do I need?"
    ]
  }
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| response | string | AI-generated answer to the question |
| match_score | string | Confidence score (0.0 - 1.0) |
| suggested_questions | array | Recommended follow-up questions |

**Error Responses:**

```json
{
  "status": "error",
  "error": "ValidationError",
  "message": "Query must be a non-empty string"
}
```

```json
{
  "status": "error",
  "error": "ValidationError",
  "message": "Query too long. Maximum 500 characters allowed."
}
```

**Example Request:**

```bash
curl -X POST http://localhost:5000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I enroll?"}'
```

**Example Response:**

```json
{
  "status": "success",
  "message": "Query processed successfully",
  "data": {
    "response": "To enroll, please visit the Registrar's Office on the 1st floor with your acceptance letter and identification.",
    "match_score": "0.92",
    "suggested_questions": [
      "What documents do I need?",
      "Where is the Registrar?"
    ]
  }
}
```

---

### 2. Health Check

**Endpoint:** `GET /api/v1/health`

**Description:** Get system health status and component information.

**Rate Limit:** None (not rate-limited)

**Response (Success):**

```json
{
  "status": "success",
  "message": "System is healthy",
  "data": {
    "status": "healthy",
    "environment": "production",
    "faq_count": 42,
    "embedding_matrix_shape": [42, 384],
    "model_loaded": true,
    "model_name": "all-MiniLM-L6-v2",
    "firebase_status": "connected",
    "api_keys_configured": 2,
    "cache_info": {
      "hits": 156,
      "misses": 42,
      "currsize": 38
    },
    "rate_limiting_enabled": true,
    "log_level": "INFO"
  }
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| status | string | Overall health status |
| environment | string | Environment name (development/production) |
| faq_count | integer | Number of FAQs in memory |
| model_loaded | boolean | Embedding model status |
| firebase_status | string | Firebase connection status |
| api_keys_configured | integer | Number of Gemini API keys |
| cache_info | object | LRU cache statistics |
| rate_limiting_enabled | boolean | Rate limiting status |

**Example Request:**

```bash
curl http://localhost:5000/api/v1/health
```

---

### 3. Reload FAQ Store

**Endpoint:** `POST /api/v1/reload`

**Description:** Reload FAQ data from Firebase without restarting the application. **Admin-only endpoint.**

**Authentication:** Requires `X-Reload-Secret` header in production

**Request Headers:**

```
X-Reload-Secret: your-reload-secret
```

**Response (Success):**

```json
{
  "status": "success",
  "message": "FAQ store reloaded successfully",
  "data": {
    "faq_count": 42,
    "embedding_matrix_shape": [42, 384]
  }
}
```

**Error Response (Unauthorized):**

```json
{
  "status": "error",
  "error": "Unauthorized",
  "message": "Invalid credentials"
}
```

**Example Request:**

```bash
curl -X POST http://localhost:5000/api/v1/reload \
  -H "X-Reload-Secret: your-secret-key"
```

---

## Query Validation & Security

### Input Sanitization

All user queries are automatically sanitized to prevent:
- SQL injection attempts
- JavaScript/HTML injection
- XSS attacks
- Other security threats

### Query Limits

- **Minimum length:** 1 character
- **Maximum length:** 500 characters (configurable via `MAX_QUERY_LENGTH`)

### Rate Limiting

The `/api/v1/ask` endpoint is rate-limited to prevent abuse:

- **Per minute:** 60 requests (configurable via `RATE_LIMIT_RPM`)
- **Per hour:** 1000 requests (configurable via `RATE_LIMIT_RPH`)

**Rate Limit Response (HTTP 429):**

```json
{
  "status": "error",
  "error": "RateLimitExceeded",
  "message": "Rate limit exceeded. Please try again later."
}
```

---

## Search Algorithm

The system uses a two-stage search approach:

### Stage 1: Semantic Search
- Query is encoded using Sentence Transformers
- Cosine similarity computed against FAQ embeddings
- Results filtered by `ANSWER_MIN_SCORE` (default: 0.5)

### Stage 2: Keyword Boosting
- Keywords extracted from query
- Matched against FAQ keywords
- Scores boosted for additional relevance

### Match Score Interpretation

| Score | Interpretation |
|-------|-----------------|
| 0.0-0.4 | Poor match - generic response |
| 0.4-0.7 | Good match - reliable answer |
| 0.7-0.9 | Excellent match - highly relevant |
| 0.9-1.0 | Perfect match - direct answer |

---

## Response Caching

Identical queries are cached using LRU (Least Recently Used) caching:

- **Cache size:** 128 unique queries (configurable via `CACHE_MAX_SIZE`)
- **Benefits:** Faster responses, reduced API calls
- **Invalidation:** Automatically cleared on `/api/v1/reload`

**Cache Info from Health Check:**

```json
"cache_info": {
  "hits": 156,        // Number of cache hits
  "misses": 42,       // Number of cache misses
  "currsize": 38      // Current cached items
}
```

---

## Environment Variables

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | development | Environment name |
| `LOG_LEVEL` | INFO | Logging level |
| `FLASK_ENV` | development | Flask environment |
| `FLASK_HOST` | 0.0.0.0 | Flask host |
| `FLASK_PORT` | 5000 | Flask port |

### Search & Ranking

| Variable | Default | Description |
|----------|---------|-------------|
| `ANSWER_MIN_SCORE` | 0.5 | Minimum confidence for AI answer |
| `CACHE_MAX_SIZE` | 128 | LRU cache size |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_ENABLED` | True | Enable rate limiting |
| `RATE_LIMIT_RPM` | 60 | Requests per minute |
| `RATE_LIMIT_RPH` | 1000 | Requests per hour |

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | * | Allowed CORS origins |
| `MAX_QUERY_LENGTH` | 500 | Max query length |
| `SANITIZE_INPUT` | True | Enable input sanitization |

---

## Examples

### JavaScript/Fetch

```javascript
async function askQuestion(query) {
  const response = await fetch('/api/v1/ask', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ query: query })
  });
  
  const data = await response.json();
  
  if (data.status === 'success') {
    console.log(data.data.response);
    console.log(data.data.suggested_questions);
  } else {
    console.error(data.message);
  }
}

askQuestion('Where is the library?');
```

### Python

```python
import requests

url = 'http://localhost:5000/api/v1/ask'
data = {'query': 'Where is the library?'}

response = requests.post(url, json=data)
result = response.json()

if result['status'] == 'success':
    print(result['data']['response'])
    print(result['data']['suggested_questions'])
else:
    print(f"Error: {result['message']}")
```

### cURL

```bash
curl -X POST http://localhost:5000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Where is the library?"}'
```

---

## Troubleshooting

### 400 Bad Request

**Problem:** Invalid JSON or missing required field

**Solution:**
- Ensure `Content-Type: application/json` header
- Verify `query` field is present and non-empty
- Check query doesn't exceed 500 characters

### 429 Too Many Requests

**Problem:** Rate limit exceeded

**Solution:**
- Wait before making additional requests
- Consider batch processing or caching
- Contact admin to increase limits if needed

### 500 Internal Server Error

**Problem:** Server-side error

**Solution:**
- Check server logs: `docker-compose logs web`
- Verify Firebase connection
- Ensure Gemini API keys are valid
- Restart application: `docker-compose restart web`

---

## API Versioning

Current API version: **v1**

Future versions will be available at:
- `/api/v2/ask`
- `/api/v2/health`
- etc.

---

## Support

For API issues:
1. Check this documentation
2. Review [Health Check](#health-check) status
3. Check application logs
4. Open a GitHub issue with:
   - Request body
   - Response received
   - Error logs
   - Environment details
