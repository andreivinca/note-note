# Merged review issues for PLAN.md

76 canonical issues merged from 122 inputs. Order: high, then medium, then low (there are no critical issues).

## High

### I1. P0 takes over the outside CODE-REVIEW-2026-10-11 fixes, and the plan cites the working tree
- Sources: facts-1, steps-1, safety-3, ux-10, contract-1, critic-1, facts-16
- Category: scope
- Section: Header (lines 5-8); §1; §4.3 F15 bullet; §4.8; §6 Phase 0 C0.1–C0.18, the F11/F13 bullet, Exit P0, C0.23; D16; U16; R25; Glossary "WT"; Appendix A last row and Appendix B; §5.12 step 6; every "WT :n" citation
- Plan text: "**C0.1–C0.18: commit the review fixes already in the working tree.** One commit per finding, named by its F-number, each with the tests the working tree already holds" / "Phase 0 commits those fixes first, so after Phase 0 every later step is applied to the post-fix tree." / "Line numbers are HEAD's unless marked **WT**"
- Problem: The user said another agent owns the in-flight review fixes and this plan must not take them over. P0 still commits them as its first 18 commits, reviews them and releases them. It writes the 1.0.41 notes for F1 and F2 ("renaming a section back…", "row actions wait for saves") and gates P0's exit on "every finding done and committed". U16's rationale ("F1 is high severity") rests on that work too. The state P0 reports is already false: F8 and F10 have been reverted and are open again, yet §4.8 calls F3–F10 "code done". The plan's safety arguments lean on that work as well. F10 is supposed to let a rename survive the row rebuild after each save, and F2 is supposed to make row actions wait for saves. Without F2, a sidebar row action runs before the open timeline's save is sent. WT citations point at a tree that keeps moving. Two of them (the §4.3 F15 bullet and §5.12 step 6) have no HEAD counterpart and describe code that does not exist at e2cdc4e.
- Evidence: The user's instruction in the task. CODE-REVIEW-2026-10-11.md:11 "18 findings are fixed; F8 and F10 are reverted and stay open", :24 "F10 | **Reverted, still open.**". §4.8 "The tree kept moving while this plan was written (F20 was reverted, F10 redone …)". e2cdc4e has neither CODE-REVIEW-2026-10-11.md nor ui/SlotLoader.qml, and the snapshot head-e2cdc4e matches `git show e2cdc4e`. Workspace.qml:2115-2117 calls flushSave and then rowAction, but the save starts only after the async conversion (NoteSession.qml:493). The verified HEAD citations are correct. At e2cdc4e, "the note could not be read for saving" is NoteSession.qml:499-501 (:509-521 keeps the draft), and readOnly is pushed by updateReadOnly() at :119-121. The skill row shape has no `count` at e2cdc4e (skills/.../providers.md:267).
- Correction: Replace §4.8 with: "Outside prerequisite, not this plan's work: the fixes for CODE-REVIEW-2026-10-11.md land on master through their own work, which this plan neither performs nor reviews. This plan is written against e2cdc4e and cites its lines. A phase that needs a review fix names it as an entry condition (F14 before P2, F2/F21 before P3's codec carries saves, F17 before P5, F10 before P6 ships). Where one has not landed, use the e2cdc4e forms, and once it lands, rebase and re-derive the cited lines." State the effect of each fix that has not landed. Without F2, a folder rename or delete may run before the open timeline's save; that save fails with an error, keeps its draft, and is retried at the note's new path. Without F10, every timeline save rebuilds the rows and ends an in-place rename. Delete C0.1–C0.18, the F11/F13 bullet, the "Do not re-implement" paragraph, Exit P0's first checkbox, C0.23's review-fix user notes, R25 (or reword it to "Cited lines are e2cdc4e's; steps name functions") and Appendix A's last row. The header becomes "Line numbers are e2cdc4e's", and the WT definitions in Appendix B and the Glossary go. Replace every WT citation with the e2cdc4e line plus the function name. §4.3's F15 bullet becomes "`updateReadOnly()` pushes `editor.readOnly = !session.writable` (NoteSession.qml:119-121)", §5.12 step 6 cites NoteSession.qml:499-501, and P2 step 7 drops "the working tree moves them". §1: "1.0.41 holds C0.19–C0.22". D16 drops "commit the WT review fixes". U16's Why becomes "the lone-`+` save failure and the link-definition deletion lose text today and should not wait". List the skill row's `count` in P1's own drift work.

### I2. Undo steps hold the pending event, so undo with the add form open duplicates it
- Sources: safety-1, ux-1, critic-4
- Category: data-safety
- Section: §5.7 Check semantics (Undo); §5.8.4 Semantics; §5.8.9 Body behaviour; §5.6.6
- Plan text: "The body keeps its own stack of `{ form, cursor }` (`form` = the snapshot string), at most 200 steps." / "`undo()` / `redo()` | Pop the stack. `fromForm`, then patch the rows, then `host.edited()`." / "`snapshot()` is `TimelineModel.form(TimelineModel.withPending(events, form))`" / "Focus leaving. Adding: nothing happens. The form stays open with its text."
- Problem: Each undo step is a snapshot string, and the snapshot includes the open add form's pending event. Restoring a step turns that pending event into a committed one while the form still holds it. withPending then appends it again, so the next save writes it twice into the user's file, and Enter in the form would append a third copy. For the same reason, Ctrl+Z after an Enter-commit does nothing: the saved state from before the commit already held the pending event.
- Evidence: A trace using only specified behaviour. Start with [A, B]. Press Ctrl+Enter and type "C"; the snapshot [A,B,C] is saved. Click B's circle: this is allowed while composing (EditorKeys 21), and the circle does not take focus, so commit pushes [A,B,C]. Click B's text: the list takes focus and the form stays open. Press Ctrl+Z (reserved, stroke.js:19-20, so it reaches the list). The snapshot becomes withPending([A,B,C], {title:"C"}) = [A,B,C,C], and it is saved. docs/README.md:40: "Never lose, duplicate or corrupt them." No planned test (EditorKeys 5, 6, 9, 21) runs an undo while the form is open.
- Correction: §5.7 Undo: "The body keeps its own stack of { form, cursor }, where form is TimelineModel.form(events): the committed events before the action, never snapshot(). Enter-commit pushes the events from before the append, so Ctrl+Z removes the added event. Esc-discard pushes TimelineModel.form(withPending(events, form)) as its own step and then closes the form, so Ctrl+Z brings the event back once as an event. undo() and redo() leave an open add form and its text as they are, and withPending appends the pending event once." Add EditorKeys cases. (a) Compose "Buy milk", click event 1's circle, click event 1's text, press Ctrl+Z: the snapshot and the saved Markdown hold "Buy milk" exactly once. (b) Enter-commit, focus the list, press Ctrl+Z: the added event is gone.

### I3. parse.py deletes CR, so lone-CR line ends join lines instead of reading as LF
- Sources: facts-3, safety-2
- Category: false-claim
- Section: §5.6.4 Reading, step 1; §6 Phase 0 C0.20 step 1
- Plan text: "`parse.py` already drops `\r`, so CRLF and lone CR read as LF. … It calls `_md.parse(markdown.replace("\r", ""))`, which returns `(tokens, state)`"
- Problem: Deleting every CR does not turn a lone CR into a line end; it joins the lines. In a lone-CR timeline, separate events merge into one. The merged title swallows the next item's marker and check state, and the first user action writes the merged event back. Today's Markdown editor already merges such a body on its first save while unkept is [] (in 1.0.40, and in the plan's Markdown fallback), although docs/providers.md:713-716 promises that a lone CR reads like LF. C0.20's parse_with_definitions copies the corrupting call.
- Evidence: parse.py:102 is `tokens = _md(markdown.replace("\r", ""))`. mistune maps \r\n and \r to \n itself (mistune/markdown.py:83-84) but never sees a CR. notefile.split returns the body exactly as written (:52-53), though its docstring (:17-18) promises otherwise. Probes: parse("- [x] A\r- [ ] B\r") gives one item, 'A- [ ] B'. The body "- [x] Book flights\r- [ ] Pack the bags\r" reads as one event and is written as "- [x] Book flights- [ ] Pack the bags\n". A lone-CR local note saves as '- [x] Book flights  Return on the 14th- [ ] Pack the bags\n' with unkept []. "Shopping\r\rMilk\rEggs\r" round-trips to "ShoppingMilkEggs\n" with unkept [].
- Correction: Add a P0 commit, "Read a lone CR as a line end". parse.py's parse() and C0.20's parse_with_definitions pass the text to mistune with its line ends normalised: either `_md.parse(markdown)`, letting mistune normalise, or `re.sub(r"\r\n?", "\n", markdown)`. Neither uses `markdown.replace("\r", "")`. Add a regression test that parse("- [x] A\r- [ ] B\r") has two items, a qthtml CASES entry and a tests/test_regressions.py case "lone-CR paragraphs stay apart". Add "lone CR | LF" to the §5.6.4 tolerated table, to §7.1, and to timeline_selftest's tolerated variants. Step 1 becomes "parse.py reads CRLF and a lone CR as LF (P0)."

### I4. notefile.py appends services/markdown to sys.path, so a site-packages `parse` breaks the local listing
- Sources: facts-4, safety-4
- Category: false-claim
- Section: §5.11.1 plugins/org.note-note.local/notefile.py; §6 P3 C3.1 step 1 (imports)
- Plan text: "# Appended, not inserted first: a module of the same name in the provider's own folder or in lib/ wins.\nsys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "services", "markdown"))" … "except timeline.NotTimeline: return None"
- Problem: Every directory ahead of an appended entry wins, the standard library and site-packages included. P3's note "run as a script, `services/markdown` is `sys.path[0]`" is also false when timeline.py is imported from notefile. If the PyPI `parse` package is installed, timeline.py's `from parse import parse_with_definitions` raises ImportError inside list.py, and `notefile.progress` catches only NotTimeline. The listing then dies without its E line, and Provider.loadList answers "the listing ended before it was complete". Local notebooks show no notes for as long as any timeline of 64 KiB or less exists. Tests pass on machines without that package.
- Evidence: A probe reproducing list.py's path setup (list.py:58 inserts only lib/), a site-packages parse.py and the plan's append fails with "ImportError: cannot import name 'parse_with_definitions' from 'parse'". Arch extra/python-parse 1.22.1 installs a top-level parse.py; hid-tools, python-parse-type, python-pytest-bdd and python-srcinfo require it. Provider.qml:448-452 is `if (!end) { …; return }`. Every existing script inserts services/markdown first: operations.py:10, parse.py:16, qthtml/siblings.py:12, onenote_md.py:19, notion_md.py:15. No module name is shared between services/markdown, lib and the local folder.
- Correction: notefile.py does not touch sys.path; delete the line, its comment and P3's "run as a script" note. Beside the lib/ insert at list.py:58, add `sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "services", "markdown"))`, as operations.py:10 has. timeline.py inserts its own folder first, as parse.py:16 does, so it works however it is imported. Add a tests/test_regressions.py check that the module names in services/markdown, lib and plugins/org.note-note.local do not overlap.

### I5. C0.20 misses the other silent losses: link titles and repeated definitions, and it is not a new finding
- Sources: facts-2, safety-9, critic-9, tests-11
- Category: false-claim
- Section: §4.6 item 2; §6 C0.20 heading and steps 1-4; §3 U7 Why; §1 "What keeps notes safe" and "three pre-existing ways"; C0.23 user notes
- Plan text: "A definition that a link uses is folded inline instead (`[t][g]` → `[t](url)`), and no information is lost." / "A used definition is folded inline by the editor and loses nothing, so it is not named." / "**C0.20 "Name a link definition the editor would drop"** (a new finding, §4.6)" / "`definitions` is `dict(state.env.get("ref_links") or {})`" / "The Markdown path is already lossless-or-read-only"
- Problem: At e2cdc4e the Markdown editor also drops all of the following silently, with unkept [] for each: a used definition's title; every inline or reference link or image title; and a second definition of the same label, including one that differs only in case. mistune consumes every definition but records only the first per key in ref_links. So the note opens editable and the first save deletes the text. That is the silent deletion C0.20 claims to end and the 1.0.41 note says is fixed. A timeline holding such a link falls back to editable Markdown under U7 (a), so the fallback is not lossless-or-read-only. The loss is also not a new finding: docs/decisions.md:716-720 already records reference-definition lines and link titles as knowingly lost. C0.20 reverses that decision without saying so, and its docs step adds a sentence while leaving the contradicting paragraph in place. The planned "used definition → []" test pins only the title-less case.
- Evidence: Probes on e2cdc4e. 'See [t][g].\n\n[g]: https://example.com "Title"\n' gives unkept [] and saves 'See [t](https://example.com).\n'. 'See [t](https://example.com "Title").\n' gives the same text. '![logo](https://example.com/a.png "T")\n' becomes '![logo](https://example.com/a.png)\n'. 'See [t][a].\n\n[a]: https://one.example\n[a]: https://two.example\n' gives ref_links {A: one}, unkept [] and the save 'See [t](https://one.example).\n'; [a] with [A] behaves the same. mistune/block_parser.py:287-293 stores a definition only `if key not in state.env["ref_links"]`. docs/decisions.md:716-720: "…a link or image title, and a reference-style link's definition line (the link itself is written inline). Each is lost on the first save."
- Correction: Make the scope a §3 question first. "docs/decisions.md:716-720 accepts that reference definition lines, link titles, code-block languages and column alignment are lost on the first save. Change that for unused definitions only, for all of them, or not now?" If C0.20 is widened: (1) parse.py wraps mistune's `ref_link` rule so that each consumed definition appends its key to state.env["definitions"], duplicates included, and parse_with_definitions returns that list. (2) unkept names "a link definition no link uses" for an unused key and for every definition after the first of a key ("a link definition given twice"), and "a link title" for any link or image token, inline or by reference, whose attrs.title is non-empty. (3) Add UNKEPT cases for a referenced title, an inline title, an image title, a duplicate and a case variant. (4) Step 4 rewrites decisions.md:716-720 itself instead of adding a sentence elsewhere. If keeping titles in the writer is preferred, ask the user. In every case, §4.6 and C0.20 drop "no information is lost" and "a new finding", the used-definition test names its input as title-less, and U7's Why says "lossless-or-read-only once C0.20 lands". Otherwise U7 names link titles and repeated definitions as known losses on the fallback path. Update §1 and C0.23's notes to match. timeline.read still refuses any definition.

### I6. Reader and model text rules disagree (control characters, empty stripped lines, whitespace set, NBSP)
- Sources: critic-3, safety-8, facts-12
- Category: contradiction
- Section: §5.6.1 Model; §5.6.4 Reading steps 9-10; §5.8.9 show(); §9 R15
- Plan text: "| `description` | `""`, or 1–40 lines joined by `"\n"`, at most 4096 code units in all. Each line follows the title's rules. There are no empty lines. |" … "10. The description is paragraphs 2…, each stripped, joined by "\n", over 4096 units refusing with …" … "no leading or trailing whitespace (Python `str.strip`)" / R15: "JS cleaning is a superset of Python's whitespace rules."
- Problem: Several of read()'s rules differ from those of write(), fromForm and validEvents. (1) Step 10 applies no control-character check, so a hand-written description holding a tab is read as a timeline and then fails validEvents. (2) Step 10 does not refuse a paragraph that strips to nothing, so a paragraph holding only NBSP, U+2003 or U+3000 yields an empty description line, which the model forbids, or is silently dropped on the next write. (3) Python's str.strip keeps U+FEFF, while JS trim() removes it, so the sets are not in a superset relation. A title with a leading U+FEFF is accepted by read but rejected by a trim()-based validEvents. (4) Stripping NBSP or EM SPACE at the edges of a line rewrites rendered text on the next check, against U8's "only whitespace and markers that render identically". Whenever validEvents fails, show() answers ok:false and the note opens as "This note could not be displayed" instead of as Markdown (U7). If JS accepted such events instead, write() would refuse every save.
- Evidence: Probes on e2cdc4e. '- [ ] Pack\n\n  a\tb\n' gives a paragraph with 'a\tb'. "- [ ] Pack\n\n   \n\n  Passport\n" gives the description "\nPassport". "- [ ] Pack\n\n  　\n" gives "" and the write "- [ ] Pack\n". "- [ ] ﻿Pack\n" gives the title "﻿Pack". In python3, '﻿x'.strip() is '﻿x' and '﻿'.isspace() is False, while in qml6 "﻿x".trim() !== "﻿x". The planner's prototype rewrites an NBSP-led description line and a title with a trailing NBSP. plan/exp/codec_check.py checks control characters per line, but the plan text omits that check. §5.8.9: "`events` failing `TimelineModel.validEvents` answers ok false". judges.md:312 rejects NBSP stripping.
- Correction: Define one edge-whitespace set explicitly in both codecs (timeline.WHITESPACE and the same class in TimelineModel.js): Python's str.isspace characters plus U+FEFF, or U+FEFF refused as a control character in both. read, write, cleanTitle, cleanDescription and validEvents all use it. Step 9: text that the strip would change refuses with "a space at the edge of a line (event N)", or, if stripping is kept, it strips with the shared set. Step 10: each further paragraph is a description line under the same edge, empty ("an empty description line (event N)") and control-character ("a control character (event N)") rules; join with "\n"; over 4096 refuses. R15's superset sentence becomes "One edge-whitespace set, defined explicitly in both codecs". Add to §7.1 item 5 and to §7.2's validEvents cases: a tab in a description, an NBSP-only and a U+3000-only paragraph, an NBSP-led line, and U+FEFF at a title's edge. Add a §7.6 pin: for each of the 55 edge strings, plus U+FEFF and U+0085 at a title's edges, `TimelineModel.validEvents(read(...))` agrees with `timeline.read`.

### I7. ChromeTextArea enforces its limit by reverting text in onTextChanged, which wipes the field's undo
- Sources: tests-1, facts-13, ux-6, critic-6
- Category: workaround
- Section: §6 P5 C5.2; §5.8.4 Description row and title `maximumLength: 256`; §5.8.5 Form fields step 6; §7.5 keys suite additions (P2); U9
- Plan text: "`property int maximumLength: 0` and `property int maximumLines: 0` (0 = none), enforced in `onTextChanged` by reverting to the last accepted text and cursor, then emitting `limitReached()` … 3. Test: a keys-suite case that types past the limit and sees the text unchanged and `limitReached` emitted." / "Input past 4096 units or 40 lines is refused: the field reverts to its last accepted text"
- Problem: Assigning `text` resets a TextArea's undo stack. After one over-limit keystroke or paste, Ctrl+Z no longer undoes earlier typing, which breaks §5.8.5's "`Ctrl+Z` is the field's text undo". Reverting with undo() instead erases the whole typed run, because Qt merges consecutive typing. Reverting inside onTextChanged also re-enters the handler. It emulates a missing maximumLength after the fact, which is the kind of workaround CLAUDE.md forbids, and the plan does not raise it as a question. The planned test cannot see the defect, because the text is unchanged. The title's maximumLength cuts a pasted long title without a word, against goal 7, "Honest about limits". §7.5 lists the case under P2, but ChromeTextArea exists only from P5. IME pre-edit is untested.
- Evidence: Qt 6.11.2 qmltestrunner probes (tst_revert.qml, tst_textarea_limit.qml, tst_textarea_undo.qml, critic tst_probe.qml). After typing "abcde", canUndo is true. After an over-limit insert that the handler reverts, the text is "abcde", reverts=1 and canUndo is false, and undo() changes nothing. With Qt.callLater(area.undo) the text becomes "" and canRedo is true. Any assignment of a different `text` sets canUndo false, while `remove()` keeps the history. docs/business-requirements.md:42-44. CLAUDE.md:10-11.
- Correction: Neither field truncates or reverts. Drop `maximumLength: 256` from the title field and `maximumLength`, `maximumLines` and `limitReached` from ChromeTextArea. While the cleaned title is over 256 units, or the description over 4096 units or 40 lines, the form message (TimelineModel.problem() in timelineFormMessage) says "A title holds up to 256 characters" or "A description holds up to 4096 characters and 40 lines". Enter and the button do not commit (the ToolForm `message` rule, docs/editing-tools.md:352-354), and `withPending` leaves the invalid pending event out of the snapshot. If a hard input cap is wanted, add it to §3 as a question for the user. The alternatives are refusing before the edit in Keys.onPressed, plus refusing an over-limit paste whole (IME commits stay unchecked), or a C++ length guard. C5.2's test becomes: type past the limit, the message shows, Enter does not commit, canUndo stays true and Ctrl+Z still undoes the typing. Move the case from §7.5's P2 list to P5.

### I8. Host confirmations do not get Escape and Enter while a timeline form has the keyboard
- Sources: ux-2
- Category: ux
- Section: §5.8.5 Keyboard map (Form fields focused); §5.9 Creation UX and commands; U7
- Plan text: "1. `Escape` → discard or cancel (accepted, so `back` never sees it). 2. `Return`/`Enter`: … 3. `Tab` / `Backtab` → switch field. … 5. `host.shortcut(event)`." and "`blocked` is **not** gated on `formOpen`. The form is part of the note, every app shortcut is safe under it, and the form claims `Escape` itself."
- Problem: The host's confirmations receive keys only through handleShortcut, which the form calls only after it has claimed Escape, Enter and Tab. With the form focused, Ctrl+D opens "Delete this note?". Escape then discards the pending event and leaves the dialog up, Enter commits the event instead of answering, and Tab switches fields. U7's "every app shortcut is safe" is false.
- Evidence: Workspace.qml:2136-2141: handleShortcut routes to deleteConfirm and rowActionConfirm first. Workspace.qml:1996-2009: requestDelete opens the dialog without moving focus. ConfirmDialog.qml:20-41: handleKey answers Escape, Left/Right/Tab/Backtab and Return/Enter. ConfirmDialog.qml:42-46: the dialog takes no focus when opened.
- Correction: Before P5, make both confirmations own the keyboard while open. ConfirmDialog.qml, already a FocusScope, gains `Keys.onPressed: function(event) { event.accepted = dialog.handleKey(event) }` and focuses itself when `opened` turns true. cancelDelete, confirmDelete, cancelRowAction and confirmRowAction hand the keyboard back with `editor.focusEditor()` on every path. Today confirmDelete does this only after deleting the open note (Workspace.qml:2043-2051), and confirmRowAction never does (:2099-2103). Replace §5.9's sentence with: "`blocked` is not gated on `formOpen`: the form is part of the note. A confirmation the host opens over it owns the keyboard until answered, so Escape and Enter reach the confirmation, not the form." Add an EditorKeys case: with text in the add form, Ctrl+D then Escape cancels the deletion, and the form keeps its text and focus.

### I9. Array.isArray is false for QML list<string>, so C0.21 drops the toolbars of existing providers
- Sources: contract-2
- Category: contract
- Section: §6 Phase 0 C0.21 "Read every provider capability one way"; §5.2.1 (`noteTypes` row)
- Plan text: "if (!Array.isArray(provider.tools)) {\n       return []\n     }" … "Valid when it is an array of 1–16 distinct ids that match the grammar"
- Problem: On Qt 6.11.2, Array.isArray is false for a QML `list<string>` property. A provider that declares `readonly property list<string> tools: [...]` works at e2cdc4e, and docs/providers.md gives `tools` the type `list`. After C0.21, toolsOf returns [] and that provider silently loses its whole toolbar, which is a non-additive break. A `list<string> noteTypes` is likewise "not a list": the declaration is ignored, the provider's timelines open as Markdown, and New Timeline is refused. C0.21 step 6's docs ("tools must be a list") contradict the code.
- Evidence: Probe listprobe.out: "list<string> isArray=false indexOf=true length=2"; "var isArray=true". toolsprobe.out: "today: bold enabled = true underline enabled = false"; "plan C0.21 toolsOf = []". Workspace.qml:2845-2848 passes `p.tools` through, and EditorApi.qml:64 calls `enabledTools.indexOf(capability)`. docs/providers.md:54: "`tools` | list".
- Correction: Add one reader to capabilities.js: `function listOf(value) { if (value === undefined || value === null || typeof value === "string" || typeof value.length !== "number") { return null } return Array.prototype.slice.call(value) }`. Use it in toolsOf, declarationProblem and of(). toolsOf: absent → null; present but listOf null → [] and one console.warn at load; otherwise the string entries. Add transitions host cases: a QML provider with `list<string> tools` keeps exactly those tools, and one with `list<string> noteTypes` counts as declaring. Docs: "`noteTypes` | list | a JS array in a `var` property, or a `list<string>`".

### I10. hello's create (and the documented create contract) fail when an older host passes no options
- Sources: contract-3
- Category: contract
- Section: §5.11.2 examples/hello; §5.2.2 (`create`)
- Plan text: "`create(target, cb, options)` honours `options.noteType` when it is one of `root.noteTypes`, else `cb({ error: "this notebook cannot hold that kind of note" })`." / "`options` is `{ noteType }`: one of the types you declare, given by every host from 1.1.0. Create exactly that type or answer `{ error }`; never another."
- Problem: The plan keeps hello's `markdown: true` "as the documented example of a provider that also runs on 1.0.40". But 1.0.40 calls create(target, cb) with no options, so hello answers an error for every New Note, or throws on `options.noteType` and never answers. The proposed docs never say what to do with an older host, so every author who copies them gets the same failure.
- Evidence: Workspace.qml:1887 `function newNote(providerId, target)` and :1912 `p.create(target, function(r) {…})` pass no options at e2cdc4e. §5.11.1's local create already defaults: `options && options.noteType ? options.noteType : root.noteTypes[0]`.
- Correction: §5.11.2: "`create(target, cb, options)`: `var noteType = options && options.noteType ? options.noteType : root.noteTypes[0]`; if `root.noteTypes.indexOf(noteType) < 0`, `cb({ error: "this notebook cannot hold that kind of note" })`." Add to the create docs: "An older host calls `create(target, cb)` with no options: make your default type then." Add a transitions host case: hello's create called with two arguments makes a Markdown note.

### I11. A size bound is not a time bound: listing progress runs quadratic mistune parsing on 64 KiB notes
- Sources: critic-2
- Category: false-claim
- Section: §9 R14; §5.11.1 list.py head_of and notefile.progress; §5.6.7 "list progress read 64 KiB"
- Plan text: "R14 | Listing cost. | Whole reads only for timeline-marked notes of 64 KiB or less, the codec imported lazily, under the existing 10 s deadline and output budget."
- Problem: timeline.read runs mistune over the whole note, and its link parsing is quadratic. list.py checks its 10 s deadline only between notes, and ProcessTask kills the listing after its default 30 s. One timeline-marked file of repeated '[a](' therefore makes every relist time out, and local notebooks stop refreshing. At e2cdc4e the listing parses no Markdown, so this is new. It breaks docs/security.md rule 7 ("Anything that decodes untrusted data gets limits and a timeout"). The save answer's progress runs the same unbounded parse.
- Evidence: Probes on e2cdc4e parse() of '- [ ] ' + '[a](' * n: 4 KiB 0.43 s, 8 KiB 1.5 s, 16 KiB 6.1 s, 32 KiB 25.3 s, 64 KiB 98.5 s. list.py:250 checks the deadline only per note. ProcessTask.qml:18 `timeoutMs: 30000`; local Provider.qml:342 sets no other timeout.
- Correction: Give R14 the measured cost instead of the deadline claim, and add a user decision U17 (it changes U12). (a) List progress only for timeline files of at most HEAD_BYTES (4 KiB): the worst case is about 0.4 s per note, and the per-note deadline check bounds the listing. (b) Compute progress in a child process with a hard time budget, dropping progress for notes it does not reach. (c) No progress in the listing. Until the user decides, set notefile.TIMELINE_PREVIEW_BYTES = HEAD_BYTES, and apply the same bound to the save answer's progress.

## Medium

### I12. Steps written for the working tree's F14/F17 forms fail at e2cdc4e (isStored, suite registration, --list-suites)
- Sources: facts-6, facts-7, steps-2, critic-5, tests-4
- Category: missing-step
- Section: §5.5 item 4 (`isStored`); §6 P2 C2.1 step 7; P3 C3.1 step 2; P5 C5.3 step 5; §7.8 Registration; Exit P0 / C0.22
- Plan text: "return !!known && known.path === path && known.document.documentType === document.documentType\n  && known.document.title === document.title && known.document.body === document.body" / "Register it in `tests/selftest.py` `SCRIPTS`" / "add `"timeline"` to `tests/transition_selftest.py` `SUITES` (`:18`). CMake and `tests/selftest.py` follow through F17" / "| EditorKeys `timeline` | via `SUITES` (F17) | via `--list-suites` (F17) |" / "CTest runs exactly `tests/transition_selftest.py --list-suites` plus the new Python tests." / "`tests/transitions.qml` fake editor (WT `:424-448`)"
- Problem: These steps depend on uncommitted working-tree fixes but never say so, and they fail at e2cdc4e. (1) `stored` maps a path to the document itself, so known.path and known.document are undefined. isStored never matches, every flush sends a save (or throws), and §5.12's "toggling twice sends nothing" breaks. (2) tests/selftest.py has no SCRIPTS list. (3) CMake names the transition suites by hand, so the new timeline EditorKeys suite would never run under ctest. (4) --list-suites does not exist, and CTest runs about 20 other tests besides, so "exactly" is false anyway. (5) The fake editor citation is WT-only. (6) The P0 test list names renameBackCases, whenSavedCases and storedCases, which do not exist.
- Evidence: NoteSession.qml:37-43 `property var stored: ({})`; :294 `session.stored[session.resolvedPath(path)] = editor.snapshotDocument()`; :364-367 `var known = session.stored[path]; return !!known && known.title === document.title && known.body === document.body`; :526. tests/selftest.py:11 `from transition_selftest import SUITES as TRANSITION_SUITES`, :15 `SUITES = [`, :41. CMakeLists.txt:99 `foreach(suite core tools lists blocks toolbar diacritics tables keys)`; CMakeLists.txt:76-129 holds the other tests. transition_selftest.py:18 and :27-40 have no --list-suites. A grep of head finds no renameBackCases, whenSavedCases, storedCases or SlotLoader.qml. The fake editor is tests/transitions.qml:375-400.
- Correction: §5.5 item 4 at e2cdc4e: `var known = session.stored[path]; return !!known && known.documentType === document.documentType && known.title === document.title && known.body === document.body`, citing :364-367 only. If F14 lands first, add the same documentType comparison to its shape. P3: "Register it in `tests/selftest.py` `SUITES` (:15-43) and as CTest `add_test(NAME timeline-codec …)`." P5 and §7.8: "add `"timeline"` to `tests/transition_selftest.py` `SUITES` (:18), which tests/selftest.py already follows (:11, :41), to the `foreach(suite …)` list at CMakeLists.txt:99, and as a timeline entry in the EditorKeys suites map (:3051-3059). If F17 has landed first, CMake reads --list-suites and needs no edit." The §7.8 EditorKeys row reads "via transition SUITES (tests/selftest.py:41) | native-transitions-timeline (CMakeLists.txt:99)". Exit P0: "CTest has native-transitions-<name> for every name in transition SUITES, plus qthtml, local-provider and regressions" (or "`ctest -N` lists …"). P2 step 7 cites tests/transitions.qml:375-400. Call noteTypeSessionCases() in the NOTE_NOTE_TEST_NOTES_ONLY branch (tests/transitions.qml:2010-2022). Make the same changes in Appendix A.

### I13. F10 is presented as fixed, but an open rename still loses its text on every timeline save
- Sources: facts-5
- Category: false-claim
- Section: §4.8 table, F10 row; §6 P0 F10 bullet; §9
- Plan text: "including F10: `NoteList` holds the rows it draws while a title is renamed in place (`heldRows`/`shownRows`), so a save that rebuilds rows (every timeline check) no longer ends a rename"
- Problem: At e2cdc4e, an open in-place rename loses its typed text whenever the rows rebuild, and the outside F10 fix has been reverted and is open again. Timelines make this far more frequent. Every check is a save, and the save answer changes the row's `progress`, so the row JSON differs and every delegate is rebuilt. With Markdown notes, the rows rebuild only when the preview line changes. §9 does not list the defect.
- Evidence: ui/NoteList.qml:496-529 (renameField) at e2cdc4e. Workspace.qml:1359 `var rowsChanged = JSON.stringify(model.rows) !== JSON.stringify(root.rows)`, under a comment that "every delegate is destroyed and built again". CODE-REVIEW-2026-10-11.md:24 "F10 | **Reverted, still open.**". §5.11.1's save commit carries `progress: result.progress`.
- Correction: Remove the F10 claim. Add to §9: "R30 | Outside defect F10, open at e2cdc4e: an open rename in the list loses its text whenever rows rebuild (ui/NoteList.qml:496-529), and each timeline check's save rebuilds them | Not fixed by this plan. It waits on the outside F10 decision, which also bears on U2 (progress as a row field)."

### I14. Existing restoreDocument calls lack documentType, and P2 step 7 misses other test sites
- Sources: steps-3, facts-8, tests-5
- Category: missing-step
- Section: §5.4 pane protocol (`restoreDocument`); §6 P2 C2.1 step 7; §9 R1
- Plan text: "`restoreDocument(snapshot)` | function → string | activates `snapshot.documentType`, sets title and base, returns `body.restore(snapshot.body, token)`" / "`editor.plain = true/false` (HEAD `:1089`, `:1103`, `:1367`, `:1369`) becomes `editor.restoreDocument({ documentType: "text"|"markdown", … })` before the scenario's `setNote`; `requestMarkdown` (HEAD `:1248`, `:2454`) → `requestBody(editor.snapshotDocument(), …)`"
- Problem: Seven existing calls on a real NoteEditor pass `{ title, body, base }` without documentType. After P2, activate(undefined) fails because bodyFor gets NoteTypes.entry(undefined), which is null, so they restore nothing. That includes EditorKeys' load() helper, behind 108 `load({` fixtures, and transitions' show(), behind every editorCases check. P2's exit ("All existing suites are green") therefore fails. Further: plainLinks calls setNote right after, so the "text" type has to travel in that setNote document. Applied literally at :2454, requestBody(editor.snapshotDocument()) serialises the main editor instead of helperlessEditor. An empty-body restore at :1367/:1369 wipes toolPermissions' selected "word". tests/audio.qml's setNote calls also need a type. R1's list of suites omits statusbar, extensions, audio and standalone.
- Evidence: tests/transitions.qml:133 (hostConflictCases, a markdown: false provider) and :328 (show(), on the real Ui.NoteEditor at :317). tests/EditorKeys.qml:209 and :266 (conflict scenarios), :371 and :376 (load()), :2469 (helperlessLoad). 108 `load({` sites. :1088-1105 (plainLinks), :1344-1376 (toolPermissions), :2454.
- Correction: Add to P2 step 7: "Every real-editor restoreDocument carries its type: `documentType: "markdown"` at tests/EditorKeys.qml:209, :266, :371, :376 and :2469 and tests/transitions.qml:328; "text" at tests/transitions.qml:133. In plainLinks (:1088-1105), call `editor.setNote({ documentType: "text", title: "", body: "https://example.com", base: "" })`, and the finally restores a "markdown" document. :2454 becomes `helperlessEditor.requestBody(helperlessEditor.snapshotDocument(), …)`. At :1367 and :1369, restore the scenario's own document (text "word", then the saved Markdown documentHtml()) and selectText("word"). The nine tests/audio.qml setNote calls use documentType "markdown"." Add statusbar, extensions, audio and standalone to R1.

### I15. tests/statusbar.qml still assigns ViewBar.wordCount, which P2 removes
- Sources: facts-9, steps-5
- Category: missing-step
- Section: §6 P2 C2.1 step 4 (ui/ViewBar.qml) and step 7; Appendix A
- Plan text: "**`ui/ViewBar.qml`**: `property string countText` replaces `wordCount` (`:36`, `:131`). The label keeps `objectName: "wordCount"`."
- Problem: A third ViewBar, in the statusbar suite, assigns `wordCount`. Once the property is gone, that file fails to load ("Cannot assign to non-existent property") and tests/statusbar_selftest.py fails. Neither §6 nor Appendix A names the file.
- Evidence: tests/statusbar.qml:147-156 `Ui.ViewBar { … wordCount: 42`; :331/:333 `count.text === "42 words"`. tests/selftest.py:36 runs statusbar_selftest. Only Workspace.qml:2889, tests/statusbar.qml:147 and tests/EditorKeys.qml:86 contain a `ViewBar {`.
- Correction: P2 step 7: "tests/statusbar.qml:156: `wordCount: 42` → `countText: "42 words"`; the check is unchanged." Add the Appendix A row `tests/statusbar.qml | ViewBar countText | P2`.

### I16. The validId test expects "constructor" to be rejected, but it is a well-formed id
- Sources: facts-10
- Category: test-gap
- Section: §6 P1 C1.1 step 10; §7.2 `validId` table
- Plan text: "`validId` accepts `text`, `timeline` and `com.example.kanban/board`, and rejects `Timeline`, `a/b`, `1x`, `-x`, a 129-character id, `__proto__`, `constructor`, `""`, `null` and `42`;"
- Problem: "constructor" matches the plan's own grammar (lowercase letters, at most 32 characters), so the test as written fails. The code is already safe: entry() uses hasOwnProperty, so "constructor" is simply an unknown type.
- Evidence: Compiling the plan's TYPE_ID/ID_PATTERN in python3 gives bool(P.match('constructor')) == True. The other rejected ids are refused.
- Correction: Move `constructor` to the accepted ids: "accepts `text`, `timeline`, `constructor` and `com.example.kanban/board`, and rejects `Timeline`, `a/b`, `1x`, `-x`, a 129-character id, `__proto__`, `""`, `null` and `42`". Keep `entry("constructor")` → null, and add an `opened()` case: a reported "constructor" opens read-only as an unknown type.

### I17. "Each line follows the title's rules" caps description lines at 256, against the reader, the form and the prototype
- Sources: facts-11, safety-11
- Category: contradiction
- Section: §5.6.1 Model vs §5.6.4 step 10, §5.6.7 Limits and §5.8.4 Description row
- Plan text: "| `description` | `""`, or 1–40 **lines** joined by `"\n"`, at most 4096 code units in all. Each line follows the title's rules. There are no empty lines. |"
- Problem: The title's rules include "1–256 UTF-16 code units", so read literally every description line is capped at 256. Step 10, the form (4096 units and 40 lines) and the prototype allow 4096 per line. If JS (fromForm, validEvents) and Python (read, write) follow different readings, a timeline Python reads fails validEvents and cannot be shown, or a line typed in the form fails write and every save is refused. The draft is then kept and closing the window is blocked. test_timeline_limits_agree compares only the MAX_* constants, so it would not catch the drift.
- Evidence: §5.6.1 title row: "One line of plain text, 1–256 UTF-16 code units …". §5.6.4 step 10. §5.8.9. scratchpad/plan/exp/codec_check.py:86-87 `check_text(line, MAX_DESCRIPTION, …)`.
- Correction: Replace the sentence with: "Each line follows the title's rules except its length: not empty, no control characters, no leading or trailing whitespace, 1–4096 units; the lines share the 4096-unit total." Add a `MAX_LINE`, or state that `MAX_DESCRIPTION` applies per line, in both TimelineModel.js and timeline.py, and include it in test_timeline_limits_agree. Add a §7.1 write case: a 300-unit description line is written and read back.

### I18. The 500-event timing case times only two pure functions and pins nothing
- Sources: facts-14, steps-10, critic-7, tests-15
- Category: test-gap
- Section: §7.5 timeline case 23; §9 R22; U12, U3; Exit P5
- Plan text: "23. A 500-event body opens. A check on event 250 finishes `setChecked` + `patch` within 200 ms (measured with `Date.now()` around the call)." / R22: "ListView virtualisation, `patch` in place (no delegate rebuilds), and a timed EditorKeys case (23)."
- Problem: The timed span covers two pure functions over 500 plain objects, which take about 0 ms, so the case cannot fail. Everything R22 names is left out: applying the ops to the ListModel, delegate bindings and the staggered 120 ms animations, form(), edited() and opening 500 events (the codec plus a full reset). The case cannot catch a regression from patching in place to a model reset, and "no delegate rebuilt" is never asserted. A 200 ms wall-clock bound in a suite CTest may run in parallel can also flake.
- Evidence: A qml6 probe (offscreen, 500 rows) printed `ops=251 pureMs=0 applyMs=4`. §5.7 setChecked is an events.map, and §5.8.2 patch is two linear scans. transition_selftest.py:160-175 runs offscreen with the software backend, and no QML suite has a wall-clock assertion today.
- Correction: Case 23 becomes: "A 500-event body opens (setNote answers ok within 1 s). Space on event 250, or `editor.bodyAction("toggle", 249)`, runs the whole commit() (toggle, the ops applied to rows, form(), host.edited()); then list.forceLayout(). Within 200 ms (keys.tryVerify), rows holds 251 checked rows and timelineCheck-250 reads checked. The timelineEvent-<i> items visible before the check are the same objects after it, counted by a Component.onCompleted counter in TimelineEvent. list.contentY is unchanged, and patch returns exactly the changed rows as set ops. The add row says 'A timeline holds at most 500 events'." Move the felt budget (open, check and PageDown at 500 events, in both hosts) to §7.7.

### I19. The planned UNKEPT case cannot pass, because to_html does not show the definition it names
- Sources: facts-15, steps-9, tests-10
- Category: test-gap
- Section: §6 P0 C0.20 steps 2-4; Appendix A
- Plan text: "qthtml `UNKEPT` case: `"Bookmarks\n\n[home]: https://example.com\n"` → `["a link definition no link uses"]`" / "`to_html` is unchanged." / "`docs/decisions.md` … gains one sentence about link definitions."
- Problem: An UNKEPT entry is (name, markdown, named, shown), and check_unkept fails an entry whose `shown` is not in to_html(markdown) ("names what it holds and shows all of it"). mistune consumes the definition, so the HTML holds only "Bookmarks": the case cannot be written as specified, or can only be written with shown="Bookmarks", which pins nothing. The read-only note would hide the very text its reason names, against the recorded decision that read-only shows what it cannot keep. decisions.md:716-719 already lists the definition line as knowingly lost, so that sentence has to be amended, not extended. writer.py gets `parse` through qthtml/siblings.py, which the step does not name. The used-definition case cannot be in CASES either, because it is not a fixpoint.
- Evidence: qthtml/selftest.py:227-233 (the tuple shape) and :513-524 (`elif shown not in to_html(markdown)`). The probe to_html('Bookmarks\n\n[home]: https://example.com\n') gives only `<p …>Bookmarks</p>`. docs/decisions.md:705-711 ("read-only shows it") and :716-719. qthtml/siblings.py:1-19; writer.py:14.
- Correction: C0.20 step 2: "qthtml/siblings.py imports and exports parse_with_definitions. to_html and unkept both parse with it, and the renderer draws each definition no link uses as its source in a code block, or as a literal paragraph (the raw-HTML precedent), so the read-only note shows what its reason names." Step 3: UNKEPT entry `("unused link definition", "Bookmarks\n\n[home]: https://example.com\n", ["a link definition no link uses"], "https://example.com")`, plus `("used link definition", "See [the guide][g].\n\n[g]: https://example.com\n", [], "the guide")`. Step 4: amend decisions.md:716-719 to "a used reference-style link's definition line (the link itself is written inline)", and record that an unused one is shown and opens read-only. Add services/markdown/qthtml/siblings.py (P0) to Appendix A. If hiding the definition is acceptable instead, ask the user, then keep to_html unchanged, use shown "Bookmarks", and name the exception in the UNKEPT comment, the check_unkept docstring and decisions.md. Do not weaken check_unkept.

### I20. EditorKeys' fake providers silently switch from the rich editor to plain text after P2
- Sources: steps-4, tests-6
- Category: test-gap
- Section: §6 P2 step 5 / step 7; C1.1 `legacyTypes`; §5.5 answer branch
- Plan text: "`legacyTypes(provider)` (no provider → `["markdown"]`; `markdown === true` → `["markdown"]`; else `["text"]`)" / "`var opened = NoteTypes.opened(capabilities, result)`"
- Problem: EditorKeys drives the real editor through two NoteSessions whose fake providers declare neither `markdown` nor `noteTypes`. Today their notes open rich, because the mode comes from editor.plain (false). After P2 they open as plain text. unchangedNoteUnsent, the regression test for 5887a8f (the rich HTML snapshot), then compares plain strings and stops pinning its bug. The conflict scenarios also run in plain mode. They all still pass, so the coverage loss goes unnoticed.
- Evidence: tests/EditorKeys.qml:171-188 (mergeProvider) and :300-317 (quietProvider loads "Milk and **bread**\n\n- [ ] eggs\n"). :333-360 (unchangedNoteUnsent). The editor at :51-65 has no `plain` binding.
- Correction: Add to P2 step 7: "`mergeProvider` (:172) and `quietProvider` (:301) declare `readonly property var noteTypes: ["markdown"]`. After its load, unchangedNoteUnsent first requires editor.documentType === "markdown"."

### I21. C6.1 and C6.2 tests use workspace actions that only C6.3 creates
- Sources: steps-6
- Category: step-order
- Section: §6 P6 C6.1 and C6.2 (tests) vs C6.3
- Plan text: "C6.1: Tests: transitions `localCases` (§7.3 items 18–21)", where item 20 is "invoking `newTimeline` (… `workspaceActions.invoke("newTimeline")`)"; "C6.2: Tests §7.3 items 22–24", where item 24 is "`WorkspaceActions` availability …"
- Problem: `newTimeline` and `addTimelineEvent` are created in C6.3, but C6.1 (item 20) and C6.2 (item 24) use them. Until then, unavailable() answers "Unknown workspace action: newTimeline", so both commits leave the runners red. C6.1's footer docs also name Ctrl+Shift+T before C6.3 binds it.
- Evidence: WorkspaceActions.qml:63-66 returns "Unknown workspace action: "; its handlers (:18-34) are only newNote, newNotebook, openSettings, toggleList and deleteNote.
- Correction: In C6.1, item 20 calls `app.newNote("", undefined, "timeline")`, which runs `activateFooterShortcut("newTimeline")`. Move item 24 and the `workspaceActions.invoke("newTimeline")` form of item 20 into C6.3's tests. Move the "Ctrl+Shift+T" clause of the footer-shortcut docs from C6.1 to C6.3.

### I22. P6 breaks two exact assertions that no step updates (local footer paths, catalog command count)
- Sources: steps-7, steps-8, tests-7
- Category: missing-step
- Section: §6 P6 C6.1 and C6.3; §7.6; Appendix A
- Plan text: "Local: `noteTypes: ["markdown", "timeline"]`, the `newTimeline` footer row, `newNoteTarget(sectionKey)` and `action("newTimeline")`" / "`defaults.js`, `WorkspaceActions.qml`, … `plugin.json`, and the `services/extensions/selftest.py` pin (§5.9)"
- Problem: The core suite pins the local notebook tab's footer to exactly "newNote,newSection,newNotebook", and the new row makes it "newNote,newTimeline,newSection,newNotebook". tests/extensions.qml pins the catalog command count at 7, and C6.3's two palette commands make it 9, so native-extensions and extensions_selftest fail. The plan updates only services/extensions/selftest.py.
- Evidence: tests/transitions.qml:1474-1475 `… join(",") === "newNote,newSection,newNotebook"` (oneNoteCases, creationHost :1457-1473). tests/extensions.qml:374 `compare(workspace.catalog.commands.length, 7)`. The workspace plugin.json has 5 commands and appearance has 1.
- Correction: C6.1: "tests/transitions.qml:1474-1475 expects `"newNote,newTimeline,newSection,newNotebook"`, named 'a local notebook tab supplies New Note, New Timeline, New section and New notebook'. creationHost.newNote records its third argument, and folders.action("newTimeline", "", "Work") records "local:section:Work:timeline"." C6.3: "tests/extensions.qml:374: `compare(workspace.catalog.commands.length, 9)`." Add both to §7.6, and the count to Appendix A's tests/extensions.qml entry.

### I23. "A crash, a note switch or a window close keeps what you typed" is false for text without a title
- Sources: safety-5, ux-7
- Category: data-safety
- Section: §3 U6 (Why); §5.8.4 The form (Semantics, Focus leaving, One form at a time)
- Plan text: "\"Never lose a note\" (goal 2). A crash, a note switch or a window close keeps what you typed." / "While adding, the pending event is appended once its cleaned title is non-empty and valid. … So a note switch, a window close or a crash keeps what was typed" / "Editing: the edit finishes as if Enter were pressed (valid) or Esc (invalid)."
- Problem: Some typed text is never in the snapshot: a description typed while the title is empty or after emptying it, and an edit whose title is empty. edited() fires, flushSave finds the snapshot already stored and clears dirty, and nothing is saved. A note switch, a reload or a window close then runs clear(), and the text is gone with no draft or undo. In edit mode, a user who empties the title to retype it after changing the description, then opens the palette or clicks the search field, gets "Esc": the old text returns and the description edit is lost without an undo step.
- Evidence: NoteSession.qml:480-483 (isStored → dirty = false); :204-206 (reload only when clean); :185-192 (selectPath → flushSave → load); Workspace.qml:353 (requestClose → flushSave). §5.8.9 clear(). CommandPalette.qml:102-105 (focusQuery takes the keyboard). Sequence: Ctrl+Enter, Tab, type "passport, adapters, chargers", Ctrl+Down: the text is gone.
- Correction: U6's Why becomes: "A crash, a note switch or a window close keeps an event once it has a title; text in a form without a title lives only while the form is open." Ask the user in §3 (CLAUDE.md: stop and ask). (a) Accept that as stated. (b) The description field takes input only while the title is valid. Pin the choice in an EditorKeys case. §5.8.4 Focus leaving, Editing: "a valid edit finishes as if Enter were pressed; an invalid one (an empty title) stays open with its text and the message "Give the event a title". Leaving focus never discards; only Esc restores the old text." One form at a time: "an action that must close an invalid edit leaves it open and says "Give the event a title"."

### I24. The Draft branch sketch drops `dirty = !!draft.error` and the conflict re-show
- Sources: safety-6
- Category: data-safety
- Section: §5.5 How the session threads the type, item 2 (Draft branch)
- Plan text: "2. **Draft branch** (`:236-245`):\n\n   var refusal = editor.restoreDocument(draft.document)\n   session.editingView = draft.view || null\n   session.noteReady(refusal !== \"\", refusal)"
- Problem: The sketch replaces all of :236-245 with three statements. It drops `session.dirty = !!draft.error` (:240) and the conflict re-show (:241-243). A restored draft whose save failed then counts as clean, is not retried on the next switch, and in the shell host is lost if the shell restarts. OneNote and Notion drafts come back without their conflict review, which breaks P2's exit. Item 3 marks the lines it keeps, but item 2 does not.
- Evidence: NoteSession.qml:236-244 (:240, :241-243). :473 `if (!session.dirty || !session.writable) { return }`. :318: noteReady sets dirty = false, so the dirty line must come after it.
- Correction: Write item 2 in full: restoreDocument, editingView, noteReady, then keep :240-243 unchanged (`session.dirty = !!draft.error`; `if (draft.conflict) { session.showConflict(path, draft.conflict) }`), then return. Add a noteTypeSessionCases case: a restored timeline draft whose save failed is dirty and is sent again on the next note switch.

### I25. An open form does not survive a session lock or a reload (read-only, reconcile, undo during a lock)
- Sources: safety-7, ux-5
- Category: data-safety
- Section: §5.8.3 Read-only; §5.8.9 (show, clear, viewState, undo/redo); §5.5
- Plan text: "**Read-only.** No add area, no form, no menu, circles inert. The cursor still moves." / "`clear()` | events `[]`, `rows.clear()`, cursor -1, form null, undo and redo `[]`." / "`undo()` / `redo()` | Pop the stack. `fromForm`, then patch the rows, then `host.edited()`."
- Problem: Sessions lock during row actions (New section, Rename or Delete of a folder), any delete, and a settings drain. If "no form" closes the form, the pending event, which was already saved, leaves the snapshot, and the next check deletes it from the file. If read-only hides the form instead, the hidden field keeps the keyboard and keeps taking text. Undo and redo are not gated on read-only, so Ctrl+Z (or IPC editorUndo) during a lock changes a note that cannot save, and the change goes out with the next unrelated edit. An external change reloads a clean note, and a note with an open form is often clean. The reload runs show() → clear(): the form closes mid-typing, the text and the undo history go, and the next keystrokes land in the list (Space checks, Delete deletes).
- Evidence: NoteSession.qml:125-133 (lock()/unlock() → updateReadOnly), called at :428 and Workspace.qml:2115-2116 (runRowAction); :204-208 and :544-551 (reload when not dirty); :480-483. Qt 6.11.2 probe tst_hidden_typing.qml: a hidden focused TextField keeps activeFocus and receives typed keys. Sequence: the form holds "Pack" (saved), New section on a folder, lock and unlock, check an event: the file loses "Pack".
- Correction: §5.8.3: "Read-only never closes, hides or clears an open form: it stays on screen with its fields `readOnly: host.readOnly`, keeps its mode and text, and the snapshot keeps the pending event. Only Enter, Esc, another note or a reload closes a form." §5.8.9 undo()/redo(): "Return early when read-only, as commit does." §5.5: "`NoteSession.reconcile` also returns while `editor.formOpen`: an open form is an edit in progress, like `dirty`; the next save is last-writer-wins as for a dirty note (§5.12)." Add a §7.3 case (reconcile while formOpen does not reload) and EditorKeys cases: (a) the add form holds a title, the editor goes read-only and back, an event is checked, and the snapshot still holds the pending event; (b) a lock and unlock keep the form, its text and its focus.

### I26. A soft line break renders as a new line in Obsidian, but the reader turns it into a space and rewrites it
- Sources: safety-10
- Category: false-claim
- Section: §3 U8; §5.6.4 step 8; §9 R5
- Plan text: "(a) anything that renders the same (blank lines between items, `*`/`+` bullets, `[X]`, CRLF, wrapped lines), normalised only when you next change it … A soft break reads as one space, so a wrapped line renders and reads as one line."
- Problem: Obsidian, with its default "Strict line breaks" off, shows a soft break as a new line. An item written there as "- [ ] Pack" with "  passport, adapters" on the next line reads as the title "Pack passport, adapters". Checking any other event rewrites the item onto one line, though the user never touched that text.
- Evidence: The planner's own variant "tight title+description soft break": "- [x] Book flights\n  Return on the 14th\n" is accepted as one event and rewritten as "- [x] Book flights Return on the 14th\n". Every save writes the whole body (§5.6.5, §5.12).
- Correction: In U8 (a), replace "anything that renders the same" with "anything that renders the same in CommonMark and on GitHub". Add to U8's Why: "A line break with no blank line, which Obsidian shows as a new line, is read as a space; the next change anywhere in the timeline writes that event on one line." Add option (c): "refuse a line break inside an event: it opens as Markdown with 'a line break inside an event (event N)'". State the limit in R5's mitigation.

### I27. Form keys take Ctrl+Up/Down and Ctrl+Tab before app shortcuts
- Sources: ux-3
- Category: ux
- Section: §5.8.5 Keyboard map (Form fields focused)
- Plan text: "3. `Tab` / `Backtab` → switch field. 4. `Down` in the title → description. `Up` on the description's first line (cursor y < its line height) → title. 5. `host.shortcut(event)`."
- Problem: Steps 3-4 run before host.shortcut and ignore modifiers. In the form, Ctrl+Down (nextNote) moves to the description, Ctrl+Up on the description's first line (previousNote) moves to the title, and Ctrl+Tab and Ctrl+Shift+Tab switch fields. This recreates the §4.2 trap, and case 13 checks only the list.
- Evidence: defaults.js:13-16 (Ctrl+Up, Ctrl+Down/Ctrl+J, Ctrl+Tab, Ctrl+Shift+Tab in the notes context). stroke.js:26-31 (Shift+Tab arrives as Backtab). §4.2: "A list that uses onDownPressed would therefore swallow Ctrl+Down before the app shortcut sees it."
- Correction: Steps 3 and 4 apply "only without Ctrl, Alt or Meta (`!(event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))`); a modified Tab, Up or Down goes on to step 5." Enter commits with or without Ctrl. Extend case 13: in the title field Ctrl+Down and Ctrl+Tab, and on the description's first line Ctrl+Up, reach the shortcutHandler stand-in.

### I28. The add row has no undo keys and sits outside the list's cursor model
- Sources: ux-4, safety-12, tests-8
- Category: contradiction
- Section: §5.8.5 Keyboard map (Add row focused); §5.8.4 Esc; §5.8.2 Structure; §5.8.9 focusEditor; §7.5 cases 9, 13; U6
- Plan text: "**Add row focused.** `host.shortcut` first, then: | `Return`, `Enter`, `Space`, `Ctrl+Enter` | Open the form. | A printable character … | `Up` | Last event. | `Home` | First event." / "Adding: discard the pending event (one undo step brings it back as an event when it had a title), close the form, and put the cursor on the add row." / "9. Esc while adding discards the pending event and Ctrl+Z brings it back."
- Problem: After Esc the keyboard is on the add row, and its table has no Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y. These keys are reserved, so host.shortcut never takes them. The discarded event, which the next save has already removed from the file, cannot be brought back from there. Case 9 fails, and U6's promise does not hold from the keyboard. Because the add row is a second FocusScope rather than a cursor position, focusEditor's "the list (cursor nextIndex)" is undefined when the next position is the add row (all done, or empty). Delete of the last event leaves the keyboard in an empty ListView.
- Evidence: stroke.js:19-20 reservedLabels include ctrl+z, ctrl+shift+z and ctrl+y. defaults.js has no undo action. §5.8.2 "AddArea (FocusScope)" sits outside the ListView. The product design (designs/product.md, KEYBOARD) made the add row a cursor position of the list's handler, with undo.
- Correction: "The add row is cursor position `events.length` of the list's one `Keys.onPressed`; the list keeps the keyboard and the add area draws the row under the cursor. On it: Return, Enter, Space and Ctrl+Enter open the form; a printable character opens it with that character in the title; Up → last event (the note's title when there are none); Home → first event; `Ctrl+Z` / `Ctrl+Shift+Z`, `Ctrl+Y` undo and redo as on the list; Delete, Alt+↑/↓ and Menu do nothing." Minimal form: add that undo/redo row to the Add-row table. "After Delete, the cursor is `Math.min(index, events.length)`. `nextIndex` is `events.length` when every event is done (the last event when read-only)." Case 9 presses Ctrl+Z with the add row focused, and case 13 reads "Down past the last row puts the cursor on the add row".

### I29. A circle click does not move the keyboard, so Ctrl+Z undoes field typing instead of the click
- Sources: ux-8
- Category: false-claim
- Section: §3 U1; §5.8.6 Mouse; §9 R11
- Plan text: "One `Ctrl+Z` undoes a mistaken click, and the status line says how many events changed." / "Click a circle (`TapHandler`) | Toggle (§5.7). The circle does not take focus." / R11: "one `Ctrl+Z` restores."
- Problem: After Ctrl+Shift+T the title is focused, and while adding events the form is focused. A mistaken circle click followed by Ctrl+Z then undoes title or field typing, not the click. The mitigation U1 and R11 rely on holds only when the list already has focus.
- Evidence: Workspace.qml:1932-1936 (newNote focuses the title). §5.8.4: the add form is kept open after each add. In the title field Ctrl+Z is reserved (stroke.js:19-20), so the TextField's own undo runs (NoteEditor.qml:1908-1913).
- Correction: §5.8.6: "Click a circle | Toggle (§5.7). The list takes the keyboard with the cursor on that event, unless a form of this timeline is open (the form keeps it, case 21)." U1's Why: "One Ctrl+Z in the list undoes a mistaken click (in a form field Ctrl+Z is the field's own)…". Add a §7.5 case: with the title focused, click a circle, press Ctrl+Z: the states are restored and the title is unchanged.

### I30. Moving an event can leave checked events below unchecked ones, and the user is not asked
- Sources: ux-9
- Category: spec-fidelity
- Section: §5.8.5 Keyboard map (Alt+Up/Down); §5.7 Out-of-order states; §3; R10
- Plan text: "`Alt+Up` / `Alt+Down` | Move the cursor event up or down. The cursor follows." / "**Out-of-order states.** These come from another editor, a phone or a sync." / U1: "so your own clicks never leave holes."
- Problem: The user's rule ("If he checks one, we will check all above") keeps the checked events a prefix. `move` keeps each event's state, so moving a checked event below an unchecked one makes a hole by the user's own action. The plan says holes come only from other editors, and asks nothing.
- Evidence: The user's words, quoted in the problem. §7.2 tests `move` only "at the bounds", §7.5 case 12 checks only that the cursor follows, and R10 lists "Obsidian, a phone, a merge".
- Correction: Add "U17 | What does moving an event do to the checks? | (a) nothing: a move can leave a checked event below an unchecked one, shown as stored; (b) the moved event takes the state of the event now above it (at the top, its own) | (a)" to §3. Amend §5.7 ("…a sync, or a move (U17)"), U1's Why ("your own checks never leave holes (a move can, U17)") and R10. Pin the rule with a §7.2 `move` case.

### I31. Providers that also target older hosts cannot tell whether the host knows a type
- Sources: contract-4
- Category: contract
- Section: §5.2.2 (`markdown` row); §5.11 "Why the built-ins drop markdown"; §5.11.2 examples/hello
- Plan text: "keep it beside `noteTypes` if your provider must also run on Note Note 1.0.40 or older" … "The footer adds `{ path: "newTimeline", title: "New Timeline", icon: <U+F0F97>, shortcut: "newTimeline" }`, and `action("newTimeline")` → `host.newNote(root.id, "new", "timeline")`."
- Problem: The contract invites providers to run on 1.0.40 but gives them nothing to test what the host can make or show. On 1.0.40, hello's New Timeline row still shows, newNote drops the third argument, and the click silently makes a Markdown note. The `newTimeline` shortcut is unknown there too. The documented example breaks "honest about limits" (goal 7).
- Evidence: Workspace.qml:1887 `function newNote(providerId, target)`. Workspace.qml:701-704 and :124-140: neither `host` nor `services` exposes a version or a list of types. docs/providers.md documents only host.newNote and host.newNotebook.
- Correction: Add a documented read-only `host.noteTypes`: the type ids this host shows, from notetypes.js. Add to "Note types": "A provider that also runs on older hosts offers creation of a type only when `host.noteTypes` holds it; an older host has no `host.noteTypes`." hello adds its New Timeline row only when `root.host && root.host.noteTypes && root.host.noteTypes.indexOf("timeline") >= 0`. Test: with a host stub that has no `noteTypes`, hello shows no New Timeline row.

### I32. An invalid declaration is ignored whole, so known types open editable while unknown ones stay read-only
- Sources: contract-5
- Category: contract
- Section: §5.2.1 (`noteTypes` row); §5.2.2 "Note types"
- Plan text: "Valid when it is an array of 1–16 distinct ids that match the grammar, and when every type with a fallback (only `timeline`, whose fallback is `markdown`) has that fallback declared beside it. An invalid declaration is ignored as if absent"
- Problem: Ignoring the declaration also stops the host from reading `noteType`. So `["text", "timeline"]` makes every timeline open editable as plain text, while `["text", "kanban"]` keeps kanban read-only: a type the host knows gets less care than one it does not. Validity also depends on the host version. A later host that gives a type a fallback turns a declaration that was valid in 1.1.0 invalid, and that type's notes open editable as the legacy type. This goes against docs/README.md rule 1, "When in doubt, open read-only".
- Evidence: §5.3 opened(): `var reported = capabilities.declaresTypes ? answer.noteType : undefined` → defaultType → `{ readOnly: false }`. §5.2.1: "Unknown-but-valid ids stay declared".
- Correction: "A declared type whose fallback is not declared is dropped from the declaration. It is undeclared: its notes open read-only as plain text with the 'does not keep' reason, and it is not creatable. The rest of the declaration stands. When nothing remains, the declaration is the legacy type, and `noteType` is still read." declarationProblem checks only the shape (not a list, empty, over 16, a duplicate, a bad id), and the load warning names the dropped type. Docs: "Declare `markdown` beside `timeline`: a `timeline` declared without it is not taken, and such notes open read-only." Test: `["text","timeline"]` → noteTypes `["text"]`, and a timeline load answer opens read-only.

### I33. Row `progress` is read from every provider and every type, unlike `noteType`
- Sources: contract-6, critic-13
- Category: contract
- Section: §5.10 Row fields; §5.2.1 (`progress` row); §5.2.2
- Plan text: "`progress: kind === "note" ? NoteTypes.progressOf(source.progress) : null`."
- Problem: `noteType` is read only from declaring providers, because "an external provider may already send it" (R20). Yet the more generic `progress` is read from every provider, legacy ones included, and for every type. A legacy provider's existing `progress`, or a Markdown row carrying one, has its preview replaced by "x of y · Next: …", which is a silent change. The plan's own docs define progress only "for a note whose type has steps".
- Evidence: §5.1 and R20 on `type`/`noteType`. docs/technical-requirements.md:101: "change it additively, never silently". "progress" is already used in providers' code (onenote.py:491, :658).
- Correction: Add `steps: true` to the timeline table entry and `NoteTypes.hasSteps(id)`. The row field becomes `progress: kind === "note" && capabilities.declaresTypes && NoteTypes.hasSteps(rowType || capabilities.defaultType) ? NoteTypes.progressOf(source.progress) : null`, and displayProgress applies the same test. Docs: "`progress` is read only from a provider that declares `noteTypes`, and only for a note of a type with steps. `done` and `total` are integers with 0 ≤ done ≤ total; `next` is a string." §7.3 item 22 gains: a legacy row's `progress` and a declaring provider's Markdown-row `progress` are both dropped.

### I34. External providers are told to use services/markdown/timeline.py, which they cannot reach
- Sources: contract-7
- Category: docs-gap
- Section: §5.2.2, new subsection "### The timeline format"
- Plan text: "read and write it with `services/markdown/timeline.py` (`read`, `write`, `summary`); store the body exactly as given"
- Problem: An external package lives outside the app tree, and nothing it receives locates services/markdown. So it cannot follow this instruction without reading host code, which breaks the success criterion "A new provider can be written against PROVIDERS.md without reading the host's code". The text also implies a provider must parse the body, which it never needs to. The plan gives hello no progress for this same reason.
- Evidence: docs/providers.md:5-6 (~/.config/notenote/plugins/<package>/). Workspace.qml:124-140 (the services). Platform.qml:25-35. operations.py:9-10 (a relative path). §5.11.2: "No `progress`: hello has no Markdown reader".
- Correction: "A provider never parses a timeline: it stores the body exactly as given and reports `noteType`. `progress` is optional. The built-in local provider computes it with the app's own codec (`services/markdown/timeline.py summary`), which a package outside the app cannot reach in this version, so leave `progress` out and the row shows your `preview`." Add a §10 row: "A host service that summarises a timeline body for providers, so external providers can report progress."

### I35. The new newNote drops the session-locked and canCreate guards
- Sources: contract-8
- Category: missing-step
- Section: §5.9 `newNote(providerId, target, noteType)` (replaces :1887-1938)
- Plan text: "1. If `!providerId`: … 2. Flush the save and clear the filter, as today. 3. Call `newNoteDestination(providerId, target, noteType)`. … 5. Call `p.create(target, cb, { noteType: type })`."
- Problem: e2cdc4e ignores `host.newNote` during a held rowAction (`if (session.locked) return`), and does nothing when `!p.canCreate`. Without those guards, a provider with `canCreate: false` and no create() hits a TypeError. `Capabilities.of().canCreate` (C0.21) is computed, but nothing reads it.
- Evidence: Workspace.qml:1888-1890 and :1908-1910. docs/providers.md:49 and :115-120.
- Correction: Add step 0: "If `session.locked`, return." After step 3: "If `!Capabilities.of(p).canCreate`, return (as today)." Add a §7.3 host case: a provider with `canCreate: false` and no `create()` calling `host.newNote(id, "x")` calls nothing and logs nothing.

### I36. The docs and the skill reference drift more widely than P1 lists, and "line for line" cannot hold
- Sources: contract-9
- Category: docs-gap
- Section: §6 Phase 1 C1.1 step 9 (Docs); Exit P1
- Plan text: "the existing drift: `retry`; save `merged` and `version`." … "`providers.md` and the skill reference agree line for line on every member touched."
- Problem: The skill's row shape lacks `count`. The skill's load answer lacks view, recovered, conflict and retry, and its save answer lacks conflict. The docs' load list lacks version, which the session reads. The skill's hasTitle lacks the text-weight rule. The skill is a summary in another shape, so it cannot agree "line for line".
- Evidence: docs/providers.md:89, :260 and :282 vs skill :267, :319 and :320. NoteSession.qml:261 and :525-529. docs/plugins.md:46-53.
- Correction: Step 9 lists the whole reconciliation: "rows: `count` (skill); load: `version`, `retry` (docs), `view`, `recovered`, `conflict`, `retry` (skill); save: `conflict` (skill), `merged`, `version` (both); `hasTitle`: the text-weight sentence and 'absent = true' (skill)". Exit P1: "For every member touched, the skill states the same fields, defaults and rules as docs/providers.md (checked member by member)."

### I37. From P1 on, no test loads a provider written against today's contract through the real loader
- Sources: contract-10
- Category: test-gap
- Section: §7.6 (standalone_selftest row); §6 C1.1 step 10
- Plan text: "`tests/standalone_selftest.py:190` (unchanged) | hello, now declaring `noteTypes`, still loads from the legacy directory"
- Problem: P1 and P6 edit examples/hello, the file the launch test copies, so after P1 no test runs a legacy provider through the real loader. Nothing pins that a provider without `noteTypes` logs no warning. A declarationProblem that warned on an absent declaration would pass every gate, because its text holds none of the gate's noise words.
- Evidence: tests/standalone_selftest.py:190 copytree(examples/hello). Its gate markers (~:203-205). The C1.1 cases cover only invalid shapes.
- Correction: Freeze e2cdc4e's examples/hello as tests/fixtures/legacy-hello/ (never edited), and copy that fixture into the legacy directory. Assert that it loads with no warning line, and that a note made from its footer (`host.newNote(id, "new")`) is passed `{ noteType: "markdown" }`, opens editable as Markdown and saves. Add to NoteTypeChecks: declarationProblem of a provider without `noteTypes` is "".

### I38. "Rows of Markdown notes are byte-identical to before" contradicts row(), which always adds the new keys
- Sources: contract-11, tests-24
- Category: contradiction
- Section: §7.3 item 22; §5.10 Row fields
- Plan text: "22. `sidebar.js` `row()` carries `noteType` only for a declaring provider's non-default type, and `progress` normalised. Rows of Markdown notes are byte-identical to before (JSON)."
- Problem: row() always writes `noteType: … : ""` and `progress: … : null`, and JSON.stringify keeps "" and null. Every row gains `"noteType":"","progress":null` and can never equal an e2cdc4e row. What matters is that rebuilds do not churn.
- Evidence: sidebar.js:24-31 builds explicit keys. §5.10. docs/decisions.md:444-448.
- Correction: Item 22: "A Markdown note's row has `noteType: ""` and `progress: null`, and two builds from an unchanged listing give byte-identical JSON (no churn)."

### I39. Nothing pins that Python's summary and JS's progress define progress the same way
- Sources: contract-15, tests-16
- Category: test-gap
- Section: §5.10 Wording; §9 R15; §7.6
- Plan text: "The definition of `{ done, total, next }` is the same in Python (`timeline.summary`) and JS (`TimelineModel.progress`). The same golden bodies pin it on both sides (§7)." / R15: "… the progress definition … | Regression pins (§7.6)."
- Problem: §7.1 item 7 tests summary alone and §7.2 tests progress alone, with no shared fixture, and §7.6 has no progress pin. If the two drift, notably on out-of-order states, the open note's row (JS) disagrees with every other row (Python).
- Evidence: The §7.6 table lists only limits, id grammar, creatable types and bodies.
- Correction: Add to §7.6 (P5) test_progress_definition_agrees: one shared case list (tests/NoteTypeChecks.js `var PROGRESS_CASES`, or tests/fixtures/progress.json) of events → the expected {done,total,next}: in order, out of order (x - x - -), all done, empty, and the §5.6.3 events. timeline_selftest.py or tests/test_regressions.py checks `summary` against it, and NoteTypeChecks checks `TimelineModel.progress`.

### I40. No test runs the fail-closed save chain (self-check refusal, codec error, failed conversion)
- Sources: tests-2
- Category: test-gap
- Section: §5.6.5 step 4; §5.12 Save step 6; §9 R4; §7.1; §7.3
- Plan text: "4. Self-check: `read(markdown) == events`, else `ValueError("the timeline could not be written as it is")`." / "6. A codec failure (dead process, `{error}`, a self-check refusal) answers `("", false)`. The session finishes with "the note could not be read for saving" and keeps the draft" / R4.
- Problem: With the P0 fix, no valid model reaches the self-check refusal. No case feeds fromTimeline an {error} or a dead process, and no session case answers a save conversion with ok=false. A writer without the self-check, or a session that saves "" after a failed conversion, would pass every test.
- Evidence: The prototype with the P0 fix gives 0 failures in 3000 models. All 24 conversion answers in tests/transitions.qml are true. "could not be read for saving" appears only at NoteSession.qml:500.
- Correction: (1) §7.1 item 6b: with timeline.convert patched to drop the last character, write(valid) raises the ValueError, and the CLI answers {"error"} with exit 1. (2) §7.3 item 14b: the fake editor answers requestBody with ("", false); provider.save is never called, the draft keeps "the note could not be read for saving", and the note stays dirty. (3) editorCases: a fromTimeline answer ("", false) reaches requestBody's callback as ("", false).

### I41. The undo stack guarantees (clear on note switch, cap, redo cleared) are untested
- Sources: tests-3
- Category: test-gap
- Section: §5.7 Undo; §7.5
- Plan text: "… at most 200 steps. … A new action clears redo. Both stacks clear when another note is shown. Each undo or redo is an edit: it emits `edited()` and is saved."
- Problem: Cases 5, 9 and 11 undo within a single note. If the stacks survived a switch, Ctrl+Z in B would restore A's form into B, and the next autosave would write A over B's file. The 200-step cap and "a new action clears redo" have no case.
- Evidence: Cases 5, 9 and 11 are single-note, §7.2 has no undo case, and clear() is the only place the stacks are emptied.
- Correction: Add to §7.5: "25. Check in timeline A, setNote timeline B, then press Ctrl+Z, Ctrl+Shift+Z and Ctrl+Y in B: B's snapshot is unchanged and no edited() is emitted. 26. Undo a check, then check another event: Ctrl+Y changes nothing. 27. After 201 checks, press Ctrl+Z 202 times: the 200th undo restores the state after the first check, and the next two change nothing." Case 5 requires exactly one edited() per undo and per redo.

### I42. The Esc test cannot see an unaccepted Escape reaching Workspace's content handler
- Sources: tests-9
- Category: test-gap
- Section: §7.5 case 9; §9 R16
- Plan text: "**Esc never reaches the host**: a `shortcutHandler` stand-in counts calls, and `back` is not run." / R16: "EditorKeys 9 and 13 cover the first two."
- Problem: In the app, `back` runs when an unaccepted Escape propagates to Workspace's content item, not through shortcutHandler. EditorKeys has no handler above the editor, so a form that forgets event.accepted passes. resetEditor never resets the stand-in either, so it leaks into later scenarios.
- Evidence: Workspace.qml:2623-2634. NoteEditor.qml:241-247. EditorKeys.qml:51-64 and :3336-3346.
- Correction: Wrap the editor in `Item { id: keySink; anchors.fill: parent; Keys.onPressed: function(event) { test.unacceptedKeys.push(event.key) } }`. Case 9 requires `test.unacceptedKeys.indexOf(Qt.Key_Escape) < 0` after Esc in each form field, both adding and editing. resetEditor sets `editor.shortcutHandler = null` and `test.unacceptedKeys = []`.

### I43. "No new QML warning" is not enforced: the noise gate misses ordinary QML warnings
- Sources: tests-12
- Category: false-claim
- Section: §6 Every commit; Exit P2; §9 R18
- Plan text: "adds no QML warning line, since the noise gates fail on any;" / R18: "The noise gates fail on new QML warnings." / Exit P2: "All existing suites are green with **no** new warning."
- Problem: The gate fails only on lines holding TypeError:, ReferenceError:, Binding loop, Unable to assign, Error: or ERROR. Warnings such as "Required property … was not initialized" pass it.
- Evidence: tests/transition_selftest.py:217-219. A qml6 probe printing ".../Body.qml:3:3: Required property host was not initialized". services/requests/selftest.py:55-57 already fails on 'qrc:' and '.qml:'.
- Correction: Either add a ".qml:" marker to the noise list at transition_selftest.py:218 in P0, after confirming that the current suites print no such line (if any do, list them and ask the user before P2). Or reword §6 and R18: "adds no warning line the gate matches; each commit compares the -v output for new .qml: lines by hand."

### I44. No case lets a late timeline or fallback answer arrive after a newer setNote
- Sources: tests-13
- Category: test-gap
- Section: §9 R3; §5.4 setNote/showAsFallback; §5.8.9 show()
- Plan text: "R3: The type is an argument of `setNote` and a field of every snapshot, activated before the body is touched. `noteToken` guards both async paths (including the fallback). Session cases 1–14 cover it."
- Problem: The session cases run on the fake editor, which has no token and no bodies and answers synchronously. EditorKeys answers cannot be held. The token checks in NoteEditor.setNote, TimelineBody.show and showAsFallback are untested.
- Evidence: tests/transitions.qml:375-400 (the fake editor) and :296-304 (a conversions fake with held callbacks), which editorCases (:331-365) already use for toHtml and toMarkdown races.
- Correction: In editorCases (P5), the conversions fake gains `timelines: []` and `toTimeline(markdown, callback) { timelines.push(callback) }`. (1) setNote timeline A, then markdown B, and answer B; A's late answer leaves documentType "markdown", B's text, and A's shown never called. (2) The same with A answered {notTimeline}: no fallback, no reason. (3) setNote timeline A, then timeline C; answer C, then A: the body holds C's events. R3 cites these cases.

### I45. Case 19 cannot prove that a focused timeline is the workspace shortcut context
- Sources: tests-14
- Category: test-gap
- Section: §5.4 "Keeping the hidden document inert"; §7.5 case 19; §9 R2
- Plan text: "`bodyFocused` stays `area.activeFocus`, so a focused timeline is the `workspace` shortcut context. … R2: A focused timeline is the `workspace` context. EditorKeys timeline case 19 proves it."
- Problem: EditorKeys has no Workspace, so shortcutContext() and the registry match never run there. "Ctrl+B and Ctrl+1 change nothing" passes whatever context Workspace would compute.
- Evidence: NoteEditor.qml:241-247. Workspace.qml:2135-2176. tests/transitions.qml:932-936 (appHost).
- Correction: Add a core-suite host case (appHost). A fake provider declaring ["markdown","timeline"] opens a timeline. With its list focused: `app.shortcutContext() === "workspace"`, `editor.bodyFocused === false`, and `app.handleShortcut` with Ctrl+B, Ctrl+1 and Ctrl+V returns false and leaves snapshotDocument() unchanged. R2 cites this case.

### I46. No test reads the built-in providers' real declarations
- Sources: tests-17
- Category: test-gap
- Section: §5.11 support matrix; §6 C1.1 items 2, 3, 6; Exit P1
- Plan text: "OneNote | `["markdown"]` | deferred | drop `markdown: true` … Sticky Notes | `["text"]` | unsupported | drop `markdown: false`" / "An invalid declaration is ignored as if absent, with one `console.warn`" / "Exit P1: Sticky still opens plain, and the others rich."
- Problem: Once the built-ins drop `markdown`, a typo in one of them falls back to legacy ["text"], and its notes open as raw plain text. The warning passes the noise gate, and no test reads a real built-in's declaration, so P1's exit claim has no test behind it.
- Evidence: The legacyTypes else-branch. The NoteTypeChecks cases use fakes only. local Provider.qml:20, sticky:14, onenote:19, notion:17.
- Correction: Add test_builtin_note_types to tests/test_regressions.py (P1): each built-in's `readonly property var noteTypes:` literal parses as JSON and equals ["markdown"] for local (["markdown","timeline"] from P6), ["text"] for sticky, ["markdown"] for onenote and ["markdown"] for notion, and none of them declares `markdown`. examples/hello keeps `markdown: true` and declares ["markdown"] (["markdown","timeline"] from P6).

### I47. The local save commit (Trap 2) has no test
- Sources: tests-18
- Category: test-gap
- Section: §5.11.1 local Provider.qml table, "save() commit (Trap 2)"; §5.12 step 7
- Plan text: "`save()` commit (`:548-549`, WT `:587-588`) | Trap 2: `return Object.assign({}, note, { …, noteType: result.noteType || "", progress: result.progress || null })`. Later fields survive."
- Problem: P4 tests Trap 1 but not Trap 2. If the commit keeps rebuilding the entry with explicit fields, every autosave drops noteType and progress until the next relist.
- Evidence: local Provider.qml:543-550 rebuilds the entry explicitly. §7.3 cases 18-21 and §7.4 contain no save-commit case.
- Correction: Add a §7.3 local case (P4): through the real provider, list a note-note-type: timeline file, then save a changed body. Without a relist, the entry and the section's row carry noteType "timeline" and the save answer's progress.

### I48. hello's timeline support is untested, though it is the example authors copy
- Sources: tests-19
- Category: test-gap
- Section: §5.11.2 examples/hello; §7.6 standalone row; §1
- Plan text: "| `tests/standalone_selftest.py:190` (unchanged) | hello, now declaring `noteTypes`, still loads from the legacy directory |"
- Problem: The only test that touches hello checks that it exists and calls action("setup"), and it runs only under CTest. Typed create and its refusal, the load answer's noteType, row noteType, restoreState's default and the New Timeline footer are never exercised.
- Evidence: tests/standalone_launch.qml:36-40. tests/selftest.py:15-43 does not run it. hello is a plain Item with in-memory notes (:7-40, :90-105).
- Correction: Add §7.3 cases (P6, core suite) on a Hello instance with a stand-in host. (1) create {noteType:"timeline"}: load and row carry "timeline". (2) create {noteType:"kanban"}: {error}, and no note is made. (3) restoreState of a note without noteType loads as markdown. (4) The footer holds newTimeline, and action("newTimeline") calls host.newNote("hello","new","timeline"). Add hello to §7.7.

### I49. Several P1 and P6 host cases cannot observe what they claim, or do not run in both runners
- Sources: tests-20, steps-15
- Category: test-gap
- Section: §6 C1.1 step 10; §7.3 Host cases and items 15-17, 20; §6 C4.1 item 3; §7.8
- Plan text: "a provider whose `noteTypes` is `"markdown"` (a string) loads as legacy with one warning that does not match the noise patterns" / "Ctrl+N passes `{ noteType: "markdown" }` to local `create`" / "the hello example still loads through the legacy directory (`tests/standalone_launch.qml:38-40`)" / "`record()` fixtures (`tests/transitions.qml` `localCases`) emit 10 fields"
- Problem: (1) Workspace.addProvider logs the warning, but host cases assign app.providers and skip addProvider, and QML cannot read the log, so "one warning" cannot be asserted. (2) Local's create ignores options until P4, and local is disabled in the runner config. "Ctrl+N … to local create" and item 20 need a wired local instance, which the plan does not name. (3) hello's legacy load belongs to tests/standalone_selftest.py. (4) record() lives in oneNoteCases. (5) Host cases need test.appHost, which exists only under --standalone or --host, so tests/selftest.py never runs them, and "registered in both runners" (D17) does not hold.
- Evidence: Workspace.qml:694-716. tests/transitions.qml:51, :130, :168, :206-247, :1246, :1457-1475, :1480, :932. transition_selftest.py:120-121, :217-222. local Provider.qml:555-557. tests/selftest.py:54-56.
- Correction: (1) Pin declarationProblem (non-empty for a string) and the legacy fallback in NoteTypeChecks, and drop "with one warning". The warning text is held only to the noise gate. (2) Use a fake provider whose `create(target, cb, options)` records its options and receives `{ noteType: "markdown" }` from Ctrl+N. Item 20 uses `localFactory.createObject(test, { host: test.appHost, notesDir: <a fresh dir> })`, or is split into a creationHost check (folders.action("newTimeline","","Work") → "local:section:Work:timeline") plus a host check of activateFooterShortcut. (3) List the hello check under tests/standalone_selftest.py. (4) Cite record() in oneNoteCases (:1480). (5) §7.8 states that host cases run only under CTest native-transitions-core and tests/selftest.py --host.

### I50. The manual checklist omits what automation cannot verify
- Sources: tests-21, critic-18
- Category: missing-step
- Section: §7.7 Manual checklist; §5.8.7 Accessibility; U9–U12
- Plan text: "Run in both hosts, light and dark themes: 1. `Ctrl+Shift+T` in a local notebook tab … 9. Sticky, OneNote and Notion notes behave exactly as in 1.0.41." / "This is a new precedent, documented in `docs/note-types.md`."
- Problem: The checklist leaves out: U10, assistive technology (case 22 only reads properties back); U11, other desktops; U9, IME and compose input; U12, felt latency at 500 events; the mouse paths (hover, double-click, the right-click menu, which no test opens, and Add new event); the §5.8.3 visual states; a half-typed event surviving a window close; and hello.
- Evidence: §3 marks U9–U12 as unverified. §7.5 never uses timelineMenu, timelineScrollBar or timelineEmpty. §7.7 has only items 1-9. R23.
- Correction: Add: "10. With Orca running, each event reads as a check box with its title and state, Orca's activate action toggles it by the prefix rule, and the add row reads as a button named Add new event. 11. Standalone on GNOME and KDE: Ctrl+Shift+T reaches Note Note. 12. Type the title and description with a dead key and with ibus, up to and past the limit. 13. A 500-event timeline opens, checks event 250 and pages with PageDown without visible delay. 14. Mouse: hover and click a circle, double-click a title, right-click an event and use Edit, Move up, Move down and Delete, click Add new event. 15. Checked, next, out-of-order and read-only events in light and dark: rings, spine and dimming as in §5.8.3. 16. Type an event title, close the window, reopen: the event is there. 17. examples/hello: New Timeline, then add and check events."

### I51. Many §5 guarantees have no test
- Sources: tests-22
- Category: test-gap
- Section: §7 (intro) against §5.2–5.9
- Plan text: "Each guarantee is tested at the lowest level that can observe it."
- Problem: Untested: (1) canColorText, tools.actions and the toolbar heights stay the same when a timeline opens; (2) typed bodies are created once and kept; (3) NoteBody's refusing defaults; (4) view-state isolation; (5) the replaced body drops its note, form and undo; (6) show() answers ok false when validEvents fails (validEvents is not in §7.2); (7) focus leaving an edit, the add form committing an open edit, and emptying both fields then Enter deleting the event; (8) printable keys on the add row, the Menu key, and Tab/Backtab and Down/Up between fields; (9) no status line for a single change; (10) tolerated variants are written canonically only on the next change; (11) a save never carries a type; (12) "No notebook here can hold timelines"; (13) the title's 256 limit; (14) C5.1's "pixel-identical" claim.
- Evidence: The §7.1–7.6 case lists, read against each quoted §5 sentence.
- Correction: Add one case per guarantee. (1) EditorKeys: those values are equal before and after setNote of a timeline. (2) The typedBodies Loader item is the same object for two timelines. (3) A bare tests/BareBody.qml: show answers ok false, restore returns "This note could not be shown", and request calls back ("", false). (4) A timeline view state restored on a Markdown note changes nothing. (5) After timeline → markdown, the hidden body holds no events, form or undo. (6) editorCases: 501 events, or a non-boolean checked, gives ok false. (7) and (8) One EditorKeys case for each behaviour. (9) A single check adds no status message. (10) A *-bullet body opens with no edited(), and its snapshot equals stored. (11) saves[0].options has no noteType. (12) A host case with only Sticky configured. (13) The title field holds at most 256 (see I7). (14) C5.1 checks round:false against the old formulas (radius Math.max(3, Math.round(side * 0.3)), border width Math.max(1.2, side / 9), the tick geometry). Otherwise remove the guarantee's text.

### I52. C1.1 ships docs promising read-only for unknown types two phases before the session does it
- Sources: critic-8
- Category: contradiction
- Section: §6 Phase 1 C1.1 steps 4 and 9; §5.2.2 "Note types"
- Plan text: "4. Workspace.qml editor plain: binding (:2837-2840) becomes transitional … 9. Docs … the properties rows and the "Note types" section without the timeline sentences (§5.2.2)"
- Problem: The C1.1 docs say "The load answer decides how the note opens" and "A note whose type … opens read-only as plain text". NoteSession applies opened() only from C2.1. In P1, a provider declaring ['kanban','markdown'] has its default-type notes opened as editable rich Markdown and rewritten on save, against the same commit's docs. This is the path the safety judge called a fatal flaw, and it breaks the rule that each commit ships its own docs and stays shippable.
- Evidence: judges.md:278. §6 C1.1 changes nothing in NoteSession. C2.1 step 5.
- Correction: Move the "Note types" paragraphs on reporting noteType, on the load answer deciding, and on unknown and undeclared types opening read-only (with their test expectations) from C1.1 step 9 to C2.1 step 8. P1 documents only noteTypes, the legacy shorthand, the compatibility paragraph and create options. Exit P1 adds: "A declaration whose first type this host does not know is honoured only from P2."

## Low

### I53. Escape table rows hold only for description lines; titles are written unescaped
- Sources: facts-17
- Category: false-claim
- Section: §5.6.2 Canonical form, escape table (used by §7.1 item 1)
- Plan text: "| `- not a list` | `\- not a list` |\n| `1. not ordered` | `1\. not ordered` |"
- Problem: These rows, and the `+` row, hold only for description lines. A title follows `- [ ] ` and is written unescaped, so a golden test that uses these strings as titles fails.
- Evidence: The prototype with the P0 fix writes `- [ ] - not a list`, `- [ ] 1. not ordered` and `- [ ] +` for titles, but `\- not a list`, `1\. not ordered` and `\+` for description lines.
- Correction: Label the three rows "(description line)" and add title rows: "`- not a list` (title) | `- not a list`", "`1. not ordered` (title) | `1. not ordered`", "`+` (title) | `+`".

### I54. The stated reason "bare keys could not be registry bindings" is wrong
- Sources: facts-18
- Category: false-claim
- Section: §5.8.5 Keyboard map, Shortcut context
- Plan text: "Bare keys could not be registry bindings anyway\n(`services/shortcuts/resolve.js:137-148`)."
- Problem: Application defaults do bind bare keys (Escape; Up, Down, Enter and Tab in search). refusal() refuses a bare key only below application priority. The design still stands, but its reason is wrong.
- Evidence: defaults.js:10-12 and :20. resolve.js:141.
- Correction: "Plugins and users cannot bind bare keys (resolve.js:141-143), so timeline keys stay local handling, as the TextEdit's own keys do."

### I55. A second `editorWritable` with a different formula
- Sources: facts-19, critic-17
- Category: contradiction
- Section: §5.9 WorkspaceActions `state`
- Plan text: "`state` gains `documentType: host.documentType` and `editorWritable: host.editorWritable`, where Workspace defines: … `readonly property bool editorWritable: session.writable`;"
- Problem: Workspace's command contextState already defines editorWritable as `!!root.currentPath && !editor.readOnly`, which commands' `requires` read. Two expressions for the same fact can drift.
- Evidence: Workspace.qml:2578-2582 (:2580). CommandRegistry.qml:22.
- Correction: Define `readonly property bool editorWritable: session.writable` once on Workspace, and have contextState read `editorWritable: root.editorWritable`.

### I56. P2's fake editor instruction names `conversions[i]`, but the tests call `conversions.shift()(…)`
- Sources: facts-20
- Category: other
- Section: §6 P2 C2.1 step 7 (tests/transitions.qml fake editor)
- Plan text: "Every existing case that read `conversions[i]` as a function calls `conversions[i].callback`."
- Problem: No case reads `conversions[i]`. A grep for it finds nothing, which would leave 24 calls broken once the fake pushes `{ document, callback }`.
- Evidence: 'conversions\[' has 0 matches; 'document.conversions.shift()(' has 24 (:439 … :1987).
- Correction: "Each `document.conversions.shift()(x, ok)` becomes `document.conversions.shift().callback(x, ok)` (24 sites, tests/transitions.qml:439-1987)."

### I57. Decisions D-4 and D-13 and the Limits row are assigned to the wrong phase or to none
- Sources: steps-11
- Category: docs-gap
- Section: §6 P2 step 8, P3 step 5, C6.4 (with §8)
- Plan text: "P2: "`docs/decisions.md` entries D-1, D-2 and D-3"; … C6.4: "D-11 to D-14"; §5.2.2: "`## Limits` (`:493`) gains the timeline row""
- Problem: D-4 is assigned to no phase. D-13 lands four phases after the code it describes (P2), against "updates its docs in the same commit". The Limits row is assigned to no phase.
- Evidence: §8's decisions table against §6. docs/release-process.md:36-37.
- Correction: P2 step 8: "D-1, D-2, D-3, D-4 and D-13". C6.4: "D-11, D-12 and D-14". P3 step 5 adds "docs/providers.md `## Limits` gains the timeline row (§5.2.2)".

### I58. runBodyAction is added twice, and the IPC helpers are documented before they exist and never specified
- Sources: steps-12, critic-14
- Category: contradiction
- Section: §6 C2.1 step 6, C5.3 step 6, C6.3; §5.4/§5.9; §8 docs/testing.md; Appendix A Workspace row
- Plan text: "C2.1: "add `documentType` and `editorWritable` properties and `runBodyAction(name)`"; C6.3: "Workspace `runBodyAction` and IPC helpers"; C5.3: "`docs/testing.md`: … and the IPC helpers"; Appendix A: "IPC `addEvent`/`toggleEvent` (P6)""
- Problem: runBodyAction is added in both P2 and P6. The IPC helpers are documented in P5 but created in P6, and §5 never specifies their arguments, effect, return value or behaviour when no writable timeline is open.
- Evidence: The quoted lines. docs/testing.md:111 (every root function is IPC-callable).
- Correction: Drop runBodyAction from C6.3, and move "and the IPC helpers" from C5.3 to C6.3's docs. Add to §5.4/§5.9: "function addEvent(title) → editor.bodyAction("addEvent", title): opens the add form with title typed in (empty opens it empty); returns editor.countText, or "" when no writable timeline is open. function toggleEvent(index) → editor.bodyAction("toggle", Number(index)); returns editor.countText, or "" when refused." act("addEvent", argument) prefills the title.

### I59. Exit P3 runs the 3000-model property test in both legs, but §7.1 runs it in the pure leg only
- Sources: steps-13
- Category: contradiction
- Section: §6 Exit P3
- Plan text: "`timeline_selftest.py` is green in both runners, with 0 failures in the 3000-model property test, both legs."
- Problem: §7.1 item 9 runs the golden body and 20 samples in the Qt leg.
- Evidence: §7.1 item 9.
- Correction: "timeline_selftest.py is green in both runners: 0 failures in the 3000-model pure property test and in the Qt leg (the golden body and 20 samples, §7.1 item 9)."

### I60. P4 misplaces record() and names the wrong rule for undeclared timelines
- Sources: steps-14
- Category: false-claim
- Section: §6 P4 steps 2 and 3
- Plan text: "Step 3: "`record()` fixtures (`tests/transitions.qml` `localCases`) emit 10 fields"; step 2: "opens read-only as text, because local does not declare `timeline` (the undeclared rule)""
- Problem: record() is in oneNoteCases, and an inline 7-field record also exists. In P4, `timeline` is not yet in notetypes.js, so the unknown-type rule applies, with a different reason.
- Evidence: tests/transitions.qml:1415, :1480, :1485. C1.1 step 1. §5.3 opened().
- Correction: Step 3: "the local listing fixtures in oneNoteCases() (tests/transitions.qml:1480 and :1485) emit 10 fields". Step 2: "(the unknown-type rule until C5.3 adds timeline to the table; the undeclared rule after)".

### I61. §7.3 item 16 is assigned to no step
- Sources: steps-16
- Category: missing-step
- Section: §6 (test assignment) vs §7.3 item 16
- Plan text: "§7.3 item 16: "`host.newNote(id, target, "timeline")` to a provider that does not declare it gives the status "…cannot hold timelines" and no `create` call.""
- Problem: No step carries item 16. It can pass only from C5.3 on, because before then noun("timeline") is "".
- Evidence: §5.3 noun(). C5.3 step 3.
- Correction: C6.1's tests: "§7.3 items 16 and 18–21".

### I62. No cursor rule after delete, cancel or empty Enter, and no scroll after an append
- Sources: ux-11
- Category: missing-step
- Section: §5.8.4 The form; §5.8.5 Keyboard map
- Plan text: "`Delete` | Delete the cursor event. …" / "Otherwise commit: one undo step, the event appended, the form cleared and **kept open**" / "Editing: the event gets back its text …" / "Adding, both fields empty: close the form."
- Problem: The plan names no cursor position after deleting a middle event, after Esc in an edit, or after Enter on an empty add form. It names no scroll after an append, so on a long timeline the new event is out of view.
- Evidence: §5.8.9 commit(next, cursor, status) needs a cursor. §5.8.2 shows the ListView scrolling on its own.
- Correction: "After Delete the cursor goes to the event that took its place, else the one above, else the add row. Esc in an edit puts the cursor on that event. Enter on an empty add form closes it with the cursor on the add row. After an append the list shows the new event (`list.positionViewAtIndex(events.length - 1, ListView.Contain)`) and the form keeps the keyboard."

### I63. The Menu key opens the event menu at the mouse pointer
- Sources: ux-12
- Category: ux
- Section: §5.8.5; §5.8.6
- Plan text: "`Menu` (the context-menu key) | Open the event's menu." / "`ui/RowMenu.qml` reused with a row-shaped object `{ index, menu: [...] }`"
- Problem: RowMenu opens only at the pointer, so the Menu key shows the menu wherever the mouse happens to be.
- Evidence: RowMenu.qml:25-28 `menu.popup()`.
- Correction: RowMenu gains `openAt(row, item)` → `menu.popup(item, 0, item.height)`. The Menu key uses it on the cursor row's delegate, right-click keeps `openFor`, and the header comment mentions both.

### I64. Three different placements of the empty state
- Sources: ux-13
- Category: contradiction
- Section: §5.8.2; §5.8.3
- Plan text: "AddArea (FocusScope) — the "Add new event" row, the empty state, or the add form" / "… followed by the empty state." / "**Empty state** … above the add row."
- Problem: The empty state is described as one of three alternatives, as below the row and as above it.
- Evidence: The three quoted sentences.
- Correction: In both sections: "The add area shows, top to bottom: the empty state (no events and no form), then the "Add new event" row or the form; when read-only, the empty state alone."

### I65. Event dates are an assumption that §3 never asks about
- Sources: ux-14
- Category: spec-fidelity
- Section: §2 (A9); §3
- Plan text: "Assumptions the plan makes (each one is visible in §3 where the user may decide otherwise)" / "A9 | Events have no dates in v1."
- Problem: No §3 row asks about dates, although §2 says every assumption appears there.
- Evidence: U1–U16 contain no date question.
- Correction: Add "U18 | Do events carry a date or time? | (a) no: order is yours; dates stay later work as an additive grammar (§10); (b) an optional date per event in v1 | (a) | Not requested; checking in order needs no dates."

### I66. Contract docs wording is wrong for invalid declarations, the id grammar and the tools row
- Sources: contract-12
- Category: docs-gap
- Section: §5.2.2 (property rows, compatibility, "Note types")
- Plan text: "Ignored when `noteTypes` is given … a provider without `noteTypes` works as before … An id is lowercase letters, digits and hyphens, at most 32 characters"
- Problem: `markdown` is ignored only when `noteTypes` is valid. The grammar requires a leading letter, so "2do" is refused. The tools row still says "(when `markdown`)".
- Evidence: §5.2.1. ID_PATTERN `^(?:[a-z][a-z0-9-]{0,31}|…)$`. docs/providers.md:54.
- Correction: "Ignored when `noteTypes` is valid"; "a provider without a valid `noteTypes` works as before"; "An id starts with a lowercase letter, followed by lowercase letters, digits and hyphens, 32 characters at most"; tools row: "omitted = all (for a Markdown note)".

### I67. Unknown types: an empty noun in refusals, and Ctrl+N does not make the documented default
- Sources: contract-13, critic-11
- Category: contradiction
- Section: §5.9 `newNoteDestination` and `newNote` step 3; §5.2.2 "Note types"; §6 C1.1 step 5
- Plan text: "refusal: p.name + ": this notebook cannot hold " + NoteTypes.noun(noteType)" / "A note you report without a type is of your default type, and Ctrl+N makes one." / "`create` always receives `{ noteType: Capabilities.creationType(Capabilities.of(p), undefined) }`, the provider's first known type."
- Problem: noun() is "" for an unknown type, so the status reads "Hello: this notebook cannot hold " (and "No notebook here can hold "). For ['kanban','markdown'], Ctrl+N asks for markdown, not the default the docs promise.
- Evidence: §5.3 noun(). C1.1 step 5. §5.2.1.
- Correction: When `!NoteTypes.known(noteType)`, both refusals read "<name>: this version of Note Note cannot make that kind of note" (or the same without a provider), with a §7.3 host case. Docs: "A note you report without a type is of your default type. Ctrl+N asks create() for your default type, or, when this version does not know it, the first type you declare that it knows."

### I68. A later type chooser must not retire the 1.1.0 contract
- Sources: contract-14
- Category: contract
- Section: §10 "A type chooser"; §5.9 "Later (third creatable type)"
- Plan text: "It replaces per-type actions and per-type footer rows."
- Problem: The `newTimeline` shortcut and the three-argument host.newNote are documented contract from 1.1.0, so replacing them later would be a non-additive change.
- Evidence: docs/technical-requirements.md: "change it additively, never silently."
- Correction: "It is added beside them: the `newTimeline` footer shortcut and workspace action and `host.newNote(id, target, noteType)` stay supported for the rest of 1.x."

### I69. The fake editor's shown is synchronous, so case 13's "slow shown" cannot be built
- Sources: tests-23
- Category: test-gap
- Section: §6 C2.1 item 7; §7.3 case 13
- Plan text: "`setNote(document, shown)`, which records … and calls `shown({ ok: true, fallback: fallback })` / 13. A(markdown) → B(timeline, slow `shown`) → A"
- Problem: The fake always calls shown at once, so a slow answer cannot be produced.
- Evidence: tests/transitions.qml:390-396.
- Correction: The fake gains `holdShown: false` and `shownQueue: []`. While holdShown is true, setNote queues shown. Case 13 answers B's queued shown after A is reselected and checks that A is ready and unchanged.

### I70. The limits pin would fail on MAX_UNDO, and the creatable-types pin never becomes equality
- Sources: tests-25
- Category: test-gap
- Section: §6 C5.3 item 5; C4.1 item 3; §7.6
- Plan text: "`test_timeline_limits_agree` (`TimelineModel.js` `var MAX_*` vs `timeline.MAX_*`) / `test_local_creatable_types_agree`: … a subset … and equal from P6 on."
- Problem: MAX_UNDO and MAX_BYTES have no counterpart on the other side. No P6 step switches the creatable-types pin to equality.
- Evidence: C5.3 item 1. C3.1 item 1. C6.1.
- Correction: Compare exactly MAX_EVENTS, MAX_TITLE, MAX_DESCRIPTION and MAX_LINES. C6.1 adds: "test_local_creatable_types_agree asserts equality."

### I71. The edge strings live only in a scratchpad, the inline-HTML sample is refused as bold, and the patch property test is unseeded
- Sources: tests-26
- Category: test-gap
- Section: §7.1 items 3 and 5; §7.2 patch
- Plan text: "3. **Edge lines.** The 55 strings from the planner's prototype … / 5. Refusals … inline HTML … / applying the ops to a copy reproduces `after` for 500 random pairs"
- Problem: The 55 strings exist only in a session scratchpad. `<b>b</b>` is refused as "bold text", not "HTML". Math.random cannot be seeded, so a failure cannot be reproduced.
- Evidence: codec_check.py EDGES (:172-176). qthtml/selftest.py:243 uses <kbd>. A seeded LCG probe ran 20000 pairs with 0 mismatches.
- Correction: Inline all 55 strings in §7.1 item 3. Name each refusal's input, using '- [ ] a <kbd>b</kbd>' for inline HTML. §7.2 uses "500 pairs from a seeded generator in NoteTypeChecks.js (a 31-bit LCG, seed 7), with the failing pair in the check's detail".

### I72. Open questions from the research brief are left unanswered
- Sources: critic-10
- Category: missing-step
- Section: Whole plan vs maps/brief.md; §7.7 item 1; §8 docs/security.md
- Plan text: "1. `Ctrl+Shift+T` in a local notebook tab with no note open creates "Untitled" in **that** tab, with the title focused."
- Problem: Five questions are neither answered, deferred nor listed: whether title focus lands during the pending load (the title is enabled only when not read-only); whether hasTitle becomes per type; that the security checklist points at a README "Limits" section that does not exist; Co-Authored-By trailers; and whether a type may scope tools to itself.
- Evidence: brief.md:116, :24, :359, :358, :325. NoteEditor.qml:1895. security.md:319-320. README.md has no Limits heading. release-process.md:9-11.
- Correction: Add an "Open questions from the research" list: (1) host case 25, in which the title has active focus after the load lands; (2) hasTitle stays per provider; (3) the security checklist line becomes 'docs/technical-requirements.md "Limits" and docs/providers.md "Limits"'; (4) no co-author trailers (release-process.md:9-11); (5) tools stay Markdown-only (D-13), and type-scoped tools wait for the plugin kind (D-2).

### I73. Local's save answer would carry noteType, against the documented save shape
- Sources: critic-12
- Category: contract
- Section: §5.11.1 operations.py save; §5.12 step 7; §5.2.2 save()
- Plan text: "the answer adds `"noteType": "" if kind == notefile.UNREADABLE else kind` / … A save never carries a type."
- Problem: mutate() passes operations.py's answer straight to the host's callback, so the host's save answer carries noteType, which contradicts the documented shape. A save never changes the type, so the field is redundant.
- Evidence: local Provider.qml:517-531. judges.md:477.
- Correction: operations.py save adds only progress. The commit is `Object.assign({}, note, { title: title.trim(), preview: result.preview, size: result.bytes, version: result.version, progress: result.progress || null })`. §5.12 step 7 drops noteType.

### I74. Two risks the safety judge required are missing
- Sources: critic-15
- Category: docs-gap
- Section: §9; D20
- Plan text: "D20 | Risks with mitigations; 16 user decisions | §9, §3 | all three"
- Problem: Missing from R1–R29: misfiling when typed creation bypasses the footer action, and a collision with the Ctrl+Alt+N override example.
- Evidence: judges.md:272.
- Correction: Add "R30 | Typed creation bypasses the provider's footer action and files a timeline in the last notebook (createTargetFor(""), local Provider.qml:265). | Typed creation runs activateFooterShortcut(footerShortcut) first and uses a type-filtered destination only when the open tab has no such row; §7.3 case 20 pins it." and "R31 | A Ctrl+Alt+* default collides with the override example in docs/commands.md:145. | Ctrl+Shift+T; the example and its fixtures stay as they are; ShortcutChecks pins the binding."

### I75. View state uses a per-type `timeline: true` tag that every body must know
- Sources: critic-16
- Category: other
- Section: §5.4 documentViewState / restoreDocumentViewState; §5.8.9 viewState
- Plan text: "`restoreDocumentViewState(state)` ignores a state that … carries `timeline: true`. A timeline's state is `{ timeline: true, cursor, scroll }`"
- Problem: The document body must know the timeline's tag, and each future type adds another. This is the per-type switch the fit judge faulted, moved to a new place.
- Evidence: judges.md:44. The user's request: "we will have other note types in the future".
- Correction: The pane's viewState() returns `{ documentType: root.documentType, state: root.body.viewState() }`, and restoreViewState(s) restores only when `s && s.documentType === root.documentType`. Bodies' states carry no tag, and the timeline's state is { cursor, scroll }.

### I76. The opened() comment describes its return value as its argument
- Sources: critic-19
- Category: other
- Section: §5.3 notetypes.js opened()
- Plan text: "// How a loaded note opens (NoteSession.load). `capabilities` is Capabilities.of(provider),\n// `answer` the provider's load answer: { documentType, readOnly, reason }."
- Problem: { documentType, readOnly, reason } is what opened() returns, while it reads `noteType` from its argument.
- Evidence: The body reads answer.noteType and returns { documentType, readOnly, reason }.
- Correction: "// How a loaded note opens (NoteSession.load): { documentType, readOnly, reason }.\n// `capabilities` is Capabilities.of(provider); `answer` is the provider's load answer, whose `noteType` is read."
