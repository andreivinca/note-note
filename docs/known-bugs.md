# Known bugs

Bugs we know about and have not fixed, usually because the fault is outside
Note Note (Qt, a provider's API) and any fix on our side would be a
workaround. Each entry says what the user sees, why it happens, how to
reproduce it, and what would fix it. Remove an entry when it is fixed, and
say in the commit which Qt or provider version fixed it.

---

## Table text turns darker after editing below the table

**Status:** open, upstream (Qt). Seen on Qt 6.11.2; the code is unchanged on
the Qt `dev` branch as of 2026-09-28. Not yet reported at bugreports.qt.io.

**What the user sees.** In a note with a table, selecting, deselecting or
typing in the text *below* the table (a checklist, say) makes the table's
text a shade darker and slightly bolder. A later edit can bring it back to
normal, so the table seems to flicker between two weights as you work. The
note's content is never affected; only how the table is painted changes.

**Why.** The table's text is drawn twice, one copy exactly on top of the
other. The anti-aliased edges add up, so the glyphs look heavier. Measured
on the test note, a deselect below the table raises the table's total glyph
alpha by about 23%, and plain paragraphs never change.

The fault is in `QQuickTextEdit::updatePaintNode`
(`src/quick/items/qquicktextedit.cpp`, around line 2517 in 6.11.2). On a
partial update Qt removes only the text nodes from the first dirty one
onward, so the table's nodes, which sit before the edit, are kept. It then
walks every frame again, and for every child frame (every table) it resets
the dirty position:

```cpp
if (frameCount > 0)
    firstDirtyPos = 0;
```

So every table cell block is laid out into a *new* node as well, next to the
node that was kept. Selection changes take the same path
(`updateSelection` → `markDirtyNodesForRange`), which is why only selecting
text is enough to trigger it. It does not depend on nesting, the render type
(`QtRendering`, `NativeRendering` and `CurveRendering` all show it) or our
editor code: a bare `TextEdit` reproduces it.

**Reproduce.** Save as `repro.qml` and run `qml6 repro.qml`. Watch the
table: it turns darker at the deselect step, and the text below it never
does.

```qml
import QtQuick
Window {
  width: 500; height: 400; visible: true; color: "white"
  TextEdit {
    id: area; anchors.fill: parent; anchors.margins: 10
    textFormat: TextEdit.RichText; font.pixelSize: 15
    text: "<table border=1><tr><td>Mon</td><td>Tue</td><td>Wed</td></tr>"
        + "<tr><td>1</td><td>2</td><td>3</td></tr></table>"
        + "<p>&nbsp;</p><ul><li>first item</li><li>second item</li></ul>"
  }
  property int step: 0
  Timer {
    interval: 1000; repeat: true; running: true
    onTriggered: {
      if (step === 0) {
        area.select(area.length - 6, area.length - 1)   // select below the table
      } else if (step === 1) {
        area.deselect()                                  // table text now drawn twice
      } else {
        stop()
      }
      step++
    }
  }
}
```

To measure it rather than eyeball it, grab the item with `grabToImage`
before and after each step and compare the summed alpha of the table
region. The grab has a transparent background, so compare alpha, not RGB.

**What would fix it.**

- *Upstream (the proper fix):* in `updatePaintNode`, a child frame's blocks
  before the first dirty position must be skipped the way the root frame's
  are, or the kept nodes for that frame must be removed before it is
  re-laid. Report it with the repro above.
- *In Note Note (a workaround, not done):* force a full node rebuild after
  every edit or selection change in a note that holds a table, for example by
  marking the document dirty from position 0. It costs a full scene-graph
  rebuild per keystroke and hides the bug rather than fixing it, so we are
  waiting for Qt instead.
