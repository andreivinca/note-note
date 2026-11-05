# Microsoft library

Everything Note Note asks of Microsoft goes through this folder: signing in,
the Graph transport, and the workarounds that reach past Graph where it has
no API. Providers call it and keep their own logic: what Sticky Notes and
OneNote do with an answer, and which Graph paths they ask for, stay in
their plugins. This file lists every Microsoft host and endpoint the app
calls, so that what each one is, and what would replace a workaround, is
answered in one place.

Standard library only. A provider script puts this folder and `lib/` on its
import path, as `sticky.py` and `onenote.py` do.

| File | What it is |
|---|---|
| `msgraph.py` | Sign-in (device code), the token file and its refresh, and the Graph transport: `request` and `http` (one paced, bounded request), `graph` and `graph_raw` (signed, with a JSON or a raw body), `download` (a resource's bytes, one attempt), `account_id`, and the caches stamped with the sign-in. Also the script `Account.qml` runs: `status`, `login`, `logout`. |
| `onenote_web.py` | **Workaround.** OneNote's web revision service and its sign-in, and a personal notebook's sections and groups as OneDrive items (`PERSONAL_ID`, `section_item`, `group_item`). |
| `Account.qml` | A provider's own Microsoft account in QML ([providers](../../docs/providers.md#servicesmicrosoft)). |
| `selftest.py` | `msgraph.py`'s tests. `onenote_web.py`'s are still the OneNote plugin's (`page_order_selftest.py`, `blank_lines_selftest.py`). |

How requests are paced, retried and refused is in
[providers](../../docs/providers.md#microsoft-retry-policies); the rate keys
below are that page's.

## Official APIs

| Host and endpoint | For | Called from | Rate key |
|---|---|---|---|
| `login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode` and `/token` | Signing in, and every token refresh | `msgraph.py` | none: signing in never waits behind a Graph cooldown |
| Graph `/me` | The account's name at sign-in, and its stable id (`account_id`) | `msgraph.py` | none at sign-in; the provider's own after |
| Graph `/me/mailFolders/notes/messages`, `/me/messages/{id}` | Sticky Notes: list, create, update, delete | `sticky.py` | `graph-mail` |
| Graph `/me/onenote/notebooks` (with `getRecentNotebooks`), `/sections`, `/sectionGroups`, `/pages`, `/pages/{id}/content`, `/resources/{id}/$value` | OneNote: list notebooks, groups, sections and pages; read, create, update and delete pages; make sections and groups; fetch pictures and recordings | `onenote.py`, `notebook_inventory.py` | `graph-onenote` |
| Graph `/me/drive/root/delta` | Which sections changed: OneNote has no change feed of its own ([OneNote changes](../../docs/onenote-changes.md)) | `section_changes.py` | `graph-onenote-drive` |
| Graph `/shares/u!{link}/driveItem` | A shared personal notebook's package, when Graph's notebook list leaves it out | `notebook_inventory.py` | `graph-onenote-drive` |

## Workarounds

Each one does what Graph cannot, through something Microsoft does not
document. Each is replaced where it lives, once Microsoft offers what is
named in its last column.

| Workaround | How | Lives in | Rate key | Replaced by |
|---|---|---|---|---|
| **Page order, blank-line removal, native list levels and list edits** ([page order](../../docs/onenote-page-order.md), [blank lines](../../docs/onenote-blank-lines.md)) | Graph `POST /drives/{d}/items/{i}/preview` on the section's file; the `getUrl` it answers (`my.microsoftpersonalcontent.com/personal/{cid}/_layouts/15/embed.aspx`) holds a WOPI token for `…/_vti_bin/wopi.ashx/files/{i}`, which signs revision reads and writes to `onenote.officeapps.live.com/o/OneNote.ashx` | `onenote_web.py`; used by `onenote.py`, `page_order.py`, `blank_lines.py`, `list_edits.py`, `list_indents.py`, `revision_objects.py` | `onenote-web`; the preview `graph-onenote-drive` | A page-order API in Graph's OneNote API, and its page `PATCH` writing what it now cannot: blank lines and skipped list levels |
| **Renaming and deleting sections and section groups** | `PATCH` or `DELETE` on the section's `.one` file, or the group's folder, in its owner's OneDrive: Graph `/drives/{d}/items/{i}` | `onenote_web.section_item`, `group_item`; called by `onenote.py` | `graph-onenote-drive` | Rename and delete on Graph's OneNote `sections` and `sectionGroups` |
| **Section order** ([section order](../../docs/onenote-section-order.md)) | The notebook's `.onetoc2` files read from OneDrive: Graph `/me/drive/items/{i}` and `/children`, then each file's `@microsoft.graph.downloadUrl` on `*.files.1drv.com`, `*.storage.live.com`, `*.sharepoint.com` or `*.microsoftpersonalcontent.com` | `section_order.py` (its `Remote`) — **not yet in this library** | `graph-onenote-section-order`; the signed downloads none | A section order on Graph's OneNote sections |
| **A OneNote ID is a OneDrive item** | A personal notebook's, section's or group's ID is `0-` and its OneDrive item ID (`PERSONAL_ID`), an observed shape. The three workarounds above, and the changed sections, depend on it | `onenote_web.PERSONAL_ID`; the other way round, `notebook_inventory.personal_notebook_id` — **not yet in this library** | — | A documented mapping, or no workaround needing one |
| **Shared personal notebooks** | Graph's notebook list leaves some out: they are found through `getRecentNotebooks` and `/shares`, their IDs derived from their OneDrive package (`personal_notebook_id`), then verified with the OneNote API | `notebook_inventory.py` | `graph-onenote`, `graph-onenote-drive` | Graph listing every notebook shared with the account |

## Not yet in the library

- `section_order.py`'s `Remote` opens its own connections: OneDrive
  metadata with the token it is handed, and the signed `.onetoc2`
  downloads. It belongs here, on `request` and `download` with a rate key of
  its own.
- `notebook_inventory.personal_notebook_id`, `PERSONAL_ID` the other way
  round, belongs beside it in `onenote_web.py`.
