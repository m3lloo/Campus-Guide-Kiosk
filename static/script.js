import { initializeApp } from "https://www.gstatic.com/firebasejs/11.6.1/firebase-app.js";
import { getFirestore, onSnapshot, collection, query, orderBy } from "https://www.gstatic.com/firebasejs/11.6.1/firebase-firestore.js";

const API_ENDPOINT = '/api/v1/ask';
const firebaseConfig = {
    apiKey: window.env.FIREBASE_API_KEY,
    authDomain: `${window.env.FIREBASE_PROJECT_ID}.firebaseapp.com`,
    projectId: window.env.FIREBASE_PROJECT_ID,
    storageBucket: `${window.env.FIREBASE_PROJECT_ID}.firebasestorage.app`,
    messagingSenderId: "595009798998",
    appId: window.env.FIREBASE_APP_ID,
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

let globalEvents = [];
const EVENTS_COLLECTION_PATH = 'events';
let myKeyboard;
let currentDepartmentFilter = 'All';

let previousSectionId = 'home-section';
let currentAlertTimer = null;

let isUnityLoaded = false;
window.unityInstance = null;
const BASE_UNITY_PATH = 'static/unity/';
const UNITY_LOADER_SCRIPT_PATH = BASE_UNITY_PATH + 'testMapWeb.loader.js';
const UNITY_FRAMEWORK_FILE = BASE_UNITY_PATH + 'testMapWeb.framework.js.unityweb';
const UNITY_DATA_FILE = BASE_UNITY_PATH + 'testMapWeb.data.unityweb';
const UNITY_WASM_FILE = BASE_UNITY_PATH + 'testMapWeb.wasm.unityweb';

let isProcessing = false;
const IDLE_TIMEOUT_MS = 5 * 60 * 1000;
let idleTimer;
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
function resetIdleTimer() {
    clearTimeout(idleTimer);
    const idleOverlay = document.getElementById('idle-overlay');
    if (idleOverlay) {
        const style = getComputedStyle(idleOverlay);
        if (style.display !== 'none' && style.opacity !== '0') {
            idleOverlay.style.opacity = '0';
            idleOverlay.style.pointerEvents = 'none';
            setTimeout(() => {
                idleOverlay.style.display = 'none';
                idleOverlay.style.pointerEvents = 'auto';
            }, 500);
            navigateTo('home-section');
        }
    }
    idleTimer = setTimeout(showIdleOverlay, IDLE_TIMEOUT_MS);
}

function showIdleOverlay() {
    const idleOverlay = document.getElementById('idle-overlay');
    if (idleOverlay) {
        idleOverlay.style.display = 'flex';
        void idleOverlay.offsetWidth;
        idleOverlay.style.opacity = '1';
        idleOverlay.style.pointerEvents = 'auto';
    }
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

    const idleOverlay = document.getElementById('idle-overlay');

    if (!isKioskOnline) {
        if (statusEl) {
            statusEl.className = 'w-full text-center py-4 px-1 leading-tight border-b border-gray-700 mt-2 net-offline hidden md:block';
            statusEl.innerHTML = `<i class="material-icons text-3xl mb-1">signal_cellular_off</i><span class="text-xs font-bold tracking-widest block">OFFLINE</span>`;
        }
        if (idleOverlay && idleOverlay.style.display !== 'none') {
            idleOverlay.innerHTML = `<i class="material-icons text-red-500 text-6xl md:text-[10rem] mb-6">cloud_off</i><h1 class="text-3xl md:text-7xl font-extrabold mb-4 text-red-500">OFFLINE</h1><p class="text-xl md:text-4xl text-gray-300">Check internet connection.</p>`;
        }
    } else {
        if (statusEl) {
            statusEl.className = 'w-full text-center py-4 px-1 leading-tight border-b border-gray-700 mt-2 net-good hidden md:block';
            statusEl.innerHTML = `<i class="material-icons text-3xl mb-1">signal_cellular_alt</i><span class="text-xs font-bold tracking-widest block">ONLINE</span>`;
        }
        if (!wasOnline && idleOverlay && idleOverlay.querySelector('.text-red-500')) {
            idleOverlay.innerHTML = `
                <div class="absolute top-6 right-6 md:top-12 md:right-12 text-right">
                    <div id="splash-time" class="text-5xl md:text-8xl font-bold text-white mb-2">--:--</div>
                </div>
                <i class="material-icons text-8xl md:text-[10rem] mb-6 animate-pulse" style="color: var(--primary-neon);">touch_app</i>
                <h1 class="text-4xl md:text-7xl font-extrabold mb-4" style="color: var(--secondary-neon);">Campus Guide</h1>
                <p class="text-xl md:text-4xl text-gray-300">Tap anywhere to start</p>`;
        }
    }
    updateButtonStatus(isKioskOnline);
}

function updateDateTime() {
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    const el = document.getElementById('datetime');
    if (el) el.innerHTML = `${dateStr}<br>${timeStr}`;
    const splashTime = document.getElementById('splash-time');
    if (splashTime) splashTime.innerText = timeStr;
}

function alertBox(message) {
    const container = document.getElementById('alertContainer');
    const existing = container.querySelector('.kiosk-alert');
    if (existing) existing.remove();

    const div = document.createElement('div');
    div.className = 'kiosk-alert';

    let icon = 'info';
    if (message.toLowerCase().includes('error')) icon = 'error';
    if (message.toLowerCase().includes('success')) icon = 'check_circle';
    if (message.toLowerCase().includes('offline')) icon = 'cloud_off';
    if (message.toLowerCase().includes('emergency')) icon = 'warning';

    // Icon color uses primary crimson
    div.innerHTML = `<i class="material-icons mr-2" style="font-size: 1.5rem; color: var(--primary-neon);">${icon}</i><span>${message}</span>`;
    container.appendChild(div);

    setTimeout(() => {
        if (div) {
            div.style.animation = 'fadeOutSlide 0.3s ease-out forwards';
            setTimeout(() => div.remove(), 300);
        }
    }, 3500);
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
            panelEl.style.opacity = '1';
        }
    } catch (e) { console.error(e); }
};

window.closeInfoPanel = function () {
    const panelEl = document.getElementById('infoPanel');
    if (panelEl) {
        panelEl.style.opacity = '0';
        setTimeout(() => panelEl.classList.add('hidden'), 300);
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
    if (!isKioskOnline) { alertBox("Offline: Cannot load map."); return; }

    window.closeInfoPanel();
    const mapPlaceholder = document.getElementById('mapPlaceholder');
    mapPlaceholder.innerHTML = `<div id="unity-container" class="w-full h-full"><canvas id="unity-canvas" class="w-full h-full" style="background-color: #121212;"></canvas></div>`;

    const loaderScript = document.createElement('script');
    loaderScript.src = UNITY_LOADER_SCRIPT_PATH;
    loaderScript.onload = () => {
        createUnityInstance(document.querySelector("#unity-canvas"), {
            dataUrl: UNITY_DATA_FILE, frameworkUrl: UNITY_FRAMEWORK_FILE, codeUrl: UNITY_WASM_FILE,
            companyName: "DefaultCompany", productName: "CampusGuideKiosk", productVersion: "1.0",
        }).then((instance) => {
            window.unityInstance = instance;
            isUnityLoaded = true;
            if (initialSearchQuery) window.handleMapSearch(initialSearchQuery);
        }).catch((m) => console.error("Unity Load Error:", m));
    };
    document.body.appendChild(loaderScript);
    isUnityLoaded = true;
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
        mapWrapper.classList.remove('hidden');
        dashboardContainer.classList.add('hidden');
        loadUnityMap();
        if (keyboardEl) keyboardEl.style.display = "none";
    } else {
        mapWrapper.classList.add('hidden');
        dashboardContainer.classList.remove('hidden');
        document.querySelectorAll('.view-section').forEach(s => {
            if (s.parentElement === dashboardContainer) {
                s.classList.add('hidden');
                s.classList.remove('animate-fade-in');
            }
        });
        const target = document.getElementById(targetId);
        if (target) {
            target.classList.remove('hidden');
            void target.offsetWidth;
            target.classList.add('animate-fade-in');
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
}

window.closeMap = function () {
    const keyboardEl = document.getElementById("virtual-keyboard");
    if (keyboardEl) keyboardEl.style.display = "none";
    window.closeInfoPanel();
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
}

function renderEvents(events) {
    const container = document.getElementById('eventsList');
    if (!container) return;
    container.innerHTML = '';
    let filtered = events;
    if (currentDepartmentFilter !== 'All') filtered = events.filter(e => e.department === currentDepartmentFilter);
    const now = new Date();
    filtered = filtered.filter(e => new Date(e.date) >= new Date(now.setHours(0, 0, 0, 0)));

    if (filtered.length === 0) {
        container.innerHTML = `<div class="p-8 text-center border-2 border-dashed border-gray-700 rounded-xl" style="color: #9ca3af;"><i class="material-icons text-4xl mb-2" style="color: #6b7280;">event_note</i><p class="text-lg md:text-2xl">No events found for this filter.</p></div>`;
        return;
    }

    filtered.forEach((event, index) => {
        const eventDate = new Date(event.date);
        const dateStr = eventDate.toDateString();
        const isToday = new Date().toDateString() === eventDate.toDateString();
        const todayBadge = isToday ? `<span class="text-xs px-2 py-1 rounded font-bold ml-2" style="background-color: var(--primary-neon);">TODAY</span>` : '';

        container.innerHTML += `
            <div class="p-4 md:p-6 rounded-xl shadow-lg border-l-8 transition-all hover:shadow-xl hover:translate-x-1 focus-within:ring-2 animate-fade-in"
                 style="background-color: #2D2D2D; border-left-color: var(--purple-neon); animation-delay: ${index * 50}ms;">
                <div class="flex items-start justify-between gap-4">
                    <div class="flex-1 min-w-0">
                        <h3 class="font-extrabold text-xl md:text-2xl text-white truncate">${event.title}</h3>
                        <div class="flex items-center text-gray-300 mt-2 flex-wrap gap-2">
                            <span class="text-sm px-2 py-1 rounded font-bold" style="background-color: #3a3a3a; color: var(--purple-neon);">${event.department}</span>
                            <span class="text-sm md:text-lg flex items-center"><i class="material-icons" style="font-size: 1rem; margin-right: 4px;">calendar_today</i>${dateStr}</span>
                            ${todayBadge}
                        </div>
                    </div>
                </div>
            </div>`;
    });
}

// --- ASK AI ---
function handleTextInput() {
    resetIdleTimer();
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
    if (!isKioskOnline) {
        answerContent.innerHTML = `<div class="flex items-center"><i class="material-icons mr-3" style="color: #f87171;">cloud_off</i><p class="text-lg md:text-2xl" style="color: #f87171;">Offline mode - Cannot process queries.</p></div>`;
        return;
    }

    isProcessing = true;
    if (statusEl) {
        statusEl.innerText = "Thinking...";
        statusEl.classList.add('animate-pulse');
        statusEl.style.color = '#FEE700';
    }

    answerContent.innerHTML = `
        <div class="animate-pulse">
            <div class="h-4 rounded w-3/4 mb-4" style="background-color: #3a3a3a;"></div>
            <div class="h-4 rounded w-5/6 mb-4" style="background-color: #3a3a3a;"></div>
            <div class="h-4 rounded w-4/5 mb-4" style="background-color: #3a3a3a;"></div>
            <div class="h-8 rounded w-1/2 mt-8" style="background-color: #3a3a3a;"></div>
        </div>
    `;

    try {
        const response = await fetch(API_ENDPOINT, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: queryText }),
        });
        const data = await response.json();
        if (data.success) {
            if (data.suggested_questions?.length > 0) {
                const qList = data.suggested_questions.map(q =>
                    `<button onclick="window.handleAskClick('${q.replace(/'/g, "\\'")}')"
                        class="text-left w-full p-2 md:p-4 my-2 rounded-lg block text-lg font-semibold border-l-4 transition-all focus:outline-none"
                        style="background-color: #3a3a3a; border-left-color: var(--secondary-neon); color: white;"
                        onmouseover="this.style.backgroundColor='#4a4a4a'" onmouseout="this.style.backgroundColor='#3a3a3a'">${q}</button>`
                ).join('');
                answerContent.innerHTML = `
                    <h4 class="text-sm font-bold mb-2 flex items-center" style="color: var(--secondary-neon);">
                        <i class="material-icons mr-2" style="font-size: 1.2rem;">lightbulb</i>Low Confidence - Suggested Questions:
                    </h4>
                    <p class="text-white text-xl md:text-3xl mb-4">${data.response}</p>
                    <div class="flex flex-col gap-2">${qList}</div>`;
            } else {
                answerContent.innerHTML = `
                    <h4 class="text-sm font-bold mb-2 flex items-center" style="color: var(--purple-neon);">
                        <i class="material-icons mr-2" style="font-size: 1.2rem;">check_circle</i>Answer
                    </h4>
                    <p class="text-white text-xl md:text-3xl leading-relaxed">${data.response}</p>`;
            }
        } else {
            answerContent.innerHTML = `<div class="flex items-center" style="color: #f87171;"><i class="material-icons mr-3" style="font-size: 1.5rem;">error</i><p class="text-lg md:text-2xl">Error: ${data.response}</p></div>`;
        }
    } catch (e) {
        console.error(e);
        answerContent.innerHTML = `<div class="flex items-center" style="color: #f87171;"><i class="material-icons mr-3" style="font-size: 1.5rem;">wifi_off</i><p class="text-lg md:text-2xl">Connection Error. Please try again.</p></div>`;
    }
    finally {
        isProcessing = false;
        if (statusEl) {
            statusEl.classList.remove('animate-pulse');
            statusEl.innerText = "Ready";
            statusEl.style.color = 'var(--purple-neon)';
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
document.addEventListener('DOMContentLoaded', () => {
    checkNetworkStatus();
    setInterval(checkNetworkStatus, 30000);
    updateDateTime();
    setInterval(updateDateTime, 1000);

    const q = query(collection(db, EVENTS_COLLECTION_PATH), orderBy("date"));
    onSnapshot(q, (snapshot) => {
        globalEvents = [];
        snapshot.forEach((doc) => { globalEvents.push({ id: doc.id, ...doc.data() }); });
        if (!document.getElementById('events-section').classList.contains('hidden')) renderEvents(globalEvents);
    });

    if (window.SimpleKeyboard) setupKeyboard();

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
        btn.addEventListener('click', (e) => {
            const t = btn.getAttribute('data-target');
            if (t === 'emergency') {
                alertBox("🚨 Emergency: Call 911 immediately");
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
});