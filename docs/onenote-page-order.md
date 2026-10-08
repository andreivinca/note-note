# OneNote page order

Page order is read directly through Graph and written through OneNote's
undocumented web revision service. Section ordering remains a separate,
read-only feature; see [section order](onenote-section-order.md).

## Reading

The section page listing uses `pagelevel=true`, selects `order`, `level` and
`links`, and requests `$orderby=order`. Graph supplies both order and hierarchy;
there is no local page-order overlay or binary parser for these reads.
The query is described in [Microsoft's OneNote content documentation](https://learn.microsoft.com/en-us/graph/onenote-get-content).
Each section's completion marker records the metadata version its list was
fetched with. Lists from before this query stay complete for discovery and
search coverage, so an upgrade spends no budget on closed sections; an
opened section is fetched again, and only saved listing cursors are dropped.
A page created by the app is recorded as a top-level page at the end of its
section, which is where Graph puts it; its create response has no level.

## Writing and consent

Graph marks page order [read-only](https://learn.microsoft.com/en-us/graph/api/resources/page?view=graph-rest-1.0).
Live no-op PATCH requests to v1.0 and beta rejected `order` with HTTP 400,
code 20114. The web client's HAR revealed a conditional section-root revision
that changes `ElementChildNodesOfSection` (`0x24001C20`), leaving page bodies,
identifiers, hierarchy and other root properties intact.

The app verifies the section's personal OneDrive file identity, calls
`driveItem/preview`, fetches the signed Microsoft preview without redirects or
a Graph Authorization header, and parses its JSON file information without
executing JavaScript. The resulting app-and-user WOPI credentials authorize
the revision service. Credentials remain in memory and are renewed from the
app's own Microsoft sign-in; no HAR, cookies or signed URLs are retained.
Service version and request-key challenges are discovered dynamically.

Sign-in requests `Notes.ReadWrite` and `Files.ReadWrite`; Microsoft asks for
account consent. That permission also permits writing OneDrive files beyond
OneNote. This uses delegated dynamic consent and requires no change to the
shared app registration. Renewal treats `Files.ReadWrite` as optional, so a
sign-in made before the app asked for it keeps normal note access, and the
OneNote list asks to sign in again. That sign-in does not sign out first: the
same account keeps its cache session, so the notebook inventory, search index,
drafts and running jobs survive.

The section's file is looked up as `/drives/{owner}/items/{item}`, the owner
being the item ID's drive prefix, and must be that personal drive's `.one`
file. `/me/drive/items` reaches only the account's own drive; for a notebook
shared with the account it returned 400.

This integration is a compatibility boundary, not a supported Graph write
API. Even [Graph's preview documentation](https://learn.microsoft.com/en-us/graph/api/driveitem-preview?view=graph-rest-1.0)
does not promise personal-account support, although the endpoint worked on the
tested account. Microsoft changes may disable ordering. The provider fails
visibly rather than guessing a different resource, recreating notes, or
retrying an uncertain write.

`web_session.py` carries the service's reads and writes and decides which
notebooks it can write. `revision_objects.py` reads the section and page
objects. Page ordering (`page_order.py`) and
[blank-line removal](onenote-blank-lines.md) (`blank_lines.py`) are the two
changes written through it.

## Provider and UI behavior

Ordering is available within fully loaded sections, with at least two parent
pages, of personal notebooks the signed-in account owns or can edit (OneNote
role Owner or Contributor). Read-only shares and work or school notebooks
offer no drags; the provider and `reorder-pages` apply the same rule. Each
parent declares its section's
reorder group and carries its subpages. Subpage indentation is shown, and
subpages retain their existing order and parent. Individual subpage promotion,
cross-section moves and section reordering are not enabled.

The generic row declaration is documented in [the provider contract](providers.md#provider-defined-ordering).
The host has no OneNote-specific drag rules. Both local-provider presentations
use this contract too. A future provider can declare section/tree groups and
handle their scopes without changing shared UI code.

Before writing, the backend fetches native Graph page identities and reads the
latest section revision. It follows that revision's ancestry, resolves only
live page-series references, and joins page metadata GUIDs to Graph's public
OneNote client links. Older sections list one page's metadata more than once;
each page cell joins the next distinct page. It requires complete membership, matching hierarchy and
the starting order the UI saw. A fresh `BaseId`/`ExpectedLatestId` guards
concurrent changes. Only the section root's page-series sequence is submitted.
The service is read back, then native Graph order is confirmed before the
canonical cache and provider rows are published. Graph trails the service by
seconds, so it is listed at most three times, after 1, 2 and 4 seconds.

The UI keeps a pending drag visible across refreshes and displays
**Saving order…**. Another drag in that group waits for completion. Failures
restore canonical rows and trigger a section refresh, including when the
server might have committed but its response was lost. No timeout or 5xx can
replay the revision automatically. Explicit rejected key challenges may retry.

## Verification on 2026-10-06

- `pagelevel=true` returned order and level for all 37 pages in a live section;
  the same listing without it returned neither field.
- A browser-authorized revision reversed two existing pages, then restored
  their starting order; both content hashes remained unchanged.
- An isolated app sign-in with `Files.ReadWrite` repeated that round trip
  using fresh preview authorization, root discovery and current revisions,
  without HAR credentials. The new `onenote.py reorder-pages` command then
  passed the same round trip. The installed Flatpak token was unchanged.
- Token renewal retained the optional write grant and authorized a fresh
  section session. A harmless revision using an old base was rejected;
  the section's properties remained unchanged.
- Synthetic tests cover public identity joins, inherited revision branches,
  subpage blocks, partial/duplicate membership, concurrent changes, credential
  boundaries and uncertain writes. QML tests exercise actual pointer drags,
  tree blocks, section boundaries, pending saves, cancellation and scrolling.

The HAR also contained notebook-level section order. Notebook-opening and
folder-revision requests using fresh app authorization returned operation
codes 14 and 6. A renewable replacement for `.onetoc2` section reading was
therefore not established during this investigation.
