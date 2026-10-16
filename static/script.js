import { initializeApp } from "https://www.gstatic.com/firebasejs/11.6.1/firebase-app.js";
import { getFirestore, onSnapshot, collection, query, orderBy } from "https://www.gstatic.com/firebasejs/11.6.1/firebase-firestore.js";

import * as fx from "./fx.js";

const API_ENDPOINT = '/api/v1/ask';
const firebaseConfig = {
    apiKey: window.env.FIREBASE_API_KEY,
    authDomain: `${window.env.FIREBASE_PROJECT_ID}.firebaseapp.com`,
    projectId: window.env.FIREBASE_PROJECT_ID,
    storageBucket: `${window.env.FIREBASE_PROJECT_ID}.firebasestorage.app`,
    messagingSenderId: "24452620493",
    appId: window.env.FIREBASE_APP_ID,
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

let globalEvents = [];
const EVENTS_COLLECTION_PATH = 'events';
let myKeyboard;
let currentDepartmentFilter = 'All';

let previousSectionId = 'home-section';

let isUnityLoaded = false;
let isUnityLoading = false;
let pendingMapSearchQuery = null;
window.unityInstance = null;
const BASE_UNITY_PATH = 'static/unity/';
const UNITY_LOADER_SCRIPT_PATH = BASE_UNITY_PATH + 'testMapWeb.loader.js';
const UNITY_FRAMEWORK_FILE = BASE_UNITY_PATH + 'testMapWeb.framework.js.unityweb';
const UNITY_DATA_FILE = BASE_UNITY_PATH + 'testMapWeb.data.unityweb';
const UNITY_WASM_FILE = BASE_UNITY_PATH + 'testMapWeb.wasm.unityweb';

let isProcessing = false;
const IDLE_TIMEOUT_MS = 5 * 60 * 1000;
let idleTimer;
let idleDismissing = false;
let previousNavTarget = 'home-section';
let mapSettled = Promise.resolve(); // resolves when the map-open animation has finished
let isKioskOnline = true;

const DEPARTMENT_MAP = {
    'All': 'All',
    'CCS': 'CCS',
    'CCA': 'CCA',
    'CBA': 'CBA',
    'CCJ': 'CCJ',
    'CEAS': 'CEAS',
    'CON': 'CON',
};

// --- DATA & HELPER FUNCTIONS ---
const locations = {
    "Admin Office": ["Admin Office - Clinic - 1st Floor", "Admin Office - ORE - 1st Floor", "Admin Office - Disciplinary Office - 2nd Floor"],
    "CCS Building": ["CCS Building - Faculty Room - 1st Floor", "CCS Building - Computer Laboratory"],
    "CCS Building B": [],
    "CCA Building": ["CCA Building - Faculty Room - 2nd Floor"],
    "CBA Building": ["CBA Building - Faculty Room - 3rd Floor"],
    "Multipurpose Building": ["Multipurpose - Canteen - Ground Floor", "Multipurpose - Scholarship Office - 2nd Floor"],
    "CCJE Building": ["CCJE Building - Faculty Room - 1st Floor", "CCJE Building - Lecture Room"],
    "CON Building": ["CON Building - Nursing Office"],
    "Registrar's Office": ["Registrar - 1st Floor", "Registrar - Library - 2nd Floor", "Registrar - Media 3rd Floor"]
};

const targetMap = {};
const targetNames = [];
Object.keys(locations).forEach(main => {
    targetMap[main] = main;
    targetNames.push(main);
    locations[main].forEach(sub => {
        targetMap[sub] = main;
        targetNames.push(sub);
    });
});

// Escapes HTML-significant characters so dynamic content (AI answers,
// Firestore event data) can be safely interpolated into innerHTML templates.
function escapeHtml(str) {
    return String(str ?? '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

function levenshtein(a, b) {
    if (!a.length) return b.length;
    if (!b.length) return a.length;
    const matrix = Array.from({ length: b.length + 1 }, () => []);
    for (let i = 0; i <= b.length; i++) matrix[i][0] = i;
    for (let j = 0; j <= a.length; j++) matrix[0][j] = j;
    for (let i = 1; i <= b.length; i++) {
        for (let j = 1; j <= a.length; j++) {
            matrix[i][j] = Math.min(matrix[i - 1][j] + 1, matrix[i][j - 1] + 1, matrix[i - 1][j - 1] + (a[j - 1] === b[i - 1] ? 0 : 1));
        }
    }
    return matrix[b.length][a.length];
}

function findClosestMatch(input) {
    let best = null, dist = Infinity;
    targetNames.forEach(name => {
        const d = levenshtein(input.toLowerCase(), name.toLowerCase());
        if (d < dist) { dist = d; best = name; }
    });
    return dist <= 3 ? best : null;
}

// --- IDLE TIMER ---
function resetIdleTimer(e) {
    clearTimeout(idleTimer);
    const idleOverlay = document.getElementById('idle-overlay');
    if (idleOverlay && !idleDismissing) {
        const style = getComputedStyle(idleOverlay);
        if (style.display !== 'none' && style.opacity !== '0') {
            idleDismissing = true;
            // Where the tap landed, so the ripple blooms from the finger.
            const p = e?.touches?.[0] ?? e;
            const point = p && Number.isFinite(p.clientX) ? { x: p.clientX, y: p.clientY } : null;
            navigateTo('home-section');
            fx.idleHide(idleOverlay, point).finally(() => { idleDismissing = false; });
        }
    }
    idleTimer = setTimeout(showIdleOverlay, IDLE_TIMEOUT_MS);
}

function showIdleOverlay() {
    const idleOverlay = document.getElementById('idle-overlay');
    if (idleOverlay) fx.idleShow(idleOverlay);
}

function updateButtonStatus(isOnline) {
    const selectors = ['.nav-button[data-target="ask-section"]', '.nav-button[data-target="map-section"]', '.quick-link-btn[data-target="ask-section"]'];
    selectors.forEach(sel => {
        const els = document.querySelectorAll(sel);
        els.forEach(el => {
            if (!isOnline) { el.disabled = true; el.style.opacity = '0.5'; }
            else { el.disabled = false; el.style.opacity = '1'; }
        });
    });
}

function checkNetworkStatus() {
    const statusEl = document.getElementById('network-status');
    const wasOnline = isKioskOnline;
    isKioskOnline = navigator.onLine;

    // Idle screen swaps between two prebuilt states instead of rewriting its
    // innerHTML (which used to destroy the clock elements).
    document.getElementById('idle-online')?.classList.toggle('hidden', !isKioskOnline);
    document.getElementById('idle-offline')?.classList.toggle('hidden', isKioskOnline);

    if (statusEl) {
        statusEl.classList.toggle('net-offline', !isKioskOnline);
        statusEl.classList.toggle('net-good', isKioskOnline);
        statusEl.innerHTML = isKioskOnline
            ? `<i class="material-icons" aria-hidden="true">signal_cellular_alt</i><span class="label">ONLINE</span>`
            : `<i class="material-icons" aria-hidden="true">signal_cellular_off</i><span class="label">OFFLINE</span>`;
    }
    if (wasOnline !== isKioskOnline && statusEl) fx.fadeIn(statusEl, { y: 0, duration: 0.5 });
    updateButtonStatus(isKioskOnline);
}

function updateDateTime() {
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    const el = document.getElementById('datetime');
    if (el) el.innerHTML = `${dateStr}<br>${timeStr}`;

    const longDate = now.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
    const setText = (id, text) => { const n = document.getElementById(id); if (n && n.textContent !== text) n.textContent = text; };
    setText('splash-time', timeStr);
    setText('splash-date', longDate);
    setText('home-time', timeStr);
    setText('home-date', longDate);

    const hour = now.getHours();
    setText('home-greeting', hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening');
}

function alertBox(message) {
    const container = document.getElementById('alertContainer');
    const existing = container.querySelector('.kiosk-alert');
    if (existing) existing.remove();

    const div = document.createElement('div');
    div.className = 'kiosk-alert';
    div.setAttribute('role', 'status');

    const lower = message.toLowerCase();
    let icon = 'info';
    if (lower.includes('error')) icon = 'error';
    if (lower.includes('success')) icon = 'check_circle';
    if (lower.includes('offline')) icon = 'cloud_off';
    if (lower.includes('emergency')) { icon = 'warning'; div.classList.add('danger'); }

    div.innerHTML = `<i class="material-icons" aria-hidden="true">${icon}</i><span>${escapeHtml(message)}</span>`;
    container.appendChild(div);
    fx.toastIn(div);

    const hold = lower.includes('emergency') ? 7000 : 3500;
    setTimeout(() => { fx.toastOut(div).then(() => div.remove()); }, hold);
}

// --- MAP & NAVIGATION ---
window.ShowDestinationInfo = function (jsonString) {
    try {
        const data = JSON.parse(jsonString);
        const titleEl = document.getElementById('infoTitle');
        const detailsEl = document.getElementById('infoDetails');
        const panelEl = document.getElementById('infoPanel');
        if (titleEl && detailsEl && panelEl) {
            titleEl.textContent = data.mainName || "Destination";
            let details = data.subLocations?.length > 0 ? data.subLocations.map(loc => `${loc.name} - ${loc.floor || ''}`).join('\n') : `Category: ${data.category || 'N/A'}`;
            detailsEl.innerText = details.trim();
            panelEl.classList.remove('hidden');
            fx.panelIn(panelEl);
        }
    } catch (e) { console.error(e); }
};

window.closeInfoPanel = function () {
    const panelEl = document.getElementById('infoPanel');
    if (panelEl && !panelEl.classList.contains('hidden')) {
        fx.panelOut(panelEl).then(() => panelEl.classList.add('hidden'));
    }
}

window.resetMapView = function () {
    resetIdleTimer();
    window.closeInfoPanel();
    if (window.unityInstance && window.unityInstance.SendMessage) window.unityInstance.SendMessage('Main Camera', 'ResetView', "");
    const mapInput = document.getElementById('searchMap');
    if (mapInput) mapInput.value = '';
    if (myKeyboard) myKeyboard.setInput('');
    document.getElementById("autocomplete-list").style.display = "none";
}

function loadUnityMap(initialSearchQuery = null) {
    if (isUnityLoaded) {
        if (initialSearchQuery) window.handleMapSearch(initialSearchQuery);
        return;
    }
    if (isUnityLoading) {
        // Already fetching Unity — remember this query and run it once the
        // instance is ready instead of re-entering the load path (which used
        // to recurse with handleMapSearch and blow the call stack).
        if (initialSearchQuery) pendingMapSearchQuery = initialSearchQuery;
        return;
    }
    if (!isKioskOnline) { alertBox("Offline: Cannot load map."); return; }

    isUnityLoading = true;
    window.closeInfoPanel();

    const loadingEl = document.getElementById('map-loading');
    const loadingText = document.getElementById('map-loading-text');
    const progressEl = document.getElementById('map-progress');
    loadingEl.classList.remove('hidden');
    loadingText.textContent = 'Preparing the map...';
    progressEl.style.transform = 'scaleX(0.04)';

    const failLoad = (detail) => {
        isUnityLoading = false;
        pendingMapSearchQuery = null;
        console.error('Unity Load Error:', detail);
        loadingText.textContent = 'The map could not be loaded. Close and try again.';
        alertBox("Failed to load map.");
    };

    // Only the stage is replaced; #infoPanel and #map-loading are siblings.
    const mapStage = document.getElementById('map-stage');
    mapStage.innerHTML = `<div id="unity-container" style="width:100%;height:100%"><canvas id="unity-canvas"></canvas></div>`;

    const startLoad = () => {
        const loaderScript = document.createElement('script');
        loaderScript.src = UNITY_LOADER_SCRIPT_PATH;
        loaderScript.onload = () => {
            loadingText.textContent = 'Loading the map...';
            createUnityInstance(document.querySelector("#unity-canvas"), {
                dataUrl: UNITY_DATA_FILE, frameworkUrl: UNITY_FRAMEWORK_FILE, codeUrl: UNITY_WASM_FILE,
                companyName: "DefaultCompany", productName: "CampusGuideKiosk", productVersion: "1.0",
                // Rendering at full device resolution is the biggest GPU cost on a kiosk panel.
                devicePixelRatio: Math.min(window.devicePixelRatio || 1, 1.5),
            }, (progress) => {
                progressEl.style.transform = `scaleX(${Math.max(0.04, progress)})`;
            }).then((instance) => {
                window.unityInstance = instance;
                isUnityLoaded = true;
                isUnityLoading = false;
                progressEl.style.transform = 'scaleX(1)';
                fx.fadeOut(loadingEl);
                // If the user already left the map while it loaded, don't burn GPU.
                if (document.getElementById('full-screen-map-wrapper').classList.contains('hidden')) setUnityRunning(false);
                const queuedQuery = initialSearchQuery || pendingMapSearchQuery;
                pendingMapSearchQuery = null;
                if (queuedQuery) window.handleMapSearch(queuedQuery);
            }).catch(failLoad);
        };
        loaderScript.onerror = () => failLoad('failed to fetch loader script');
        document.body.appendChild(loaderScript);
    };

    // Unity's startup blocks the main thread for a second or more. Let the map
    // open animation finish and paint a frame first so the transition stays smooth.
    mapSettled
        .then(() => new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve, 80))))
        .then(startLoad);
}

// Unity keeps rendering at full rate even when its canvas is hidden. Pause the
// emscripten main loop whenever the map is closed so the rest of the UI stays smooth.
function setUnityRunning(running) {
    const mod = window.unityInstance?.Module;
    try {
        if (running) mod?.resumeMainLoop?.();
        else mod?.pauseMainLoop?.();
    } catch (e) {
        console.warn('Could not change Unity run state:', e);
    }
}

function navigateTo(targetId, focusQuery = '') {
    const dashboardContainer = document.getElementById('dashboard-container');
    const mapWrapper = document.getElementById('full-screen-map-wrapper');
    const keyboardEl = document.getElementById("virtual-keyboard");
    const currentActiveBtn = document.querySelector('.nav-button.active');

    if (currentActiveBtn) {
        const cid = currentActiveBtn.getAttribute('data-target');
        if (cid !== 'map-section') previousSectionId = cid;
    }

    if (targetId === 'map-section') {
        if (!isKioskOnline) { alertBox("Offline: Cannot load map."); return; }
        const wasHidden = mapWrapper.classList.contains('hidden');
        mapWrapper.classList.remove('hidden');
        dashboardContainer.classList.add('hidden');
        if (wasHidden) {
            mapSettled = fx.mapIn(mapWrapper);
            setUnityRunning(true);
        }
        loadUnityMap();
        if (keyboardEl) keyboardEl.style.display = "none";
    } else {
        if (!mapWrapper.classList.contains('hidden')) setUnityRunning(false);
        mapWrapper.classList.add('hidden');
        dashboardContainer.classList.remove('hidden');
        document.querySelectorAll('.view-section').forEach(s => {
            if (s.parentElement === dashboardContainer) s.classList.add('hidden');
        });
        const target = document.getElementById(targetId);
        if (target) {
            target.classList.remove('hidden');
            fx.enterSection(target);
            if (targetId === 'events-section') { renderFilterButtons(); renderEvents(globalEvents); }
            if (targetId === 'ask-section') {
                const qi = document.getElementById('textQueryInput');
                if (qi && focusQuery) {
                    qi.value = focusQuery;
                    if (myKeyboard) myKeyboard.setInput(focusQuery);
                    handleTextInput();
                }
            }
        }
        if (keyboardEl) keyboardEl.style.display = "none";
    }
    document.querySelectorAll('.nav-button').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('data-target') === targetId) {
            btn.classList.add('active');
            btn.setAttribute('aria-current', 'page');
        } else {
            btn.removeAttribute('aria-current');
        }
    });
    const activeBtn = document.querySelector('.nav-button.active');
    fx.moveNavIndicator(activeBtn);
    if (activeBtn && activeBtn.getAttribute('data-target') !== previousNavTarget) fx.popNavIcon(activeBtn);
    previousNavTarget = activeBtn?.getAttribute('data-target') ?? null;
}

window.closeMap = function () {
    const keyboardEl = document.getElementById("virtual-keyboard");
    if (keyboardEl) keyboardEl.style.display = "none";
    window.closeInfoPanel();
    setUnityRunning(false);
    document.getElementById('full-screen-map-wrapper').classList.add('hidden');
    navigateTo(previousSectionId || 'home-section');
}

// --- EVENTS ---
function renderFilterButtons() {
    const container = document.getElementById('eventFilters');
    if (!container || container.children.length > 0) return;
    Object.keys(DEPARTMENT_MAP).forEach(key => {
        const btn = document.createElement('button');
        btn.className = `filter-chip ${key === 'All' ? 'active' : ''}`;
        btn.textContent = key;
        btn.onclick = () => {
            document.querySelectorAll('.filter-chip').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentDepartmentFilter = key;
            renderEvents(globalEvents);
        };
        container.appendChild(btn);
    });
    fx.bindPhysics(container);
}

function renderEvents(events) {
    const container = document.getElementById('eventsList');
    if (!container) return;
    container.innerHTML = '';
    let filtered = events;
    if (currentDepartmentFilter !== 'All') filtered = events.filter(e => e.department === currentDepartmentFilter);
    const startOfToday = new Date();
    startOfToday.setHours(0, 0, 0, 0);
    filtered = filtered.filter(e => new Date(e.date) >= startOfToday);

    if (filtered.length === 0) {
        container.innerHTML = `<div class="empty-state" style="grid-column: 1 / -1;"><i class="material-icons" aria-hidden="true">event_busy</i><p>No upcoming events for this filter.</p></div>`;
        fx.fadeIn(container.firstElementChild);
        return;
    }

    const todayStr = new Date().toDateString();
    container.innerHTML = filtered.map((event) => {
        const eventDate = new Date(event.date);
        const isToday = todayStr === eventDate.toDateString();
        const day = eventDate.getDate();
        const mon = eventDate.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
        const weekday = eventDate.toLocaleDateString('en-US', { weekday: 'long' });
        return `
            <article class="event-card">
                <div class="event-date" aria-hidden="true"><span class="day">${day}</span><span class="mon">${mon}</span></div>
                <div class="event-body">
                    <h3 class="event-title">${escapeHtml(event.title)}</h3>
                    <div class="event-meta">
                        <span class="badge">${escapeHtml(event.department)}</span>
                        <span>${weekday}</span>
                        ${isToday ? '<span class="badge today">TODAY</span>' : ''}
                    </div>
                </div>
            </article>`;
    }).join('');

    const cards = container.querySelectorAll('.event-card');
    fx.bindPhysics(container);
    fx.staggerIn(cards, { gap: 0.05, y: 18 });
}

// --- ASK AI ---
function handleTextInput() {
    resetIdleTimer();
    if (isProcessing) return; // ignore double-taps on Send while a request is in flight
    const inputField = document.getElementById('textQueryInput');
    const query = inputField.value.trim();
    if (query.length > 0) handleAsk(query);
    else alertBox("Please enter a question.");
}

window.handleAskClick = (query) => {
    const inputField = document.getElementById('textQueryInput');
    if (inputField) {
        inputField.value = query;
        if (myKeyboard) myKeyboard.setInput(query);
        handleTextInput();
    }
}

async function handleAsk(queryText) {
    const statusEl = document.getElementById('queryStatus');
    const answerContent = document.getElementById('answerContent');
    // Words are wrapped in spans so the answer can arrive word by word.
    const wordSpans = (text) => String(text ?? '').split(/(\s+)/)
        .map(w => /^\s+$/.test(w) || w === '' ? w : `<span class="w">${escapeHtml(w)}</span>`)
        .join('');
    const showAnswer = (html) => {
        answerContent.innerHTML = html;
        fx.fadeIn(answerContent.querySelector('.answer-kicker'), { y: 8, duration: 0.35 });
        fx.revealWords(answerContent.querySelector('.answer-text'));
        const chips = answerContent.querySelectorAll('.suggest-btn');
        if (chips.length) {
            fx.bindPhysics(answerContent);
            fx.staggerIn(chips, { delay: 0.5, gap: 0.07, y: 14 });
        }
        answerContent.scrollTop = 0;
    };

    if (!isKioskOnline) {
        showAnswer(`<div class="answer-error"><i class="material-icons" aria-hidden="true">cloud_off</i><p>Offline. Cannot process questions right now.</p></div>`);
        return;
    }

    isProcessing = true;
    if (statusEl) {
        statusEl.innerText = "Thinking...";
        statusEl.classList.add('busy');
    }

    answerContent.innerHTML = `
        <p class="answer-kicker">Thinking</p>
        <div class="skeleton" aria-hidden="true">
            <i style="width: 78%"></i><i style="width: 92%"></i><i style="width: 64%"></i>
        </div>`;
    fx.fadeIn(answerContent.querySelector('.skeleton'), { y: 8, duration: 0.3 });

    try {
        const response = await fetch(API_ENDPOINT, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: queryText }),
        });
        const data = await response.json();
        if (data.status === 'success' && data.data) {
            const matchScore = parseFloat(data.data.match_score) || 0;
            const isLowConfidence = matchScore < 0.7 && data.data.suggested_questions?.length > 0;

            if (isLowConfidence) {
                // Build buttons with a data-index instead of inline onclick="...('${q}')" —
                // a suggested question containing a `"` would otherwise break out of the
                // attribute and corrupt the markup, leaving the button non-functional.
                const suggestions = data.data.suggested_questions;
                const qList = suggestions.map((q, i) =>
                    `<button type="button" data-suggested-index="${i}" class="suggest-btn suggested-question-btn">${escapeHtml(q)}</button>`
                ).join('');
                showAnswer(`
                    <p class="answer-kicker"><i class="material-icons" aria-hidden="true">lightbulb</i>${matchScore > 0 ? `Not sure about this one (${(matchScore * 100).toFixed(0)}% match). Did you mean:` : 'No match found. Try one of these:'}</p>
                    <p class="answer-text">${wordSpans(data.data.response)}</p>
                    <div class="suggest-row">${qList}</div>`);
                answerContent.querySelectorAll('.suggested-question-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const q = suggestions[Number(btn.getAttribute('data-suggested-index'))];
                        if (q) window.handleAskClick(q);
                    });
                });
            } else {
                showAnswer(`
                    <p class="answer-kicker ok"><i class="material-icons" aria-hidden="true">check_circle</i>Answer</p>
                    <p class="answer-text">${wordSpans(data.data.response)}</p>`);
            }
        } else {
            showAnswer(`<div class="answer-error"><i class="material-icons" aria-hidden="true">error</i><p>Error: ${escapeHtml(data.message || 'Unknown error')}</p></div>`);
        }
    } catch (e) {
        console.error(e);
        showAnswer(`<div class="answer-error"><i class="material-icons" aria-hidden="true">wifi_off</i><p>Connection error. Please try again.</p></div>`);
    }
    finally {
        isProcessing = false;
        if (statusEl) {
            statusEl.classList.remove('busy');
            statusEl.innerText = "Ready";
        }
    }
}

// --- KEYBOARD & AUTOCOMPLETE ---
function setupKeyboard() {
    const isMobile = window.innerWidth < 768;
    if (isMobile) return;

    if (!window.SimpleKeyboard) return;
    const Keyboard = window.SimpleKeyboard.default;

    myKeyboard = new Keyboard({
        onChange: input => {
            const focusedInput = document.querySelector('.current-input:focus');
            if (focusedInput) {
                focusedInput.value = input;
                setTimeout(() => focusedInput.focus(), 150);
                if (focusedInput.id === 'searchMap') handleAutocomplete(input);
            }
        },
        onKeyPress: button => {
            if (button === "{enter}") {
                const focusedInput = document.querySelector('.current-input:focus');
                if (focusedInput?.id === 'searchMap') window.handleMapSearch(focusedInput.value);
                if (focusedInput?.id === 'textQueryInput') handleTextInput();
            }
        },
        layout: { 'default': ['q w e r t y u i o p', 'a s d f g h j k l', '{shift} z x c v b n m {backspace}', '{numbers} {space} {enter}'] }
    });

    const inputs = [document.getElementById('searchMap'), document.getElementById('textQueryInput')];
    const keyboardEl = document.getElementById("virtual-keyboard");

    inputs.forEach(inputEl => {
        if (!inputEl) return;
        inputEl.classList.add('current-input');
        inputEl.addEventListener('focus', () => {
            if (window.innerWidth >= 768) {
                keyboardEl.style.display = "block";
                setTimeout(() => myKeyboard.setInput(inputEl.value), 0);
            }
        });
        inputEl.addEventListener('input', (e) => {
            if (myKeyboard && window.innerWidth >= 768) {
                myKeyboard.setInput(e.target.value);
            }
            if (inputEl.id === 'searchMap') handleAutocomplete(e.target.value);
        });
    });

    document.addEventListener('click', (e) => {
        if (keyboardEl.style.display === "block") {
            const isInput = e.target.classList.contains('current-input');
            const isKeyboard = keyboardEl.contains(e.target);
            if (!isInput && !isKeyboard) keyboardEl.style.display = "none";
        }
        if (!e.target.closest('#searchMap') && !e.target.closest('#autocomplete-list')) {
            document.getElementById("autocomplete-list").style.display = "none";
        }
    });
}

function handleAutocomplete(val) {
    const listBox = document.getElementById("autocomplete-list");
    const input = document.getElementById("searchMap");
    listBox.innerHTML = "";
    if (!val || val.trim().length < 2) { listBox.style.display = "none"; return; }

    let matches = targetNames.filter(t => t.toLowerCase().includes(val.toLowerCase())).slice(0, 5);
    matches.forEach(name => {
        const div = document.createElement("div");
        div.className = "autocomplete-item";
        div.innerText = name;
        div.onclick = () => {
            input.value = name;
            if (myKeyboard) myKeyboard.setInput(name);
            listBox.style.display = "none";
            window.handleMapSearch(name);
        };
        listBox.appendChild(div);
    });
    listBox.style.display = matches.length ? "block" : "none";
}

window.handleMapSearch = (q) => {
    resetIdleTimer();
    const keyboardEl = document.getElementById("virtual-keyboard");
    if (keyboardEl) keyboardEl.style.display = "none";

    document.getElementById('searchMap').blur();
    document.getElementById("autocomplete-list").style.display = "none";
    window.closeInfoPanel();

    if (!q || q.trim() === "") return;
    if (!isKioskOnline) { alertBox("Offline."); return; }

    const lowerQ = q.toLowerCase();
    let match = targetNames.find(t => t.toLowerCase() === lowerQ) || findClosestMatch(q);

    if (!match) { alertBox(`Not found: "${q}"`); return; }

    const targetKey = targetMap[match];
    if (window.unityInstance && window.unityInstance.SendMessage) {
        window.unityInstance.SendMessage('MapManager', 'HighlightTarget', targetKey);
    } else {
        alertBox("Loading Map...");
        loadUnityMap(match);
    }
};

// --- INIT ---
// fx.js uses top-level await, so this module can finish evaluating AFTER
// DOMContentLoaded has already fired. Run init immediately in that case.
function init() {
    checkNetworkStatus();
    setInterval(checkNetworkStatus, 30000);
    updateDateTime();
    setInterval(updateDateTime, 1000);

    // Don't open a doomed Firestore listener when the project isn't configured
    // (it just spams 400s). Events then show their normal empty state.
    const pid = window.env.FIREBASE_PROJECT_ID;
    if (!pid || pid.startsWith('your_') || !window.env.FIREBASE_API_KEY || window.env.FIREBASE_API_KEY.startsWith('your_')) {
        console.warn('Firebase is not configured in .env (FIREBASE_API_KEY / FIREBASE_PROJECT_ID / FIREBASE_APP_ID). Events are disabled.');
    } else {
        const q = query(collection(db, EVENTS_COLLECTION_PATH), orderBy("date"));
        onSnapshot(q, (snapshot) => {
            globalEvents = [];
            snapshot.forEach((doc) => { globalEvents.push({ id: doc.id, ...doc.data() }); });
            if (!document.getElementById('events-section').classList.contains('hidden')) renderEvents(globalEvents);
        }, (err) => {
            console.error('Events listener error:', err.code || err.message);
        });
    }

    if (window.SimpleKeyboard) setupKeyboard();

    // Motion: press/hover physics, nav indicator, idle ambience, first entrance
    fx.bindPhysics();
    const placeIndicator = (instant) => fx.moveNavIndicator(document.querySelector('.nav-button.active'), { instant });
    placeIndicator(true);
    document.fonts?.ready.then(() => placeIndicator(true));
    window.addEventListener('resize', () => placeIndicator(true));
    fx.bindSpotlight();
    fx.idleIntro();
    fx.startIdleAmbient();
    fx.rotateText(
        document.getElementById('ask-rotator'),
        ['Ask the Campus Guide', 'Where is the Clinic?', 'What are the library hours?', 'How do I enroll?'],
        { every: 4200 },
    );
    fx.enterSection(document.getElementById('home-section'));

    // Empty-state suggestion chips in Ask AI
    document.querySelectorAll('.suggest-btn[data-ask]').forEach(btn => {
        btn.addEventListener('click', () => window.handleAskClick(btn.getAttribute('data-ask')));
    });

    document.getElementById('idle-overlay').addEventListener('click', resetIdleTimer);
    document.addEventListener('click', resetIdleTimer);
    document.addEventListener('touchstart', resetIdleTimer, { passive: true });

    document.querySelectorAll('.nav-button').forEach(btn => {
        btn.addEventListener('click', () => {
            if (!btn.disabled) {
                navigateTo(btn.getAttribute('data-target'));
            }
        });
        btn.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                if (!btn.disabled) navigateTo(btn.getAttribute('data-target'));
            }
        });
    });

    document.querySelectorAll('.quick-link-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const t = btn.getAttribute('data-target');
            if (t === 'emergency') {
                alertBox("Emergency: call 911 immediately");
                return;
            }
            navigateTo(t, btn.getAttribute('data-query'));
            if (t === 'map-section') {
                const loc = btn.getAttribute('data-location');
                if (loc) {
                    document.getElementById('searchMap').value = loc;
                    window.handleMapSearch(loc);
                }
            }
        });
    });

    const textQuerySubmit = document.getElementById('textQuerySubmit');
    if (textQuerySubmit) {
        textQuerySubmit.addEventListener('click', handleTextInput);
        textQuerySubmit.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleTextInput();
            }
        });
    }
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();