---
name: frappe-realtime-updates
description: Use when backend Frappe changes must refresh mounted UI through realtime create, update, delete, workflow, or background-job events.
---

Use this skill whenever a backend Frappe change must refresh mounted UI in real time, especially listing/index pages, detail pages, dashboards, or custom admin surfaces that need server-pushed create/update/delete visibility.

Read the relevant UI skill first for the surface being changed:

- For listings: `frontend-listing-screens.md`, then the platform adapter, then `frappe-listing-realtime.md`.
- For admin details: `frontend-admin-panels.md`, `frontend-forms.md`, `frontend-ui-states.md`, `frontend-admin-detail-pages.md`, then the platform adapter.
- For Frappe Desk list filters: `frontend-admin-panels.md`, then `frappe-list-filters.md`.

## Backend Emission

- Prefer normal Frappe ORM writes (`insert`, `save`, `submit`, `cancel`, `delete_doc`) so `Document.notify_update()` publishes the standard events automatically.
- Do not use raw SQL or low-level `frappe.db.set_value` for changes that must be reflected live unless you also call the correct realtime notification after persistence.
- Emit only after the local DB state is committed or guaranteed to commit. Use `after_commit=True` for custom events.
- Do not emit realtime before a transaction that can still roll back.
- If the backend flow calls external APIs, webhooks, storage providers, or long-running work, persist the local document first, commit it, emit the local state, then run external work in a background job unless synchronous behavior is explicitly required.

Standard Frappe document updates publish:

```python
frappe.publish_realtime(
	"doc_update",
	{"modified": doc.modified, "doctype": doc.doctype, "name": doc.name},
	doctype=doc.doctype,
	docname=doc.name,
	after_commit=True,
)

frappe.publish_realtime(
	"list_update",
	{"doctype": doc.doctype, "name": doc.name, "user": frappe.session.user},
	after_commit=True,
)
```

Use custom events only when the UI needs domain-specific payloads that cannot be represented by the standard document/list refresh events.

### Defensive Emission for Generated, Background-Job, and Scheduled-Task Paths

Standard `Document.notify_update()` (fired by `insert`, `save`, `submit`, `cancel`, `delete_doc`) publishes `doc_update` and `list_update` with `after_commit=True`. This is sufficient for most request-context writes. For whitelisted generators, background jobs (`frappe.enqueue`), and scheduled tasks (`scheduler_events`) where a mounted listing or detail page must refresh reliably, add an explicit defensive emission as a safety net.

Pattern: call an explicit `frappe.db.commit()` after the ORM write, then publish both events immediately (no `after_commit=True`, since the data is already committed). This uses a separate code path from `notify_update`, so if the `after_commit` hook mechanism ever fails to flush in a worker or scheduler context, the explicit call still delivers the event. Client-side debounce (300-750 ms) collapses the duplicate events from both paths into a single reload.

```python
def _publish_doc_realtime(doc: Document) -> None:
	frappe.publish_realtime(
		"doc_update",
		{"modified": doc.modified, "doctype": doc.doctype, "name": doc.name},
		doctype=doc.doctype,
		docname=doc.name,
	)
	frappe.publish_realtime(
		"list_update",
		{"doctype": doc.doctype, "name": doc.name, "user": frappe.session.user},
	)


# Whitelisted generator
plan.insert()
frappe.db.commit()
_publish_doc_realtime(plan)

# Background job / scheduled task — commit + emit per record so partial
# progress is visible to connected clients even if a later record fails.
for plan_name in matching_plans:
	plan_doc = frappe.get_doc("Shift Requirement Plan", plan_name)
	plan_doc.save()
	frappe.db.commit()
	_publish_doc_realtime(plan_doc)
```

Rules:
- Place the explicit `publish_realtime` calls **after** `frappe.db.commit()`, not before. Do not use `after_commit=True` here — the commit has already happened and the next commit may never arrive in a worker context.
- Centralize both events in a per-doctype helper (e.g. `_publish_plan_realtime`) so the payload shape stays consistent and callers stay one-liners.
- In background-job and scheduled-task loops, commit and emit per record when records are independent. This makes partial progress visible to connected clients. If the records must be all-or-nothing, commit and emit once after the loop instead.
- Do not add defensive emission to Frappe Desk's own form/list views or to standard CRUD endpoints that Frappe already covers — it is for custom generators, background jobs, and scheduled tasks only.
- Do not use defensive emission as a replacement for ORM writes. Always use `insert`/`save`/`delete_doc` for the actual persistence; the explicit `publish_realtime` is purely supplemental.

## Standard Event Semantics

- `doc_update`: document-specific event sent to `doc:<Doctype>/<name>`. Use for an open detail/form view of one record.
- `list_update`: doctype-level event sent to `doctype:<Doctype>`. Use for listing/index/report views that need to react when any record of that DocType changes.
- `docinfo_update`: document-specific metadata event. Use only for docinfo/sidebar/comment-style metadata, not row data.
- User-specific events should pass `user=<user>` and should not be used for shared list freshness.

## Frappe Desk Lists

- Use Frappe's native list realtime path before adding custom code.
- Ensure list auto-refresh is not disabled by `disable_auto_refresh` unless the product explicitly wants manual refresh.
- Let the list subscribe with `frappe.realtime.doctype_subscribe(doctype)` and listen for `list_update`.
- On `list_update`, refetch the changed document by `name` using the current list filters, then append, update, remove, sort, and re-render.
- Do not refresh repeatedly during bulk operations or while the filter row is actively being edited.
- Preserve selected rows, current filters, sort, pagination, and scroll behavior where the platform already supports it.

## Detail Pages

- Subscribe to record-specific updates for the active record only.
- On `doc_update` for the current record, refetch the detail payload instead of trusting a partial realtime payload as the full source of truth.
- If the user has unsaved local edits, do not overwrite the form silently. Show a conflict/refresh state or mark that a refresh is needed.
- After a successful local save, update the local detail state immediately and avoid a duplicate user-visible reload.
- Unsubscribe when leaving the detail route, closing the modal, or changing the active record ID.

## External Clients

- For Next.js and Flutter clients, expose a small realtime adapter instead of scattering Socket.IO code across pages. Own one connection per authenticated client session/backend boundary and multiplex all mounted consumers over it. Shared source code alone does not prevent each instance from opening another socket.
- Reference-count doctype/document rooms across consumers; release a room only when its last owner leaves. Dispose consumer listeners independently, restore each unique room once after recovery, and run one bounded retry/credential-validation cycle per connection. Invalidate the old connection on logout or credential replacement; never let stale consumers reconnect using a newer session.
- Keep event names, room names, and payload shapes typed or centralized.
- Connect to the site Socket.IO namespace that matches the Frappe site.
- For Masar Admin Flutter, the Socket.IO URL must include the namespace in both local and production. Local: `http://masar.localhost:9000/masar.localhost`. Production: `https://masaradmin.conceptiqs.com/masarbackend.conceptiqs.com`. Keep production HTTP APIs pointed at `https://masarbackend.conceptiqs.com`; do not change API base URL just to change the socket host.
- Use the stored credential scheme for Flutter Socket.IO (`Authorization: token <api_key>:<api_secret>` for legacy keys, `FlutterDevice` for managed-device credentials), with `path: /socket.io`. Header-authenticated Flutter web uses polling because browser WebSocket handshakes cannot attach arbitrary headers; native clients can use WebSocket headers. Do not assume a browser upgrade retains authentication.
- Many independent polling sessions can exhaust browser HTTP connection slots, especially when retained tabs mount all screens. Diagnose queued handshakes, delayed heartbeats, and `Session ID unknown` responses; do not mask the cause with longer timeouts or more retries.
- For local separate frontend/backend ports, verify the Node realtime authentication URL targets Frappe, not the Flutter server. In the standard Frappe development routing, bench-level `developer_mode` rewrites the browser Origin port to `webserver_port`; restart the Node process after changing it. Do not enable development mode in production as a socket workaround.
- For separate production domains, inspect the installed Frappe origin/namespace checks and proxy `/socket.io/` through the frontend host when appropriate. Set `X-Frappe-Site-Name` to the backend site; upstream Host and Origin must satisfy the middleware's hostname check, and the authentication destination must be the backend. Preserve Authorization, polling GET/POST, and WebSocket upgrade support. CORS alone does not override origin checks.
- Subscribe only after the user is authenticated and authorized for the target DocType or document.
- Listing listeners should invalidate/refetch the affected row or first page. Avoid unbounded full-list reloads unless the collection is intentionally tiny.
- Detail listeners should refetch the current record by ID.
- Always clean up listeners on unmount/dispose and guard against duplicate subscriptions after route changes.

## Verification

- Create a record from another session or background job and confirm an open listing shows it without manual refresh.
- Edit a visible record from another session and confirm the row and detail page update.
- Confirm filtered listings do not show records that no longer match the active filters.
- Confirm unsaved detail edits are not overwritten by a remote update.
- Confirm delete/cancel/archive flows remove or update visible rows according to the active filters.
- Confirm no duplicate network requests accumulate after navigating away and back.
- With many mounted consumers, confirm a single session connection and unique room subscriptions. Observe at least two heartbeat cycles, test recovery and logout/re-login, and inspect socket response bodies rather than interpreting successful HTTP statuses as successful socket authentication.
