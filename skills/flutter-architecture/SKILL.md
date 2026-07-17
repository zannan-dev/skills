---
name: flutter-architecture
description: Use when structuring Flutter projects, creating new Flutter features, or changing feature/module boundaries.
---

Follow these architecture rules strictly when working on Flutter code.

## Project Structure

Organize by **feature**, not by layer. Each feature is a self-contained module:

```
lib/
├── features/
│   └── <feature_name>/
│       ├── bloc/                # BLoC classes (events, states, bloc)
│       ├── data/                # Repositories and data sources
│       ├── models/              # Data models for this feature
│       ├── screens/             # Full-page screens
│       └── widgets/             # Reusable widgets scoped to this feature
├── core/
│   ├── helpers/                 # Shared helper classes
│   ├── widgets/                 # Shared widgets (error, empty, loading)
│   ├── config/                  # App configuration
│   └── exceptions/              # Custom exception handling
└── main_dev.dart / main_prod.dart
```

## Rules

### File Organization
- **One widget per file.** Never define multiple public widgets in a single file.
- **File naming.** Use snake_case matching the class name: `PlayerCard` → `player_card.dart`.
- **Feature isolation.** A feature should not directly import another feature's internal files. Use shared `core/` for cross-feature code.

### Helpers & Utilities
- Create **helper classes** for reusable methods (formatting, validation, conversions).
- Use a **separate helper** for `shared_preferences` — never call it directly in widgets or BLoCs.
- Use a **custom exception formatter** to convert any exception into a human-readable message.

### App Configuration
- Use **separate entry points** per environment: `main_dev.dart`, `main_prod.dart`.
- Each entry point loads its own configuration (API base URL, feature flags, debug settings).

### Global Context
- Add `navigatorKey` to the GoRouter configuration and use it to access context globally in helper classes (for navigation, dialogs, toasts outside the widget tree).

### Navigation Shell
- Implement a **navigation screen** (using GoRouter's `ShellRoute` or `StatefulShellRoute`) that holds the sidebar and body branch only; do not place the top bar in the navigation screen.
- The shared admin top appbar belongs only inside first-level navigation destination screens, such as dashboards, listings, and index screens rendered directly from the sidebar/right navigation body.
- Nested detail, create, edit, profile, and form screens must not include the shared admin top appbar or its user/session details. Use a compact local action row or detail header for Back, Save, Reset, Refresh, and record-specific actions instead.
- Shared admin top bars should not contain global search, date range, notification actions, or desktop sidebar collapse/expand controls unless a first-level page explicitly owns that feature.
- The navigation shell may own sidebar collapsed/expanded state and persistence callbacks, but the sidebar widget renders the desktop collapse/expand control.
- Page top bars may render narrow-layout drawer open controls when the sidebar is hidden.
- In production/non-debug builds, keep body branches mounted (e.g. using `StatefulShellRoute.indexedStack`) so each sidebar item preserves its nested route stack and local widget state while switching sections.
- Treat the navigation shell as its own feature (`features/navigation/`).
