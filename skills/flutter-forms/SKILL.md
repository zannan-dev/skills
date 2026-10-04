---
name: flutter-forms
description: Use when implementing Flutter forms, form layouts, field widgets, validation, selection dialogs, and save-state behavior.
---

Follow these Flutter implementation rules for forms. Read `frontend-forms.md` first; it owns form UX behavior.

## Layout Implementation

- Use Flutter widgets that match the shared form layout rules: sections, readable field widths, scrollable bodies, and reachable submit actions.
- Place Save in the form/detail screen's compact local action row or detail header when the screen pattern supports it. Do not add the shared admin top appbar with user/session details to nested detail, create, edit, profile, or form screens.
- For mobile complex forms, use full-screen scrollable forms or sheets with safe areas and sticky actions where established.
- For desktop/tablet-wide forms, use structured 2-3 column layouts where space permits.
- For dynamic metadata-backed detail forms, create the metadata `Future` in the parent detail view `State.initState()` so it starts in parallel with the detail BLoC record load. Pass that future into the form widget instead of creating it inside the form after the record is loaded.
- Keep metadata retry ownership in the parent detail view. The form can request retry through a callback, but the parent should replace the shared future so the form and any dependent UI stay synchronized.
- For dynamic admin detail tabs backed by `FrappeTabSchema`, use the shared `AdminDynamicDetailTabBar` inside the existing `DefaultTabController`.
- For form section labels, use the shared `AdminFormSectionTitle`; pass subtitles only when useful copy exists.

## Selection Components

- Use `DropdownButtonFormField` or the platform's default inline dropdown for Frappe `Select` fields whose options come from static newline-separated metadata.
- Do not use `DropdownButton`/dropdowns for network-bound, dynamic, searchable, or non-static option sets.
- Mobile: navigate to a dedicated search/selection screen and return the selected value.
- Desktop: open a search dialog/overlay.
- Desktop search/dialog selectors for links should be keyboard accessible:
  - Open with `Space` or `Enter` when the field is focused.
  - In the open selector, move through results with `ArrowUp`/`ArrowDown`.
  - Submit selection with `Enter`.
- When ArrowUp/ArrowDown changes the highlighted option, scroll the result list to keep that option visible; use row keys or measured viewport bounds rather than fixed-height math when row heights can vary.
- Build Frappe link-search `or_filters` from the selector's requested/searchable fields, including `name` and the target `title`/`id` fields when metadata or the requested field list confirms they exist. Do not blindly filter on non-existent Frappe fields because it can fail the REST request.
- In link-search dialogs, treat Enter as "select highlighted item" when one is active; only execute a new search on Enter when there is no highlighted option.
- Represent link selection inside the same result list (selected/highlighted row state), and avoid extra inline selected-value callouts outside the options list.
- Keep selection state in the same form draft/controller flow as manual input.
- Debounce link-search dialog input (e.g., ~300ms) while typing so filtering requests happen in short intervals instead of every single character event.

## Input Types & Keyboard Hints

Set `keyboardType` on `TextField` / `TextFormField`:

| Field | `keyboardType` |
|-------|---------------|
| Email | `TextInputType.emailAddress` |
| Phone | `TextInputType.phone` |
| Decimal numeric | `TextInputType.numberWithOptions(decimal: true)` |
| Integer numeric | `TextInputType.number` |
| URL | `TextInputType.url` |
| Multiline text | `TextInputType.multiline` + `maxLines > 1` |
| Search | `TextInputType.text` + `textInputAction: TextInputAction.search` |

Use `inputFormatters` to restrict input where needed. Set `autofillHints` where applicable.

## Keyboard Dismissal & Focus Management

Ensure users can always dismiss the keyboard on both iOS and Android, especially since iOS numeric and phone keyboards lack a native "Done" button.

- **TextInputAction:** For standard single-line text fields that do not have a logical "Next" field to jump to, explicitly set `textInputAction: TextInputAction.done` so the keyboard's bottom-right action key acts as a dismissal button.
- **No Accessory Overlays:** Rely on native solutions rather than building custom "Done" toolbars or importing packages like `keyboard_actions` for iOS numeric keyboards, keeping the UI clean and native.

## Field Styling

- Use `InputDecorationTheme` defaults to control form appearance globally instead of custom per-field decoration overrides.
- Inputs should use a subtle filled background (`fillColor`) that differentiates fields from white canvas surfaces.
- Use visually darker outline borders for form fields so their boundaries are clear in dense admin screens.
- Prefer shared theme tokens for labels/error/disabled styling to keep edit screens visually consistent across records.

## Random Data Filling

- Follow `frontend-dummy-data.md`.
- Button label: `Fill Dummy Data`.
- Show only when `kDebugMode` is true.
- Import from `lib/core/utils/dummy_data_generator.dart`.
- Never create per-feature generator classes.

## Save Feedback

- Read `flutter-theming.md` whenever adding user-facing form feedback. Use the app's shared toast helper for save success and async failures; never use `SnackBar`, `showSnackBar`, or `ScaffoldMessenger` messages. Keep field-specific inline validation where required by `frontend-forms.md`.
- Surface create and update success through screen-level state handling (for example, separate `Created` and `Updated` states) so operators get clear confirmation exactly once.
- Keep error messaging distinct from success to avoid mixed or repeated feedback when listing screens also refresh after save.

## Verification

- Check changed form files for prohibited snackbar message calls and use the existing shared toast helper.
- Verify one correctly typed success/error toast per save outcome, with inline field errors preserved where applicable.
- Run `dart format` and targeted Flutter analysis.
