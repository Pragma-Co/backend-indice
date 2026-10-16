import html
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar

BASE_URL = "https://quicksearch.dla.mil/"
SEARCH_URL = f"{BASE_URL}qsSearch.aspx"
REQUEST_DELAY_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 5
STATUS_ACTIVE = "1"

ROW_PATTERN = re.compile(r'<tr class="grid_(?:item|alternate)"[^>]*>(.*?)</tr>', re.S)
CELL_PATTERN = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
INPUT_PATTERN = re.compile(r"<input\b[^>]*>", re.I)
NAME_PATTERN = re.compile(r'name="([^"]*)"')
VALUE_PATTERN = re.compile(r'value="([^"]*)"')
IDENT_PATTERN = re.compile(r"ident_number=(\d+)")
PAGE_PATTERN = re.compile(r"Page (\d+) of (\d+)")
TAG_PATTERN = re.compile(r"<[^>]+>")


@dataclass
class ListingRow:
    ident_number: int
    document_id: str
    status: str
    fsc: str
    document_date: str
    title: str


def plain_text(fragment: str) -> str:
    return " ".join(html.unescape(TAG_PATTERN.sub(" ", fragment)).split())


def hidden_fields(page: str) -> dict[str, str]:
    fields = {}
    for tag in INPUT_PATTERN.findall(page):
        if 'type="hidden"' not in tag.lower():
            continue
        name = NAME_PATTERN.search(tag)
        if name:
            value = VALUE_PATTERN.search(tag)
            fields[name.group(1)] = html.unescape(value.group(1)) if value else ""
    return fields


def parse_page_info(page: str) -> tuple[int, int]:
    match = PAGE_PATTERN.search(plain_text(page))
    return (int(match.group(1)), int(match.group(2))) if match else (1, 1)


def parse_listing_rows(page: str) -> list[ListingRow]:
    rows = []
    for row_html in ROW_PATTERN.findall(page):
        cells = CELL_PATTERN.findall(row_html)
        ident = IDENT_PATTERN.search(row_html)
        if len(cells) < 6 or ident is None:
            continue
        rows.append(
            ListingRow(
                ident_number=int(ident.group(1)),
                document_id=plain_text(cells[1]),
                status=plain_text(cells[2]),
                fsc=plain_text(cells[3]),
                document_date=plain_text(cells[4]),
                title=plain_text(cells[5]),
            )
        )
    return rows


def user_agent() -> str:
    contact = os.environ.get("QUICKSEARCH_CONTACT")
    suffix = f"; {contact}" if contact else ""
    return f"fatec-api6-research/0.1 (academic project{suffix})"


class QuickSearchClient:
    def __init__(self, delay_seconds: float = REQUEST_DELAY_SECONDS):
        self.delay_seconds = delay_seconds
        self.last_request_at = 0.0
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.opener.addheaders = [("User-Agent", user_agent())]

    def request(self, url: str, form: dict[str, str] | None = None) -> bytes:
        data = urllib.parse.urlencode(form).encode() if form is not None else None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            wait = self.delay_seconds - (time.monotonic() - self.last_request_at)
            if wait > 0:
                time.sleep(wait)
            try:
                with self.opener.open(
                    urllib.request.Request(url, data=data), timeout=REQUEST_TIMEOUT_SECONDS
                ) as response:
                    return response.read()
            except (urllib.error.URLError, TimeoutError):
                if attempt == MAX_ATTEMPTS:
                    raise
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
            finally:
                self.last_request_at = time.monotonic()
        raise RuntimeError("unreachable")

    def search_active(self, fsc: str | None = None, terms: str = ""):
        form_page = self.request(SEARCH_URL).decode("utf-8", "replace")
        criteria = {
            "DocumentIDTextBox": "",
            "IDNumberTextBox": "",
            "DocumentTitleKeyWords": terms,
            "DropDownListStatus": STATUS_ACTIVE,
            "DropDownListContains": "OR",
            "DropDownListTitleOrKeywords": "TOS",
        }
        form = {**hidden_fields(form_page), **criteria, "GetFilteredButton": "Search"}
        if fsc:
            form["ExListBoxFSCHF"] = fsc
            form["ExListBoxFSCHFN"] = fsc

        page = self.request(SEARCH_URL, form).decode("utf-8", "replace")
        while True:
            page_number, page_count = parse_page_info(page)
            yield page_number, page_count, parse_listing_rows(page)
            if page_number >= page_count:
                return
            form = {**hidden_fields(page), **criteria, "btnNext.x": "5", "btnNext.y": "5"}
            page = self.request(SEARCH_URL, form).decode("utf-8", "replace")
