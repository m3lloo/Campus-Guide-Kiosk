"""
Campus Guide Kiosk — Flask Backend (Refactored)
================================================
Key improvements over original:
  - Single flat 'faqs' collection (aligned with admin_tool.py)
  - Embeddings pre-loaded into RAM as a numpy matrix at startup
  - One vectorized cos_sim call instead of a per-document loop
  - LRU cache for repeated queries (avoids redundant search + AI calls)
  - Real API key rotation with exponential backoff on ResourceExhausted
  - Embedding context built identically to admin_tool.py (same vector space)
  - Clean None-safety throughout
"""

import warnings
import os
import time
import traceback
import numpy as np
from functools import lru_cache
from flask import Flask, jsonify, request, render_template
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, InternalServerError
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, util
import firebase_admin
from firebase_admin import credentials, firestore
import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer

warnings.filterwarnings("ignore")
load_dotenv()

app = Flask(__name__)

# ---------------------------------------------------------------------------
# NLTK Setup
# ---------------------------------------------------------------------------
print("⏳ Checking NLTK resources...")
for resource, path in [('corpora/stopwords', 'stopwords'), ('tokenizers/punkt', 'punkt')]:
    try:
        nltk.data.find(resource)
    except LookupError:
        nltk.download(path, quiet=True)
print("✅ NLTK ready.")

stemmer = PorterStemmer()
STOP_WORDS = set(stopwords.words('english'))

# ---------------------------------------------------------------------------
# Embedding Model
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = None
print("⏳ Loading Embedding Model...")
try:
    EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    print("✅ Embedding Model loaded.")
except Exception as e:
    print(f"❌ FATAL: Error loading Embedding Model: {e}")

# ---------------------------------------------------------------------------
# Firebase Setup
# ---------------------------------------------------------------------------
SERVICE_ACCOUNT_KEY = "firebase/campus_guide_kiosk.json"
FAQ_COLLECTION = 'faqs'           # Aligned with admin_tool.py
EVENTS_COLLECTION = 'events'

db = None
try:
    if not firebase_admin._apps:
        if os.path.exists(SERVICE_ACCOUNT_KEY):
            cred = credentials.Certificate(SERVICE_ACCOUNT_KEY)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase Admin connected.")
        else:
            print(f"⚠️  WARNING: Firebase credentials file not found at {SERVICE_ACCOUNT_KEY}")
            print("   The app will start but Firebase queries will fail.")
    db = firestore.client()
except Exception as e:
    print(f"⚠️  Firebase connection failed: {e}")
    print("   The app will start but API calls will return errors.")

# ---------------------------------------------------------------------------
# In-Memory Embedding Store
# Pre-loaded at startup so queries never hit Firestore for embeddings.
# Layout:
#   FAQ_STORE = [
#     { 'id': str, 'answer': str, 'category': str, 'keywords': set,
#       'generated_questions': list },
#     ...
#   ]
#   EMBEDDING_MATRIX = np.ndarray shape (N, 384)  float32
# ---------------------------------------------------------------------------
FAQ_STORE = []
EMBEDDING_MATRIX = None   # numpy matrix, rows = FAQ_STORE indices


def build_embedding_context(answer: str, questions: list) -> str:
    """
    Builds the string that was encoded at write-time in admin_tool.py.
    Must be identical to admin_tool.prepare_fact_data() to keep the
    vector space consistent.
    """
    q_str = ' '.join(questions) if questions else ''
    return f"Answer: {answer}. Possible Questions: {q_str}"


def load_faq_store():
    """
    Fetches all FAQ documents from Firestore once at startup and
    builds an in-memory numpy matrix of their embeddings.
    Re-call this whenever data is known to have changed (e.g. after
    a webhook from the admin tool, or on a scheduled interval).
    """
    global FAQ_STORE, EMBEDDING_MATRIX

    if db is None or EMBEDDING_MODEL is None:
        print("⚠️  Skipping FAQ store load (db or model unavailable).")
        return

    print("⏳ Loading FAQ store into memory...")
    docs = list(db.collection(FAQ_COLLECTION).stream())

    if not docs:
        print("⚠️  No FAQ documents found.")
        FAQ_STORE = []
        EMBEDDING_MATRIX = None
        return

    store = []
    vectors = []

    for doc in docs:
        data = doc.to_dict()
        emb = data.get('embedding')
        if emb is None:
            # Document has no embedding — skip (shouldn't happen with admin_tool)
            print(f"⚠️  FAQ {doc.id} has no embedding, skipping.")
            continue

        store.append({
            'id': doc.id,
            'answer': data.get('answer', ''),
            'category': data.get('category', 'general'),
            'keywords': set(data.get('keywords', [])),
            'generated_questions': data.get('generated_questions', []),
        })
        vectors.append(np.array(emb, dtype=np.float32))

    if not vectors:
        FAQ_STORE = []
        EMBEDDING_MATRIX = None
        print("⚠️  No embeddable FAQs found.")
        return

    FAQ_STORE = store
    EMBEDDING_MATRIX = np.vstack(vectors)   # shape: (N, 384)
    print(f"✅ FAQ store loaded: {len(FAQ_STORE)} documents.")


# Load at startup
load_faq_store()

# ---------------------------------------------------------------------------
# Gemini API — key rotation with exponential backoff
# ---------------------------------------------------------------------------
_RAW_KEYS = [
    os.environ.get(f"API_KEY_{i}") for i in range(1, 6)
]
API_KEYS = [k for k in _RAW_KEYS if k]

if not API_KEYS:
    print("⚠️  No Gemini API keys found. AI responses will be disabled.")

SYSTEM_INSTRUCTION = (
    "You are a helpful Campus Guide Kiosk assistant. "
    "Answer the user's question based ONLY on the provided context. "
    "1. If the context is about a location, give the location and hours clearly. "
    "2. If the context is a specific process (e.g. Enrollment), list requirements concisely. "
    "3. Be polite but brief (max 50 words). "
    "4. Do not mention 'database', 'vectors', or 'embedding'."
)

_current_key_index = 0


def get_gemini_response(prompt: str) -> str:
    """
    Calls Gemini with automatic key rotation on ResourceExhausted.
    Tries each key once with a short backoff before giving up.
    """
    global _current_key_index

    if not API_KEYS:
        return "AI service is currently offline."

    attempts = len(API_KEYS)
    for attempt in range(attempts):
        key_index = (_current_key_index + attempt) % len(API_KEYS)
        try:
            genai.configure(api_key=API_KEYS[key_index])
            model = genai.GenerativeModel(
                'gemini-2.5-flash',
                system_instruction=SYSTEM_INSTRUCTION
            )
            response = model.generate_content(prompt)
            _current_key_index = key_index   # remember the working key
            return response.text.strip()

        except ResourceExhausted:
            print(f"⚠️  API key [{key_index}] exhausted, rotating...")
            time.sleep(0.5 * (attempt + 1))   # 0.5s, 1.0s, 1.5s ...
            continue

        except InternalServerError as e:
            print(f"⚠️  Gemini InternalServerError: {e}")
            return "I'm having trouble connecting right now. Please try again."

        except Exception as e:
            print(f"❌ Gemini Error: {e}")
            return "I apologize, I am having trouble connecting to the AI right now."

    # All keys exhausted
    _current_key_index = (_current_key_index + 1) % len(API_KEYS)
    return "All AI service slots are currently busy. Please try again shortly."

# ---------------------------------------------------------------------------
# Keyword helpers
# ---------------------------------------------------------------------------


def get_query_keywords(text: str) -> set:
    if not text:
        return set()
    tokens = nltk.word_tokenize(text.lower())
    return {stemmer.stem(w) for w in tokens if w.isalnum() and w not in STOP_WORDS}

# ---------------------------------------------------------------------------
# Core vectorized search
# ---------------------------------------------------------------------------


# Score thresholds — easier to tune in one place
RESULT_MIN_SCORE = 0.35      # minimum to appear in results
ANSWER_MIN_SCORE = 0.45      # minimum to give an AI answer
KEYWORD_BOOST = 0.12      # added per keyword overlap hit
TOP_K = 3         # number of candidates to return


def search_faqs(user_query: str) -> list:
    """
    Vectorized semantic search over the in-memory FAQ store.
    Returns up to TOP_K results sorted by descending score.
    Each result: { answer, category, generated_questions, score }
    """
    if EMBEDDING_MATRIX is None or not FAQ_STORE:
        return []

    # Encode the raw query (same model as admin_tool, no context wrapper needed
    # for the query side — asymmetric retrieval is fine with MiniLM)
    query_vec = EMBEDDING_MODEL.encode(user_query, convert_to_tensor=False)
    query_vec = np.array(query_vec, dtype=np.float32)

    # Single vectorized cosine similarity  (N,) in one call
    norms = np.linalg.norm(EMBEDDING_MATRIX, axis=1) * \
        np.linalg.norm(query_vec)
    norms = np.where(norms == 0, 1e-9, norms)
    scores = EMBEDDING_MATRIX.dot(query_vec) / norms   # shape: (N,)

    # Keyword boost — vectorized via list comprehension (fast enough for <10k docs)
    query_kw = get_query_keywords(user_query)
    boosts = np.array([
        KEYWORD_BOOST * min(len(query_kw & faq['keywords']), 3)
        for faq in FAQ_STORE
    ], dtype=np.float32)
    scores = scores + boosts

    # Filter and sort
    above_threshold = np.where(scores >= RESULT_MIN_SCORE)[0]
    if len(above_threshold) == 0:
        return []

    top_indices = above_threshold[np.argsort(
        scores[above_threshold])[::-1][:TOP_K]]

    results = []
    for idx in top_indices:
        faq = FAQ_STORE[idx]
        results.append({
            'answer':               faq['answer'],
            'category':             faq['category'],
            'generated_questions':  faq['generated_questions'],
            'score':                float(scores[idx]),
        })
    return results

# ---------------------------------------------------------------------------
# LRU cache — skip search + AI for repeated identical queries
# Caches up to 128 unique queries in memory.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=128)
def cached_search_and_respond(user_query: str):
    """
    Cached wrapper around search + Gemini call.
    Returns (response_text, suggested_questions, match_score).
    lru_cache requires all args to be hashable — str qualifies.
    """
    matches = search_faqs(user_query)

    if not matches or matches[0]['score'] < ANSWER_MIN_SCORE:
        return (
            "I couldn't find that specific information. "
            "Try asking about a department like 'Registrar', 'Clinic', or 'Library'.",
            ["Where is the Registrar?", "Where is the Clinic?",
                "Enrollment Requirements"],
            0.0,
        )

    best = matches[0]
    prompt = (
        f"User Question: {user_query}\n"
        f"Database Fact: {best['answer']}\n"
        f"Answer the user politely and concisely."
    )
    response_text = get_gemini_response(prompt)

    # Suggested follow-up questions come from the matched FAQ's own
    # generated_questions field (written by admin_tool at ingest time)
    suggestions = best['generated_questions'][:4]

    # Fallback: surface other top matches as navigation hints
    if not suggestions and len(matches) > 1:
        suggestions = [m['answer'][:60] + '...' for m in matches[1:]]

    return response_text, suggestions, best['score']

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route('/')
def index():
    return render_template(
        'index.html',
        fb_api_key=os.getenv("FIREBASE_API_KEY"),
        fb_project_id=os.getenv("FIREBASE_PROJECT_ID"),
        fb_app_id=os.getenv("FIREBASE_APP_ID"),
    )


@app.route('/api/v1/ask', methods=['POST'])
def handle_ask_query():
    try:
        data = request.get_json(silent=True)
        if not data or 'query' not in data:
            return jsonify({"response": "Invalid request.", "success": False}), 400

        user_query = data['query'].strip()
        if not user_query:
            return jsonify({"response": "Empty query.", "success": False}), 400

        print(f"\n🗣️  User: {user_query}")

        response_text, suggested_questions, match_score = cached_search_and_respond(
            user_query)

        print(
            f"✅ Score: {match_score:.2f} | Response: {response_text[:60]}...")

        return jsonify({
            "response":             response_text,
            "success":              True,
            "match_score":          f"{match_score:.2f}",
            "suggested_questions":  suggested_questions,
        })

    except Exception:
        traceback.print_exc()
        return jsonify({"response": "System error. Please try again.", "success": False}), 500


@app.route('/api/v1/reload', methods=['POST'])
def reload_faq_store():
    """
    Admin endpoint — call this after adding/editing FAQs via admin_tool.py
    to refresh the in-memory store without restarting Flask.
    Protect this with a secret header in production.
    """
    secret = request.headers.get('X-Reload-Secret', '')
    expected = os.getenv('RELOAD_SECRET', '')
    if expected and secret != expected:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    # Invalidate LRU cache so stale answers aren't served
    cached_search_and_respond.cache_clear()
    load_faq_store()
    return jsonify({"success": True, "faq_count": len(FAQ_STORE)})


@app.route('/api/v1/health', methods=['GET'])
def health_check():
    return jsonify({
        "status":          "ok",
        "faq_count":       len(FAQ_STORE),
        "model_loaded":    EMBEDDING_MODEL is not None,
        "db_connected":    db is not None,
        "api_keys_loaded": len(API_KEYS),
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    
    print("\n" + "="*60)
    print("🚀 Campus Guide Kiosk Starting Up")
    print("="*60)
    print(f"Port: {port}")
    print(f"Debug Mode: {debug_mode}")
    print(f"Flask Env: {os.environ.get('FLASK_ENV', 'development')}")
    print(f"Embedding Model Loaded: {EMBEDDING_MODEL is not None}")
    print(f"Firebase Connected: {db is not None}")
    print(f"API Keys Configured: {len(API_KEYS)} key(s)")
    print(f"FAQs in Memory: {len(FAQ_STORE)}")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode, use_reloader=False)
