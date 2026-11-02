# OneNote section-order investigation: offline handoff

Prepared 2026-11-02 for Note Note. Investigation only; no implementation or live requests.

## Result and evidence limit

**These captures establish how the browser opens a notebook folder and receives its ordered section/group objects. They do not contain a section-order or section-group-order write.** The two captured ordering writes change pages inside sections. The third captured write changes page-content objects. An exact, observed folder-write payload therefore cannot be supplied from these materials.

The most useful authorization finding is concrete: the browser opens the notebook using a WOPI **`/folders/<item>`** resource. Its opening response supplies separate **`/files/<item>`** credentials for sections and a `/folders/<item>` credential for a child section group. Note Note's current preview parser accepts only `/files/<item>`, and its revision reads/writes hard-code `IsFolderCell=false`. Reusing a section session as a notebook session is consequently not an established authorization path.

The captured client JavaScript also names operation result **6 `invalidFileID`** and **14 `unspecifiedFailure`**. A resource/credential mismatch is a plausible explanation for the earlier failure, but the failed app requests are not in these captures and their exact cause remains unknown.

No network requests were made. No app sign-in files were read. The HARs were parsed in memory with Python; no extracted payloads or credentials were saved. This handoff is the only file written. All identifiers below are descriptive placeholders; no captured identifier values, tokens, cookies, signed URLs, authorization-header values or e-mail addresses are reproduced.

## Evidence convention and request inventory

Indices are **zero-based positions in `log.entries`**, separately for each HAR. Timestamps are copied as recorded, including their timezone. Query values are omitted. The following aliases always mean these complete capture filenames:

| Alias | Capture file | Entries |
| --- | --- | ---: |
| A | `onedrive.live.com_Archive [26-10-06 00-42-27].har` | 5 |
| B | `onedrive.live.com_Archive [26-10-06 00-49-34].har` | 231 |
| C | `onedrive.live.com.har` | 8 |

**Date correction:** C's requests are dated **2026-10-08**, not 2026-10-06. Do not treat all three files as one October 6 browser session.

All revision-service requests below POST to `https://onenote.officeapps.live.com/o/OneNote.ashx`. Their outer body is JSON of shape `{"Mode":1,"srs":[[operationKind, operationObject], ...]}`. All returned HTTP 200 and operation status 0. `perfTag` appears on some URLs, but is not part of the revision body.

| Evidence | Capture/index | Timestamp | URL path; operation | Payload/response shape and significance |
| --- | --- | --- | --- | --- |
| A4 | A, 4 | `2026-10-06T00:42:09.960+03:00` | `/o/OneNote.ashx`; kind 3, PutChanges | One revision, `IsFolderCell=false`, one object of class `0x60007`, with a two-reference `0x24001C20` child list. This is a section's page-series order, not notebook section order. `StatusCode=0`, `IsConflict=false`. Its preceding root read is absent. |
| B12 | B, 12 | `2026-10-06T00:49:08.740+03:00` | POST `/o/onenoteframe.aspx`; browser frame bootstrap | Form includes `access_token`, `access_token_ttl`, `fileGetUrl`, `fileName`, `user_id`, `DocID`, diagnostics and UI fields. URL query includes `wopisrc`. That source is the same folder resource used by B30. The form token equals B30's FileId token. Values are omitted. |
| B27 | B, 27 | `2026-10-06T00:49:08.931+03:00` | GET `/officeonline/o/s/<build>/OneNoteDS.js`; static JavaScript | Defines GetCellsRequest as kind 1, PutChangesRequest as kind 3, GetChangesResponse, object-class names and the OperationResult enum. This is source-code evidence, not an operation executed by this GET. |
| B30 | B, 30 | `2026-10-06T00:49:09.016+03:00` | `/o/OneNote.ashx`; kind 1, GetCells | Opens a folder FileId. Returns `Responses:[[1,{...,Cells:[folderState,sectionState,pageState]}]]`. The folder state includes a complete ordered root, section proxies and one folder proxy. Detailed below. |
| B71 | B, 71 | `2026-10-06T00:49:12.958+03:00` | GET `/officeonline/o/s/<build>/OneNoteDS.box4.dll1.js`; static JavaScript | Contains the section drag handler and FolderEditor.G4a implementation, including link reordering and sequential assignment of a registered ordering property. Source-code evidence only; no corresponding folder write appears in the HAR. |
| B201 | B, 201 | `2026-10-06T00:49:15.740+03:00` | `/o/OneNote.ashx`; two kind-2 GetChanges operations | Reads the opened section root and an existing page cell. Both have `IsFolderCell=false`, known cell IDs, nonempty ClientKnowledge and known expected heads. Responses have empty revision lists and omit a new latest revision. This is incremental polling, not folder-root discovery. |
| B229 | B, 229 | `2026-10-06T00:49:24.731+03:00` | `/o/OneNote.ashx`; kind 2, GetChanges | Reads another page cell: `PageId` present, `IsFolderCell=false`, empty-string ClientKnowledge, expected head NIL. Returns page revisions, LatestRevisionId, ClientKnowledge and PageHtml. Its page-content head is not the base for B230's section-root write. |
| B230 | B, 230 | `2026-10-06T00:49:25.072+03:00` | `/o/OneNote.ashx`; kind 3, PutChanges | One section-root object, class `0x60007`, `IsFolderCell=false`. Compared with B30's section state, only `0x24001C20` changes: its two existing page-series references are reversed. Both expected-head fields and BaseId equal B30's section LatestRevisionId. `StatusCode=0`, `IsConflict=false`. |
| C0 | C, 0 | `2026-10-08T04:24:30.861Z` | `/o/OneNote.ashx`; kind 2, GetChanges | Incremental page-cell read, `PageId` present, `IsFolderCell=false`, known expected head and ClientKnowledge. Empty returned revision list. |
| C4 | C, 4 | `2026-10-08T04:24:33.771Z` | `/o/OneNote.ashx`; kind 3, PutChanges | Page-content revision containing five objects: classes `0x20044`, `0x6000C`, `0x6000D`, `0x6000E`, `0x120001`. `IsFolderCell=false`; no folder root or ordering-ID property. `StatusCode=0`, `IsConflict=false`. The exact user edit is not needed to establish that this is not section ordering. |
| C7 | C, 7 | `2026-10-08T04:24:38.801Z` | `/o/OneNote.ashx`; kind 2, GetChanges | Polls the same page cell using C4's new revision as expected head. Empty returned revision list. |

Across all three files there are **eight OneNote.ashx requests / nine operations**: one GetCells, five GetChanges and three PutChanges. Every recorded PutChanges has `IsFolderCell=false`; no recorded GetChanges has `IsFolderCell=true`. B contains no recorded WebSocket messages. No positive-size request body in B is missing its postData text. These checks establish the contents of the supplied exports, not the completeness of the user's wider browser activity.

## What the notebook-opening response actually shows

### Opening request and current revision

Evidence: **B30**, with bootstrap context **B12** and the operation name from **B27**.

The GetCells operation object has these fields:

```text
FileId: URL-encoded query string with WOPIsrc, access_token, access_token_ttl
PageTarget: opaque slash-delimited string, length 94
            (two nonempty components of length 46, then a trailing slash)
OperationId: 1
IsRemoveSsrEnabled: false
SearchQuery: null
IsNewFile: false
InitialParaId: 0
RequestUrl: browser URL string, length 860; value omitted
SkipPageHtmlInResponse: false
SessionStartInfoJson: JSON encoded inside a string, with session/build/UI/host telemetry
```

The recorded FileId's decoded WOPIsrc has this shape, with no source query:

```text
https://my.microsoftpersonalcontent.com/personal/<drive>/_vti_bin/wopi.ashx/folders/<item>
```

GetCells does not use the current app's unknown-root GetChanges request. It returns the notebook folder and selected section/page state together. In `Cells[0]`:

- `StatusCode=0`, `AvailableFileAccess=1` (observed numeric value; not independently interpreted as a permission grant).
- `RootCellId` equals this cell's `CellId`. It is a concrete `guid|1` value, **not** the app's UNKNOWN_ROOT sentinel.
- `LatestRevisionId` equals the sole returned revision's `Id`; ClientKnowledge is an opaque 112-character string.
- `FileId` is the same folder FileId as the opening request.
- The sole revision has `BaseId=NIL`, `ExpectedLatestId=NIL`, `IsFolderCell=true`, `RelativePath=null`, `Ops=[]`, one object group and one root descriptor.
- The root descriptor's role equals `revision_objects.CONTENT_ROOT`; its ObjectId selects the folder-content object below.
- Folder `ContextId` is the literal four-character **string `"null"`**, both at cell level and in the returned revision. It is not JSON null and is not the app's NIL value. This is an observed serialization detail, not a recommendation to copy it blindly into a write.

`Cells[1]` is a section state with its own root cell, LatestRevisionId, 456-character ClientKnowledge and section FileId. `Cells[2]` is page state under that section FileId. Their revision objects have `IsFolderCell=false`. The folder's revision and ClientKnowledge must never be replaced by either child's state.

**Unresolved:** the single base-NIL folder revision may be a synthesized folder view rather than a persisted TOC revision chain. Its suitability as a conditional write base must be established live. There is no separate folder GetChanges request in these files showing how the browser refreshes that head.

### Folder objects and two distinct child lists

Evidence: **B30 response, `Cells[0].RevisionList[0].ObjectGroups`**; class names from **B27**.

The object group contains **35 objects**: one folder root, sixteen section proxies with sixteen metadata objects, and one folder proxy with one metadata object.

| ClassId | Captured client class name | Count | Properties and shapes |
| --- | --- | ---: | --- |
| `0x60004` | `folderContentNode` | 1 | `0x08004C0B` has string value `"true"`; `0x24001C20` contains 17 ordered references; `0x24004C02` contains 16 ordered references. |
| `0x60005` | `sectionProxyNode` | 16 | `0x1C00200F`: credential-bearing FileId string; `0x1C002035`: opaque string; `0x1C004C04`: GUID-shaped identity string; `0x24003442`: one metadata-object reference. |
| `0x20031` | `sectionMetadata` | 16 | `0x1C004C04`: GUID-shaped identity matching its proxy; `0x1C004C03`: name string; `0x14001CBE`: scalar string. No captured identity or name values are reproduced. |
| `0x6002D` | `notebookFolderProxyNode` | 1 | `0x1C00200F`: child-folder FileId; `0x1C002035`: opaque string; `0x24003442`: one metadata-object reference. |
| `0x20032` | `folderMetadata` | 1 | `0x1C004C05`: name string. |

The `0x24001C20` references include all sixteen section proxies followed by the folder proxy. The `0x24004C02` references are **exactly the same sequence with the folder proxy excluded**. This gives a concrete mixed-child sequence and a section-only sequence in this snapshot. It does not prove which list or lists a folder reorder must write, or whether their server meanings extend beyond this sample.

References use the same comma-separated `{guid}{integer}` serialization parsed by `revision_objects.references()`. Object/cell/revision IDs use `guid|integer`. The GUID-shaped proxy/metadata identity is a useful additional equality check; it is not itself proof of a Graph section-ID mapping.

**`NotebookElementOrderingID` (`0x14001CB9`) does not occur in these returned folder objects.** The objects are runtime folder/proxy classes, not the `0x20001` TOC property containers parsed by `toc.py`. Do not equate the returned JSON snapshot with the `.onetoc2` binary representation or transplant binary TOC entries into this service.

The folder proxy is positive evidence that a section group is represented and has a position in this parent snapshot. There is no child-group opening, group reorder, nested-group ordering trace or cross-folder move in these captures.

### Additional evidence from captured JavaScript

Evidence: **B71**, FolderEditor.G4a, around character offset 876949 in the captured response; **B27**, property registration around offset 1426558. Offsets count the decoded response text, not HAR bytes.

The section drag handler resolves section metadata objects and calls FolderEditor.G4a. That method repositions links in two parts of its in-memory graph and then assigns sequential values starting at 1 through `properties.setValue(...NPj, rank)` while iterating section-type children. B27 registers NPj through `k.$(185, ..., 1)`.

**Inference:** this is consistent with a folder sequence plus per-section ordering metadata and the repository's documented NotebookElementOrderingID. It is stronger evidence than guessing solely from a property name, but is **not a serialized request**. The registration number alone does not establish the wire property's full ID, the destination objects, whether metadata is transformed server-side, or whether both root lists must be submitted. No matching network write exists in the exports. Do not use this source fragment as an implementation-ready payload recipe.

## Conditional writes: observed page behavior versus proposed folder behavior

### The observed page-order write

Evidence: **B30 → B201 → B229 → B230**, with **A4** as a second isolated section-root write. The elapsed sequence includes page navigation and polling; B229's page read is not required to form B230's root reorder.

For B230, let `L` denote B30's **section** LatestRevisionId, `S` its section RootCellId, and `Fsection` the section FileId returned by GetCells. The recorded operation has this shape:

```text
kind = 3 (PutChanges)
Revision = {
    Id: newly allocated guid|integer,
    FileId: Fsection,
    RelativePath: null,
    CellId: S,
    ContextId: NIL,
    ExpectedLatestId: L,
    BaseId: L,
    RootObjectDescriptors: null,
    ObjectGroups: [{ Id: new guid|integer, Objects: [updatedSectionRoot] }],
    IsFolderCell: false
}
BaseRevision: null
ExpectedLatestId: L
ExpectedIncrementalActionId: NIL
IsVersionHistoryEnabled: true
ClientKnowledge: section ClientKnowledge (length 456)
RtcMachineIdHint: null
ShouldSendUpdateNotificationOnSuccess: true
ChangeStateList: null
MergePromptStatus: 0
```

The operation also carries the common fields already constructed by `common_operation()`: operation/dependency IDs, null local Cobalt IDs, false backup/pin flags, zero routing/request counters, null lineage and encryption-session fields. Comparing the submitted root with the live section objects returned by B30 proves that only `0x24001C20` changes. All other root properties and the existing root ObjectId are preserved. The service replies with status 0 and `IsConflict=false`.

The three relevant concurrency fields are **Revision.BaseId, Revision.ExpectedLatestId and outer ExpectedLatestId**. They all equal the same latest revision of the cell being changed. A page-cell head, folder head or unrelated section head is not an interchangeable base.

### What is not established for a folder write

There is no observed request from which to state an exact folder-order write sequence, changed-object list, folder ContextId encoding or folder conditional-head behavior. The likely experiment is a kind-3 revision of the folder root with `IsFolderCell=true`, using the folder FileId and fresh folder head. That is a **proposal**, not a captured success.

In particular, it is unsafe to decide now between changing `0x24001C20`, changing `0x24004C02`, changing both, or also submitting per-section metadata. The static client code suggests more than one in-memory representation changes. A proper implementation must resolve this before enabling writes, through a new focused browser trace or equivalent verified protocol evidence.

## Authorization comparison and explanation of codes 14 and 6

### Browser credential shapes

Evidence: **B12, B30, B201, B229, B230**. The comparisons below were performed in memory and retain only shapes, lengths and equality results.

- The notebook-opening FileId is a URL-encoded three-parameter string: `WOPIsrc`, `access_token`, `access_token_ttl`. In B30 it is 1539 characters long after JSON decoding. The decoded token is 1314 characters, with three dot-separated components; TTL is a 13-digit value. Token contents/claims were not needed.
- That FileId targets `/personal/<drive>/_vti_bin/wopi.ashx/folders/<item>` on `my.microsoftpersonalcontent.com`. B12's `wopisrc` query names the same resource; its form `DocID` matches that resource's item; its form token equals the GetCells FileId token.
- B30's `X-AccessToken` header equals this folder token. The subsequent section/page reads and section-root write keep using that same **folder token in the header**, while their body FileIds contain **different, section-specific tokens**.
- The 17 proxies in the folder snapshot each carry their own `0x1C00200F` FileId. Their decoded tokens are 1388 characters. Sixteen WOPIsrc paths use `/files/<item>`; one uses `/folders/<item>`. These are issued resource credentials, not IDs to derive by editing the parent source string. Treat the entire property as secret, even though it appears among revision properties.
- B230's section FileId is 1601 characters; A4's is 1609. In C the section FileId token is 1353 characters, while the header token is 1280. These are observations of browser sessions, not required lengths or validation constants for app credentials.
- Revision-service requests have `X-Key`: an opaque 108-character canary, distinct from access_token. Within B, the same key is used for opening, section/page reads and the write. A has a different key. There is no evidence of a separate folder-order key.
- `X-OfficeVersion` is a four-part numeric version string, 16 characters in these requests. A and B use the same version; C uses a different one. B uses one version across GetCells, GetChanges and PutChanges. No captured evidence calls for a different folder service version.
- Other headers include `X-UserType` (WOPI), `X-UserSessionId` (GUID-shaped), `X-Requested-With` and `X-xhr`. TTL is present as `X-AccessTokenTtl` on B's later requests; B30 omits that header while retaining TTL inside FileId.
- A/B revision requests include cookies (21 HAR cookie records); C's recorded revision requests have neither a Cookie header nor cookie records. None has an HTTP Authorization header. C's omission does not prove cookies are unnecessary for notebook-folder opening. Browser cookie values must never be adopted by the app.

All recorded OneNote.ashx requests already have a key and version and return 200. They do **not** show OneNote.ashx key/version discovery. Some other browser handlers return 412, but those are not evidence for a folder revision operation. The existing app's discovery strategy is independently described in the repository and implemented in `Session.operation()`.

### What the app currently mints

Code evidence: `web_session.py` lines 74, 119, 133, 206, 217 and 231; `docs/onenote-page-order.md`.

`Session.for_section()` verifies a personal `.one` drive item under its owner's drive, POSTs that item's `/preview`, validates the returned signed preview URL, fetches it without Graph authorization or redirects, and parses `g_fileInfo` without executing JavaScript. `frame_info()` extracts `wopiSrc`, `wopiTokenAppAndUser` and `wopiTokenAppAndUserTtl`, verifies the exact expected **`/files/<section-item>`** source and expiry, then constructs the same three-parameter FileId shape. The same freshly minted token is placed in the app session's X-AccessToken header.

The app therefore has the correct overall credential envelope and a separately live-verified page-writing path. It does not reproduce B's notebook-level header credential plus child FileIds, and its strict parser cannot accept a notebook folder source unchanged. The captures contain no app-generated preview response, so no comparison of actual app token lengths, claims, audiences or permissions can be made offline.

`Session.operation()` already negotiates `X-NewKey` after an explicit HTTP 412 challenge, accepts a returned version with that challenge, and discovers a version from an initial non-mutating 503. No browser key, version string or token should be hard-coded from these HARs.

### Hypothesis for the earlier failure

Evidence for the meanings: **B27**, OperationResult enum, around offset 2824049; evidence for the earlier occurrence: the final investigation paragraphs in `docs/onenote-page-order.md` and `docs/onenote-section-order.md`. The failed app request bodies and responses do not survive in the supplied materials.

1. **Leading hypothesis: wrong resource identity/authorization.** Code 6 is `invalidFileID`. The browser's successful GetCells opens a notebook **folder** FileId, while the existing app path authorizes a section **file**. A folder flag, folder cell or edited WOPIsrc combined with section-scoped credentials could be rejected as invalid FileId. Malformed FileId encoding or unsupported preview/resource semantics are also possible; code 6 alone does not distinguish them.
2. **First resource to investigate: the notebook package drive item.** Verify the package and request preview authorization for that item, accepting it only if Microsoft actually issues authorization for the expected notebook folder source. This matches the resource shape in B30. Whether personal notebook-package `/preview` yields suitable renewable app-and-user folder credentials remains unproved.
3. **For a section group's own children:** the corresponding holder is its group folder. B30 actually issues a folder FileId for the group proxy, but does not demonstrate opening it with app authorization. Reordering the group's position among its siblings would target its **parent** folder, not necessarily the group's own folder.
4. **The `.onetoc2` item is not the observed browser resource.** None of the revision requests targets a TOC file; the opening resource is a folder. A preview minted for a `.onetoc2` file would still need independent proof of a service mapping. Do not assume a file token can authorize the folder merely because the TOC stores the eventual order.
5. **A section-file preview is the established path for pages, not for notebook opening.** It remains useful as a control in a later read-only session. Do not derive folder credentials by replacing `/files/` with `/folders/`, substituting an item ID, or recycling a child's token.
6. **Code 14 is nonspecific.** The enum calls it `unspecifiedFailure`; it is not evidence by itself of insufficient scope, a wrong key or a wrong version. The different GetCells operation, missing folder authorization, PageTarget/bootstrap differences, or a server-side limitation could all matter. The two numbers must not be assigned more precise causes from the surviving sentence alone.

There is evidence of a **different opening operation** (GetCells, kind 1) and **different resource class** (folder). There is no evidence of a distinct folder endpoint, version or request key. Whether `Files.ReadWrite` plus notebook-package preview is sufficient is the principal live authorization question.

## Proposed implementation, after the missing evidence is resolved

This is a staged design, not authorization to implement or a claim that the folder mutation is ready to ship. Resolve renewable folder authorization and the serialized folder-write contract first. Keep the current read-only TOC path until a replacement is independently established.

### Module boundaries and reuse

| Area | Reuse unchanged | Addition or deliberate change |
| --- | --- | --- |
| `web_session.py` transport | `Transport`, bounded reads/deadline, no redirects, credential-safe exceptions, independent web budget, explicit-rejection replay policy. | Folder-specific user-facing messages can be added where section wording would mislead. Preserve the transport's no-replay rule for uncertain mutations. |
| Operation envelope | `Session.operation()` already handles arbitrary kind numbers, single-operation response validation, key/version challenges and conflicts. `common_operation()` supplies the existing shared read/write fields. | Add an explicit GetCells method with that operation's own recorded fields. Do not assume a batched Cells response can be consumed as a normal top-level revision state. |
| Identity and consent | `writable_notebook()`, grant checks, personal-ID validation, owner-drive addressing and verified group-folder identity checks. | Add notebook-package verification for id, name, `package.type=oneNote`, personal owner drive and holder identity. `group_item()` already verifies a group's folder/name/parent; it does not establish ordering support. Do not reuse `section_item()` for a folder. |
| Preview boundary | Existing signed-preview GET, JSON parsing approach and in-memory credential lifetime; `preview_url()` if the actual folder preview uses its existing allowed shape. | Add `Session.for_notebook()` or `for_folder()` only once the package/group preview shape is observed. Adapt source validation explicitly for the expected `/folders/<item>` resource while keeping `.one` validation strict. `frame_info()` cannot accept folder sources unchanged. Reject an unfamiliar preview route rather than broadly relaxing host/path checks. |
| Revision primitives | `properties()`, `references()`, `latest_objects()` and their bounds/ancestry validation in `revision_objects.py`. The observed folder snapshot has an empty Ops list and base-NIL chain compatible with those primitives. | Add a small `Folder` parser for the observed root/proxy/metadata classes, both root sequences and safe resource identity joins. Keep credential-bearing properties transient and out of caches/logs. |
| Mutation construction | The existing conditional-revision pattern and success interpretation. `with_children()` preserves other root properties when changing `0x24001C20`. | `Session.read()` and `Session.write()` cannot be used unchanged for folders: they hard-code `IsFolderCell=false` and ContextId=NIL. Add explicit folder operations with validated context/head semantics. Do not introduce a generic abstraction merely to remove a few repeated fields. |
| Order policy | The exact-membership / expected-order / no-op checks in `page_order.py`, plus the command's budget and failure discipline. | Add `folder_order.py` for sibling section ordering. Keep `section_order.py` and `toc.py` as the existing read-only TOC path. The binary parser must never gain an upload/write path for this feature. |
| Provider command | `cmd_reorder_pages()` structure in `onenote.py` lines 2294 onward: fresh identities, budgets, access checks, conditional save and visible failure. | A later `reorder-sections` command should accept a holder, expected current sibling order and wanted permutation. Add group ordering only after separate evidence; no cross-holder moves. This investigation changes no command/UI code. |

Avoid copying credential-bearing response objects into test fixtures. Use independently invented synthetic IDs, tokens and properties in tests; retain only the documented structure.

### Read and preflight steps

1. Validate the command's holder and arrays before requesting anything. Require an editable personal notebook, write consent, at least two siblings, bounded lengths, strings only, no duplicates and an exact permutation. Keep all relevant Graph, OneDrive and web budgets available beyond the notes reserve, following the existing command.
2. Read fresh, completely paginated Graph sections/groups for the **specific holder** and verify notebook/parent membership. Verify live OneDrive package/folder children and each relevant `.one` file/folder identity. Do not treat a flattened notebook section list or a partially cached listing as complete siblings.
3. Obtain fresh app-generated authorization for the verified holder. Reject a WOPIsrc referring to another resource. Never use HAR credentials, browser cookies, hand-edited source URLs or guessed child tokens.
4. Use GetCells to discover the actual folder state. Select the cell by validated FileId/resource, folder revision flags and content-root descriptor, not solely by `Cells[0]`. The first-cell position is an observation of B30, not a universal contract.
5. Resolve only the latest revision's ancestry and live proxy references. Require the expected root class, supported properties and complete metadata. Validate that all root references resolve once, that the section-only sequence matches the section projection of the mixed sequence if that relationship is established, and that the Graph/OneDrive join is bijective. Use verified item identities from the FileId's source plus independent holder checks; names/GUID-shaped metadata alone are insufficient.
6. Preserve groups, hidden/special children and unknown properties. B30's one group is last, but that does not establish a general rule that groups are always last. If any live child cannot be classified or its preservation cannot be proved, fail before writing. A sections-only operation must preserve the full group subsequence and group positions according to the subsequently verified service contract.
7. Require the fresh service section order to equal the caller's expected order; compare membership and holder state too. A stale cached TOC order is not a write base. If expected equals wanted, return without a mutation.
8. Read a fresh folder state immediately before forming the write, using a verified full folder read or another GetCells if needed. Do not feed an incremental response with no LatestRevisionId to the writer. Recheck membership, order and joins after any refresh. Never reuse the selected section's or page's head/ClientKnowledge.

### Proposed write and success handling

Once a real folder-write trace establishes the changed objects/properties, build exactly that supported minimal change. Preserve existing object identities, all unrelated properties, section contents, child FileIds and hierarchy. Do not normalize every ordering number, rebuild the notebook, or overwrite unknown metadata to make the desired sequence appear plausible.

The conditional envelope should follow the existing writer **if live evidence confirms folder support**:

```text
L = fresh folder state's LatestRevisionId
Revision.CellId = fresh folder state's actual root cell
Revision.FileId = verified holder folder FileId
Revision.IsFolderCell = true
Revision.ContextId = folder context encoding verified separately
Revision.BaseId = L
Revision.ExpectedLatestId = L
outer ExpectedLatestId = L
outer ClientKnowledge = fresh folder state's ClientKnowledge
new revision/object-group IDs = newly allocated local IDs
ObjectGroups = only the proven order-related object changes
```

The rest of the envelope should follow the known PutChanges contract where validated. RootObjectDescriptors, BaseRevision and the folder context must not be guessed merely because the page writer uses null/NIL. The candidates for the actual change include the mixed root list, the section-only root list and ordering metadata; the present HARs do not select among them.

Require an explicit matching operation response with status 0 and no conflict. Initially, independently read the folder back for verification and observe eventual TOC/UI convergence. The shipped page-order path's immediate cache publication without read-back is based on its established write contract; do not transfer that confidence to an unverified folder path. Later cache publication and suppression of stale TOC refreshes need their own measured convergence behavior; the page writer's 30-second Graph delay is not evidence of a correct TOC delay.

### Failure handling

- Rejected membership, hierarchy, order, resource identity, unsupported properties or missing revision ancestry: stop before mutation and request a holder refresh. Never choose an alphabetical guess and submit it as the intended current order.
- Explicit base/head conflicts: show a concurrent-change failure, invalidate the affected holder's canonical order and refresh. Do not silently rebase the user's reorder onto a changed sibling set.
- Operation 6 or 14: report the actual numeric code without secret payloads; disable this attempted write. Do not probe alternative resources or switch to a TOC upload automatically. Code 7 follows existing denied-access/sign-in guidance.
- Key challenges explicitly rejecting the request may retry under the existing Session policy; explicit 429 rejections retain the existing limited transport retry. A timeout, 5xx, malformed response or lost connection may follow a commit: never replay the write or mark the provider job retryable.
- Once a mutation might have been submitted, clear/invalidate affected order knowledge on failure and show that the outcome needs checking. Do not let an exception containing a FileId, signed URL or credential-bearing object reach output/logs.
- Queue eventual UI writes per holder, as page writes are queued per section, and revalidate the expected order for each one. Coordinate with section/group creation, deletion and renaming. A pending local display order is not authoritative server state.

## Live verification plan for a later session with the user present

This plan authorizes no action during this offline investigation. All future checks and any service change are confined to the user's test notebook **“Blocnotesul lui Andrei”**. Do not infer its identity from a capture, and do not inspect other notebooks as experimental targets.

### Phase 1: read-only, with fresh authorization

1. With the user present, obtain the app's own fresh consent/sign-in through the normal supported flow. Do not import browser/HAR tokens or search existing app sign-in stores. Record only redacted request shapes, codes and locally computed equality results; keep credentials and complete revision snapshots in memory.
2. Identify the test notebook by its exact name and independently verify its personal drive package identity, editable role, current sections/groups and the direct holder of the two candidate sections. If the name is ambiguous or identity/permissions cannot be verified, stop.
3. List the package's children and the maintained `.onetoc2` metadata read-only using the existing reader. Establish current sibling order and content identities, with no credential-bearing downloads or revision dumps saved. If multiple TOCs exist, apply the reader's existing unique-newest validation rather than choosing by filename alone.
4. Request preview for the verified notebook package item. Check whether its fresh file information actually supplies a usable `/folders/<expected-item>` source and app-and-user credential. If preview fails, yields only file-scoped authorization or uses an unfamiliar boundary, stop the write track. Do not rewrite the source or substitute a `.onetoc2` item automatically.
5. Attempt only the minimal GetCells read supported by observed/newly inspected client code. `PageTarget=null` or omitted browser telemetry may be useful read-only experiments, but their success is not established by B30. Record the differing field shapes and safe status codes. Negotiate version/key dynamically; never copy the captured ones.
6. Validate the returned folder classes, actual root, full section/group membership, both sequences and credential-resource joins. Read it again without changes to establish whether the reported folder head is stable and usable for concurrency. Establish a full folder refresh path; verify context serialization and whether cookies/bootstrap side effects are needed. A successful section-file read is only a control, not proof of folder access.
7. Read-only gate: obtain trustworthy serialized folder-write evidence before attempting a service mutation. Prefer a focused capture of an already occurring browser reorder, if the user supplies one. The current files are insufficient. Static code inspection must establish the actual serializer/object changes if no such capture exists. **If this gate cannot be met without an extra experiment, end the session with read-only findings; do not spend a separate browser reorder and then another service experiment.**

### Phase 2: at most one reversible service round trip

Proceed only if Phase 1 establishes renewable folder authorization, exact mutation properties and a genuine conditional head, and the user confirms the two existing sections in the test notebook. This is one test: **swap those two sections, then restore their original order**, with no other mutations. Choose direct sibling sections, preferably adjacent, in one holder; do not move them across groups or change a group's position.

1. Capture the original order and all necessary comparison state in memory. Read current membership and a fresh folder revision immediately before the swap. Verify that the expected order still equals the original. Prepare a minimal delta using the proven folder contract and set BaseId plus both expected-head fields to that exact head.
2. Submit the swap once through the revision service. Require explicit success and no conflict. Do not upload a hand-built `.onetoc2`, create/delete/rename anything, or use a browser reorder as a second independent test.
3. Read the folder again and verify that only the intended order-related properties changed. Check both root sequences/metadata as appropriate, unchanged sibling membership/identities and unchanged hierarchy. Check service/UI/TOC convergence read-only, with bounded polling. Where feasible, compare content through in-memory hashes without saving note bodies; a hash match only covers the content actually fetched.
4. Restore using **another freshly read folder head**, after proving that current membership and order still equal the swap's result. Never restore against the pre-swap base. Submit the inverse delta once, require explicit success, and verify the original order and unchanged identities/content again.
5. If the swap's outcome is uncertain, read before deciding whether restoration is needed. If a conflict, unrelated edit, identity mismatch or changed membership appears, stop automatic writes and reconcile with the user. Do not force the old order over another person's change. If safe restoration cannot be confirmed, state the remaining order plainly and arrange recovery with the user rather than claiming a successful round trip.

Do not add a stale-base test, group swap or second pair of sections to this session: each would be another mutation experiment. Concurrency rejection can be covered with synthetic tests initially and verified separately only if later authorized.

## Open questions and risks

1. **Missing primary write evidence:** no supplied request changes notebook section/group order. The exact root arrays, metadata objects, ordering property IDs and descriptor/context fields to write remain unresolved. The surviving repository phrase “HAR ... contained notebook-level section order” is supported as a read, not as a captured folder mutation.
2. **Renewable folder authorization:** notebook-package preview may not issue the required app-and-user folder credential. Group-folder preview and parent-to-child authorization are also unverified. A preview for `.onetoc2` is not the browser path demonstrated here.
3. **Folder revision semantics:** the GetCells folder state is one full base-NIL revision with a string-encoded null context. It could be synthesized. Is its LatestRevisionId a stable conditional base? What read returns the true current head, and what happens when that head is stale? These are prerequisites, not implementation details to guess.
4. **Dual sequences and groups:** the snapshot has two related root lists and one group at the end. The static code changes graph links and a rank property. Which representations must be changed atomically, and are sections and groups independently ordered or interleaved? No group move is demonstrated.
5. **Identity joins:** proxy FileIds provide strong resource identities, but exact Graph-to-folder/section joins must be verified for each holder. Current code supports both observed personal-ID formats; the captures do not establish all newer IDs, shares or nested groups. Existing group rename/delete identity validation does not prove a group-order revision contract.
6. **Hidden/deleted/system entries:** the binary reader already handles historical entries and special folders. Runtime folder views may omit or transform them. Missing children or unsupported structure must disable writing, not be normalized away.
7. **Credentials embedded in revision objects:** proxy `0x1C00200F` properties contain tokens. A generic dump, persisted raw snapshot, exception string or naive test fixture could leak them. Keep raw states in memory and select only nonsecret structural facts for diagnostics.
8. **Browser/app differences:** browser headers use folder authorization while child FileIds have separate credentials, and the October 6 requests carry cookies. App section authorization has worked independently, but that does not establish the notebook authorization chain or absence of cookie/bootstrap requirements.
9. **Consistency and uncertain commits:** successful service state, web UI order, TOC download and the app's cached read order may converge at different times. Lost responses require reconciliation without replay, including during restoration. No safe convergence delay for folder writes is established here.
10. **Compatibility boundary:** this remains an undocumented web service and personal-OneDrive mapping, with server/build changes possible. No supported Graph order write, safe binary TOC upload or universal account support has been established by this investigation.

## Repository sources inspected

All paths below are under `/home/andrei/Projects/note-note`; they were read only.

- `docs/onenote-page-order.md`: established page-order authorization, conditional save, queue/failure behavior and earlier codes 14/6.
- `docs/onenote-section-order.md`: binary TOC order, live-child joining, repeated/skipped ranks, several-TOC policy and read-only limits.
- `docs/engine-notes.md`, OneNote portions: Graph's missing section-order property, sync/budget constraints and native revision editing boundaries.
- `plugins/org.note-note.onenote/web_session.py`: identity/preview validation, credentials, transport, operation challenges, section reads/writes and group-folder verification.
- `plugins/org.note-note.onenote/revision_objects.py`: property/reference parsing, latest-branch materialization and section/page-series classes.
- `plugins/org.note-note.onenote/page_order.py`: complete membership/hierarchy checks, expected order, minimal root change and conditional write orchestration.
- `plugins/org.note-note.onenote/toc.py`: binary TOC properties (`0x24001CF6`, `0x1C001D6B`, `0x14001CB9`, `0x1C001D94`), active ancestry and historical-entry treatment.
- `plugins/org.note-note.onenote/section_order.py`: package/children validation, TOC selection/cache and live Graph section joining; currently orders sections within holders while groups remain alphabetic in the UI.
- `plugins/org.note-note.onenote/onenote.py`, `cmd_reorder_pages`: budgets/access, fresh Graph membership, uncertain-write invalidation and publication of an explicitly accepted page order.
