# Code style

- No spaghetti code, no hacky code, no workarounds. If a proper fix requires touching more code, do the proper fix.
- Write clean code: easy to read, easy to understand, easy to change.
- Every `if`, `else`, `for`, `while`, etc. must use braces `{ }`, even when the body is a single line.
- Never put an `if`, `else`, `for` or `while` and its body on the same line. The body goes on its own lines between the braces, one statement per line — `if (x) { a() }` is not allowed, and neither is a one-line function body that holds one.

# Code quality comes first

- Code quality is this project's first principle, above any fix or feature. A bug stays unfixed rather than be fixed with a workaround, hacky code, or anything else that lowers the quality of the code.
- When a change would need a workaround or a hack, or would otherwise lower the code's quality, stop and ask before going on: say what breaks this rule and what the alternatives are. Never trade quality away silently.

# Do not over-design

- Write the plain thing where it is used. A few repeated lines are better than an indirection made only to avoid them: an abstraction has to remove real complexity, not a little repetition.
- Example: each provider writes its note menu out in full, so the menu says what it holds:

  ```qml
  readonly property var noteMenu: [{ id: "delete", title: "Delete", icon: "󰆴", command: "deleteNote" }]
  ```

  Not served from the host to save the five copies — `readonly property var noteMenu: root.services ? [root.services.menus.deleteNote] : []`. That added a host service, a null guard in every provider and a copy in every test double, and the menu no longer said what it holds.
