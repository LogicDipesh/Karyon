# Release Notes

All notable changes to ResQ are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Category-grouped resource picker** in the Simulation panel.
  The Simulate button now opens a picker that groups every dispatchable
  resource (Ambulances, NDRF Teams, Fire Units) into colour-coded
  categories. Each unit is an individual toggle button showing its
  current status (available / busy / unavailable). Hospitals are shown
  but disabled (they are not dispatchable).
- **`POST /api/allocate`** endpoint that accepts a JSON body of
  resource IDs to mark unavailable and re-runs the greedy allocator
  from scratch:
  ```bash
  curl -X POST -H "Content-Type: application/json" \
       -d '{"unavailable_resource_ids":["A02","N01","F01"]}' \
       http://127.0.0.1:8000/api/allocate
  ```
  Hospital IDs in the request are silently ignored. The response now
  also includes the echoed `unavailable_resource_ids` for confirmation.

### Changed
- **Simulate button** no longer hard-codes "Ambulance A02 Unavailable".
  Clicking it opens the resource picker; the user selects units and
  clicks **Run Allocation** to trigger `/api/allocate`.
- **Allocation helper** (`_run_allocation_with_unavailable`) was
  extracted in `backend/main.py` so `/api/simulate` and
  `/api/allocate` share identical logic (full reset of busy resources
  → apply unavailability set → re-run greedy allocator → diff).
- **Reset** now also refreshes the resource picker in place if it is
  currently open, so stale "unavailable" highlights don't survive a
  re-seed.
- **Picker actions** (Run Allocation / Clear / Cancel) live directly
  inside the picker panel; selection state is preserved while the
  picker stays open.

### Deprecated
- `POST /api/simulate` is kept for backward compatibility but is a
  thin wrapper around `/api/allocate` with `["A02"]` as the hard-coded
  selection. Prefer `/api/allocate` for new integrations.

### Removed
- The hard-coded "Ambulance A02 Unavailable" simulate scenario and its
  matching button label.

### Fixed
- None.

### Security
- No new external dependencies. No secrets, API keys, tokens, or
  credentials are introduced or required. The only network egress
  remains the public OpenStreetMap tile CDN used by Leaflet (already
  present in prior releases).
