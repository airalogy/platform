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
