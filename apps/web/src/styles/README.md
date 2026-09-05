# Platform UI typography

`css/typography.css` is the source of truth for Platform interface typography. It applies to product UI such as navigation, task workbenches, lists, forms, metadata, and metrics. AIMD document prose remains owned by `@airalogy/aimd-renderer` and must not be restyled with these UI classes.

## Font families

- `--aira-font-sans`: the shared Chinese/English product UI stack. The browser, Naive UI, and UnoCSS all inherit this variable.
- `--aira-font-mono`: code, identifiers, and technical values that require a monospaced face.

Do not add page-local `font-family` declarations for ordinary Platform UI.

The global fallback line height is unitless so any legacy or intentionally custom font size receives a proportional line box. Semantic roles still provide their own exact line height. Do not set a fixed global `rem` or `px` line height on a parent container.

## Semantic roles

| Class | Use |
| --- | --- |
| `aira-type-display` | A prominent number or single high-emphasis value |
| `aira-type-page-title` | One page-level heading |
| `aira-type-section-title` | A major card or section heading |
| `aira-type-card-title` | A compact card or subsection heading |
| `aira-type-item-title` | A Protocol, Project, Record, Lab, or list item title |
| `aira-type-body` | Normal explanatory content |
| `aira-type-label` | Controls, compact headings, and field labels |
| `aira-type-meta` | Ownership, location, time, status, and other secondary facts |
| `aira-type-caption` | Tertiary hints and compact annotations |
| `aira-type-status` | Compact status badges whose colors are defined by their state |
| `aira-type-metric` | Counts and comparable numeric values |
| `aira-type-code` | Code, stable IDs, and technical identifiers |
| `aira-type-eyebrow` | Short uppercase section labels; add `aira-type-eyebrow--accent` only for the current primary task |

Use `aira-text-primary`, `aira-text-secondary`, `aira-text-muted`, or `aira-text-subtle` only when the semantic role needs a deliberate color override. Use `aira-numeric` to add tabular numerals to a role other than `aira-type-metric`.

Prefer one semantic class over page-local combinations such as `text-xs text-gray-500 font-* leading-*`. Component-specific typography is appropriate only when the interaction itself requires a distinct treatment and should still reference the shared CSS variables.

## Shared interaction patterns

Contained application pages receive a shared 1rem horizontal gutter below the small-screen breakpoint. Full-canvas routes remain exempt. Keep this in the shell rather than adding different phone padding to individual pages.

Use the opt-in `aira-dialog` class on Naive UI card modals. `css/interaction.css` owns viewport gutters, bounded height, scrollable content and a visible footer; it deliberately uses global selectors because card presets are teleported. Set a specific width through an inline `--aira-dialog-width` variable, not a scoped rule on the modal root. Keep one confirmation action and a back/cancel action in the footer.

Use `aira-disclosure` on native `details` for optional form fields and secondary reference information. Keep required fields and actionable blockers visible; do not hide errors inside a closed disclosure. The disclosure summary must be keyboard operable and describe what it contains.

Use `OperationFeedback` for persistent failure feedback. Keep user input after errors, prevent duplicate submissions while a request is pending, and distinguish a failed preview from an uncertain confirmation. An interrupted response does not prove that the write failed: tell users to check the saved destination before repeating it.

Core workspace links share one navigation definition for desktop links and the compact, current-module menu. Account controls stay separate. These UI choices do not grant permissions: APIs remain authoritative.

Check the same journey at phone, tablet and desktop widths, with keyboard navigation, long translated text, failure recovery and AI disabled. Do not apply these product UI rules to AIMD document prose.
