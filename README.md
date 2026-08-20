# Project Title

- **Application name:** Breakline Surf Forecasts
- **Student:** Brian Thoms
- **Course:** IT 401
- **Assignment:** A4 — Search, Retrieval, Pagination, and Search Telemetry

## Project Overview

Breakline is a Flask application that helps surfers find and revisit useful marine forecasts. A user can request an hourly forecast by city, by selecting a point on a Leaflet map, or by granting browser location access and using the nearest named beach or surf break. Breakline combines APIFreaks marine-weather data, OpenStreetMap coastal information, and short Wikipedia overviews, then persists successful forecasts in MySQL through Flask-SQLAlchemy.

The application's purpose is to reduce the time required to compare coastal conditions and make a surfing plan. Its intended users are surfers and coastal visitors who want a readable forecast for a specific place and hour.

Authenticated users receive a private forecast history. A4 search improves the original application by making that history retrievable rather than merely chronological. Users can search across beach and surf-spot names, combine filters, sort results, page through large histories, reopen stored reports without another weather API call, and search within a radius of their current location.

## Search and Retrieval Features

| Capability | Implementation |
|---|---|
| Keyword search | Case-insensitive substring search for a beach, city, requested location, or surf spot. |
| Fields searched | `ForecastRequest.surf_break_name`, `ForecastRequest.requested_location`, `Beach.name`, and `Beach.city`. |
| Filters | Forecast start/end dates, time of day, current-location radius, and an implicit authenticated-user filter. |
| Time groups | Overnight `00–04`, morning `05–11`, afternoon `12–16`, and evening `17–23`. |
| Radius search | Haversine distance in SQL, from 1 through 100 miles; the results page also displays each distance. |
| Sorting | Newest request first or surf-spot name A–Z. |
| Ranking | Deterministic rule-based ordering rather than a relevance score. Newest-first uses request time; A–Z uses the displayed spot name. Request ID is the final tie-breaker. |
| Pagination | Database-backed pagination with 10 results per page, a total-count query, numbered links, and previous/next controls. |
| Search telemetry | Valid search criteria and result counts are recorded. Pagination views and forecast-result views are recorded as interactions. |
| Search recall | Shows matched forecasts as a count and percentage of the signed-in user's complete forecast history. |

Searches always include `ForecastRequest.user_id == current_user.id`; one user cannot search or open another user's history.

## Search Workflow

```mermaid
flowchart TD
    U[Authenticated user] --> F[Profile search form]
    F --> V{Validate query, dates, time, radius, sort, page}
    V -->|Invalid| E[Accessible field and summary errors]
    V -->|Valid| Q[Build owner-scoped SQLAlchemy SELECT]
    Q --> J[Join ForecastRequest, SurfForecast, and Beach]
    J --> K[Apply keyword and optional filters]
    K --> O[Apply newest-first or A-Z ordering]
    O --> P[COUNT plus LIMIT/OFFSET: 10 per page]
    P --> R[Render matching stored forecasts]
    P --> S[(history_searches)]
    R --> I{User interaction}
    I -->|Changes page| T[(page_view telemetry)]
    I -->|Opens forecast| C[(result_view telemetry)]
    C --> D[Saved forecast detail]
```

1. Flask normalizes and validates the submitted GET parameters.
2. The repository builds a SQL query restricted to the signed-in user.
3. Keyword and structured filters are combined with SQL `AND`; the keyword fields are combined with SQL `OR`.
4. SQL ordering and pagination are applied before records are returned to the browser.
5. The rendered page preserves active filters, sort order, location context, and telemetry search ID in pagination links.
6. Valid new searches, page views, and result views are stored for later evaluation. Invalid and empty searches are not recorded.

## Searchable Information

| Model | Searchable fields | Filter fields | Ranking/sorting fields | Reason |
|---|---|---|---|---|
| `ForecastRequest` | `surf_break_name`, `requested_location` | `user_id` | `requested_at`, `id` | Contains the user's original label, selected break, ownership, and request chronology. |
| `Beach` | `name`, `city` | `latitude`, `longitude` through calculated distance | `name` through the displayed-name expression | Supplies normalized location names and coordinates. |
| `SurfForecast` | None in the keyword expression | `forecast_date`, `forecast_hour` | None currently | Dates and hours are structured values and are more precise as filters than text. |
| `HistorySearch` | Not exposed as user-searchable content | User and timestamp support later analysis | Not used in live result ranking yet | Retains search intent and result-count signals for evaluation. |
| `HistorySearchInteraction` | Not exposed as user-searchable content | Search, user, interaction type, page, and position | Not used in live result ranking yet | Retains engagement signals for future recommendations. |

The displayed-name expression uses the first available value from surf-break name, beach name, and requested location. That same priority is used for alphabetical ordering so the table label and database ordering agree.

## Retrieval Strategy

### Keyword matching

The search repository escapes `%`, `_`, and backslash characters, adds `%` around the normalized query, and applies SQLAlchemy `ilike()` to four fields. The expression is equivalent to:

```sql
WHERE user_id = :current_user
  AND (
    surf_break_name ILIKE :pattern
    OR requested_location ILIKE :pattern
    OR beach.name ILIKE :pattern
    OR beach.city ILIKE :pattern
  )
```

SQLAlchemy translates `ILIKE` appropriately for the configured database. This project does not currently use MySQL full-text indexes, stemming, fuzzy matching, or embeddings.

### Combining filters

- Fields inside keyword search are combined with `OR`.
- Keyword, date range, time group, and radius constraints are combined with `AND`.
- Start and end dates are independently optional and inclusive.
- Time groups translate to an inclusive `forecast_hour BETWEEN first_hour AND last_hour` condition.
- Radius uses the Haversine formula against stored `Beach.latitude` and `Beach.longitude` values.
- The authenticated-user predicate is always present.

### Sorting and ranking

The default order is `requested_at DESC, id DESC`. Alphabetical order uses a lowercase `COALESCE` display-name expression followed by request time and ID as deterministic tie-breakers. This is rule-based ranking: keyword matches do not receive different relevance scores based on the matched field or term position.

### Retrieval limitations

- Substring matching does not understand meaning, synonyms, misspellings, or word importance.
- Singular and plural forms can differ.
- Every matching text field has equal weight.
- A query such as `HB` will not automatically expand to `Huntington Beach`.
- Radius results are filtered by distance but are not currently sorted by nearest distance.
- Pagination uses offset-based retrieval; very large histories may eventually benefit from cursor pagination.

## Search Telemetry

Breakline records first-party telemetry only for authenticated users and valid searches.

### Recorded search activity

`history_searches` stores:

- user ID;
- keyword text;
- forecast start and end dates;
- time-of-day filter;
- whether a location radius was used;
- radius in miles;
- sort order;
- total result count; and
- creation timestamp.

For privacy, telemetry does **not** store the user's precise current latitude, longitude, or reverse-geocoded current-location label.

`history_search_interactions` stores:

- user ID and optional originating search ID;
- optional forecast-request ID;
- interaction type (`page_view` or `result_view`);
- page number;
- absolute result position; and
- interaction timestamp.

Invalid searches create no telemetry. Telemetry writes are isolated from search delivery: a telemetry database failure is rolled back and logged without blocking valid results.

### Why telemetry is recorded

These records can reveal common query vocabulary, filters that produce zero results, popular time windows, frequently opened surf spots, and the positions at which users engage. Future retrieval can use aggregate signals to improve query suggestions, ranking, and recommendations. Before personalization, the project should add retention rules, user-facing privacy language, result-impression events, and a method for users to delete their activity.

## Database Schema

| Table | Purpose | Primary key | Important attributes | Relationships |
|---|---|---|---|---|
| `users` | Local profile for Google-authenticated users | `id` | `google_sub`, email, display name, avatar, timestamps | One-to-many forecast requests, history searches, and interactions |
| `beaches` | Normalized beach/coastal location | `id` | name, city, state/province, country, latitude, longitude | One-to-many forecasts; one-to-one Wikipedia info |
| `surf_forecasts` | Persisted hourly APIFreaks conditions | `id` | beach, date, hour, wave/swell/wind-wave values, source, retrieval time | Many-to-one beach; referenced by forecast requests |
| `forecast_requests` | Authenticated user's successful forecast history | `id` | user, beach, forecast, lookup mode, requested location, surf-break name, timestamp | Many-to-one user, beach, and surf forecast |
| `forecast_feedback` | User rating and optional comments for a saved forecast request | `id` | forecast request, 1–5 rating, comment, created/updated timestamps | One-to-one forecast request |
| `wikipedia_spot_info` | Cached Wikipedia API overview and provenance | `id` | page/revision IDs, summary, URL, license, timestamps | One-to-one beach |
| `history_searches` | One valid profile-history search | `id` | filters, radius usage, sort, result count, timestamp | Many-to-one user; one-to-many interactions |
| `history_search_interactions` | Search-results engagement event | `id` | type, page, position, timestamp | Many-to-one user and optional search; optional forecast request |

```mermaid
erDiagram
    USERS ||--o{ FORECAST_REQUESTS : makes
    USERS ||--o{ HISTORY_SEARCHES : submits
    USERS ||--o{ HISTORY_SEARCH_INTERACTIONS : generates
    BEACHES ||--o{ SURF_FORECASTS : has
    BEACHES ||--o| WIKIPEDIA_SPOT_INFO : has
    BEACHES ||--o{ FORECAST_REQUESTS : referenced_by
    SURF_FORECASTS ||--o{ FORECAST_REQUESTS : referenced_by
    FORECAST_REQUESTS ||--o| FORECAST_FEEDBACK : receives
    HISTORY_SEARCHES ||--o{ HISTORY_SEARCH_INTERACTIONS : produces
    FORECAST_REQUESTS o|--o{ HISTORY_SEARCH_INTERACTIONS : opened_by
```

`db.create_all()` creates new tables. The idempotent `init-db` and `upgrade-db` commands also apply the supported hourly-forecast schema upgrade. The project does not yet use Alembic/Flask-Migrate.

## Current Features

- **Homepage:** Responsive Breakline landing page, session planner, map/city lookup switch, and forecast report.
- **API integration:** Hourly APIFreaks forecasts, OpenStreetMap tiles/Overpass/Nominatim data, and Wikipedia MediaWiki Action API extracts.
- **Web scraping:** No HTML scraping is used in the current implementation. Wikipedia scraping was replaced with the supported API; `wikipedia_scraper.py` remains only as a backward-compatible import wrapper.
- **MySQL persistence:** Flask-SQLAlchemy models store users, beaches, hourly forecasts, Wikipedia information, request history, searches, and interactions.
- **CRUD operations:** The application creates user/search/request records, reads stored forecasts and profiles, and updates existing beach/forecast/cache records. Database relationships support cascading cleanup, but there is not yet a user-facing delete or account-edit interface.
- **Keyword search:** Searches surf-spot, requested-location, beach-name, and city fields.
- **Filtering:** Inclusive date range, time of day, current-location radius, and mandatory user ownership.
- **Sorting:** Newest first and surf spot A–Z.
- **Ranking:** Deterministic recency or alphabetical ordering with stable tie-breakers.
- **Pagination:** 10 results per page with counts, numbered pages, previous/next links, and automatic return to the results table.
- **Search telemetry:** Search criteria, result counts, pagination activity, and result views.
- **Forecast feedback:** Signed-in users can submit or update a 1–5 usefulness rating and optional comments for each saved forecast request; ratings are visible in forecast history.
- **Google sign-in:** OpenID Connect authorization-code flow with verified email and no stored Google access/refresh tokens.
- **Location features:** Interactive map, browser geolocation, separate current/forecast markers, nearest named beach or surf break, readable city/state/country, and distance display.
- **Wikipedia information:** Cached, attributed, plain-text API summaries with revision and license provenance.
- **Data validation:** Server-side validation of query length, dates, hours, coordinates, radius, sorting, page numbers, and ownership.

## Project Structure

```text
.
├── app.py                         # Flask factory and database CLI commands
├── config.py                      # Environment-based configuration
├── data/
│   └── surf_spots.json            # Legacy prototype sample data
├── docs/
│   └── screenshots/               # Project screenshots
├── models/
│   ├── beach.py                   # Normalized coastal locations
│   ├── forecast_feedback.py       # Per-request forecast rating and comments
│   ├── forecast_request.py        # Authenticated forecast history
│   ├── history_search.py          # Search and interaction telemetry
│   ├── surf_forecast.py           # Persisted hourly conditions
│   ├── user.py                    # Google-authenticated local profile
│   └── wikipedia_spot_info.py     # Cached Wikipedia API content
├── routes/
│   ├── auth.py                    # OAuth, profile search, history detail
│   └── main.py                    # Forecast and about routes
├── services/
│   ├── forecast_repository.py     # Beach/forecast upsert logic
│   ├── marine_weather_service.py  # APIFreaks client and normalization
│   ├── request_history_repository.py # Search SQL, distance, pagination
│   ├── search_analytics_repository.py # Telemetry persistence
│   ├── wikipedia_repository.py    # Wikipedia database cache
│   ├── wikipedia_service.py       # MediaWiki API client/ranking
│   └── wikipedia_scraper.py       # Compatibility wrapper; no scraping
├── static/
│   ├── map.js                     # Leaflet, geolocation, OSM lookups
│   ├── profile.js                 # Profile radius geolocation
│   └── style.css                  # Responsive presentation
├── templates/
│   ├── _forecast_report.html
│   ├── base.html
│   ├── history_forecast.html
│   ├── index.html
│   └── profile.html
├── tests/                         # Flask, service, auth, search tests
├── .env.example                   # Credential placeholders
└── requirements.txt               # Python dependencies
```

## Installation Instructions

### Prerequisites

- Python 3.10 or newer
- Git
- MySQL database/schema and a user allowed to create/modify tables
- APIFreaks Marine Weather API key
- Google OAuth web-client credentials for sign-in
- Internet access for APIFreaks, Google, OpenStreetMap, Leaflet, and Wikipedia

### Clone and configure

```bash
git clone <repository-url>
cd profthoms-it401-final-project

python3 -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
cp .env.example .env
```

Replace the placeholders in `.env`; never commit actual credentials.

### Apply database migrations/schema upgrades

For a fresh configured database:

```bash
flask --app app init-db
```

For an existing Breakline database, including the A4 telemetry tables:

```bash
flask --app app upgrade-db
```

These commands create application tables but do not create the MySQL database/schema itself.

### Run the application

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). Browser geolocation works on localhost and requires HTTPS in production.

Run tests with:

```bash
python -m pytest -q
```

### Google OAuth setup

1. Create/select a Google Cloud project and configure the OAuth consent screen.
2. Create an OAuth client of type **Web application**.
3. Add `http://127.0.0.1:5000/auth/google/callback` for local development.
4. Add the client ID and secret to `.env`.
5. Add the exact HTTPS callback URI before production deployment.

Breakline requests only `openid email profile`, requires a verified email, keys users by Google's stable `sub` claim, and does not persist Google tokens.

## Environment Variables

| Variable | Required | Purpose |
|---|---:|---|
| `SECRET_KEY` | Recommended | Signs Flask session cookies. Use a strong production value. |
| `FLASK_ENV` | No | `development` or `production`; defaults to development. |
| `APIFREAKS_API_KEY` | Yes for forecasts | Server-side APIFreaks Marine Weather credential. |
| `APIFREAKS_BASE_URL` | No | Overrides the marine API base URL for testing. |
| `WIKIPEDIA_BASE_URL` | No | Overrides the default English Wikipedia host. |
| `WIKIPEDIA_USER_AGENT` | Recommended | Identifies the app/operator to Wikimedia. |
| `WIKIPEDIA_CACHE_DAYS` | No | Database cache lifetime; defaults to 30 days. |
| `GOOGLE_CLIENT_ID` | Yes for sign-in | Google OAuth web-client ID. |
| `GOOGLE_CLIENT_SECRET` | Yes for sign-in | Google OAuth web-client secret. |
| `DB_HOST` | Yes | MySQL hostname; project default is `brian.cikeys.com`. |
| `DB_PORT` | No | MySQL port; defaults to `3306`. |
| `DB_NAME` | Yes | Existing MySQL database/schema name. |
| `DB_USERNAME` | Yes | MySQL username. |
| `DB_PASSWORD` | Yes | MySQL password. |
| `DATABASE_URL` | No | Complete SQLAlchemy URL overriding the individual `DB_*` values. |

The project uses `APIFREAKS_API_KEY`, not `RAPIDAPI_KEY`. `.env.example` contains placeholders only.

## Error Handling

| Condition | Behavior |
|---|---|
| Empty search submission | Shows “Enter at least one search filter,” returns no search results, and records no telemetry. A normal unsubmitted profile visit still shows history. |
| Invalid keyword | Rejects text over 150 characters; SQL wildcard characters are escaped before matching. |
| Invalid dates | Marks malformed dates and rejects an end date earlier than the start date. |
| Invalid time/sort | Accepts only allow-listed values and highlights the affected field. |
| Invalid radius/location | Requires valid latitude/longitude and a radius from 1 through 100 miles. Non-finite and out-of-range values are rejected. |
| Invalid page number | Non-numeric, zero, and negative pages fall back to page 1. Pages beyond the result set redirect to the last valid page. |
| No results | Shows a dedicated no-match state and a clear-filters action. Zero-result valid searches are retained for evaluation. |
| Database forecast error | Rolls back and logs the failure; a successfully retrieved external forecast can still render. |
| Telemetry read/write error | Rolls back and logs the analytics failure without blocking valid search results or saved-report views. |
| API timeout/error | Displays a user-safe retry/configuration message without exposing credentials. Optional Wikipedia/OSM failures degrade gracefully. |
| Unauthorized history access | Owner-scoped queries return `404` rather than exposing another user's record. |

## Search Evaluation

The automated A4 evaluation uses a controlled authenticated history containing The Wedge/Newport Beach at 05:00, Malibu Point at 12:00, and Sunset Cliffs/San Diego at 17:00. Dates are relative to the test execution date.

| # | Test query | Expected | Actual automated result | Precision/recall observation | Ranking observation |
|---:|---|---|---|---|---|
| 1 | Keyword `wEdGe` | The Wedge only | The Wedge returned; Malibu and Sunset excluded | High precision and complete recall for an exact substring despite case differences | Single result; ranking not material |
| 2 | Keyword `Newport` | The Wedge via `Beach.city` | The Wedge returned | Demonstrates recall across normalized city even when the displayed spot name differs | Single result |
| 3 | Time `afternoon` | Malibu Point at 12:00 | Malibu returned; 05:00 and 17:00 records excluded | Exact precision for the documented `12–16` boundary | Default recency retained within the filtered set |
| 4 | Date range tomorrow through +2 days | Malibu and Sunset | Both returned; today's Wedge excluded | Inclusive bounds produced complete recall for the controlled set | Newest request first unless A–Z selected |
| 5 | Radius 10 miles from Newport test coordinates | The Wedge only | The Wedge returned; Malibu and San Diego excluded | Correct geographic filtering for the controlled coordinates | Radius filters but does not yet rank nearest first |

### Evaluation summary

- **Expected versus actual:** All five controlled queries match their expected sets; the complete suite currently reports 35 passing tests.
- **Precision:** Strong for exact substrings and structured filters because each condition maps directly to stored fields.
- **Recall:** Strong within the controlled data, but production recall will fall for synonyms, misspellings, abbreviations, and unmapped aliases.
- **Ranking quality:** Stable and understandable, but not relevance-aware. Recency and A–Z are useful presentation orders rather than learned relevance.
- **Planned improvements:** Build a larger labeled evaluation set; record result impressions; add aliases, normalization, full-text or trigram matching; compare nearest-first and engagement-informed ranking; monitor zero-result queries.

## Screenshots

### Existing application evidence

#### Homepage

![Breakline homepage](docs/screenshots/homepage.png)

#### Forecast form and API result

![APIFreaks marine forecast form and result](docs/screenshots/api-results.png)

#### Combined map, forecast, and Wikipedia API interface

![Map, forecast, and Wikipedia information](docs/screenshots/combined-interface.png)

#### Wikipedia API result

The filename is retained from the pre-API prototype; the current application does not scrape Wikipedia HTML.

![Wikipedia API surf-break information](docs/screenshots/scraped-results.png)

### A4 search screenshot checklist

The authenticated A4 screens must be captured after Google sign-in and after `upgrade-db` creates the telemetry tables. Add the following real screenshots to `docs/screenshots/` before final submission:

| Required evidence | Target filename |
|---|---|
| Search form | `search-form.png` |
| Search results | `search-results.png` |
| Filtered results | `filtered-results.png` |
| Sorted/ranked results | `sorted-results.png` |
| Pagination | `pagination.png` |
| No-results state | `no-results.png` |
| Search-history/telemetry database evidence | `search-telemetry.png` |

Do not substitute mockups for these screenshots; they should show the running authenticated application and actual database evidence.

## Design Decisions

- **Searchable fields:** Names and user-entered location labels match the words users naturally remember. Numeric forecast measurements were excluded from keyword search because structured comparisons would be clearer.
- **Filters:** Date, hour group, and radius have unambiguous types and map efficiently to SQL predicates. User ID is mandatory for privacy.
- **Ranking:** Recency is the default because recent activity is usually most useful in a history view. A–Z supports known-item lookup. Stable ID tie-breaking prevents records from moving unpredictably between pages.
- **Pagination size:** Ten rows keep the profile scannable on desktop and mobile, limit ORM hydration, and provide enough data per page without a long scroll.
- **Telemetry:** Query/result counts expose retrieval gaps, while page and result-view interactions provide early engagement signals. Precise current coordinates are deliberately not retained.
- **API over scraping:** Wikipedia's MediaWiki API offers structured extracts, revision metadata, predictable error handling, and clearer policy compliance than parsing HTML.

## Known Limitations

- Keyword matching does not understand synonyms, misspellings, or semantic similarity.
- Singular and plural forms may differ.
- Ranking is rule-based and does not weight matching fields.
- MySQL full-text indexes are not currently used.
- Search is not personalized and telemetry does not yet affect live ranking.
- Result impressions and dwell time are not recorded, so a click cannot yet be compared reliably with every result the user saw.
- Radius filtering is not nearest-first sorting.
- Offset pagination may become slower for very large histories.
- Public Overpass and Nominatim services are best-effort and may be unavailable or rate-limited.
- OpenStreetMap and Wikipedia coverage varies by region.
- There is no user-facing favorite, delete, profile-edit, or account-deletion interface.
- The project uses idempotent schema commands rather than a versioned migration framework.

## Future Work

- Add result-impression telemetry, dwell time, favorites, and explicit feedback.
- Add semantic search and embeddings for surf-spot aliases, synonyms, and misspellings.
- Add personalized and engagement-informed ranking with privacy controls.
- Recommend beaches, forecast windows, and Wikipedia content from prior searches and interactions.
- Add query suggestions, autocomplete, recent-search shortcuts, and zero-result recovery.
- Evaluate MySQL full-text search, trigram/fuzzy search, and nearest-first geographic ordering.
- Add retrieval-augmented generation for cited surf-spot and safety summaries.
- Add Alembic/Flask-Migrate, telemetry retention/deletion policies, and an account-deletion workflow.
- Build a larger labeled search benchmark and monitor precision, recall, click-through rate, and zero-result rate over time.

## External Sources and Responsible Use

| Source | Purpose |
|---|---|
| APIFreaks Marine Weather API | Hourly marine conditions by coordinates or location text |
| OpenStreetMap tiles | Leaflet map presentation |
| OpenStreetMap Overpass | Nearest named surf break or beach |
| OpenStreetMap Nominatim | City/state/country reverse geocoding |
| English Wikipedia MediaWiki API | Plain-text introductory surf-spot context and provenance |

Breakline keeps credentials server-side, displays OpenStreetMap and Wikipedia attribution, uses timeouts/cancellation, caches Wikipedia content, and treats community-maintained location information as best-effort. Forecasts are for planning only; users should always verify local conditions and hazards.
