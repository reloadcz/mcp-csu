# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp>=1.0.0",
#     "httpx>=0.27.0",
# ]
# ///
"""mcp-csu: MCP server for Czech Statistical Office (ČSÚ) DataStat API.

Provides AI assistants with access to 700+ statistical datasets
about the Czech Republic via data.csu.gov.cz.

Usage:
    uv run server.py
"""

import asyncio
import json
import time
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

CATALOG = "https://data.csu.gov.cz/api/katalog/v1"
DATA = "https://data.csu.gov.cz/api/dotaz/v1"

TIMEOUT = 60.0
MIN_REQUEST_INTERVAL = 0.15
MAX_CONCURRENT = 3
DEFAULT_MAX_ROWS = 100
CACHE_TTL = 600  # seconds

_cache: dict[str, tuple[float, Any]] = {}

_semaphore = asyncio.Semaphore(MAX_CONCURRENT)
_last_request_time = 0.0

mcp = FastMCP(
    "ČSÚ DataStat",
    instructions="""\
Server for accessing Czech Statistical Office (ČSÚ) data.
Contains 700+ datasets covering population, economy, prices, wages,
employment, industry, agriculture, trade, tourism, environment, and more.

Typical workflow:
1. search_datasets("obyvatelstvo") — find datasets by keyword
2. get_dataset("OBY01") — examine dataset structure (dimensions, indicators)
3. get_dataset_selections("OBY01") — find predefined tables
4. get_selection_data("OBY01T01") — retrieve actual data as CSV

Tips:
- Search in Czech for best results (obyvatelstvo=population, mzdy=wages,
  nezaměstnanost=unemployment, ceny=prices, inflace=inflation, HDP=GDP)
- Predefined selections (výběry) are the easiest way to get data
- For specific values, use get_value() after examining dataset dimensions
- Dataset codes: CEN0101H, OBY01, RSO01, etc.
- Selection codes: CEN0101HT01, OBY01T01, etc.
""",
)


async def _request(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    accept: str = "application/json",
    raw: bool = False,
) -> Any:
    """Rate-limited HTTP request to the DataStat API."""
    global _last_request_time

    async with _semaphore:
        now = time.monotonic()
        wait = MIN_REQUEST_INTERVAL - (now - _last_request_time)
        if wait > 0:
            await asyncio.sleep(wait)

        headers = {"Accept-Language": "cs", "Accept": accept}
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=headers,
            )
            _last_request_time = time.monotonic()

            if resp.status_code >= 400:
                try:
                    err = resp.json()
                    msg = err.get("chyba") or err.get("error") or resp.text
                except Exception:
                    msg = resp.text
                return f"API error {resp.status_code}: {msg}"

            if raw:
                return resp.text
            return resp.json()


async def _cached_get(url: str) -> Any:
    """GET with in-memory cache (for catalog listings that rarely change)."""
    now = time.monotonic()
    if url in _cache:
        ts, data = _cache[url]
        if now - ts < CACHE_TTL:
            return data
    result = await _request("GET", url)
    if not isinstance(result, str):  # don't cache errors
        _cache[url] = (now, result)
    return result


def _search_body(query: str) -> dict:
    """Build the search request body for catalog hledani endpoints."""
    return {
        "podminky": {
            "polozkyFiltru": [
                {
                    "typPodminky": "TEXTOVE_HLEDANI",
                    "textoveHledani": {"text": query},
                }
            ],
            "vztahPolozek": "VSE",
        }
    }


def _fmt_periods(item: dict) -> str:
    return ", ".join(
        u.get("nazevUrovne", "?") for u in item.get("urovneTypObdobi", [])
    )


def _fmt_territories(item: dict) -> str:
    return ", ".join(
        u.get("nazevUrovne", "?") for u in item.get("urovneTypUzemi", [])
    )


# ---------------------------------------------------------------------------
# Discovery tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_datasets(query: str) -> str:
    """Search for statistical datasets by keyword.

    Search works best with Czech terms:
    obyvatelstvo=population, mzdy=wages, ceny=prices,
    nezaměstnanost=unemployment, průmysl=industry, HDP=GDP,
    inflace=inflation, vzdělání=education, zdraví=health.

    Returns dataset codes usable with get_dataset() and get_dataset_selections().
    """
    data = await _request("POST", f"{CATALOG}/sady/hledani", json_body=_search_body(query))
    if isinstance(data, str):
        return data

    sady = data.get("sady", [])
    if not sady:
        return f"No datasets found for '{query}'."

    lines = [f"Found {len(sady)} dataset(s):\n"]
    for s in sady:
        lines.append(f"  {s['kod']} (v{s.get('verze', '?')}) — {s.get('nazev', '?')}")
        lines.append(f"    Period: {_fmt_periods(s)} | Territory: {_fmt_territories(s)}")
    return "\n".join(lines)


@mcp.tool()
async def search_selections(query: str) -> str:
    """Search for predefined data tables (selections) by keyword.

    Selections are pre-configured views of datasets — the easiest way to get data.
    Retrieve their data with get_selection_data(code).
    Search in Czech for best results.
    """
    data = await _request("POST", f"{CATALOG}/vybery/hledani", json_body=_search_body(query))
    if isinstance(data, str):
        return data

    vybery = data.get("vybery", [])
    if not vybery:
        return f"No selections found for '{query}'."

    lines = [f"Found {len(vybery)} selection(s):\n"]
    for item in vybery[:50]:
        v = item.get("vyber", item)
        s = item.get("sada", {})
        lines.append(f"  {v.get('kod', '?')} — {v.get('nazev', '?')}")
        detail = f"    Period: {_fmt_periods(v)} | Territory: {_fmt_territories(v)}"
        if s.get("kod"):
            detail += f" | Dataset: {s['kod']}"
        lines.append(detail)
    if len(vybery) > 50:
        lines.append(f"\n  ... and {len(vybery) - 50} more")
    return "\n".join(lines)


@mcp.tool()
async def list_datasets(offset: int = 0, limit: int = 30) -> str:
    """List all available datasets with pagination.

    Use offset and limit to page through results.
    Total: ~730 datasets.
    """
    limit = min(limit, 100)
    data = await _cached_get(f"{CATALOG}/sady")
    if isinstance(data, str):
        return data

    total = len(data)
    page = data[offset : offset + limit]
    lines = [f"Datasets {offset + 1}–{offset + len(page)} of {total}:\n"]
    for s in page:
        lines.append(f"  {s['kod']} (v{s.get('verze', '?')}) — {s.get('nazev', '?')}")
    if offset + limit < total:
        lines.append(f"\n  ... use offset={offset + limit} to see more")
    return "\n".join(lines)


@mcp.tool()
async def list_selections(offset: int = 0, limit: int = 30) -> str:
    """List all predefined data tables (selections) with pagination.

    Selections are pre-configured data views that can be fetched directly.
    Use get_selection_data(code) to retrieve their data.
    """
    limit = min(limit, 100)
    data = await _cached_get(f"{CATALOG}/vybery")
    if isinstance(data, str):
        return data

    total = len(data)
    page = data[offset : offset + limit]
    lines = [f"Selections {offset + 1}–{offset + len(page)} of {total}:\n"]
    for item in page:
        v = item.get("vyber", item)
        s = item.get("sada", {})
        lines.append(f"  {v.get('kod', '?')} — {v.get('nazev', '?')}")
        if s.get("kod"):
            lines.append(f"    Dataset: {s['kod']} — {s.get('nazev', '?')}")
    if offset + limit < total:
        lines.append(f"\n  ... use offset={offset + limit} to see more")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Exploration tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_dataset(dataset_code: str) -> str:
    """Get detailed info about a dataset: description, dimensions, indicators, keywords.

    Use this to understand dataset structure before querying data.
    The dimension codes and indicator codes are needed for get_value()
    and custom_query().
    """
    data = await _request("GET", f"{CATALOG}/sady/{dataset_code}")
    if isinstance(data, str):
        return data

    lines = [
        f"Dataset: {data['kod']} (v{data.get('verze', '?')})",
        f"Name: {data.get('nazev', '?')}",
    ]

    popisy = data.get("popisy", {})
    if popisy.get("klicovaSlova"):
        lines.append(f"Keywords: {', '.join(popisy['klicovaSlova'])}")

    meta = data.get("metadataNKOD", {})
    if meta.get("periodicitaAktualizaceKod"):
        lines.append(f"Update frequency: {meta['periodicitaAktualizaceKod']}")
    if meta.get("temata"):
        lines.append(f"Topics: {', '.join(meta['temata'])}")

    dims = data.get("variantyDimenze", [])
    if dims:
        lines.append(f"\nDimensions ({len(dims)}):")
        for d in dims:
            levels = d.get("urovneHierarchie", [])
            items_count = sum(lv.get("pocetPolozek", 0) for lv in levels)
            level_names = [lv.get("nazevUrovne", lv.get("kodUrovne", "?")) for lv in levels]
            levels_str = f" [{' > '.join(level_names)}]" if len(level_names) > 1 else ""
            lines.append(
                f"  {d['kod']} — {d.get('nazev', '?')} ({items_count} items){levels_str}"
            )

    ukazatele = data.get("ukazatele", [])
    if ukazatele:
        lines.append(f"\nIndicators ({len(ukazatele)}):")
        for u in ukazatele:
            lines.append(f"  {u['kod']} — {u.get('nazev', '?')}")
            if u.get("definiceNahled"):
                preview = u["definiceNahled"][:120]
                if len(u["definiceNahled"]) > 120:
                    preview += "..."
                lines.append(f"    {preview}")

    return "\n".join(lines)


@mcp.tool()
async def get_dataset_selections(dataset_code: str) -> str:
    """List predefined data tables for a specific dataset.

    These selections can be fetched directly with get_selection_data(code).
    This is the recommended way to find available pre-built data views.
    """
    data = await _request("GET", f"{CATALOG}/sady/{dataset_code}/vybery")
    if isinstance(data, str):
        return data

    if not data:
        return f"No predefined selections for dataset {dataset_code}."

    lines = [f"Selections for {dataset_code} ({len(data)}):\n"]
    for v in data:
        lines.append(f"  {v.get('kod', '?')} — {v.get('nazev', '?')}")
        lines.append(f"    Period: {_fmt_periods(v)} | Territory: {_fmt_territories(v)}")
    return "\n".join(lines)


@mcp.tool()
async def get_dimension_items(
    dimension_code: str,
    level: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> str:
    """Get possible values for a dimension (e.g., years, regions, categories).

    Args:
        dimension_code: Dimension code from get_dataset() output (e.g., CasR, Uz0).
        level: Filter by hierarchy level code (e.g., STAT, KRAJ, OKRES).
        offset: Skip first N items.
        limit: Max items to return (default 50, max 200).

    Item codes are needed for get_value() and custom_query().
    """
    limit = min(limit, 200)
    data = await _request("GET", f"{CATALOG}/dimenze/{dimension_code}/polozky")
    if isinstance(data, str):
        return data

    if level:
        data = [item for item in data if item.get("kodUrovne") == level]

    total = len(data)
    data = data[offset : offset + limit]

    if not data:
        return f"No items found for dimension {dimension_code}" + (
            f" at level {level}" if level else ""
        )

    lines = [f"Dimension {dimension_code} — {total} item(s)" + (f" at level {level}" if level else "") + ":\n"]
    for item in data:
        en_name = ""
        for loc in item.get("lokalizovanyNazev", []):
            if loc.get("jazyk") == "en":
                en_name = f" ({loc['text']})"
                break
        level_info = f" [{item['kodUrovne']}]" if item.get("kodUrovne") and item["kodUrovne"] != "#DEFAULT" else ""
        agg = " [aggregation]" if item.get("agregacniPolozka") else ""
        lines.append(f"  {item['kod']} — {item.get('nazev', '?')}{en_name}{level_info}{agg}")

    if total > offset + limit:
        lines.append(f"\n  ... {total - offset - limit} more items (use offset={offset + limit})")
    return "\n".join(lines)


@mcp.tool()
async def get_indicator(indicator_code: str) -> str:
    """Get detailed information about a statistical indicator.

    Returns the indicator's full definition, display format, and related datasets.
    """
    data = await _request("GET", f"{CATALOG}/ukazatele/{indicator_code}")
    if isinstance(data, str):
        return data

    lines = [
        f"Indicator: {data['kod']} (v{data.get('verze', '?')})",
        f"Name: {data.get('nazev', '?')}",
    ]
    if data.get("definiceNahled"):
        lines.append(f"Definition: {data['definiceNahled']}")
    fmt = data.get("formatZobrazeniHodnoty", {})
    if fmt.get("sablona"):
        lines.append(f"Format: {fmt['sablona']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Data retrieval tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_selection_data(
    selection_code: str,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> str:
    """Fetch actual statistical data from a predefined selection as CSV.

    This is the primary and most reliable way to get data.
    Find selection codes via search_selections() or get_dataset_selections().

    Args:
        selection_code: Selection code (e.g., CEN0101HT01).
        max_rows: Maximum number of data rows to return (default 100).
            Set to 0 for unlimited (use with caution — some tables are very large).
    """
    text = await _request(
        "GET",
        f"{DATA}/data/vybery/{selection_code}",
        params={"format": "CSV"},
        accept="text/csv",
        raw=True,
    )
    if not isinstance(text, str):
        return f"Unexpected response type: {type(text)}"

    if text.startswith("{"):
        try:
            err = json.loads(text)
            return f"API error: {err.get('chyba', err.get('error', text))}"
        except json.JSONDecodeError:
            pass

    if max_rows > 0:
        csv_lines = text.split("\n")
        header = csv_lines[0] if csv_lines else ""
        data_lines = [line for line in csv_lines[1:] if line.strip()]
        total = len(data_lines)
        if total > max_rows:
            truncated = [header] + data_lines[:max_rows]
            return (
                "\n".join(truncated)
                + f"\n\n[Showing {max_rows} of {total} rows. Use max_rows=0 for all data"
                + f" or max_rows={min(total, max_rows * 2)} to see more.]"
            )

    return text


@mcp.tool()
async def get_value(
    dataset_code: str,
    indicator_code: str,
    dimension_codes: list[str],
    item_codes: list[str],
    version: str | None = None,
) -> str:
    """Get a single specific value from a dataset.

    This is the most precise way to query data — returns exactly one value.
    Requires knowing the exact dimension and item codes from
    get_dataset() and get_dimension_items().

    Args:
        dataset_code: Dataset code (e.g., RSO01).
        indicator_code: Indicator code (e.g., 3971b).
        dimension_codes: List of dimension codes (e.g., ["CasR", "TYPPROSJED", "UZ023H2U"]).
        item_codes: List of item codes matching dimension_codes order
            (e.g., ["2023", "501", "CZ"]).
        version: Dataset version (optional, defaults to latest).

    Example: Number of municipalities in Czech Republic in 2023:
        get_value("RSO01", "3971b", ["CasR","TYPPROSJED","UZ023H2U"], ["2023","501","CZ"])
    """
    if len(dimension_codes) != len(item_codes):
        return "Error: dimension_codes and item_codes must have the same length."

    params: dict[str, Any] = {
        "kodyDimenzi": ",".join(dimension_codes),
        "kodyPolozek": ",".join(item_codes),
    }
    if version:
        params["verze"] = version

    data = await _request(
        "GET",
        f"{DATA}/data/sady/{dataset_code}/hodnoty/{indicator_code}",
        params=params,
    )
    if isinstance(data, str):
        return data

    value = data.get("formatovanaHodnota") or data.get("ciselnaHodnota") or data.get("textovaHodnota")
    indicator = data.get("ukazatel", {})
    dims = data.get("dimenze", [])

    lines = [f"Value: {value}"]
    if indicator.get("nazev"):
        lines.append(f"Indicator: {indicator['nazev']}")
    for d in dims:
        vd = d.get("variantaDimenze", {})
        pd = d.get("polozkaDimenze", {})
        lines.append(f"  {vd.get('nazev', '?')}: {pd.get('nazev', pd.get('kod', '?'))}")

    info = data.get("informace", {})
    if info.get("casZverejneni"):
        lines.append(f"Published: {info['casZverejneni']}")

    notes = data.get("poznamky", [])
    if notes:
        for note in notes:
            if isinstance(note, dict) and note.get("text"):
                lines.append(f"Note: {note['text']}")

    return "\n".join(lines)


@mcp.tool()
async def custom_query(
    dataset_code: str,
    dataset_version: str,
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    table_filters: list[dict[str, Any]] | None = None,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> str:
    """Execute a custom data query on a dataset (advanced).

    IMPORTANT: Prefer get_selection_data() for predefined tables — it is much
    simpler and more reliable. Use custom_query only when no suitable predefined
    selection exists.

    Caveats:
    - All dataset dimensions must be placed in columns, rows, or table_filters.
    - Datasets with multiple time dimensions (e.g., CasM + CasR + CASRMX) may
      only work with certain dimension combinations matching predefined selections.
    - Hierarchical territory dimensions may need "filtr" with "urovenHierarchieKod".

    Args:
        dataset_code: Dataset code.
        dataset_version: Dataset version string from get_dataset().
        columns: Column dimensions. Each dict must have "kodDimenze" (str).
            Optionally add "filtr" with [{"zobrazitPolozky": ["code1","code2"]}].
        rows: Row dimensions. Same structure as columns.
            Use "kodDimenze": "#UKAZATEL" to put indicators as rows.
        table_filters: Header/filter dimensions. Same structure, but can also
            include "filtrTabulkyKod" (str) to filter to a single item.
        max_rows: Max CSV rows to return.
    """
    body: dict[str, Any] = {"sloupce": columns, "radky": rows}
    if table_filters:
        body["filtryTabulky"] = table_filters

    text = await _request(
        "POST",
        f"{DATA}/data/sady/{dataset_code}/vlastni",
        params={"verzeSady": dataset_version, "format": "CSV"},
        json_body=body,
        accept="text/csv",
        raw=True,
    )
    if not isinstance(text, str):
        return f"Unexpected response: {type(text)}"

    if text.startswith("{"):
        try:
            err = json.loads(text)
            return f"API error: {err.get('chyba', err.get('error', text))}"
        except json.JSONDecodeError:
            pass

    if max_rows > 0:
        csv_lines = text.split("\n")
        header = csv_lines[0] if csv_lines else ""
        data_lines = [line for line in csv_lines[1:] if line.strip()]
        total = len(data_lines)
        if total > max_rows:
            truncated = [header] + data_lines[:max_rows]
            return (
                "\n".join(truncated)
                + f"\n\n[Showing {max_rows} of {total} rows. Use max_rows=0 for all.]"
            )

    return text


@mcp.tool()
async def get_dataset_metadata(dataset_code: str, version: str) -> str:
    """Get metadata about dataset content: record count, time range, last update.

    Args:
        dataset_code: Dataset code.
        version: Dataset version from get_dataset().
    """
    data = await _request(
        "GET",
        f"{DATA}/metadata/sady/{dataset_code}",
        params={"verze": version},
    )
    if isinstance(data, str):
        return data

    lines = [f"Metadata for {dataset_code} (v{version}):"]
    if data.get("pocetUdaju"):
        lines.append(f"  Total records: {data['pocetUdaju']:,}")
    if data.get("casovaDimenzeOd"):
        lines.append(f"  Time range: {data['casovaDimenzeOd']} — {data.get('casovaDimenzeDo', '?')}")
    if data.get("casZverejneni"):
        lines.append(f"  Published: {data['casZverejneni']}")
    if data.get("casZmeny"):
        lines.append(f"  Last updated: {data['casZmeny']}")

    dims = data.get("dimenze", [])
    if dims:
        lines.append(f"  Dimensions ({len(dims)}):")
        for d in dims:
            lines.append(
                f"    {d.get('kod', '?')} — {d.get('nazev', '?')}"
                + (f" ({d.get('pocetPolozek', '?')} items)" if d.get("pocetPolozek") else "")
            )

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
