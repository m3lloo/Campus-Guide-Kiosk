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
  - Centralized logging and error handling
  - Input validation and security features
"""

import warnings
import os
import time
import numpy as np
from functools import lru_cache
from flask import Flask, jsonify, request, render_template
import google.genai as genai
from google.genai import errors as genai_errors
from google.api_core.exceptions import ResourceExhausted, InternalServerError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
import firebase_admin
from firebase_admin import credentials, firestore
import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from sentence_transformers import SentenceTransformer

# Import custom modules
from config import config
from logging_config import logger, log_api_call, log_error
from error_handlers import (
    APIError,
    ValidationError,
    validate_api_request,
    validate_query,
    check_admin_secret,
    create_success_response,
    create_error_response,
)

# Memory optimization for low-resource deployments
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

warnings.filterwarnings("ignore")

app = Flask(__name__)

# Trust X-Forwarded-* headers from N reverse proxy hops (e.g. nginx) so that
# rate limiting and request logging see the real client IP instead of the
# proxy's. Disabled (0) by default — only enable via TRUSTED_PROXY_COUNT when
# the app truly sits behind that many trusted proxies, otherwise these
# headers are client-controlled and would let rate limiting be spoofed.
if config.app.trusted_proxy_count > 0:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=config.app.trusted_proxy_count,
        x_proto=config.app.trusted_proxy_count,
        x_host=config.app.trusted_proxy_count,
    )

# CORS — restrict to configured origins (CORS_ORIGINS env var, default "*")
CORS(
    app,
    resources={r"/api/*": {"origins": config.security.cors_origins}},
    supports_credentials=False,
)

# Rate limiting setup
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[
        f"{config.rate_limit.requests_per_minute}/minute",
        f"{config.rate_limit.requests_per_hour}/hour",
    ]
    if config.rate_limit.enabled
    else [],
)

logger.info(
    f"[START] Campus Guide Kiosk starting in {config.environment} mode")

RELOAD_SECRET_CONFIGURED = bool(os.getenv("RELOAD_SECRET", ""))
if not RELOAD_SECRET_CONFIGURED:
    logger.warning(
        "RELOAD_SECRET is not set — /api/v1/reload and /api/v1/analytics "
        "are UNAUTHENTICATED. Set RELOAD_SECRET before deploying to production."
    )

# ---------------------------------------------------------------------------
# NLTK Setup
# ---------------------------------------------------------------------------
logger.info("[LOADING] Checking NLTK resources...")
for resource, path in [
    ("corpora/stopwords", "stopwords"),
    ("tokenizers/punkt", "punkt"),
]:
    try:
        nltk.data.find(resource)
    except LookupError:
        nltk.download(path, quiet=True)
logger.info("[OK] NLTK ready.")

stemmer = PorterStemmer()
STOP_WORDS = set(stopwords.words("english"))

# ---------------------------------------------------------------------------
# Embedding Model
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = None
logger.info("[LOADING] Loading Embedding Model...")
try:
    EMBEDDING_MODEL = SentenceTransformer(config.embedding.model_name)
    logger.info(
        f"[OK] Embedding Model '{config.embedding.model_name}' loaded.")
except Exception as e:
    log_error("ModelLoadError", f"Failed to load embedding model: {e}")
    logger.critical("❌ FATAL: Embedding Model failed to load")

# ---------------------------------------------------------------------------
# Firebase Setup
# ---------------------------------------------------------------------------
SERVICE_ACCOUNT_KEY = config.firebase.service_account_key
FAQ_COLLECTION = config.firebase.faq_collection
EVENTS_COLLECTION = config.firebase.events_collection
QUERY_LOGS_COLLECTION = config.firebase.query_logs_collection

db = None
try:
    if not firebase_admin._apps:
        if os.path.exists(SERVICE_ACCOUNT_KEY):
            cred = credentials.Certificate(SERVICE_ACCOUNT_KEY)
            firebase_admin.initialize_app(cred)
            logger.info("[OK] Firebase Admin connected.")
        else:
            logger.warning(
                f"Firebase credentials file not found at {SERVICE_ACCOUNT_KEY}"
            )
            logger.warning(
                "The app will start but Firebase queries will fail.")
    db = firestore.client()
except Exception as e:
    log_error("FirebaseError", f"Firebase connection failed: {e}")
    logger.warning("The app will start but API calls will return errors.")

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
EMBEDDING_MATRIX = None  # numpy matrix, rows = FAQ_STORE indices


def build_embedding_context(answer: str, questions: list) -> str:
    """
    Builds the string that was encoded at write-time in admin_tool.py.
    Must be identical to admin_tool.prepare_fact_data() to keep the
    vector space consistent.
    """
    q_str = " ".join(questions) if questions else ""
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
        logger.warning("Skipping FAQ store load (db or model unavailable).")
        return

    logger.info("[LOADING] Loading FAQ store into memory...")
    try:
        docs = list(db.collection(FAQ_COLLECTION).stream())
    except Exception as e:
        log_error("FirestoreError", f"Failed to load FAQs: {e}")
        return

    if not docs:
        logger.warning("No FAQ documents found.")
        FAQ_STORE = []
        EMBEDDING_MATRIX = None
        return

    store = []
    vectors = []

    for doc in docs:
        try:
            data = doc.to_dict()
            emb = data.get("embedding")
            if emb is None:
                logger.warning(f"FAQ {doc.id} has no embedding, skipping.")
                continue

            store.append(
                {
                    "id": doc.id,
                    "answer": data.get("answer", ""),
                    "category": data.get("category", "general"),
                    "keywords": set(data.get("keywords", [])),
                    "generated_questions": data.get("generated_questions", []),
                }
            )
            vectors.append(np.array(emb, dtype=np.float32))
        except Exception as e:
            log_error("FAQParseError", f"Error parsing FAQ {doc.id}: {e}")
            continue

    if not vectors:
        FAQ_STORE = []
        EMBEDDING_MATRIX = None
        logger.warning("No embeddable FAQs found.")
        return

    FAQ_STORE = store
    EMBEDDING_MATRIX = np.vstack(vectors)  # shape: (N, 384)
    logger.info(
        f"[OK] FAQ store loaded: {len(FAQ_STORE)} documents, {EMBEDDING_MATRIX.shape[1]} dimensions."
    )


# Load at startup
load_faq_store()

# ---------------------------------------------------------------------------
# Gemini API — key rotation with exponential backoff
# ---------------------------------------------------------------------------
API_KEYS = config.gemini.api_keys

if not API_KEYS:
    logger.warning("No Gemini API keys found. AI responses will be disabled.")

SYSTEM_INSTRUCTION = (
    "You are a helpful Campus Guide Kiosk assistant. "
    "Answer the user's question based ONLY on the provided context. "
    "1. If the context is about a location, give the location and hours clearly. "
    "2. If the context is a specific process (e.g. Enrollment), list requirements concisely. "
    "3. Be polite but brief (max 50 words). "
    "4. Do not mention 'database', 'vectors', or 'embedding'."
)

_current_key_index = 0
_GEMINI_CLIENTS = {}  # key_index -> genai.Client, built lazily and reused


def _get_gemini_client(key_index: int):
    """Returns a cached genai.Client for the given key index, creating it on first use."""
    client = _GEMINI_CLIENTS.get(key_index)
    if client is None:
        client = genai.Client(api_key=API_KEYS[key_index])
        _GEMINI_CLIENTS[key_index] = client
    return client


GEMINI_TROUBLE_MSG = "I'm having trouble connecting right now. Please try again."
GEMINI_BUSY_MSG = "All AI service slots are currently busy. Please try again shortly."
GEMINI_OFFLINE_MSG = "AI service is currently offline."


class GeminiUnavailable(Exception):
    """Gemini call failed; str(e) is a user-safe message. Never cached."""


def _is_quota_error(e: Exception) -> bool:
    if isinstance(e, ResourceExhausted):
        return True
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    return code == 429 or "RESOURCE_EXHAUSTED" in str(e)


def get_gemini_response(prompt: str) -> str:
    """
    Calls Gemini with automatic key rotation on quota (429) errors.
    Tries each key once with a short backoff before giving up.
    Raises GeminiUnavailable on failure so callers don't cache error text.
    """
    global _current_key_index

    if not API_KEYS:
        logger.warning("Gemini: No API keys available")
        raise GeminiUnavailable(GEMINI_OFFLINE_MSG)

    attempts = len(API_KEYS)
    for attempt in range(attempts):
        key_index = (_current_key_index + attempt) % len(API_KEYS)
        try:
            client = _get_gemini_client(key_index)
            response = client.models.generate_content(
                model=config.gemini.model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION
                ),
            )
            _current_key_index = key_index  # remember the working key
            logger.debug(
                f"Gemini response generated successfully with key {key_index}")
            return response.text.strip()

        except Exception as e:
            # google-genai raises its own errors (not google.api_core ones),
            # so detect quota exhaustion via the HTTP status / status text.
            if _is_quota_error(e):
                logger.warning(f"API key [{key_index}] exhausted, rotating...")
                time.sleep(0.5 * (attempt + 1))  # 0.5s, 1.0s, 1.5s ...
                continue
            if isinstance(e, (InternalServerError, genai_errors.ServerError)):
                logger.warning(f"Gemini server error: {e}")
                raise GeminiUnavailable(GEMINI_TROUBLE_MSG) from e
            log_error("GeminiError", f"Gemini error: {e}")
            raise GeminiUnavailable(GEMINI_TROUBLE_MSG) from e

    # All keys exhausted
    logger.error("All Gemini API keys exhausted")
    _current_key_index = (_current_key_index + 1) % len(API_KEYS)
    raise GeminiUnavailable(GEMINI_BUSY_MSG)


# ---------------------------------------------------------------------------
# Keyword helpers
# ---------------------------------------------------------------------------


def get_query_keywords(text: str) -> set:
    """Extract and stem keywords from text."""
    if not text:
        return set()
    try:
        tokens = nltk.word_tokenize(text.lower())
        return {stemmer.stem(w) for w in tokens if w.isalnum() and w not in STOP_WORDS}
    except Exception as e:
        logger.warning(f"Error extracting keywords: {e}")
        return set()


# ---------------------------------------------------------------------------
# Core vectorized search
# ---------------------------------------------------------------------------


# Score thresholds — easier to tune in one place
RESULT_MIN_SCORE = 0.35  # minimum to appear in results
ANSWER_MIN_SCORE = config.app.answer_min_score  # minimum to give an AI answer
KEYWORD_BOOST = 0.12  # added per keyword overlap hit
TOP_K = 3  # number of candidates to return


def search_faqs(user_query: str) -> list:
    """
    Vectorized semantic search over the in-memory FAQ store.
    Returns up to TOP_K results sorted by descending score.
    Each result: { answer, category, generated_questions, score }
    """
    if EMBEDDING_MATRIX is None or not FAQ_STORE:
        logger.warning(
            "Search attempted but FAQ store is empty or embedding matrix not loaded"
        )
        return []

    try:
        # Encode the raw query (same model as admin_tool, no context wrapper needed
        # for the query side — asymmetric retrieval is fine with MiniLM)
        query_vec = EMBEDDING_MODEL.encode(user_query, convert_to_tensor=False)
        query_vec = np.array(query_vec, dtype=np.float32)

        # Single vectorized cosine similarity  (N,) in one call
        norms = np.linalg.norm(EMBEDDING_MATRIX, axis=1) * \
            np.linalg.norm(query_vec)
        norms = np.where(norms == 0, 1e-9, norms)
        scores = EMBEDDING_MATRIX.dot(query_vec) / norms  # shape: (N,)

        # Keyword boost — vectorized via list comprehension (fast enough for <10k docs)
        query_kw = get_query_keywords(user_query)
        boosts = np.array(
            [
                KEYWORD_BOOST * min(len(query_kw & faq["keywords"]), 3)
                for faq in FAQ_STORE
            ],
            dtype=np.float32,
        )
        scores = scores + boosts

        # Filter and sort
        above_threshold = np.where(scores >= RESULT_MIN_SCORE)[0]
        if len(above_threshold) == 0:
            logger.debug(
                f"No FAQ matches above threshold for query: {user_query[:50]}")
            return []

        top_indices = above_threshold[np.argsort(
            scores[above_threshold])[::-1][:TOP_K]]

        results = []
        for idx in top_indices:
            faq = FAQ_STORE[idx]
            results.append(
                {
                    "answer": faq["answer"],
                    "category": faq["category"],
                    "generated_questions": faq["generated_questions"],
                    "score": float(scores[idx]),
                }
            )
        return results
    except Exception as e:
        log_error("SearchError", f"Search failed: {e}")
        return []


# ---------------------------------------------------------------------------
# LRU cache — skip search + AI for repeated identical queries
# Caches up to 128 unique queries in memory.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=config.app.cache_max_size)
def cached_search_and_respond(user_query: str):
    """
    Cached wrapper around search + Gemini call.
    Returns (response_text, suggested_questions, match_score).
    lru_cache requires all args to be hashable — str qualifies.
    """
    matches = search_faqs(user_query)

    if not matches or matches[0]["score"] < ANSWER_MIN_SCORE:
        return (
            "I couldn't find that specific information. "
            "Try asking about a department like 'Registrar', 'Clinic', or 'Library'.",
            [
                "Where is the Registrar?",
                "Where is the Clinic?",
                "Enrollment Requirements",
            ],
            0.0,
        )

    best = matches[0]
    prompt = (
        f"User Question: {user_query}\n"
        f"Database Fact: {best['answer']}\n"
        f"Answer the user politely and concisely."
    )
    # May raise GeminiUnavailable — lru_cache doesn't cache exceptions, so a
    # transient outage is never served from cache after Gemini recovers.
    response_text = get_gemini_response(prompt)

    # Suggested follow-up questions come from the matched FAQ's own
    # generated_questions field (written by admin_tool at ingest time)
    suggestions = best["generated_questions"][:4]

    # Fallback: surface other top matches as navigation hints
    if not suggestions and len(matches) > 1:
        suggestions = [m["answer"][:60] + "..." for m in matches[1:]]

    return response_text, suggestions, best["score"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# Error handlers


@app.errorhandler(APIError)
def handle_api_error(error):
    """Handle custom API errors."""
    response, status_code = create_error_response(
        error.error_type, error.message, error.status_code
    )
    return jsonify(response), status_code


@app.errorhandler(400)
def handle_bad_request(error):
    """Handle bad request errors."""
    response, status_code = create_error_response(
        "BadRequest", "Invalid request format"
    )
    return jsonify(response), status_code


@app.errorhandler(404)
def handle_not_found(error):
    """Handle 404 errors."""
    response, status_code = create_error_response(
        "NotFound", "Resource not found", 404)
    return jsonify(response), status_code


@app.errorhandler(500)
def handle_internal_error(error):
    """Handle internal server errors."""
    log_error("InternalServerError", str(error))
    response, status_code = create_error_response(
        "InternalServerError", "An unexpected error occurred"
    )
    return jsonify(response), status_code


@app.errorhandler(429)
def handle_rate_limit_exceeded(error):
    """Handle rate limit errors (raised by Flask-Limiter)."""
    response, status_code = create_error_response(
        "RateLimitExceeded", "Rate limit exceeded. Please try again later.", 429
    )
    return jsonify(response), status_code


@app.route("/")
def index():
    """Serve the main HTML template."""
    try:
        return render_template(
            "index.html",
            fb_api_key=os.getenv("FIREBASE_API_KEY"),
            fb_project_id=os.getenv("FIREBASE_PROJECT_ID"),
            fb_app_id=os.getenv("FIREBASE_APP_ID"),
        )
    except Exception as e:
        log_error("TemplateError", f"Failed to render index template: {e}")
        response, status_code = create_error_response(
            "TemplateError", "Failed to load page"
        )
        return jsonify(response), status_code


@app.route("/api/v1/ask", methods=["POST"])
@limiter.limit(f"{config.rate_limit.requests_per_minute}/minute")
def handle_ask_query():
    """Handle user questions via semantic search + AI."""
    start_time = time.time()
    try:
        data = request.get_json(silent=True)
        if not data:
            raise ValidationError("Request body must be valid JSON")

        # Validate required fields
        validate_api_request(data, ["query"])

        # Sanitize and validate input
        user_query = validate_query(
            data["query"], config.security.max_query_length)

        logger.info(f"🗣️  User query: {user_query[:50]}...")

        # Log query to analytics if enabled
        if os.getenv("ENABLE_ANALYTICS", "True").lower() == "true":
            try:
                if db:
                    db.collection(QUERY_LOGS_COLLECTION).document().set(
                        {
                            "query": user_query,
                            "timestamp": firestore.SERVER_TIMESTAMP,
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to log query to analytics: {e}")

        # Get response
        try:
            response_text, suggested_questions, match_score = cached_search_and_respond(
                user_query
            )
        except GeminiUnavailable as e:
            # AI down: degrade to the best stored FAQ answer (uncached).
            matches = search_faqs(user_query)
            if not matches or matches[0]["score"] < ANSWER_MIN_SCORE:
                response_text, suggested_questions, match_score = str(e), [], 0.0
            else:
                response_text = matches[0]["answer"]
                suggested_questions = matches[0]["generated_questions"][:4]
                match_score = matches[0]["score"]

        duration_ms = (time.time() - start_time) * 1000
        log_api_call("/api/v1/ask", "POST", 200, duration_ms, user_query)

        logger.info(
            f"[OK] Response sent - Score: {match_score:.2f} - Duration: {duration_ms:.1f}ms"
        )

        return (
            jsonify(
                create_success_response(
                    {
                        "response": response_text,
                        "match_score": f"{match_score:.2f}",
                        "suggested_questions": suggested_questions,
                    },
                    "Query processed successfully",
                )
            ),
            200,
        )

    except ValidationError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_api_call("/api/v1/ask", "POST", 400, duration_ms)
        response, status_code = create_error_response(
            "ValidationError", str(e))
        return jsonify(response), status_code

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_api_call("/api/v1/ask", "POST", 500, duration_ms)
        log_error("QueryError", f"Query processing failed: {e}")
        response, status_code = create_error_response(
            "InternalServerError", "Failed to process query"
        )
        return jsonify(response), status_code


def _check_admin_authorized(secret: str, log_message: str):
    """
    Shared admin-secret gate for /api/v1/reload and /api/v1/analytics.
    Returns None if the request is authorized, or an (response, status_code)
    tuple the caller should return immediately otherwise.
    """
    expected = os.getenv("RELOAD_SECRET", "")
    if not expected and config.environment == "production":
        # Fail closed: never expose admin endpoints in production without a secret.
        log_error("Unauthorized", f"{log_message} (RELOAD_SECRET unset in production)")
        return create_error_response("Unauthorized", "Invalid credentials", 401)
    if check_admin_secret(secret, expected):
        return None
    log_error("Unauthorized", f"{log_message} from {request.remote_addr}")
    return create_error_response("Unauthorized", "Invalid credentials", 401)


@app.route("/api/v1/reload", methods=["POST"])
def reload_faq_store():
    """
    Admin endpoint — call this after adding/editing FAQs via admin_tool.py
    to refresh the in-memory store without restarting Flask.
    Protect this with a secret header in production.
    """
    try:
        secret = request.headers.get("X-Reload-Secret", "")
        auth_error = _check_admin_authorized(
            secret, "Reload attempted with invalid secret"
        )
        if auth_error:
            response, status_code = auth_error
            return jsonify(response), status_code

        logger.info("📤 Reloading FAQ store...")
        # Invalidate LRU cache so stale answers aren't served
        cached_search_and_respond.cache_clear()
        load_faq_store()
        logger.info(f"✅ FAQ store reloaded: {len(FAQ_STORE)} documents")

        return (
            jsonify(
                create_success_response(
                    {
                        "faq_count": len(FAQ_STORE),
                        "embedding_matrix_shape": list(EMBEDDING_MATRIX.shape)
                        if EMBEDDING_MATRIX is not None
                        else None,
                    },
                    "FAQ store reloaded successfully",
                )
            ),
            200,
        )

    except Exception as e:
        log_error("ReloadError", f"Failed to reload FAQ store: {e}")
        response, status_code = create_error_response(
            "InternalServerError", "Failed to reload FAQ store"
        )
        return jsonify(response), status_code


@app.route("/api/v1/health", methods=["GET"])
def health_check():
    """Comprehensive health check endpoint."""
    try:
        firebase_status = "connected" if db is not None else "disconnected"
        health_data = {
            "status": "healthy",
            "environment": config.environment,
            "faq_count": len(FAQ_STORE),
            "embedding_matrix_shape": list(EMBEDDING_MATRIX.shape)
            if EMBEDDING_MATRIX is not None
            else None,
            "model_loaded": EMBEDDING_MODEL is not None,
            "model_name": config.embedding.model_name,
            "firebase_status": firebase_status,
            "api_keys_configured": len(API_KEYS),
            "cache_info": {
                "hits": cached_search_and_respond.cache_info().hits,
                "misses": cached_search_and_respond.cache_info().misses,
                "currsize": cached_search_and_respond.cache_info().currsize,
            },
            "rate_limiting_enabled": config.rate_limit.enabled,
            "log_level": config.app.log_level,
        }

        logger.debug(f"Health check: {health_data}")
        return jsonify(create_success_response(health_data, "System is healthy")), 200

    except Exception as e:
        log_error("HealthCheckError", f"Health check failed: {e}")
        response, status_code = create_error_response(
            "InternalServerError", "Health check failed"
        )
        return jsonify(response), status_code


@app.route("/api/v1/analytics", methods=["GET"])
def get_analytics():
    """
    Get query analytics. Admin-only endpoint.

    Query parameters:
    - limit: Number of recent queries (default: 100, max: 1000)
    - secret: Admin secret for authentication
    """
    try:
        # Check admin authentication
        secret = request.args.get("secret", "")
        auth_error = _check_admin_authorized(
            secret, "Analytics requested without valid secret"
        )
        if auth_error:
            response, status_code = auth_error
            return jsonify(response), status_code

        try:
            limit = min(int(request.args.get("limit", 100)), 1000)
            if limit < 1:
                raise ValueError("limit must be positive")
        except (TypeError, ValueError):
            response, status_code = create_error_response(
                "ValidationError", "Query parameter 'limit' must be a positive integer"
            )
            return jsonify(response), status_code

        logger.info(f"📊 Analytics requested (limit: {limit})")

        # Try to fetch from Firebase
        if db is None or QUERY_LOGS_COLLECTION is None:
            logger.warning("Analytics unavailable - Firebase not connected")
            return (
                jsonify(
                    create_success_response(
                        {
                            "total_queries": 0,
                            "recent_queries": [],
                            "message": "Analytics data unavailable",
                        },
                        "Analytics (limited mode)",
                    )
                ),
                200,
            )

        try:
            # Fetch recent queries from Firebase
            query_logs = (
                db.collection(QUERY_LOGS_COLLECTION)
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )

            queries = []
            for doc in query_logs:
                data = doc.to_dict()
                queries.append(
                    {
                        "query": data.get("query", ""),
                        "timestamp": data.get("timestamp", ""),
                    }
                )

            logger.info(f"✅ Returned {len(queries)} analytics records")

            return (
                jsonify(
                    create_success_response(
                        {
                            "total_queries": len(queries),
                            "recent_queries": queries,
                            "cache_stats": {
                                "hits": cached_search_and_respond.cache_info().hits,
                                "misses": cached_search_and_respond.cache_info().misses,
                                "cached_size": cached_search_and_respond.cache_info().currsize,
                            },
                        },
                        "Analytics retrieved successfully",
                    )
                ),
                200,
            )

        except Exception as e:
            log_error("FirestoreAnalyticsError",
                      f"Failed to fetch analytics: {e}")
            return (
                jsonify(
                    create_success_response(
                        {
                            "total_queries": 0,
                            "recent_queries": [],
                            "cache_stats": {
                                "hits": cached_search_and_respond.cache_info().hits,
                                "misses": cached_search_and_respond.cache_info().misses,
                                "cached_size": cached_search_and_respond.cache_info().currsize,
                            },
                            "message": "Partial analytics available",
                        },
                        "Analytics (cache only)",
                    )
                ),
                200,
            )

    except Exception as e:
        log_error("AnalyticsError", f"Analytics endpoint error: {e}")
        response, status_code = create_error_response(
            "InternalServerError", "Failed to retrieve analytics"
        )
        return jsonify(response), status_code


@app.before_request
def log_request():
    """Log incoming requests."""
    logger.debug(f"{request.method} {request.path} from {request.remote_addr}")


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


if __name__ == "__main__":
    port = config.app.port
    debug_mode = config.app.debug

    logger.info("\n" + "=" * 60)
    logger.info("[START] Campus Guide Kiosk Starting Up")
    logger.info("=" * 60)
    logger.info(f"Environment: {config.environment}")
    logger.info(f"Port: {port}")
    logger.info(f"Debug Mode: {debug_mode}")
    logger.info(f"Embedding Model: {config.embedding.model_name}")
    logger.info(f"Firebase Connected: {db is not None}")
    logger.info(f"API Keys Configured: {len(API_KEYS)}")
    logger.info(f"FAQs in Memory: {len(FAQ_STORE)}")
    logger.info(
        f"Rate Limiting: {'Enabled' if config.rate_limit.enabled else 'Disabled'}"
    )
    logger.info("=" * 60 + "\n")

    app.run(host=config.app.host, port=port,
            debug=debug_mode, use_reloader=False)
