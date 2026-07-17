---
name: flutter-listing-screens
description: Use when implementing Flutter listing, table, index, pagination, search, filter, refresh, row action, or bulk-selection screens.
---

Follow these Flutter implementation rules for listing screens. Read `frontend-listing-screens.md` first; it owns listing UX behavior.

## Data Flow

- Use BLoC for listing state.
- BLoC calls a repository; repositories call the API client.
- Fetch only basic row fields for the list view and load full details on demand.
- For Frappe dynamic listings whose columns come from DocType metadata, repositories must fetch applied runtime meta from the Frappe form-meta path, such as `frappe.desk.form.load.getdoctype`, instead of `/api/resource/DocType/<doctype>` when Property Setters or Custom Fields should affect the UI.
- Cache dynamic Frappe listing metadata in persistent app storage. On first listing load, use the cached metadata immediately when present, then fetch fresh applied metadata in the background and update the cache and rows if it changed.
- For admin details navigation from `frontend-listing-screens.md`, use a separate feature BLoC concern for detail loading rather than calling APIs directly from widgets.
- Search, filtering, sorting, pagination, and refresh must be represented as BLoC events.
- Implement the pagination reset behavior required by `frontend-listing-screens.md` inside those events.
- Trigger search updates from text input through debounce (for example 300ms) to avoid firing every keystroke as a network request, while retaining immediate submit support.
- For dynamic filter popovers and inline filter text fields, emit filter/search updates in `onChanged` and apply debounce there; avoid `onSubmitted` as the only trigger path.
- Refresh events on dynamic Frappe listings should be able to force-refresh metadata before reloading rows so already-open Flutter admin sessions pick up changed Desk/list configuration.

## Pagination Persistence

- Default page size is defined by the feature repository or shared listing defaults, matching `frontend-listing-screens.md`.
- Load the persisted page size before the first list fetch.
- Save page-size changes through the app's shared preferences helper before/when reloading page 1.
- Shared pagination widgets stay generic and emit `onPageSizeChanged`; feature BLoC/repository code owns persistence keys.

## Widgets

- Use shared widgets from `lib/core/widgets/` for repeated listing pieces such as toolbar, pagination, table header, selection controls, loading, empty, and error states.
- Keep shared widgets generic: no feature models, BLoCs, repositories, or API calls inside them.
- Feature screens own row data, selection state, callbacks, and feature-specific filters.
- Manage multi-row selection locally in the listing screen, not in global providers.
- For selected-row delete, keep the selected IDs local to the listing screen, show an explicit confirmation dialog with the selected count, dispatch a feature BLoC bulk-delete event, clear the local selection after confirmation, and reload through the repository/BLoC path.
- For bulk deletes on Frappe backends, do not loop over individual API calls or use `Future.wait`. Instead, repositories must call the native bulk RPC endpoint (`/api/method/frappe.desk.reportview.delete_items`), passing `doctype` and a JSON-encoded array of `items`.
- Shared listing toolbars may expose a right-side custom control slot before Refresh/Add actions for feature-owned controls such as Frappe-style filter popovers.
- Ensure shared listing toolbar controls meet full-height hit testing (rows/buttons should use full-height tap areas, e.g., sort control split panes, menu anchors, and action buttons must be tappable across the control container height).
- For Frappe-style dynamic filter popovers in Flutter, keep draft filter rows local to the popover until Apply. Use the feature BLoC's existing filter-change event only on Apply/Clear so pagination resets once.
- Dynamic filter popovers must derive field choices from applied metadata value fields plus standard system fields, and must derive valid operators from the selected field type using Frappe Desk-compatible rules.
- Dynamic filter popover field selection should use the shared existing Frappe link picker/search pattern backed by the local metadata field list, instead of a static dropdown. Search field choices by label, field name, and field type, and reset that draft row's operator/value when the selected field changes.
- Encode filter state with both `value` and `operator` for every popover row. Repositories should preserve supported Frappe operators (`=`, `!=`, `like`, `not like`, `in`, `not in`, `is`, comparisons, `Between`, `Timespan`) instead of collapsing non-text fields to `=`.
- Link filter values should use searchable async selectors backed by the linked doctype; Select/Check values should use local option controls; generic text/numeric/date inputs may use compact text fields when no specialized control exists.
- For Frappe-style cell-to-filter behavior, pass filterable value-item taps through the feature BLoC's existing filter-change event with `{value, operator: '='}` so pagination resets once and inline filters/filter popovers stay in sync.
- If the tapped value item matches the currently active `=` filter for the same field, remove that field filter instead of reapplying it. Preserve search, sort, and filters on other fields.
- Use the raw record value for the filter payload and keep formatted display values only for rendering. Normalize boolean/check values to the backend's expected raw representation when needed.
- Keep the first visible/subject column non-filterable, even if it is a value field. Let its value and surrounding space use the row/detail navigation path.
- Attach the filter gesture to the rendered value widget/text/chip only, not the full cell `SizedBox` or table column width. Surrounding cell whitespace should continue to open row details through the parent row gesture.
- Keep checkbox columns, action cells, and explicit detail navigation outside the filter gesture. Add a lightweight hover/tooltip affordance such as `Filter by <Field>` only on value items that will actually apply a filter.

## Desktop Flutter Tables

- Use a table-like layout for desktop/admin listings.
- Keep the header, toolbar, and pagination outside the vertically scrollable row body.
- Wrap only the table/header/body region in horizontal scrolling when columns overflow.
- Reuse the shared checkbox column and table-header select-all widgets when the shared listing UX requires selection.
- Navigate to the details page from row-body taps only; checkbox cells and row action buttons must consume their own taps.
- Navigate details pages using GoRouter (`context.go` or `context.push`); in nested admin shells, keep the detail page inside the active section router.

## Mobile Flutter Listings

- Use list tiles or compact cards, not full data tables.
- Prefer pull-to-refresh and infinite scroll/Load more rather than page-number controls.
- Hide desktop-only pagination controls according to `frontend-listing-screens.md`.
