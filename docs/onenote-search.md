# OneNote content search

OneNote search uses a persistent text cache. Initial indexing runs while the
provider is enabled in the shell, starting with unread pages in the active
notebook. Up to two background jobs each read one page's HTML and extract text
without fetching image or attachment resources. Searches use the cache and
make no Graph requests.

Startup discovers notebooks and sections before downloading their page lists.
Discovery also checks recent notebooks for personal OneDrive shares omitted
from Microsoft's main notebook list. It resolves missing personal notebook
links through Graph's OneDrive API (using the optional `Files.Read` scope),
then verifies the notebook with OneNote before adding its sections. Known
links are skipped, and duplicate notebooks are merged by their OneNote IDs.
Failures keep the existing inventory and appear as listing warnings.
Notebook traversal and share verification also save their pending requests,
so a budget pause resumes without repeating completed discovery requests.
Page discovery then fetches up to 100 titles per response, with one background
job queued at a time. Expanding a section promotes its page-list request;
opening and saving notes retain a queue slot and an HTTP slot. Discovered
titles appear immediately, and pagination resumes from the saved continuation
after a restart or budget pause. Cached pages stay visible until the complete
section listing can establish which pages were deleted.
Reaching the cache limit stops that continuation and reports incomplete
coverage. Existing sections can still refresh, and partial listings preserve
cached pages until the complete section response establishes deletions.

The search panel shows how many listed pages are searchable while indexing
is incomplete. Results update as text arrives. Indexing continues when the
Note Note window is hidden. Shell restarts resume from the saved cache, and
disabling the provider or signing out stops its jobs. Cached search remains
available while Graph requests are throttled.

The initial search scope is all pages in the provider's listing, subject to
the existing 3,000-page listing limit. Notebook tabs show coverage for their
own notebook. A partial or capped listing remains marked incomplete even
when every known page has been indexed. Search covers visible text and link
targets, case-insensitively; it does not add OCR, handwriting recognition or
attachment-content search.

## Refresh and request usage

- Successful page reads and saves update the cached text without another
  request. New pages are added and confirmed deletions remove their text.
  Saves index the validated merged page, including remote edits. An unresolved
  local conflict leaves the index at the fetched remote version. The search
  cache never changes the editor's merge baseline.
- Changed page timestamps trigger another background read. Unchanged entries
  are revisited after seven days because Graph sometimes misses timestamp
  changes. Closed-app time counts toward that interval.
- Failed pages remain pending, with retry delays from five minutes up to one
  day. Existing text survives transient failures; inaccessible or missing
  pages lose their cached text. Incomplete coverage remains visible.
- Page discovery, indexing and automatic page checks yield to interactive
  queue jobs. Their admission reserves 20 requests in each configured window
  under the shared budget lock, and leaves the last HTTP slot for interactive
  work. Budget exhaustion defers background work alone. Real service throttles
  still pause the provider's normal Graph lane.

Initial download time depends on page count, response times and the available
budget. Indexing accounts for each page request and keeps capacity available
for normal note use.

Microsoft's delegated OneNote limit is 120 requests per minute and 400 per
hour. Graph JSON batches can contain up to 20 requests, but each is evaluated
against the service limit separately. Batching HTML downloads therefore cannot
remove the request cost of full content search. A large first-time index can
take several hours while normal note use continues. A previously exhausted
budget still has to recover; upgrading does not erase requests already spent.
See [OneNote limits](https://learn.microsoft.com/en-us/graph/throttling-limits#onenote-service-limits)
and [Graph batching](https://learn.microsoft.com/en-us/graph/json-batching#batch-size-limitations).

## Storage and lifecycle

`plugins/org.note-note.onenote/search_index.py` owns extraction, cache transactions,
coverage and retry/refresh selection. `PageInventory.qml` schedules resumable
page-list responses, and `SearchCache.qml` schedules content reads through
the existing request queue and answers searches outside it. Workers claim
distinct pages under the cache lock; abandoned claims become
available when their process exits, with a ten-minute lease as a fallback.
The host uses `searchChanged()` to refresh an open query, with one callback
per search.

The private cache stores only normalized text and index metadata. It is
bounded to 128 KiB of text per page and 16 MiB total JSON. Oversized pages
remain unavailable to full content search rather than being silently cut
short. An account's cache is cleared on sign-out. Token refresh retains it;
a new sign-in starts a new cache. Older unscoped listing caches are rebuilt
once after upgrading. See [security](security.md) for file permissions and
protection against late responses.

`debugState` reports the window state, queue pauses and content-search
counts, worker count and budget delay without exposing note text.
