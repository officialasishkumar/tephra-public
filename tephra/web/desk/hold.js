// Hold-to-confirm (docs/UI-DESIGN.md 10.5). Press and hold for --dur-hold: a fill sweeps
// across; at full the label reads "Release to approve" and releasing inside the button
// completes it (the up-event decides, WCAG 2.5.2). A tap, Enter, Space or an assistive
// technology click never approves: it calls onTap, which opens a confirmation step (the
// single-pointer alternative, WCAG 2.5.7). Sliding off or pointercancel resets.

import { el, icon } from './dom.js';

const HOLD_MS = 1200; // --dur-hold; kept under reduced motion as essential feedback
const TAP_MS = 250;
export const EARLY_RELEASE_HINT = 'Keep holding to approve, or tap for a confirmation step.';

// `label` is a string, or a function returning nodes (so parts of it can be kept unbroken).
export function holdButton({ label, iconId = 'i-check', className = 'approve', onHold, onTap, onEarlyRelease }) {
  const text = el('span', { class: 'approve__label' });
  // Swapped by hiding, not by replacing nodes: a click is lost when the node pressed is removed.
  const armedText = el('span', { class: 'approve__label', text: 'Release to approve', hidden: true });
  const showLabel = () => {
    if (typeof label === 'function') text.replaceChildren(...label());
    else text.textContent = label;
  };
  showLabel();
  const button = el('button', { type: 'button', class: className }, iconId ? icon(iconId) : null, text, armedText);
  let phase = 'idle'; // idle | holding | armed
  let started = 0;
  let frame = 0;
  let suppressClick = false;

  const blocked = () =>
    button.disabled || button.getAttribute('aria-disabled') === 'true' || button.dataset.busy === 'true';

  function paint() {
    if (phase === 'idle') return;
    const progress = Math.min(1, (performance.now() - started) / HOLD_MS);
    button.style.setProperty('--hold', progress.toFixed(3));
    if (progress >= 1 && phase === 'holding') {
      phase = 'armed';
      button.classList.add('is-armed');
      text.hidden = true;
      armedText.hidden = false;
    }
    if (phase === 'holding') frame = requestAnimationFrame(paint);
  }

  function reset() {
    cancelAnimationFrame(frame);
    phase = 'idle';
    button.classList.remove('is-holding', 'is-armed');
    button.style.setProperty('--hold', '0');
    text.hidden = false;
    armedText.hidden = true;
  }

  button.addEventListener('pointerdown', (event) => {
    suppressClick = false;
    if (blocked() || !event.isPrimary || event.button !== 0) return;
    // Touch pointers are captured by default, which would hide a slide off the button.
    if (button.hasPointerCapture(event.pointerId)) button.releasePointerCapture(event.pointerId);
    phase = 'holding';
    started = performance.now();
    button.classList.add('is-holding');
    frame = requestAnimationFrame(paint);
  });

  button.addEventListener('pointermove', (event) => {
    if (phase === 'idle') return;
    const r = button.getBoundingClientRect();
    const inside =
      event.clientX >= r.left && event.clientX <= r.right && event.clientY >= r.top && event.clientY <= r.bottom;
    if (!inside) {
      suppressClick = true;
      reset();
    }
  });

  button.addEventListener('pointerup', () => {
    if (phase === 'idle') return;
    const held = performance.now() - started;
    const armed = phase === 'armed' || held >= HOLD_MS;
    reset();
    if (armed) {
      suppressClick = true;
      onHold();
    } else if (held >= TAP_MS) {
      suppressClick = true;
      if (onEarlyRelease) onEarlyRelease(EARLY_RELEASE_HINT);
    }
    // A short tap falls through to the click event below.
  });

  for (const name of ['pointerleave', 'pointercancel']) {
    button.addEventListener(name, () => {
      if (phase === 'idle') return;
      suppressClick = true;
      reset();
    });
  }

  button.addEventListener('click', (event) => {
    if (suppressClick) {
      suppressClick = false;
      event.preventDefault();
      return;
    }
    if (blocked()) return;
    onTap();
  });

  // A long press must not open the phone's context menu or select the label.
  button.addEventListener('contextmenu', (event) => event.preventDefault());

  button.setLabel = (next) => {
    label = next;
    if (phase === 'idle') showLabel();
  };
  return button;
}
