# Campus Guide Kiosk

A Flask-based interactive kiosk application that provides campus information and directions using AI-powered semantic search and Google's Gemini API.

## Features

- 🤖 **AI-Powered Search**: Uses Sentence Transformers for semantic understanding
- 🧠 **Gemini Integration**: AI-generated responses to campus queries
- 🔥 **Firebase Backend**: Real-time FAQ database
- 🌐 **Unity WebGL Frontend**: Interactive 3D campus map
- 💾 **Vectorized Search**: Fast in-memory embedding-based retrieval
- 🔄 **LRU Cache**: Optimized query caching for repeated questions
- 🔀 **API Key Rotation**: Automatic Gemini API key fallback on quota limits

## Project Structure

```
.
├── app.py                  # Main Flask application
├── index.py                # Admin tool for managing FAQ data
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (create from .env.example)
├── firebase/
│   └── campus_guide_kiosk.json  # Firebase credentials
├── routes/
│   └── v1/                 # API v1 endpoints
├── static/
│   ├── script.js           # Frontend JavaScript
│   ├── style.css           # Frontend styling
│   └── unity/              # Unity WebGL build files
├── templates/
│   └── index.html          # Main HTML template
├── data/                   # Data storage directory
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

**Response:**
```json
{
  "response": "The registrar is located in Building A, Room 101...",
  "success": true,
  "match_score": "0.87",
  "suggested_questions": ["What are the registrar hours?", "How do I enroll?"]
}
```

### `/api/v1/health` (GET)
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "faq_count": 42,
  "model_loaded": true,
  "db_connected": true,
  "api_keys_loaded": 1
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

### Using Gunicorn (Production)
```bash
gunicorn --workers 4 --bind 0.0.0.0:5000 app:app
```

### Using Docker (Optional)
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "app:app"]
```

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
- **google-generativeai** - Gemini API
- **firebase-admin** - Firebase integration
- **sentence-transformers** - Semantic embeddings
- **nltk** - Natural language processing
- **torch** - Deep learning backend

## License

[Add your license here]

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss.

## Support

For issues or questions, please open a GitHub issue.

---

**Last Updated**: May 2026  
**Version**: 1.0.0
