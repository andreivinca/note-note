.pragma library

// Application defaults. Labels and dispatch both use the parsed keys.
var ACTIONS = [
  { id: "commandPalette", keys: ["Ctrl+Shift+P"], context: "application", group: "Getting around", description: "Open the command palette" },
  { id: "search", keys: ["Ctrl+K", "Ctrl+L"], context: "notes", group: "Getting around", description: "Search your notes" },
  { id: "nextSearch", keys: ["Down"], context: "search", repeatable: true, group: "Search", description: "The next search result" },
  { id: "previousSearch", keys: ["Up"], context: "search", repeatable: true, group: "Search", description: "The previous search result" },
  { id: "acceptSearch", keys: ["Enter", "NumEnter", "Tab"], context: "search", group: "Search", description: "Open the search result" },
  { id: "previousNote", keys: ["Ctrl+Up"], context: "notes", repeatable: true, group: "Getting around", description: "The note above" },
  { id: "nextNote", keys: ["Ctrl+Down", "Ctrl+J"], context: "notes", repeatable: true, group: "Getting around", description: "The note below" },
  { id: "nextTab", keys: ["Ctrl+Tab"], context: "notes", repeatable: true, group: "Getting around", description: "The next notebook" },
  { id: "previousTab", keys: ["Ctrl+Shift+Tab"], context: "notes", repeatable: true, group: "Getting around", description: "The notebook before it" },
  { id: "openTree", keys: ["Ctrl+Right"], context: "notes", repeatable: true, group: "Getting around", description: "Open the notebook under the cursor" },
  { id: "closeTree", keys: ["Ctrl+Left"], context: "notes", repeatable: true, group: "Getting around", description: "Fold the notebook under the cursor" },
  { id: "toggleList", workspaceAction: true, keys: ["Ctrl+E"], context: "notes", group: "Getting around", description: "Show or hide the sidebar" },
  { id: "back", keys: ["Escape"], context: "notes", group: "Getting around", description: "Clear the search or put the window away" },
  { id: "newNote", workspaceAction: true, keys: ["Ctrl+N"], context: "notes", group: "Notes", description: "A new note in the open notebook" },
  { id: "newNotebook", workspaceAction: true, keys: ["Ctrl+Shift+N"], context: "notes", group: "Notes", description: "A new notebook" },
  { id: "deleteNote", workspaceAction: true, keys: ["Ctrl+D"], context: "notes", group: "Notes", description: "Delete the note you are reading" },
  { id: "openSettings", workspaceAction: true, keys: [], context: "application", group: "Application", description: "Open Settings" },
  { id: "savePage", keys: ["Ctrl+S"], context: "page", group: "Settings", description: "Save settings" },
  { id: "paste", keys: ["Ctrl+V"], context: "editor", protected: true, group: "Editing", description: "Paste text or an image" },
  { id: "pastePlain", keys: ["Ctrl+Shift+V"], context: "editor", protected: true, group: "Editing", description: "Paste plain text" }
]

for (var tab = 1; tab <= 9; tab++) {
  ACTIONS.push({ id: "selectTab" + tab, action: "selectTab", parameters: { tab: tab }, keys: ["Alt+" + tab],
    context: "notes", group: "Getting around", description: "Open notebook " + tab })
}
