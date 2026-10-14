# OneNote changes from OneDrive

OneNote has no change feed: Graph's OneNote API offers no delta query and no
notifications a desktop app can receive, and a page's `lastModifiedDateTime`
does not move reliably. The provider used to find changes by asking every
minute for the open page and its section's page list: 120 of OneNote's 400
requests an hour while a page sat open and nothing changed.

A OneNote section is a `.one` file in its notebook's OneDrive folder, and any
change to its pages changes that file. OneDrive's
[delta](https://learn.microsoft.com/en-us/graph/api/driveitem-delta?view=graph-rest-1.0),
an official Graph v1.0 API, lists the files changed since a cursor. The
provider asks it once a minute, and asks OneNote for the open page and its
section only while that section has changed.

## How it works

`onenote.py changes` (`section_changes.py`) answers which tracked sections
changed since its last call:

```json
{"tracked": ["0-ABCDEF0123456789!101", "..."], "changed": ["0-ABCDEF0123456789!101"]}
```

- **Tracked sections.** The cursor follows the account's own drive
  (`/me/drive/root/delta`), so it sees the notebooks the account owns and no
  other: a notebook shared with it lives in its owner's drive. A section is
  tracked when its notebook's `userRole` is `Owner` and both IDs are personal
  OneDrive IDs. A personal section's ID is `0-` followed by its file's item
  ID, so a changed item names its section with no further request.
- **The cursor.** The first call starts one with `token=latest`: one request,
  instead of listing every file in the drive. It is kept for the signed-in
  account in `note-note-onenote-changes.json`, so a restart continues where
  the last run stopped. What changed before a cursor started is unknown, so
  a new one, or one OneDrive no longer keeps (HTTP 410), reports every
  tracked section as changed.
- **Busy drives.** A round follows at most ten pages of the feed and keeps
  its place in the rest, so a drive full of other activity (photos uploading)
  is read over several minutes.
- **Optional work.** A round runs under the background reserve and on the
  `graph-onenote-drive` budget, never OneNote's. A paused round answers
  `deferred`, and a failed one is not run again: the next minute is its retry.

`Provider.qml` asks every third poll tick, while a OneNote page is open, and
then checks the page and lists its section when any of these holds:

- OneDrive reported the section changed in the last 2.5 minutes. Graph shows
  a change up to about a minute and a half after OneDrive does, so a single
  check straight after the report could read the old page.
- The section is not tracked.
- The round failed, was deferred, or the page is not listed yet.

Every other minute costs OneNote nothing.

## Costs

For one open page, in an hour without changes:

| | OneNote | OneDrive |
|---|---:|---:|
| Before | 120 | 0 |
| Now, tracked section | 0 | 60 |
| Now, untracked section | 120 | 60 |

While a section is being edited, here or elsewhere, it is checked every
minute as before, until 2.5 minutes after its last change. Our own saves
change the file too, so a burst of saves is followed by about three checks.

## Limits

- **Section, not page.** The feed names the changed section file. Which page
  changed is still found by comparing the open page's text.
- **Any change counts.** Someone the notebook is shared with, or a OneNote
  app syncing, can change a file without a visible edit. Such a report costs
  one check that finds nothing.
- **Shared notebooks and work or school accounts** are not tracked and are
  polled as before. Each shared folder would need a cursor of its own.
- **Other sections** come back with the periodic listing or Refresh, as
  before; only the open page's section follows the feed.

## Verification on 2026-10-14

On a personal account with four owned notebooks and 38 sections:

- One root cursor covered every notebook. `token=latest` returned it in one
  request.
- Edits on OneNote for the web, the OneNote phone app and in Note Note
  (Graph PATCH, a list indent and a page reorder through the revision
  service) each changed the section file. Each appeared at the next poll,
  10 to 20 seconds after the file changed.
- A feed page held the changed file, its two parent folders and its
  notebook's package; nothing else from the drive in six minutes.
- The notebook package's `eTag` stayed the same across every change, so a
  change is read from the section file, not the notebook.
- A title typed on the web at 21:57 was not in Graph's page list at 21:58:21
  and was at 21:58:37. No edited page's `lastModifiedDateTime` changed.
- A section changed while nobody edited it, presumably a OneNote app syncing
  or another member of the notebook.
