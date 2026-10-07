# OneNote blank lines

OneNote stores a blank line as an outline element holding one empty rich-text
object. OneNote clients leave its text empty or leave the text property out; a
`<br/>` written through Graph becomes a single line-break character (`\x0b`).
Graph exports each as a bare `<br/>` without a generated ID, and
[Graph's update API](https://learn.microsoft.com/en-us/graph/onenote-update-page)
targets elements only by ID. The page's absolutely positioned outline `div`
cannot be replaced either. No Graph command can therefore remove a blank line
between two blocks, or turn one into text.

## Removal

The save planner (`onenote_patch.py`) names each run of consecutive breaks by
the generated IDs of the siblings around it, with the run's length and the
positions to remove. Breaks at the start or end of a page stay in OneNote, as
before; the editor does not show them.

OneNote's web client deletes a blank line by writing a revision of the page
whose outline no longer lists that element. `blank_lines.py` does the same
through the [web revision service](onenote-page-order.md#writing-and-consent):

1. Read the section, and join the page's public client ID to its page cell.
   Older sections list one page's metadata more than once; each cell joins
   the next distinct page.
2. Read the page cell and confirm its own page metadata names that page.
3. Resolve each neighbour's generated ID `tag:{guid}{n}` to the object
   `guid|n`: an element, or the content of exactly one element.
4. Require both neighbours under one parent, with exactly the run's number of
   elements between them, each holding only blank text (or none, and no
   ASCII text) and no child elements.
   A `<br/>` beside a list can be the text of the element the list hangs
   under; that element is not blank, and the save keeps the draft.
5. Write one revision of the changed parents, conditional on the page
   revision just read, and read the page back to confirm.

The removal runs before the save's Graph commands, which never target blank
lines. If a later step fails, the next save plans against the page without
them. Every failure keeps the draft.

## Availability

Removal has the same terms as page ordering: a personal notebook the account
owns, and the optional OneDrive write permission (**Enable page ordering…**).
Elsewhere the save keeps the draft and asks for the blank lines to be removed
in OneNote.

## Verification on 2026-10-07

- Note Note's own create and save paths wrote `<br/>`; Graph returned both
  without IDs, and the planner could not delete them.
- A revision listing the outline without that element removed the blank line;
  Graph showed the change on the next read. The outline and every paragraph
  kept their IDs, and an untouched blank line remained.
- `write_page` then removed another blank line end to end.
- A page created by OneNote in 2025 stored its blank line with empty text, in
  a section whose page groups list each page's metadata twice. A read-only
  dry run joined its cell and outline. Another blank line on that page had
  no text property at all; removing it failed until that counted as blank.
