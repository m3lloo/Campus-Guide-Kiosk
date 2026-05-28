"""
Campus Guide Kiosk — Admin Data Manager (Refactored)
=====================================================
Key improvements over original:
  - Writes to 'faqs' collection — same collection app.py reads from
  - build_embedding_context() is imported-equivalent to app.py's version
    so the vector space at write-time == query-time (no more mismatch)
  - API usage counter persisted to a local JSON file across sessions
  - Gemini key rotation with backoff (mirrors app.py)
  - Removed dead 'campus_entities' / 'topics' sub-collection references
  - After add/edit, optionally calls app.py's /api/v1/reload endpoint
    so Flask picks up changes without a restart
"""

from nltk.stem import PorterStemmer
from nltk.corpus import stopwords
import os
import re
import json
import time
import nltk
import numpy as np
import firebase_admin
from firebase_admin import credentials, firestore
from sentence_transformers import SentenceTransformer
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SERVICE_ACCOUNT_KEY_PATH = "firebase/campus_guide_kiosk.json"
FAQ_COLLECTION_NAME = 'faqs'          # must match app.py
EVENTS_COLLECTION_NAME = 'events'

USAGE_FILE = '.api_usage.json'        # persists counter across runs
DAILY_FREE_LIMIT = 200

# Optional: set APP_RELOAD_URL in .env to auto-refresh app.py after changes
#   APP_RELOAD_URL=http://localhost:5000/api/v1/reload
#   RELOAD_SECRET=your_secret
APP_RELOAD_URL = os.getenv("APP_RELOAD_URL", "")
RELOAD_SECRET = os.getenv("RELOAD_SECRET", "")

# ---------------------------------------------------------------------------
# NLTK
# ---------------------------------------------------------------------------
print("⏳ Checking NLTK resources...")
for resource, pkg in [('corpora/stopwords', 'stopwords'), ('tokenizers/punkt', 'punkt')]:
    try:
        nltk.data.find(resource)
    except LookupError:
        nltk.download(pkg, quiet=True)
print("✅ NLTK ready.")


stemmer = PorterStemmer()
CHATBOT_STOP_WORDS = set(stopwords.words('english') + [
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'of', 'in', 'at', 'on',
    'with', 'by', 'what', 'where', 'how', 'to', 'please', 'want', 'need',
    'know', 'tell', 'find',
])

# ---------------------------------------------------------------------------
# Embedding Model
# ---------------------------------------------------------------------------
print("⏳ Loading Sentence Transformer Model...")
try:
    EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    print("✅ Embedding Model loaded.")
except Exception as e:
    print(f"❌ Error loading SentenceTransformer: {e}")
    EMBED_MODEL = None

# ---------------------------------------------------------------------------
# Gemini — key rotation (mirrors app.py)
# ---------------------------------------------------------------------------
_RAW_KEYS = [os.environ.get(f"API_KEY_{i}") for i in range(1, 6)]
API_KEYS = [k for k in _RAW_KEYS if k]

if not API_KEYS:
    # Fallback: try the legacy single-key name used in the original script
    legacy = os.environ.get("API_Key") or os.environ.get("API_KEY")
    if legacy:
        API_KEYS = [legacy]

_current_key_index = 0
gemini_model_instance = None


def _get_gemini_model():
    """Returns a configured GenerativeModel, rotating keys on exhaustion."""
    global _current_key_index, gemini_model_instance
    if not API_KEYS:
        return None
    genai.configure(api_key=API_KEYS[_current_key_index])
    gemini_model_instance = genai.GenerativeModel('gemini-2.5-flash')
    return gemini_model_instance


def _call_gemini(prompt: str) -> str | None:
    """Call Gemini with rotation. Returns text or None on total failure."""
    global _current_key_index
    if not API_KEYS:
        return None
    for attempt in range(len(API_KEYS)):
        key_index = (_current_key_index + attempt) % len(API_KEYS)
        try:
            genai.configure(api_key=API_KEYS[key_index])
            m = genai.GenerativeModel('gemini-2.5-flash')
            resp = m.generate_content(prompt)
            _current_key_index = key_index
            _increment_usage()
            return resp.text.strip()
        except ResourceExhausted:
            print(f"⚠️  API key [{key_index}] exhausted, rotating...")
            time.sleep(0.5 * (attempt + 1))
        except Exception as e:
            print(f"⚠️  Gemini error: {e}")
            return None
    print("❌ All API keys exhausted.")
    return None

# ---------------------------------------------------------------------------
# API usage counter — persisted to disk so it survives restarts
# ---------------------------------------------------------------------------


def _load_usage() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(USAGE_FILE, 'r') as f:
            data = json.load(f)
        if data.get('date') != today:
            return {'date': today, 'count': 0}
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {'date': today, 'count': 0}


def _save_usage(data: dict):
    try:
        with open(USAGE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"⚠️  Could not save usage counter: {e}")


def _increment_usage():
    data = _load_usage()
    data['count'] += 1
    _save_usage(data)


def _get_usage() -> tuple[int, int]:
    """Returns (used_today, remaining)."""
    data = _load_usage()
    used = data.get('count', 0)
    return used, max(0, DAILY_FREE_LIMIT - used)

# ---------------------------------------------------------------------------
# Firebase
# ---------------------------------------------------------------------------


def initialize_firestore_admin():
    if firebase_admin._apps:
        return firestore.client()
    try:
        if not os.path.exists(SERVICE_ACCOUNT_KEY_PATH):
            raise FileNotFoundError(
                f"Key not found: {SERVICE_ACCOUNT_KEY_PATH}")
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase Admin SDK initialized.")
        return firestore.client()
    except Exception as e:
        print(f"❌ Firebase Error: {e}")
        return None


db = initialize_firestore_admin()

# ---------------------------------------------------------------------------
# Embedding context builder
# CRITICAL: this function must produce the same string as app.py's
# build_embedding_context() so embeddings are in the same vector space.
# ---------------------------------------------------------------------------


def build_embedding_context(answer: str, questions: list) -> str:
    q_str = ' '.join(questions) if questions else ''
    return f"Answer: {answer}. Possible Questions: {q_str}"


# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------
CATEGORY_MAP = {
    1: "administrative_office", 2: "academic_facility", 3: "room_location",
    4: "dining_area", 5: "general_facility", 6: "health_safety",
    7: "transport_parking", 8: "sports_recreation", 9: "bookstore_merchandise",
    10: "housing_accommodation", 11: "student_services", 12: "it_tech_support",
    13: "tuition_financial_aid", 14: "career_placement_alumni",
    15: "accessibility_pwd", 16: "school_personnel", 17: "student_organizations",
    18: "faculty_office", 19: "admissions_enrollment", 20: "events_activities",
    21: "policies_regulations", 22: "academic_program_course", 23: "system_info",
    0: "general",
}
CATEGORY_DESCRIPTION = {
    1: "Registrar / Admin / Finance",       2: "College Buildings / Labs",
    3: "Classroom / Room Numbers",          4: "Canteen / Dining Hall",
    5: "Student Union / Chapel",            6: "Clinic / Security",
    7: "Parking / Shuttles",                8: "Gym / Courts",
    9: "Bookstore / Uniforms",              10: "Dormitories",
    11: "Library / Guidance",              12: "Wi-Fi / Portal",
    13: "Tuition / Scholarships",          14: "OJT / Alumni",
    15: "Accessibility",                   16: "Specific People (Deans, Staff)",
    17: "Clubs / Orgs",                    18: "Faculty Rooms",
    19: "Admissions / Enrollment",         20: "School Calendar / Events",
    21: "Policies / Handbook",             22: "Curriculum / Thesis",
    23: "About the AI / Kiosk",             0: "General (Default)",
}
CATEGORY_NAME_TO_NUM = {v: k for k, v in CATEGORY_MAP.items()}

EVENT_DEPARTMENT_MAP = {
    'All': 'All Departments', 'CCS': 'Computer Studies (CCS)',
    'CCA': 'Comm & Arts (CCA)', 'CBA': 'Business (CBA)',
    'CCJ': 'Criminal Justice (CCJ)', 'CEAS': 'Education & Arts (CEAS)',
    'CON': 'Nursing (CON)',
}

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def generate_keywords(text_blob: str) -> list:
    if not text_blob:
        return []
    text = re.sub(r'[^a-z0-9\s]', ' ', text_blob.lower())
    try:
        tokens = nltk.word_tokenize(text)
    except Exception:
        tokens = text.split()
    suggested = set()
    for word in tokens:
        if word not in CHATBOT_STOP_WORDS and len(word) > 2:
            suggested.add(word)
            suggested.add(stemmer.stem(word))
    return sorted(suggested)


def generate_embedding(text: str) -> list | None:
    if EMBED_MODEL is None:
        return None
    vec = EMBED_MODEL.encode(text, convert_to_tensor=False)
    return vec.tolist() if vec is not None else None


def optimize_answer(answer: str) -> str:
    prompt = (
        f"Rewrite this fact to be concise, polite, and factual for a school kiosk "
        f"(max 40 words, no markdown): '{answer}'"
    )
    result = _call_gemini(prompt)
    return result if result else answer


def generate_hypothetical_questions(answer: str) -> list:
    prompt = (
        f"You are simulating a university student.\n"
        f"The answer is: \"{answer}\".\n"
        f"List 5 distinct, short questions a student would ask to get this answer.\n"
        f"Format: just the questions, one per line, no numbering, no dashes."
    )
    result = _call_gemini(prompt)
    if not result:
        return []
    lines = result.strip().split('\n')
    return [l.strip('- ').strip() for l in lines if l.strip()][:5]


def prepare_faq_document(answer: str, questions: list, manual_keywords: list,
                         category: str) -> dict:
    """
    Builds the Firestore document dict.
    Schema is shared between this tool and app.py — do not change field names
    without updating app.py's load_faq_store() as well.
    """
    # Keywords from answer + questions + manual additions
    full_blob = f"{answer} {' '.join(questions)} {' '.join(manual_keywords)}"
    final_keywords = generate_keywords(full_blob)

    # Embedding context — MUST match app.py's build_embedding_context()
    embed_text = build_embedding_context(answer, questions)
    embedding = generate_embedding(embed_text)

    doc = {
        'answer':              answer,
        'generated_questions': questions,
        'keywords':            final_keywords,
        'category':            category.lower() if category else 'general',
        'created_at':          firestore.SERVER_TIMESTAMP,
    }
    if embedding is not None:
        doc['embedding'] = embedding
    else:
        print("⚠️  No embedding generated — document will be unsearchable via semantic search.")
    return doc


def notify_app_reload():
    """
    Optionally call app.py's /api/v1/reload endpoint so the in-memory
    FAQ store is refreshed without restarting Flask.
    Requires APP_RELOAD_URL and optionally RELOAD_SECRET in .env
    """
    if not APP_RELOAD_URL or not _REQUESTS_AVAILABLE:
        return
    try:
        headers = {'X-Reload-Secret': RELOAD_SECRET} if RELOAD_SECRET else {}
        resp = _requests.post(APP_RELOAD_URL, headers=headers, timeout=5)
        if resp.ok:
            data = resp.json()
            print(
                f"✅ App store reloaded. FAQs in memory: {data.get('faq_count', '?')}")
        else:
            print(f"⚠️  Reload endpoint returned {resp.status_code}")
    except Exception as e:
        print(f"⚠️  Could not reach app reload endpoint: {e}")

# ---------------------------------------------------------------------------
# Category selection UI
# ---------------------------------------------------------------------------


def get_category_selection(default_num: int = 0) -> str | None:
    print("\n--- CATEGORY SELECTION ---")
    items = list(CATEGORY_DESCRIPTION.items())
    half = (len(items) + 1) // 2
    for i in range(half):
        col1 = f"[{items[i][0]:2}] {items[i][1]}"
        col2 = ""
        if i + half < len(items):
            col2 = f"[{items[i+half][0]:2}] {items[i+half][1]}"
        print(f"{col1:<42} {col2}")

    while True:
        raw = input(
            f"👉 Select Category (default {default_num}) or 'cancel': ").strip()
        if raw.lower() == 'cancel':
            return None
        if not raw:
            return CATEGORY_MAP.get(default_num, 'general')
        try:
            return CATEGORY_MAP.get(int(raw), CATEGORY_MAP.get(default_num, 'general'))
        except ValueError:
            print("Invalid input. Enter a number or 'cancel'.")

# ---------------------------------------------------------------------------
# FAQ CRUD
# ---------------------------------------------------------------------------


def add_faq_interactive():
    if db is None:
        print("❌ No database connection.")
        return

    print("\n=== ➕ Add New FAQ (AI Enhanced) ===")
    raw_answer = input("👉 Answer Text: ").strip()
    if not raw_answer:
        return

    final_answer = raw_answer
    final_questions = []

    if API_KEYS:
        print("⏳ AI is optimizing answer and predicting questions...")
        optimized = optimize_answer(raw_answer)
        generated_qs = generate_hypothetical_questions(optimized)

        print(f"\n✨ AI-Optimized Answer: {optimized}")
        use_opt = input("👉 Use AI-Optimized Answer? (Y/n): ").strip().lower()
        if use_opt in ('y', ''):
            final_answer = optimized
        else:
            manual_edit = input(
                "👉 Edit answer manually? (y/N): ").strip().lower()
            if manual_edit == 'y':
                edited = input("New Answer: ").strip()
                if edited:
                    final_answer = edited

        if generated_qs:
            print(f"\n🧠 Predicted Questions: {generated_qs}")
            use_qs = input(
                "👉 Use AI-Generated Questions? (Y/n): ").strip().lower()
            if use_qs in ('y', ''):
                final_questions = generated_qs
    else:
        print("⚠️  Gemini not configured — skipping AI optimization.")

    extra_kw = input(
        "👉 Additional keywords (comma-separated, optional): ").strip()
    manual_kw = [k.strip().lower() for k in extra_kw.split(',') if k.strip()]

    cat = get_category_selection()
    if cat is None:
        return

    doc = prepare_faq_document(final_answer, final_questions, manual_kw, cat)
    try:
        ref = db.collection(FAQ_COLLECTION_NAME).add(doc)
        print(f"\n✅ FAQ Added! ID: {ref[1].id}")
        notify_app_reload()
    except Exception as e:
        print(f"❌ Error saving FAQ: {e}")


def edit_faq_interactive(doc_id: str, faq_data: dict):
    if db is None:
        return

    print(f"\n=== ✏️  Edit FAQ ID: {doc_id} ===")
    current_answer = faq_data['answer']
    print(f"Current Answer: {current_answer}")
    new_answer = input(
        "👉 New Answer (blank = keep current): ").strip() or current_answer

    final_answer = new_answer
    final_questions = faq_data.get('generated_questions', [])

    if new_answer != current_answer and API_KEYS:
        print("⏳ Answer changed — re-optimizing and re-generating questions...")
        optimized = optimize_answer(new_answer)
        generated_qs = generate_hypothetical_questions(optimized)

        print(f"\n✨ AI-Optimized Answer: {optimized}")
        if input("👉 Use new AI-Optimized Answer? (Y/n): ").strip().lower() in ('y', ''):
            final_answer = optimized

        if generated_qs:
            print(f"\n🧠 New Predicted Questions: {generated_qs}")
            if input("👉 Replace questions with new AI-Generated ones? (Y/n): ").strip().lower() in ('y', ''):
                final_questions = generated_qs

    print(
        f"\nCurrent Keywords (auto): {', '.join(faq_data.get('keywords', []))}")
    extra_kw = input(
        "👉 Additional keywords to merge in (comma-separated): ").strip()
    manual_kw = [k.strip().lower() for k in extra_kw.split(',') if k.strip()]

    current_cat_name = faq_data.get('category', 'general')
    current_cat_num = CATEGORY_NAME_TO_NUM.get(current_cat_name, 0)
    print(f"Current Category: {current_cat_name}")
    cat = get_category_selection(default_num=current_cat_num)
    if cat is None:
        return

    doc = prepare_faq_document(final_answer, final_questions, manual_kw, cat)
    doc['updated_at'] = firestore.SERVER_TIMESTAMP
    doc.pop('created_at', None)   # preserve original created_at

    try:
        db.collection(FAQ_COLLECTION_NAME).document(doc_id).update(doc)
        print(f"\n✅ FAQ Updated! ID: {doc_id}")
        notify_app_reload()
    except Exception as e:
        print(f"❌ Error updating FAQ: {e}")


def delete_faq(faqs: list) -> bool:
    try:
        num = int(input("👉 # to DELETE: ")) - 1
        if 0 <= num < len(faqs):
            faq = faqs[num]
            confirm = input(
                f"DELETE '{faq['answer'][:40]}...' ? (y/N): ").strip().lower()
            if confirm == 'y':
                db.collection(FAQ_COLLECTION_NAME).document(faq['id']).delete()
                print("✅ Deleted.")
                notify_app_reload()
                return True
    except (ValueError, IndexError):
        pass
    return False


def fetch_all_faqs() -> dict | None:
    if db is None:
        return None
    print("⏳ Fetching FAQs...")
    try:
        docs = db.collection(FAQ_COLLECTION_NAME).stream()
        by_cat: dict = {}
        for doc in docs:
            f = doc.to_dict()
            f['id'] = doc.id
            cat = f.get('category', 'general')
            by_cat.setdefault(cat, []).append(f)
        return by_cat
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

# ---------------------------------------------------------------------------
# FAQ manager menus
# ---------------------------------------------------------------------------


def manage_category_faqs(cat_name: str, faqs: list):
    while True:
        print(f"\n--- {cat_name} ({len(faqs)} FAQs) ---")
        if not faqs:
            print("No FAQs in this category.")
            break
        for i, f in enumerate(faqs):
            preview = f['answer'][:55]
            qs = f.get('generated_questions', [])
            q_hint = f" → Q: {qs[0][:40]}" if qs else ""
            print(f"[{i+1:2}] {preview}...{q_hint}")

        print("\n[R] Return | [E] Edit | [D] Delete | (number) View full")
        choice = input("👉 Choice: ").strip().upper()

        if choice == 'R':
            break
        elif choice == 'D':
            if delete_faq(faqs):
                break
        elif choice == 'E':
            try:
                num = int(input("👉 # to EDIT: ")) - 1
                if 0 <= num < len(faqs):
                    edit_faq_interactive(faqs[num]['id'], faqs[num])
                break
            except (ValueError, IndexError):
                pass
        else:
            try:
                num = int(choice) - 1
                if 0 <= num < len(faqs):
                    f = faqs[num]
                    print(f"\n--- Full FAQ ({f['id']}) ---")
                    print(f"Answer:    {f['answer']}")
                    print(f"Category:  {f['category']}")
                    print(f"Questions: {f.get('generated_questions')}")
                    print(f"Keywords:  {f.get('keywords')}")
            except (ValueError, IndexError):
                pass


def manage_faqs():
    while True:
        print("\n=== 🤖 FAQ Manager ===")
        all_faqs = fetch_all_faqs()
        if all_faqs is None:
            return

        cats = sorted(all_faqs.keys())
        print(f"\nCategories ({len(cats)} total):")
        for i, c in enumerate(cats):
            print(f"  [{i+1:2}] {c}  ({len(all_faqs[c])} items)")

        print("\n[A] Add FAQ | [M] Main Menu")
        choice = input("👉 Choice: ").strip().upper()

        if choice == 'M':
            break
        elif choice == 'A':
            add_faq_interactive()
        else:
            try:
                cat_name = cats[int(choice) - 1]
                manage_category_faqs(cat_name, all_faqs[cat_name])
            except (ValueError, IndexError):
                pass

# ---------------------------------------------------------------------------
# Event CRUD
# ---------------------------------------------------------------------------


def fetch_all_events() -> list | None:
    if db is None:
        return None
    print("⏳ Fetching events...")
    try:
        docs = db.collection(EVENTS_COLLECTION_NAME).stream()
        events = []
        for doc in docs:
            e = doc.to_dict()
            e['id'] = doc.id
            events.append(e)
        events.sort(key=lambda x: x.get('date', '9999-01-01T00:00:00'))
        return events
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def _parse_date_input(prompt_str: str, current_val: str = '') -> str | None:
    """Prompts for a date, returns ISO string or None on invalid input."""
    raw = input(prompt_str).strip()
    if not raw and current_val:
        # Keep existing if blank
        try:
            return datetime.fromisoformat(current_val).isoformat()
        except Exception:
            return current_val
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M").isoformat()
    except ValueError:
        print("❌ Invalid date format. Use YYYY-MM-DD HH:MM.")
        return None


def _select_department(current: str = 'All') -> str:
    depts = list(EVENT_DEPARTMENT_MAP.keys())
    print("\n--- Departments ---")
    for i, d in enumerate(depts):
        print(f"  [{i+1}] {d} — {EVENT_DEPARTMENT_MAP[d]}")
    print(
        f"  Current: {current} ({EVENT_DEPARTMENT_MAP.get(current, current)})")
    raw = input("👉 Dept # (blank = keep current): ").strip()
    if not raw:
        return current
    try:
        return depts[int(raw) - 1]
    except (ValueError, IndexError):
        print("Invalid input, keeping current.")
        return current


def add_event():
    if db is None:
        return
    print("\n=== ➕ Add Event ===")
    title = input("Title: ").strip()
    if not title:
        return
    details = input("Details: ").strip()
    iso = _parse_date_input("Date (YYYY-MM-DD HH:MM): ")
    if iso is None:
        return
    dept = _select_department()
    try:
        db.collection(EVENTS_COLLECTION_NAME).add({
            'title':      title,
            'date':       iso,
            'details':    details,
            'department': dept,
            'created_at': firestore.SERVER_TIMESTAMP,
        })
        print("✅ Event Added.")
    except Exception as e:
        print(f"❌ Error: {e}")


def edit_event_interactive(doc_id: str, event_data: dict):
    print(f"\n=== ✏️  Edit Event ID: {doc_id} ===")

    title = event_data['title']
    details = event_data.get('details', '')
    dept = event_data.get('department', 'All')

    print(f"Current Title: {title}")
    new_title = input("👉 New Title (blank = keep): ").strip() or title

    print(f"Current Details: {details}")
    new_details = input("👉 New Details (blank = keep): ").strip() or details

    try:
        friendly = datetime.fromisoformat(
            event_data['date']).strftime("%Y-%m-%d %H:%M")
    except Exception:
        friendly = event_data['date']

    iso = _parse_date_input(
        f"Current Date: {friendly}\n👉 New Date (blank = keep, YYYY-MM-DD HH:MM): ",
        current_val=event_data['date'],
    )
    if iso is None:
        return

    new_dept = _select_department(current=dept)

    try:
        db.collection(EVENTS_COLLECTION_NAME).document(doc_id).update({
            'title':      new_title,
            'date':       iso,
            'details':    new_details,
            'department': new_dept,
            'updated_at': firestore.SERVER_TIMESTAMP,
        })
        print("✅ Event Updated.")
    except Exception as e:
        print(f"❌ Error: {e}")


def delete_event(events: list) -> bool:
    try:
        num = int(input("👉 # to DELETE: ")) - 1
        if 0 <= num < len(events):
            e = events[num]
            if input(f"DELETE '{e['title']}' on {e['date']} ? (y/N): ").strip().lower() == 'y':
                db.collection(EVENTS_COLLECTION_NAME).document(
                    e['id']).delete()
                print("✅ Deleted.")
                return True
    except (ValueError, IndexError):
        pass
    return False


def manage_events():
    while True:
        print("\n=== 📅 Event Manager ===")
        events = fetch_all_events()
        if events is None:
            return

        if not events:
            print("No events found.")
        else:
            for i, e in enumerate(events):
                try:
                    date_str = datetime.fromisoformat(
                        e['date']).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    date_str = e['date']
                dept_str = EVENT_DEPARTMENT_MAP.get(
                    e.get('department', 'All'), '')
                print(f"[{i+1:2}] {date_str} ({dept_str}): {e['title'][:45]}")

        print("\n[A] Add | [E] Edit | [D] Delete | [M] Main Menu")
        choice = input("👉 Choice: ").strip().upper()

        if choice == 'M':
            break
        elif choice == 'A':
            add_event()
        elif choice == 'E':
            if not events:
                continue
            try:
                num = int(input("👉 # to EDIT: ")) - 1
                if 0 <= num < len(events):
                    edit_event_interactive(events[num]['id'], events[num])
            except (ValueError, IndexError):
                pass
        elif choice == 'D':
            if not events:
                continue
            delete_event(events)
        else:
            print("Invalid choice.")

# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------


def main_menu():
    if db is None:
        print("\n❌ Cannot run — Firebase initialization failed.")
        return

    while True:
        used, remaining = _get_usage()
        print("\n==========================")
        print("   CAMPUS KIOSK MANAGER   ")
        print("==========================")
        if API_KEYS:
            print(
                f"🤖 Gemini API  |  Used today: {used}  |  Est. remaining: {remaining}")
            print("==========================")
        print("[1] 🤖 Manage FAQs")
        print("[2] 📅 Manage Events")
        print("[0] 🚪 Exit")
        choice = input("👉 Choice: ").strip()

        if choice == '1':
            manage_faqs()
        elif choice == '2':
            manage_events()
        elif choice == '0':
            print("Goodbye.")
            break
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main_menu()

# ---------------------------------------------------------------------------
# Install dependencies:
#   pip install firebase-admin nltk numpy sentence-transformers \
#               google-generativeai python-dotenv requests
# ---------------------------------------------------------------------------
