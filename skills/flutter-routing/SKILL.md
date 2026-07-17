---
name: flutter-routing
description: Use when adding or changing Flutter navigation, routes, route arguments, guards, redirects, or navigator behavior.
---

Follow these routing rules strictly when working on Flutter code.

## Navigation Method

Use `go_router` for all navigation. Do not use legacy imperative navigation (`Navigator.push`) or custom `onGenerateRoute`.

## Structure

```
lib/
└── core/
    └── app_route.dart      # Central GoRouter configuration
```

## Rules

### Route Declaration`
- The `AppRouter` class lives in its **own file** (`app_route.dart`).
- Declare route path constants inside the `AppRouter` class.
- GoRoute builder should construct pages cleanly.

### Navigation and GoRouter Usage
- **Always navigate using GoRouter context extension methods**: `context.go(AppRouter.path)` or `context.push(AppRouter.path)`.
- Use `context.go()` for absolute navigation (resets stack when switching top-level/tabs/flows) and `context.push()` to push a route onto the stack.

### Route Arguments and Parameters
- For URL-friendly paths and deep linking, pass identifiers or minimal parameters as **path parameters** (e.g. `/profile/:id`) or **query parameters** (e.g. `/search?query=foo`).
- Access path parameters via `state.pathParameters` and query parameters via `state.uri.queryParameters`.
- For complex, non-serializable objects (when necessary), pass them in the route state's `extra` parameter:
  ```dart
  context.push(AppRouter.detail, extra: item);
  ```
  And extract them using `state.extra`.

### Error Handling & Deep Linking
- Keep route names and paths lowercase and URL-friendly (e.g. `/role-selection`).
- Implement or maintain a user-friendly `errorBuilder` to catch undefined routes and prevent crashes.
