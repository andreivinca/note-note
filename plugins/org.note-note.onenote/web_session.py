"""App-authenticated access to OneNote's web revision service.

This is an undocumented Microsoft interface, not a Graph API. It writes what
Graph cannot: page order (page_order.py) and blank-line removal
(blank_lines.py), both changing the objects revision_objects.py reads.
Credentials are minted through Graph's driveItem preview and live only in
this process. No browser cookies, HAR files or account-specific identifiers
are needed. See docs/onenote-page-order.md for the compatibility boundary.
"""
import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import msgraph
import provider_io
import ratelimit

NIL = "00000000-0000-0000-0000-000000000000|0"
# The web client's unknown-root sentinel, resolved by the server on reads.
UNKNOWN_ROOT = "40c4a0be-3ff1-49c7-b169-ba9d74e0724c|1"
ENDPOINT = "https://onenote.officeapps.live.com/o/OneNote.ashx"
PERSONAL_ITEM = re.compile(r"0-([0-9A-Fa-f]{16}![0-9]+)\Z")
EDITOR_ROLES = ("owner", "contributor")
MAX_BODY = 16 * 1024 * 1024
MAX_SECONDS = 120
RATE_KEY = "onenote-web-order"
RATE_WINDOWS = [(60, 40), (3600, 200)]


class WebError(msgraph.GraphError):
    """An operation that must settle visibly, without automatic job replay."""


def writable_notebook(notebook):
    """Whether the service can write this notebook's sections.

    Their files live in the owner's personal OneDrive, which the account
    reaches when it owns the notebook or may edit it. Provider.qml's
    pageOrderingNotebook() offers drags on the same terms.
    """
    return (str(notebook.get("userRole", "")).lower() in EDITOR_ROLES
            and bool(PERSONAL_ITEM.fullmatch(str(notebook.get("id", "")))))


def write_granted():
    """Whether the sign-in holds the Files.ReadWrite the service needs. One
    made before the app asked for it does not, and Provider.qml asks to sign
    in again."""
    msgraph.access_token()
    token = msgraph.signed_in(msgraph.config()[0]) or {}
    return "Files.ReadWrite" in token.get("scope", "").split()


def personal_item(identifier):
    match = PERSONAL_ITEM.fullmatch(str(identifier))
    if not match:
        raise WebError("OneNote's revision service reaches only sections of personal notebooks")
    return match[1]


def preview_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = (parsed.scheme == "https" and parsed.hostname == "my.microsoftpersonalcontent.com"
                 and not parsed.username and not parsed.password and parsed.port in (None, 443)
                 and re.fullmatch(
                     r"/personal/[0-9a-fA-F]{16}/_layouts/15/embed\.aspx", parsed.path))
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise WebError("Microsoft returned an unsupported notebook preview URL")
    return urllib.parse.urlunsplit(parsed._replace(fragment=""))


def frame_info(raw, item_id):
    text = raw.decode("utf-8", errors="replace")
    match = re.search(r"\bvar\s+g_fileInfo\s*=\s*", text)
    if not match:
        raise WebError("Microsoft's notebook preview no longer provides revision authorization")
    try:
        info, _ = json.JSONDecoder().raw_decode(text, match.end())
        source = info["wopiSrc"]
        token = info["wopiTokenAppAndUser"]
        ttl = int(info["wopiTokenAppAndUserTtl"])
        parsed = urllib.parse.urlsplit(source)
        expected = "/personal/%s/_vti_bin/wopi.ashx/files/%s" % (item_id.split("!", 1)[0], item_id)
        valid = (parsed.scheme == "https" and parsed.hostname == "my.microsoftpersonalcontent.com"
                 and not parsed.username and not parsed.password and parsed.port in (None, 443)
                 and not parsed.query and not parsed.fragment
                 and urllib.parse.unquote(parsed.path).casefold() == expected.casefold()
                 and isinstance(token, str) and 0 < len(token) <= 65536
                 and ttl > time.time() * 1000)
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise WebError("Microsoft returned mismatched or expired revision authorization")
    return {"WOPIsrc": source, "access_token": token, "access_token_ttl": ttl}


def common_operation():
    return {"OperationId": 1, "DependentOn": 0, "LocalCobaltSessionId": None,
            "LocalCobaltMachineId": None, "LocalCobaltClusterId": None,
            "LocalCobaltSessionHasBackup": False, "WaciiEnabledRequests": 0,
            "SettingsRoutedToServer": 0, "LineageId": None, "EncryptionSessionString": None,
            "ShouldPinRevisionForAugLoop": False}


class Transport:
    def __init__(self):
        self.opener = urllib.request.build_opener(provider_io.NoRedirect)
        self.deadline = time.monotonic() + MAX_SECONDS

    def request(self, method, url, body=None, headers=None, mutation=False):
        request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)

        def once():
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise WebError("OneNote's revision service timed out; refresh the section to check it")
            try:
                try:
                    response = self.opener.open(request, timeout=min(30, remaining))
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    raw = provider_io.read_bounded(response, MAX_BODY, self.deadline)
                    status, returned = response.status, response.headers
                if status == 429:
                    raise ratelimit.Retry(ratelimit.retry_after_of(returned) or ratelimit.SHORT_RETRY)
                return status, raw, returned
            except (OverflowError, OSError, http.client.HTTPException) as error:
                # Exceptions involving signed URLs or headers can contain
                # credentials. A mutation's outcome may also be uncertain:
                # a malformed or cut-off response (http.client) can follow
                # a revision the server already committed.
                message = ("Microsoft did not confirm the change; refresh the section before trying again"
                           if mutation else "Could not read the section from OneNote's revision service")
                raise WebError(message) from error

        # Only explicit 429 rejections replay. No timeout, 5xx or lost write
        # response can cause the same revision to be submitted again.
        return ratelimit.attempt_loop(RATE_KEY if url == ENDPOINT else None,
                                     RATE_WINDOWS, once, attempts=2)


class Session(Transport):
    def __init__(self, auth):
        super().__init__()
        self.file_id = urllib.parse.urlencode(auth)
        self.headers = {"Content-Type": "application/json; charset=utf-8",
                        "X-AccessToken": auth["access_token"],
                        "X-AccessTokenTtl": str(auth["access_token_ttl"]),
                        "X-UserSessionId": str(uuid.uuid4()), "X-UserType": "WOPI",
                        "X-Requested-With": "XMLHttpRequest", "X-xhr": "1"}

    @classmethod
    def for_section(cls, section, graph=msgraph.graph):
        item_id = personal_item(section["id"])
        # The section's file lives in its owner's OneDrive; a notebook
        # shared with this account is reached by that drive, not /me/drive.
        drive_id = item_id.split("!", 1)[0]
        path = "/drives/%s/items/%s" % (drive_id, urllib.parse.quote(item_id, safe=""))
        status, metadata = graph("GET", path + "?$select=id,name,file,parentReference")
        parent = metadata.get("parentReference") if isinstance(metadata, dict) else None
        if (status != 200 or not isinstance(parent, dict)
                or str(metadata.get("id", "")).casefold() != item_id.casefold()
                or str(parent.get("driveId", "")).casefold() != drive_id.casefold()
                or parent.get("driveType") != "personal"
                or "file" not in metadata or not str(metadata.get("name", "")).lower().endswith(".one")):
            raise WebError("The OneNote section could not be verified as a writable OneDrive file")
        status, preview = graph("POST", path + "/preview", data={}, retry_policy=msgraph.RetryPolicy.REPLAY)
        if status != 200 or not isinstance(preview, dict):
            raise WebError("Microsoft could not authorize changes to this section (HTTP %s)" % status)
        url = preview_url(preview.get("getUrl"))
        # A signed preview URL is already authorized. Sending a Graph token
        # or following a redirect would cross the credential boundary.
        status, raw, _ = Transport().request("GET", url)
        if status != 200:
            raise WebError("Microsoft could not open the notebook preview (HTTP %s)" % status)
        return cls(frame_info(raw, item_id))

    def operation(self, kind, operation):
        body = json.dumps({"Mode": 1, "srs": [[kind, operation]]}).encode()
        for attempt in range(4):
            status, raw, returned = self.request("POST", ENDPOINT, body, self.headers, mutation=kind == 3)
            if status == 412 and returned.get("X-NewKey"):
                self.headers["X-Key"] = returned["X-NewKey"]
                if returned.get("X-OfficeVersion"):
                    self.headers["X-OfficeVersion"] = returned["X-OfficeVersion"]
                continue
            if (kind != 3 and status == 503 and "X-OfficeVersion" not in self.headers
                    and returned.get("X-OfficeVersion")):
                self.headers["X-OfficeVersion"] = returned["X-OfficeVersion"]
                continue
            if status != 200:
                raise WebError("Microsoft did not confirm the change (HTTP %s); refresh the section" % status)
            try:
                response = json.loads(raw)["Responses"]
                if len(response) != 1 or response[0][0] != kind:
                    raise ValueError("unexpected operation response")
                value = response[0][1]
                code = value["StatusCode"]
                if type(code) is not int:
                    raise ValueError("invalid operation status")
            except (KeyError, TypeError, ValueError, IndexError) as error:
                raise WebError("Microsoft returned an invalid revision response; refresh the section") from error
            if code in (2, 4, 5) or value.get("IsConflict"):
                raise WebError("The section changed in OneNote — refresh it and try again")
            if code == 7:
                raise WebError("Microsoft denied the change; sign in to OneNote again and check notebook access")
            if code != 0:
                raise WebError("OneNote's revision service rejected the change (code %s)" % code)
            return value
        raise WebError("Microsoft's revision authorization challenge did not settle")

    def read_section(self):
        return self.read(UNKNOWN_ROOT)

    def read(self, cell):
        """A cell's revisions: the section root, or one page's content."""
        operation = dict(common_operation(), FileId=self.file_id,
                         RevisionRequest={"CellId": cell, "ContextId": NIL, "ClientKnowledge": None},
                         IsFolderCell=False, IsUserAlone=False, IsBackendAlone=False, IsHidden=False,
                         IsAsleep=False, ExpectedLatestRevisionId=NIL)
        return self.operation(2, operation)

    def write_section(self, state, root):
        """One revision of the section root, conditional on `state`."""
        return self.write(state["RootCellId"], state, [root])

    def write(self, cell, state, objects):
        """One revision of `cell`, conditional on the revision `state` read."""
        identifier = str(uuid.uuid4())
        revision = {"Id": identifier + "|1", "RelativePath": None, "CellId": cell,
                    "ContextId": NIL, "ExpectedLatestId": state["LatestRevisionId"],
                    "BaseId": state["LatestRevisionId"], "RootObjectDescriptors": None,
                    "IsFolderCell": False, "FileId": self.file_id,
                    "ObjectGroups": [{"Id": identifier + "|2", "Objects": list(objects)}]}
        operation = dict(common_operation(), Revision=revision, ClientKnowledge=state["ClientKnowledge"],
                         BaseRevision=None, ExpectedLatestId=state["LatestRevisionId"],
                         ExpectedIncrementalActionId=NIL, IsVersionHistoryEnabled=True,
                         RtcMachineIdHint=None, ShouldSendUpdateNotificationOnSuccess=True,
                         ChangeStateList=None, MergePromptStatus=0)
        self.operation(3, operation)
        return revision["Id"]
