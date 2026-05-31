# Campus Guide Kiosk

A Flask-based interactive kiosk application that provides campus information and directions using AI-powered semantic search and Google's Gemini API.

## Features

- AI-Powered Search: Uses Sentence Transformers for semantic understanding
- Gemini Integration: AI-generated responses to campus queries
- Firebase Backend: Real-time FAQ database
- Unity WebGL Frontend: Interactive 3D campus map
- Vectorized Search: Fast in-memory embedding-based retrieval
- LRU Cache: Optimized query caching for repeated questions
- API Key Rotation: Automatic Gemini API key fallback on quota limits

## Project Structure

```
.
├── app.py                  # Main Flask application
├── config.py               # Configuration management
├── error_handlers.py       # Error handling & validation
├── logging_config.py       # Logging setup
├── index.py                # Admin tool for managing FAQ data
├── requirements.txt        # Python dependencies
├── pytest.ini              # Test configuration
├── .env                    # Environment variables (create from .env.example)
├── firebase/
│   └── campus_guide_kiosk.json  # Firebase credentials
├── static/
│   ├── script.js           # Frontend JavaScript
│   ├── style.css           # Frontend styling
│   └── unity/              # Unity WebGL build files
├── templates/
│   └── index.html          # Main HTML template
├── tests/                  # Automated test suite
├── data/                   # Data storage directory
├── logs/                   # Application logs
├── Dockerfile              # Docker container setup
├── docker-compose.yml      # Docker composition for deployment
└── venv/                   # Virtual environment (ignored in git)
```

## Setup & Installation

### Prerequisites
- Python 3.8+
- pip or conda
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/CampusGuideKiosk.git
cd CampusGuideKiosk
```

### 2. Create Virtual Environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```

**Required environment variables:**
- `FIREBASE_API_KEY`: Firebase project API key
- `FIREBASE_PROJECT_ID`: Firebase project ID
- `FIREBASE_APP_ID`: Firebase app ID
- `API_KEY_1`: Google Gemini API key (add more as API_KEY_2, API_KEY_3, etc.)
- `firebase/campus_guide_kiosk.json`: Firebase service account credentials file

### 5. Run the Application
```bash
python app.py
```

The app will start at `http://localhost:5000`

## API Endpoints

### `/api/v1/ask` (POST)
Ask the kiosk a question about campus facilities or procedures.

**Request:**
```json
{
  "query": "Where is the registrar?"
}
```

**Response (Success):**
```json
{
  "status": "success",
  "message": "Query processed successfully",
  "data": {
    "response": "The registrar is located in Building A, Room 101...",
    "match_score": "0.87",
    "suggested_questions": ["What are the registrar hours?", "How do I enroll?"]
  }
}
```

**Response (Low Confidence):**
When match_score < 0.70, suggested questions are provided:
```json
{
  "status": "success",
  "message": "Query processed successfully",
  "data": {
    "response": "Possible answer...",
    "match_score": "0.65",
    "suggested_questions": ["Related Question 1", "Related Question 2"]
  }
}
```

### `/api/v1/health` (GET)
Health check endpoint.

**Response:**
```json
{
  "status": "success",
  "message": "System is healthy",
  "data": {
    "status": "healthy",
    "faq_count": 42,
    "model_loaded": true,
    "db_connected": true,
    "api_keys_loaded": 1
  }
}
```

### `/api/v1/reload` (POST)
Reload FAQ data from Firebase (admin-only endpoint, protected by secret).

## Managing FAQ Data

Use `index.py` to manage campus information:

```bash
python index.py
```

This tool allows you to:
- Add new FAQs with AI-generated follow-up questions
- Edit existing entries
- Delete outdated information
- View all FAQs

All data is stored in the Firebase `faqs` collection.

## Configuration & Tuning

Edit these constants in `app.py` to adjust search behavior:

```python
RESULT_MIN_SCORE = 0.35      # Minimum score for results
ANSWER_MIN_SCORE = 0.45      # Minimum score for AI response
KEYWORD_BOOST = 0.12         # Keyword overlap scoring
TOP_K = 3                     # Number of results to return
```

## Deployment

### Local Development
```bash
python app.py
```

### Using Gunicorn (Production)
```bash
gunicorn --workers 4 --bind 0.0.0.0:5000 --timeout 120 app:app
```

### Using Docker (Recommended)
The project includes a multi-stage Dockerfile optimized for production:

```bash
# Build and run with Docker Compose
docker-compose up -d

# Or build manually
docker build -t campus-guide-kiosk .
docker run -p 5000:5000 --env-file .env campus-guide-kiosk
```

Docker Compose handles:
- Container orchestration
- Environment variables from `.env`
- Volume mapping for Firebase credentials and logs
- Health checks
- Automatic restart policy

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment instructions.

## Troubleshooting

### Issue: "Embedding Model failed to load"
- The model downloads automatically on first run; ensure stable internet connection
- Model is cached in `~/.cache/huggingface/`

### Issue: "Firebase connection failed"
- Verify `firebase/campus_guide_kiosk.json` exists and is valid
- Check Firebase credentials in `.env`

### Issue: "API key exhausted"
- Add more Gemini API keys as `API_KEY_2`, `API_KEY_3`, etc. in `.env`
- Keys are rotated automatically on quota limits

## Architecture Notes

- **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional vectors)
- **Search Strategy**: Vectorized cosine similarity with keyword boosting
- **Caching**: LRU cache with 128-entry limit for repeated queries
- **API Rotation**: Exponential backoff for API quota management

## Dependencies

See [requirements.txt](requirements.txt) for full list. Key packages:
- **Flask** - Web framework
- **google-genai** - Gemini API (Google's latest Generative AI library)
- **firebase-admin** - Firebase integration
- **sentence-transformers** - Semantic embeddings
- **nltk** - Natural language processing
- **torch** - Deep learning backend

## License

[Add your license here]

## Documentation

For more detailed information, see:
- [API Documentation](API.md) - Complete API reference
- [Security Guidelines](SECURITY.md) - Security best practices and configurations
- [Deployment Guide](DEPLOYMENT.md) - Detailed deployment instructions
- [Contributing Guidelines](CONTRIBUTING.md) - How to contribute to this project

## Testing

Run the automated test suite:
```bash
pytest
```

Tests include:
- Unit tests for error handlers and validation
- Integration tests for API routes
- Security tests for input validation

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Support

For issues or questions, please open a GitHub issue.

---

**Last Updated**: May 31, 2026  
**Version**: 1.1.0  
**Status**: Production-Ready
