---
name: flutter-theming
description: Use when changing Flutter ThemeData, Theme.of(context), brand colors, typography, notifications, local fonts, or animations.
---

Follow these Flutter theming implementation rules strictly. Visual behavior and device intent live in `frontend-device-layout.md` and other `frontend-*` UI skills.

## Fonts

- Never use Google Fonts. Use only bundled/local font assets declared in `pubspec.yaml`.

## Notifications

- Never use Snackbars for user-facing messages. Use the `toastification` package or the app's toast helper.
- This includes form saves, publishing, validation feedback, authentication, and async failure messages—not only theme changes. Do not introduce `SnackBar`, `showSnackBar`, or `ScaffoldMessenger` message calls in feature code.
- Reuse the app's existing toast helper before calling `toastification` directly. Masar Admin uses `ToastHelper.success/error/info` from `lib/core/utils/toast_helper.dart`; Masar mobile uses `AppToast` from `lib/core/utils/app_toast.dart`.
- Toast helpers must support multi-line and larger messages.
- Use appropriate toast types: success, error, warning, info.

## Animations

- Use `flutter_animate` for transitions and micro-interactions.
- Apply animations to enhance UX, such as list item entry, page transitions, and loading states.
- Do not over-animate or animate layout in ways that harms scanability.

## Theme Usage

- Define colors, text styles, and spacing in `ThemeData` or the app theme layer.
- Reference theme values via `Theme.of(context)` or established app theme constants.
- Do not hardcode colors or font sizes in feature widget code when theme values exist.
- Support light/dark themes where the app supports them.
- In this app, keep detail/list surfaces on white backgrounds by using `scaffoldBackgroundColor`/`canvasColor` set to white in the app theme.
- For form controls, prefer shared input tokens rather than per-screen overrides: darker outline borders for clearer field distinction and a subtle filled background for text inputs.

## Verification

- Search touched Flutter files for `SnackBar`, `showSnackBar`, and `ScaffoldMessenger`; user-facing feedback must use the shared toast helper instead.
- Confirm success and failure use the correct toast type and are emitted once from screen-level listeners.
- Run `dart format` and targeted Flutter analysis on changed files.
