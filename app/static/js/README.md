# Frontend Client Scripts (`app/static/js`)

## Overview
Client-side JavaScript modules handling dynamic browser interactions, interactive Chart.js visualizations, real-time activity filtering, and custom CSV data exports for the Athar dashboard.

## Interface
- `[export.js:activeFilterMode]` Module-scoped state tracking active export filter mode (`year`, `month`, `custom`)
- `[export.js:activeProjects]` Cached array of loaded project records for export preview
- `[export.js:TYPE_TRANSLATIONS]` Mapping of activity type identifiers to Arabic labels
- `[export.js:STATUS_TRANSLATIONS]` Mapping of project status identifiers to Arabic labels
- `[export.js:getCommunitySlug]` Extracts current community slug from DOM select or URL query
- `[export.js:getCommunityName]` Extracts community display name from active DOM option
- `[export.js:setFilterMode]` Toggles export date filter controls and displays
- `[export.js:onCommunityChange]` Event handler triggering export preview refresh on community selection
- `[export.js:buildQueryParams]` Serializes form filter inputs into URL search parameter strings
- `[export.js:getFilterDescriptionText]` Formats human-readable summary of active export filters
- `[export.js:updateLivePreview]` Fetches matching projects and renders live tabular preview capped at 10 items
- `[export.js:triggerCsvDownload]` Redirects browser window to CSV export endpoint with serialized filters
- `[export.js:escapeHtml]` Utility escaping HTML special characters to prevent XSS
- `[filters.js:dashboard:filtered]` Custom DOM event dispatched on document when dashboard project cards update

## Invariants
- `[charts.js:loadStats]` Aborts stats loading, displays error message, and destroys existing charts if `communitySlug` is falsy or missing.
- `[charts.js:loadStats]` Destroys existing Chart.js instances before binding new charts to canvas elements to avoid rendering leaks.
- `[charts.js:loadStats]` Throws Error when API response status is not 200 OK (`response.ok` is false).
- `[filters.js:DOMContentLoaded]` Verifies presence of DOM containers `list-comm`, `dashboard-filters`, and `filter-results` before initializing; aborts if missing.
- `[filters.js:loadCommunities]` Throws Error if response payload is not an array.
- `[filters.js:loadProjects]` Validates projects payload is an array; discards stale responses using a request counter (`requestId`) to prevent race conditions.
- `[filters.js:loadProjects]` Prompts user and aborts fetch if no community slug is selected.
- `[filters.js:applyFilters]` Enforces date bounds (`projectDate >= start` and `projectDate <= end`) and normalized status comparison.
- `[filters.js:applyFilters]` Type filter `other` excludes all standard activity types; specific types require exact or prefix match.
- `[export.js:triggerCsvDownload]` Prompts user alert and aborts download if community slug is empty.
- `[export.js:updateLivePreview]` Resets count badge and displays empty state if slug is empty.
- `[export.js:updateLivePreview]` Limits live table preview to at most 10 rows (`projects.slice(0, 10)`).

## Side Effects
- `[charts.js:loadStats]` Dispatches asynchronous GET requests to `/api/${encodeURIComponent(communitySlug)}/stats`.
- `[charts.js:loadStats]` Mutates DOM KPI text nodes (`totalMembers`, `totalProjects`, `totalEdits`, `statsError`) and canvas chart contexts.
- `[filters.js:loadCommunities]` Dispatches asynchronous GET request to `/api/communities` and populates `list-comm` select options.
- `[filters.js:loadProjects]` Dispatches asynchronous GET request to `/api/${encodeURIComponent(slug)}/projects`.
- `[filters.js:displayProjects]` Clears and mutates DOM tree under `#filter-results` with project cards; binds click/keydown listeners and dispatches custom event `dashboard:filtered`.
- `[filters.js:openProjectModal]` / `[filters.js:closeModal]` Toggles modal visibility, aria attributes, and adds/removes `modal-open` CSS class on `document.body`.
- `[export.js:updateLivePreview]` Performs GET request to `/api/${encodeURIComponent(slug)}/projects` and updates preview table DOM elements.
- `[export.js:triggerCsvDownload]` Modifies `window.location.href` to trigger browser download navigation to `/api/${encodeURIComponent(slug)}/export`.

## Verification
- Run: `pytest`

