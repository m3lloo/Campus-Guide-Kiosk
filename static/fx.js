// Motion layer for the kiosk (motion.dev, self-hosted in static/vendor/motion.js).
//
// Every animation here has a job:
//   hierarchy  - staggered entrances reveal content in reading order
//   feedback   - press / hover physics acknowledge a touch
//   state      - the nav indicator and section swaps show where you went
//   waiting    - the idle ring invites a tap, word reveal paces a new answer
//
// Safe by design: if the library fails to load or the user prefers reduced
// motion, every function becomes a no-op and the UI is simply static.

let M = null;
try {
    M = await import('./vendor/motion.js');
} catch (e) {
    console.warn('Motion failed to load, running without animation.', e);
}

const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
const live = () => M && !reducedQuery.matches;

const SPRING = { type: 'spring', stiffness: 260, damping: 28 };
const SPRING_SOFT = { type: 'spring', stiffness: 170, damping: 24 };
const EASE_OUT = [0.16, 1, 0.3, 1];

const done = Promise.resolve();
const toList = (x) => (x instanceof Element ? [x] : Array.from(x || []));

/** Fade + rise a set of elements in sequence (hierarchy). */
export function staggerIn(targets, { delay = 0, gap = 0.06, y = 22 } = {}) {
    const els = toList(targets);
    if (!live() || els.length === 0) return done;
    return M.animate(
        els,
        { opacity: [0, 1], y: [y, 0] },
        { delay: M.stagger(gap, { startDelay: delay }), duration: 0.65, ease: EASE_OUT },
    ).finished;
}

/** Enter a section: its [data-reveal] blocks cascade in. */
export function enterSection(section) {
    if (!section) return done;
    const blocks = section.querySelectorAll('[data-reveal]');
    return staggerIn(blocks.length ? blocks : section, { gap: 0.055 });
}

/** Fade a section's contents when there is no [data-reveal] markup. */
export function fadeIn(el, { y = 12, duration = 0.4 } = {}) {
    if (!live() || !el) return done;
    return M.animate(el, { opacity: [0, 1], y: [y, 0] }, { duration, ease: EASE_OUT }).finished;
}

/** Slide the single gold pill behind the active nav button. */
export function moveNavIndicator(button, { instant = false } = {}) {
    const indicator = document.getElementById('nav-indicator');
    const rail = document.getElementById('nav-rail');
    if (!indicator || !button) return;

    indicator.style.width = `${button.offsetWidth}px`;
    indicator.style.height = `${button.offsetHeight}px`;
    const x = button.offsetLeft;
    const y = button.offsetTop;

    if (!live()) {
        // Static placement without the library: still correct, just instant.
        indicator.style.transform = `translate(${x}px, ${y}px)`;
        indicator.style.opacity = '1';
        rail?.classList.add('has-indicator');
        return;
    }

    rail?.classList.add('has-indicator');
    if (instant) {
        M.animate(indicator, { x, y, opacity: 1 }, { duration: 0 });
    } else {
        M.animate(indicator, { x, y, opacity: 1 }, SPRING);
    }
}

/** Touch feedback: tiles/buttons dip on press, lift on hover. */
export function bindPhysics(root = document) {
    if (!M) return;
    const targets = root.querySelectorAll('.tile, .ask-bar, .btn, .suggest-btn, .event-card, .filter-chip, .nav-button');
    targets.forEach((el) => {
        if (el.dataset.physics) return;
        el.dataset.physics = '1';

        M.press(el, () => {
            if (!live()) return;
            M.animate(el, { scale: 0.965 }, { type: 'spring', stiffness: 520, damping: 30 });
            return () => {
                if (live()) M.animate(el, { scale: 1 }, { type: 'spring', stiffness: 380, damping: 18 });
            };
        });

        if (el.matches('.tile, .event-card, .suggest-btn')) {
            M.hover(el, () => {
                if (!live()) return;
                M.animate(el, { y: -4 }, SPRING);
                return () => live() && M.animate(el, { y: 0 }, SPRING);
            });
        }
    });
}

/**
 * Cross-fade a line of text through a list of phrases (state: "here is what
 * you can do"). Returns a stop function. Skips ticks while the element is not
 * visible, so it costs nothing when the screen is not on show.
 */
export function rotateText(el, phrases, { every = 3800 } = {}) {
    if (!el || phrases.length < 2) return () => {};
    let i = 0;
    let busy = false;
    const timer = setInterval(async () => {
        if (busy || document.hidden || !el.offsetParent) return;
        busy = true;
        i = (i + 1) % phrases.length;
        if (live()) await M.animate(el, { opacity: 0, y: -10 }, { duration: 0.28, ease: EASE_OUT }).finished;
        el.textContent = phrases[i];
        if (live()) await M.animate(el, { opacity: [0, 1], y: [12, 0] }, { duration: 0.5, ease: EASE_OUT }).finished;
        busy = false;
    }, every);
    return () => clearInterval(timer);
}

/** Idle overlay: ambient light and an invitation to tap, until dismissed. */
let idleLoops = [];
let stopHint = () => {};

const IDLE_HINTS = [
    'Find the Registrar',
    'See what is on this week',
    'Ask anything about campus',
    'Check the library hours',
];

export function startIdleAmbient() {
    stopIdleAmbient();
    if (!live()) return;

    // Slow drifting light. Long durations + transform only = calm and cheap.
    const drift = (sel, path, duration) => {
        const el = document.querySelector(sel);
        if (el) idleLoops.push(M.animate(el, path, { duration, repeat: Infinity, ease: 'easeInOut' }));
    };
    drift('.idle-orb.a', { x: [0, -90, 40, 0], y: [0, 70, -30, 0], scale: [1, 1.08, 0.96, 1] }, 34);
    drift('.idle-orb.b', { x: [0, 80, -50, 0], y: [0, -60, 40, 0], scale: [1, 0.95, 1.1, 1] }, 40);

    document.querySelectorAll('#touch-mark .ring').forEach((ring, i) => {
        idleLoops.push(
            M.animate(
                ring,
                { scale: [1, 1.9], opacity: [0.55, 0] },
                { duration: 2.6, delay: i * 1.3, repeat: Infinity, ease: 'easeOut' },
            ),
        );
    });
    const mark = document.getElementById('touch-mark');
    if (mark) {
        idleLoops.push(
            M.animate(mark, { scale: [1, 1.05, 1] }, { duration: 3.2, repeat: Infinity, ease: 'easeInOut' }),
        );
    }

    const hint = document.getElementById('idle-hint');
    if (hint) {
        hint.textContent = IDLE_HINTS[0];
        stopHint = rotateText(hint, IDLE_HINTS, { every: 3400 });
    }
}

export function stopIdleAmbient() {
    idleLoops.forEach((a) => a.stop());
    idleLoops = [];
    stopHint();
    stopHint = () => {};
}

/** Idle intro: title lines rise from a mask, mark springs in, clock fades. */
export function idleIntro() {
    if (!live()) return;
    M.animate('.idle-title .line-in', { y: ['112%', '0%'] }, { delay: M.stagger(0.09, { startDelay: 0.12 }), duration: 0.9, ease: EASE_OUT });
    M.animate('#touch-mark', { opacity: [0, 1], scale: [0.55, 1] }, { type: 'spring', stiffness: 170, damping: 15, delay: 0.05 });
    M.animate('#idle-sub', { opacity: [0, 1], y: [16, 0] }, { delay: 0.45, duration: 0.7, ease: EASE_OUT });
    M.animate('#idle-hint', { opacity: [0, 1], y: [16, 0] }, { delay: 0.6, duration: 0.7, ease: EASE_OUT });
    M.animate('#idle-clock', { opacity: [0, 1], y: [-14, 0] }, { delay: 0.25, duration: 0.8, ease: EASE_OUT });
}

export function idleShow(overlay) {
    overlay.style.display = 'flex';
    overlay.style.pointerEvents = 'auto';
    startIdleAmbient();
    if (!live()) {
        overlay.style.opacity = '1';
        return done;
    }
    idleIntro();
    return M.animate(overlay, { opacity: [0, 1], scale: [1.03, 1] }, { duration: 0.7, ease: EASE_OUT }).finished;
}

/** Dismiss: a gold ripple blooms from the tap while the screen eases away. */
export async function idleHide(overlay, point) {
    overlay.style.pointerEvents = 'none';
    if (live()) {
        if (point && Number.isFinite(point.x)) {
            const ripple = document.createElement('div');
            ripple.className = 'tap-ripple';
            ripple.style.left = `${point.x}px`;
            ripple.style.top = `${point.y}px`;
            document.body.appendChild(ripple);
            M.animate(ripple, { scale: [0.1, 9], opacity: [1, 0] }, { duration: 0.9, ease: EASE_OUT })
                .finished.then(() => ripple.remove());
        }
        await M.animate(overlay, { opacity: 0, scale: 1.045 }, { duration: 0.6, ease: EASE_OUT }).finished;
    }
    overlay.style.opacity = '0';
    overlay.style.display = 'none';
    overlay.style.pointerEvents = 'auto';
    if (M) M.animate(overlay, { scale: 1 }, { duration: 0 });
    stopIdleAmbient();
}

/** Mouse-only spotlight that follows the pointer across a tile. */
export function bindSpotlight(root = document) {
    if (!window.matchMedia('(hover: hover)').matches) return;
    root.querySelectorAll('.tile').forEach((tile) => {
        if (tile.dataset.spot) return;
        tile.dataset.spot = '1';
        let raf = 0;
        tile.addEventListener('pointermove', (e) => {
            if (e.pointerType !== 'mouse' || raf) return;
            raf = requestAnimationFrame(() => {
                raf = 0;
                const r = tile.getBoundingClientRect();
                tile.style.setProperty('--mx', `${e.clientX - r.left}px`);
                tile.style.setProperty('--my', `${e.clientY - r.top}px`);
            });
        });
    });
}

/** A small pop on the icon of the tab you just selected. */
export function popNavIcon(button) {
    const icon = button?.querySelector('.material-icons');
    if (!icon || !live()) return;
    M.animate(icon, { scale: [1, 1.28, 1], y: [0, -4, 0] }, { duration: 0.5, ease: EASE_OUT });
}

/** Map overlay opens with a gentle scale-in (state transition). */
export function mapIn(wrapper) {
    if (!live()) return done;
    return M.animate(wrapper, { opacity: [0, 1], scale: [0.98, 1] }, { duration: 0.5, ease: EASE_OUT }).finished;
}

/** Fade an element out, then take it out of layout. */
export async function fadeOut(el, { duration = 0.45 } = {}) {
    if (!el) return;
    if (live()) await M.animate(el, { opacity: 0 }, { duration, ease: EASE_OUT }).finished;
    el.classList.add('hidden');
    el.style.opacity = '';
}

/** Floating panels spring up from below. */
export function panelIn(el) {
    if (!live()) return done;
    return M.animate(el, { opacity: [0, 1], y: [28, 0], scale: [0.97, 1] }, SPRING_SOFT).finished;
}

export async function panelOut(el) {
    if (live()) await M.animate(el, { opacity: 0, y: 16 }, { duration: 0.25, ease: EASE_OUT }).finished;
}

/** Toast: spring in, auto-dismiss out. Returns a dismiss function. */
export function toastIn(el) {
    if (!live()) return done;
    return M.animate(el, { opacity: [0, 1], x: [48, 0], scale: [0.96, 1] }, SPRING).finished;
}

export async function toastOut(el) {
    if (live()) await M.animate(el, { opacity: 0, x: 32 }, { duration: 0.25, ease: EASE_OUT }).finished;
}

/** Answer reveal: words arrive one by one so the reader can follow along. */
export function revealWords(container) {
    const words = container?.querySelectorAll('.w');
    if (!words || words.length === 0 || !live()) return done;
    // Cap total time so long answers never feel slow.
    const gap = Math.min(0.045, 1.1 / words.length);
    return M.animate(
        words,
        { opacity: [0, 1], y: [10, 0] },
        { delay: M.stagger(gap), duration: 0.45, ease: EASE_OUT },
    ).finished;
}

export const motionReady = () => !!M;
export const onReducedMotionChange = (fn) => reducedQuery.addEventListener('change', fn);
