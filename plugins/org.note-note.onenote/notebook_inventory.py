"""Discover notebooks and their direct and nested section relationships.

Graph's notebook relationships retain the location of shared content.
Personal shared notebooks missing from the main list are resolved through
recent notebook links and OneDrive, then verified with the OneNote API.
"""
import base64
import re
import urllib.parse


ROOT_PATH = re.compile(r"^/v1\.0/(?:me|users/[^/]+|users\('[^']+'\)|groups/[^/]+|sites/[^/]+)/onenote/")
SECTION_FIELDS = "id,displayName,lastModifiedDateTime,pagesUrl,self"
NOTEBOOK_EXPAND = "sections($select=" + SECTION_FIELDS + "),sectionGroups($expand=sections)"
RECENT_NOTEBOOKS = "/me/onenote/notebooks/getRecentNotebooks(includePersonalNotebooks=true)"


def notebook_links(notebook):
    """Normalize the web and client variants without guessing ownership."""
    result = set()
    for link in notebook.get("links", {}).values():
        url = link.get("href", "")
        if url.startswith("onenote:"):
            url = url[len("onenote:"):]
        try:
            parsed = urllib.parse.urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme == "https" and parsed.hostname and not parsed.username:
            result.add(urllib.parse.urlunsplit(parsed._replace(fragment="")))
    return result


def share_item_url(url):
    share = "u!" + base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    return "/shares/" + share + "/driveItem"


def personal_notebook_id(item):
    """Derive a candidate ID from a personal OneDrive notebook package.

    The candidate must still be verified with OneNote before it is listed.
    """
    item = item.get("remoteItem") or item
    item_id = item.get("id", "")
    if (item.get("package", {}).get("type") != "oneNote"
            or not re.fullmatch(r"[0-9A-Fa-f]{1,16}![A-Za-z0-9]+", item_id)):
        return ""
    return "0-" + item_id


class DiscoveryError(Exception):
    def __init__(self, status, response):
        super().__init__("Could not list notebooks (HTTP %s)" % status)
        self.status = status
        self.response = response


def graph_url(url):
    """Accept only Graph OneNote relationship URLs before sending a token."""
    if not isinstance(url, str):
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    if (parsed.scheme != "https" or parsed.netloc != "graph.microsoft.com"
            or parsed.fragment or not ROOT_PATH.match(parsed.path)):
        return ""
    decoded = urllib.parse.unquote(parsed.path)
    if any(part in (".", "..") for part in decoded.split("/")):
        return ""
    return url


def section_record(section, notebook=None):
    parent = notebook or section.get("parentNotebook") or {}
    result = {"id": section["id"], "name": section.get("displayName", ""),
              "notebook": parent.get("displayName", ""), "notebookId": parent.get("id", ""),
              "modified": section.get("lastModifiedDateTime", "")}
    for field in ("self", "pagesUrl"):
        url = graph_url(section.get(field))
        if url:
            result[field] = url
    if "pagesUrl" not in result and "self" in result:
        result["pagesUrl"] = result["self"] + "/pages"
    return result


class Discovery:
    """A serializable traversal: pending relationships survive budget pauses.

    Local tasks unpack expanded relationships. Network tasks perform one
    request each and remain pending until that request has returned.
    """

    def __init__(self, limit, progress=None, cached_notebooks=()):
        self.limit = limit
        url = ("/me/onenote/notebooks?$select=id,displayName,userRole,self,sectionsUrl,sectionGroupsUrl,links"
               "&$expand=" + NOTEBOOK_EXPAND + "&$top=100")
        self.state = progress or {
            "tasks": [{"kind": "notebooks", "url": url, "label": "Notebooks", "required": True},
                      {"kind": "recent", "url": RECENT_NOTEBOOKS, "label": "Recent notebooks"}],
            "notebooks": [], "sections": [], "warnings": [],
            "links": [], "groups": [], "visited": [], "recentChecks": 0,
        }
        # Recent links are history, not evidence that a notebook still exists.
        # Verify cached notebooks by ID as well, so an unavailable history link
        # cannot hide a working shared notebook or keep a removed one forever.
        if not self.state.get("cachedQueued"):
            if cached_notebooks:
                self.state["tasks"].append({"kind": "cached", "notebooks": list(cached_notebooks)})
            self.state["cachedQueued"] = True
        self.book_ids = {book["id"].casefold() for book in self.state["notebooks"]}
        self.checked_book_ids = set(self.state.get("checkedNotebooks", []))
        self.section_ids = {section["id"] for section in self.state["sections"]}
        self.group_ids = set(self.state["groups"])
        self.links = set(self.state["links"])
        self.visited = set(self.state["visited"])

    def prepend(self, tasks):
        self.state["tasks"][0:0] = tasks

    def warn(self, label, message):
        warning = label + ": " + message
        if warning not in self.state["warnings"]:
            self.state["warnings"].append(warning)

    def continuation(self, task, response):
        next_url = response.get("@odata.nextLink")
        if not next_url:
            return []
        endpoint = graph_url(next_url)
        if not endpoint:
            self.warn(task["label"], "Microsoft returned an invalid listing link")
        elif endpoint in self.visited:
            self.warn(task["label"], "Microsoft returned a repeated listing link")
        else:
            return [dict(task, url=endpoint)]
        return []

    def relationships(self, parent, notebook):
        return [{"kind": "relationship", "field": field, "parent": parent,
                 "notebook": notebook, "label": notebook.get("displayName", "Notebook")}
                for field in ("sections", "sectionGroups")]

    def add_notebook(self, notebook):
        key = notebook["id"].casefold()
        self.links.update(notebook_links(notebook))
        if key in self.book_ids:
            return []
        if len(self.book_ids) >= self.limit:
            self.warn("Notebooks", "the notebook listing limit was reached")
            return []
        self.book_ids.add(key)
        book = {"id": notebook["id"], "name": notebook.get("displayName", "Notebook"),
                "userRole": notebook.get("userRole", "")}
        endpoint = graph_url(notebook.get("self"))
        if endpoint:
            book["self"] = endpoint
        self.state["notebooks"].append(book)
        return self.relationships(notebook, {"id": book["id"], "displayName": book["name"]})

    def sections(self, values, notebook):
        for value in values:
            if value["id"] in self.section_ids:
                continue
            if len(self.section_ids) >= self.limit:
                self.warn("Sections", "the section listing limit was reached")
                return
            self.section_ids.add(value["id"])
            self.state["sections"].append(section_record(value, notebook))

    def groups(self, values, task):
        tasks = []
        for group in values:
            if group["id"] in self.group_ids:
                continue
            if len(self.group_ids) >= self.limit:
                self.warn(task["label"], "the section group listing limit was reached")
                break
            self.group_ids.add(group["id"])
            tasks.extend(self.relationships(group, task["notebook"]))
        return tasks

    def relationship(self, task):
        parent, field = task["parent"], task["field"]
        values = parent.get(field)
        follow = []
        if isinstance(values, list):
            if field == "sections":
                self.sections(values, task["notebook"])
            else:
                follow = self.groups(values, task)
            url = parent.get(field + "@odata.nextLink")
        else:
            url = parent.get(field + "Url")
        if url:
            endpoint = graph_url(url)
            if endpoint:
                follow.append({"kind": field, "url": endpoint, "label": task["label"],
                               "notebook": task["notebook"]})
            else:
                self.warn(task["label"], "Microsoft returned an invalid relationship link")
        self.prepend(follow)

    def recent(self, values):
        tasks = []
        for notebook in values:
            links = notebook_links(notebook)
            if self.links.intersection(links):
                continue
            self.links.update(links)
            personal = sorted(link for link in links
                              if urllib.parse.urlsplit(link).netloc == "d.docs.live.net")
            if not personal:
                continue
            if self.state["recentChecks"] >= self.limit:
                self.warn("Recent notebooks", "the recent notebook resolution limit was reached")
                break
            self.state["recentChecks"] += 1
            tasks.append({"kind": "drive", "url": share_item_url(personal[0]),
                          "label": notebook.get("displayName", "Notebook")})
        return tasks

    def cached(self, notebooks):
        tasks = []
        for notebook in notebooks:
            notebook_id = notebook["id"]
            if notebook_id.casefold() in self.book_ids or notebook_id.casefold() in self.checked_book_ids:
                continue
            endpoint = graph_url(notebook.get("self"))
            if not endpoint:
                endpoint = "/me/onenote/notebooks/" + urllib.parse.quote(notebook_id, safe="")
            tasks.append({"kind": "notebook", "url": endpoint + "?$expand=" + NOTEBOOK_EXPAND,
                          "id": notebook_id, "label": notebook.get("name", "Notebook")})
        return tasks

    def drive(self, response, task):
        notebook_id = personal_notebook_id(response)
        if not notebook_id:
            self.warn(task["label"], "the recent link did not resolve to a personal OneNote notebook")
            return []
        if notebook_id.casefold() in self.book_ids:
            return []
        path = "/me/onenote/notebooks/" + urllib.parse.quote(notebook_id, safe="")
        return [{"kind": "notebook", "url": path + "?$expand=" + NOTEBOOK_EXPAND,
                 "id": notebook_id, "label": task["label"]}]

    def response(self, task, response):
        kind = task["kind"]
        follow = []
        if kind == "notebooks":
            for notebook in response.get("value", []):
                follow.extend(self.add_notebook(notebook))
        elif kind == "sections":
            self.sections(response.get("value", []), task["notebook"])
        elif kind == "sectionGroups":
            follow = self.groups(response.get("value", []), task)
        elif kind == "recent":
            follow = self.recent(response.get("value", []))
        elif kind == "drive":
            follow = self.drive(response, task)
        elif kind == "notebook":
            if response.get("id", "").casefold() != task["id"].casefold():
                self.warn(task["label"], "Microsoft returned a different notebook for the recent link")
            else:
                follow = self.add_notebook(response)
        if kind not in ("drive", "notebook"):
            follow.extend(self.continuation(task, response))
        self.prepend(follow)

    def step(self, graph, max_bytes):
        task = self.state["tasks"][0]
        if task["kind"] in ("relationship", "sections", "sectionGroups") and len(self.section_ids) >= self.limit:
            self.state["tasks"].pop(0)
            self.warn("Sections", "the section listing limit was reached")
            return
        if task["kind"] in ("notebooks", "recent", "drive", "notebook") and len(self.book_ids) >= self.limit:
            self.state["tasks"].pop(0)
            self.warn("Notebooks", "the notebook listing limit was reached")
            return
        if task["kind"] == "relationship":
            self.state["tasks"].pop(0)
            self.relationship(task)
            return
        if task["kind"] == "cached":
            self.state["tasks"].pop(0)
            self.prepend(self.cached(task["notebooks"]))
            return
        url = task["url"]
        if not url.startswith("/") and not graph_url(url):
            self.state["tasks"].pop(0)
            self.warn(task["label"], "Microsoft returned an invalid listing link")
            return
        if url in self.visited:
            self.state["tasks"].pop(0)
            self.warn(task["label"], "Microsoft returned a repeated listing link")
            return
        if len(self.visited) >= self.limit * 4:
            self.warn("Notebooks", "the relationship request limit was reached")
            self.state["tasks"] = []
            return
        # Keep the task until the request returns. A Deferred or network
        # failure therefore resumes this URL, including share verification.
        status, response = graph("GET", url, max_bytes=max_bytes)
        if status != 200 and task.get("required"):
            raise DiscoveryError(status, response)
        self.state["tasks"].pop(0)
        self.visited.add(url)
        if task["kind"] == "notebook":
            self.checked_book_ids.add(task["id"].casefold())
        if (task["kind"] == "drive" and status in (403, 404, 410)
                or task["kind"] == "notebook" and status in (404, 410)):
            # A recent link must resolve and verify before it is a notebook.
            # OneDrive also reports deleted links as 403. Known notebooks get
            # a separate ID lookup above; genuine permission failures there
            # still warn and preserve the cached inventory.
            return
        if status != 200:
            self.warn(task["label"], "could not retrieve the list (HTTP %s)" % status)
        else:
            self.response(task, response)

    def progress(self):
        self.state.update(links=sorted(self.links), groups=sorted(self.group_ids), visited=sorted(self.visited),
                          checkedNotebooks=sorted(self.checked_book_ids))
        return self.state


def discover(graph, limit, max_bytes, progress=None, checkpoint=None, cached_notebooks=()):
    """List notebooks and walk their direct and nested section relationships."""
    discovery = Discovery(limit, progress, cached_notebooks)
    while discovery.state["tasks"]:
        if checkpoint and "url" in discovery.state["tasks"][0]:
            checkpoint(discovery.progress())
        discovery.step(graph, max_bytes)
    return discovery.state["notebooks"], discovery.state["sections"], discovery.state["warnings"]
