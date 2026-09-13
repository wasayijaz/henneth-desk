# 001 — Make Company Intelligence motion feel immediate and composed

- **Status**: DONE
- **Commit**: 06fd0ac5
- **Severity**: HIGH
- **Category**: Duration & easing, loading and progress states, hover and press feedback
- **Estimated scope**: 2 files, about 45 lines

## Problem

Company Intelligence currently treats a route change like a long processing sequence. The broad selector also animates nested cards as well as their parent sections, so the page arrives as visual noise instead of a clear hierarchy.

```css
/* Henneth Desk 2.CI.0/styles.css:107 — current */
.workspace.is-entering .detail>.hero,.workspace.is-entering .detail>.grid4,.workspace.is-entering .detail>.panel,.workspace.is-entering .detail>.company-route-stack,.workspace.is-entering .detail .metric,.workspace.is-entering .detail [class*="-card"],.workspace.is-entering .detail [class*="-tile"]{animation:ciProcessingSettle 420ms var(--ease-out) both}
```

The entrance also animates `filter`, which is visually muddy and costs more paint work than transform and opacity.

```css
/* Henneth Desk 2.CI.0/styles.css:109 — current */
@keyframes ciProcessingSettle{from{opacity:0;transform:translate3d(0,7px,0);filter:saturate(.7)}to{opacity:1;transform:none;filter:none}}
```

Mobile drawers use the generic curve, charts take 900 ms to finish, and controls have hover feedback but no press response.

```css
/* Henneth Desk 2.CI.0/styles.css:79,166 — current */
.rail,.tree-panel{transition:transform var(--dur-base) var(--ease-out)}
.ci-svg-draw{animation:ciChartDraw 900ms cubic-bezier(.23,1,.32,1) forwards}
```

Finally, reduced-motion mode removes every transition, including harmless color feedback.

```css
/* Henneth Desk 2.CI.0/styles.css:17 — current */
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;scroll-behavior:auto!important;transition:none!important}}
```

## Target

Add exact motion tokens and use them consistently:

```css
--dur-press:120ms;
--dur-enter:240ms;
--dur-drawer:280ms;
--ease-in-out:cubic-bezier(.77,0,.175,1);
--ease-drawer:cubic-bezier(.32,.72,0,1);
```

- Animate only direct content sections with `opacity` and `transform` for 240 ms.
- Stagger direct page sections at 0, 35, 55, 75, and 95 ms, keeping the visible sequence under 335 ms.
- Use the drawer curve for mobile side panels over 280 ms.
- Draw charts in 600 ms.
- Give buttons and links a 120 ms `scale(.98)` press response on devices that support hover; do not move cards on press.
- In reduced-motion mode, remove movement and chart drawing but retain 120 ms color, background-color, border-color, and opacity feedback.

## Repo conventions to follow

- Motion tokens live in `Henneth Desk 2.CI.0/styles.css:2` beside `--dur-fast`, `--dur-base`, and `--ease-out`.
- Route entry is already triggered centrally by `enhanceMotion()` in `Henneth Desk 2.CI.0/app.js:4182`; keep that interface and change CSS behavior only.
- Existing interaction rules specify individual properties instead of `transition: all`; preserve that convention.

## Steps

1. In `Henneth Desk 2.CI.0/styles.css`, add the five motion tokens to `:root`.
2. Replace the 420 ms nested entrance selector with direct-child page sections, a 240 ms opacity/transform keyframe, and bounded stagger delays.
3. Change mobile drawer transitions to `var(--dur-drawer) var(--ease-drawer)`.
4. Shorten `ciChartDraw` to 600 ms using `var(--ease-out)`.
5. Add 120 ms press feedback for interactive buttons and routed links without changing layout.
6. Refine the reduced-motion override so movement is removed while color and opacity feedback remain.
7. In `Henneth Desk 2.CI.0/app.js`, keep route-focus restoration but allow `focusView` route changes to trigger the entrance; continue suppressing motion during search and form rerenders.
8. Add a deterministic motion-contract checker and run it with the existing JavaScript syntax and design checks.

## Boundaries

- Do NOT touch intelligence data, calculations, route structure, authentication, or publishing.
- Do NOT change markup. JavaScript may change only at the existing `enhanceMotion` call because browser verification proved that `focusView` route navigation otherwise suppresses the planned entrance entirely.
- Do NOT add dependencies.
- Do NOT introduce looping decorative animation or animate layout properties.
- If these selectors have drifted since commit `06fd0ac5`, STOP and report instead of improvising.

## Verification

- **Mechanical**: run `node -c "Henneth Desk 2.CI.0/app.js"`, `python scripts/design_lint.py`, and the new motion-contract checker; all must exit 0.
- **Feel check**: in the CI preview, switch between Overview, Intelligence, Financials, and Events & Filings and confirm:
  - the heading establishes hierarchy before supporting sections without nested-card cascades;
  - the total entrance feels complete in roughly one-third of a second;
  - rapidly changing routes never leaves content invisible;
  - drawers start quickly and settle softly on mobile;
  - buttons compress slightly on press without shifting neighboring content;
  - at reduced motion, movement and chart drawing disappear while color feedback remains.
- **Done when**: all checks pass, desktop and mobile screenshots show no layout regression, and computed styles expose the exact target durations and curves.
