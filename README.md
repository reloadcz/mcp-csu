# mcp-csu

MCP server for the [Czech Statistical Office](https://www.czso.cz/) (ČSÚ / CZSO) [DataStat API](https://data.csu.gov.cz/). Gives AI assistants direct access to 700+ statistical datasets about the Czech Republic — population, economy, prices, wages, employment, industry, agriculture, trade, tourism, environment, and more.

Single Python file. No cloning required — just `uvx mcp-csu`.

## Features

- **Full catalog access** — search, browse, and inspect all 700+ datasets and 1500+ predefined tables
- **Data retrieval** — fetch statistical data as CSV, query individual values with full context
- **AI-optimized output** — human-readable text for metadata, CSV for data, automatic truncation with row counts
- **Rate limiting** — built-in concurrency control (3 parallel requests) and minimum request interval (150ms)
- **Caching** — catalog listings cached in memory for 10 minutes to avoid redundant requests
- **No authentication** — the DataStat API is public

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package runner)

That's it. Python and all dependencies are managed automatically by `uv`.

## Configuration

### Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "csu": {
      "command": "uvx",
      "args": ["mcp-csu"]
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "csu": {
      "command": "uvx",
      "args": ["mcp-csu"]
    }
  }
}
```

### Any MCP client

The server uses **stdio** transport (default). Launch command:

```
uvx mcp-csu
```

## Data model

The DataStat database has a hierarchical structure:

```
Dataset (sada)              e.g. CEN0101H — "Míra inflace"
├── Dimensions (dimenze)    e.g. CasR (years), Uz0 (territory)
│   └── Items (položky)     e.g. "2024", "CZ"
├── Indicators (ukazatele)  e.g. 6134J06 — "Průměrná roční míra inflace"
└── Selections (výběry)     e.g. CEN0101HT01 — "Průměrná roční míra inflace"
    └── CSV data            pre-configured table ready to fetch
```

**Datasets** contain raw multidimensional data. Each dataset has **dimensions** (time, territory, categories) and **indicators** (what is measured).

**Selections** are predefined views — a specific slice of a dataset with fixed dimension arrangement. They are the easiest way to get data.

## Tools

### Discovery

#### `search_datasets`

Full-text search across all datasets. Returns dataset codes, names, time period types, and territory levels.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | yes | Search keyword (Czech recommended) |

```
search_datasets("inflace")
→ Found 3 dataset(s):
    WCEN01 (v4) — Index spotřebitelských cen (indexy, míra inflace)
    WCEN01M (v1) — Index spotřebitelských cen — měsíční data
    CEN0101H (v1) — Míra inflace
```

#### `search_selections`

Full-text search across all predefined data tables.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | yes | Search keyword (Czech recommended) |

```
search_selections("mzdy")
→ Found 30 selection(s):
    MZDQ1T1 — Průměrný evidenční počet zaměstnanců a průměrné hrubé měsíční mzdy...
      Period: Čtvrtletí | Territory: Stát | Dataset: MZDQ1
```

#### `list_datasets`

Paginated listing of all datasets.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `offset` | int | 0 | Skip first N items |
| `limit` | int | 30 | Items per page (max 100) |

#### `list_selections`

Paginated listing of all predefined tables.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `offset` | int | 0 | Skip first N items |
| `limit` | int | 30 | Items per page (max 100) |

### Exploration

#### `get_dataset`

Full dataset metadata: dimensions with item counts, indicators with definitions, keywords, update frequency.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dataset_code` | string | yes | Dataset code (e.g. `CEN0101H`) |

```
get_dataset("CEN0101H")
→ Dataset: CEN0101H (v1)
  Name: Míra inflace
  Keywords: míra inflace
  Update frequency: MONTHLY

  Dimensions (4):
    CasM — Měsíce (720 items)
    CasR — Roky (61 items)
    CASRMX — Měsíce, roky (780 items)
    Uz0 — Území (1 items)

  Indicators (4):
    6134J09 — Přírůstek průměrného ročního indexu spotřebitelských cen - měsíční
    6134J06 — Průměrná roční míra inflace
    ...
```

#### `get_dataset_selections`

List predefined data tables for a specific dataset.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dataset_code` | string | yes | Dataset code |

```
get_dataset_selections("CEN0101H")
→ Selections for CEN0101H (2):
    CEN0101HT01 — Průměrná roční míra inflace
      Period: Rok | Territory: Stát
    CEN0101HT02 — Míra inflace - měsíční
      Period: Měsíc | Territory: Stát
```

#### `get_dimension_items`

Get all possible values for a dimension. Supports hierarchy level filtering and pagination.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dimension_code` | string | — | Dimension code from `get_dataset()` |
| `level` | string | null | Filter by hierarchy level (e.g. `STAT`, `KRAJ`, `OKRES`) |
| `offset` | int | 0 | Skip first N items |
| `limit` | int | 50 | Items per page (max 200) |

```
get_dimension_items("UZ023H2U", level="KRAJ")
→ Dimension UZ023H2U — 14 item(s) at level KRAJ:
    CZ010 — Hlavní město Praha (Capital City Prague) [KRAJ]
    CZ020 — Středočeský kraj (Central Bohemian Region) [KRAJ]
    CZ031 — Jihočeský kraj (South Bohemian Region) [KRAJ]
    ...
```

#### `get_indicator`

Indicator definition and display format.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `indicator_code` | string | yes | Indicator code from `get_dataset()` |

### Data retrieval

#### `get_selection_data`

**Primary data access tool.** Fetches CSV data from a predefined selection.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `selection_code` | string | — | Selection code (e.g. `CEN0101HT01`) |
| `max_rows` | int | 100 | Max data rows. 0 = unlimited |

```
get_selection_data("CEN0101HT01", max_rows=5)
→ "Ukazatel","Území","Roky","Hodnota"
  "Průměrná roční míra inflace","Česko","2025","2.5"
  "Průměrná roční míra inflace","Česko","2024","2.4"
  "Průměrná roční míra inflace","Česko","2023","10.7"
  "Průměrná roční míra inflace","Česko","2022","15.1"
  "Průměrná roční míra inflace","Česko","2021","3.8"

  [Showing 5 of 29 rows. Use max_rows=0 for all data or max_rows=10 to see more.]
```

#### `get_value`

Retrieve a single specific value. The most precise query — returns one number with full context (indicator name, dimension labels, publication date).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dataset_code` | string | — | Dataset code |
| `indicator_code` | string | — | Indicator code |
| `dimension_codes` | list[str] | — | Dimension codes in order |
| `item_codes` | list[str] | — | Item codes matching dimensions |
| `version` | string | null | Dataset version (latest if omitted) |

```
get_value("RSO01", "3971b",
          ["CasR", "TYPPROSJED", "UZ023H2U"],
          ["2023", "501", "CZ"])
→ Value: 6 258
  Indicator: Počet územních jednotek
    Roky: 2023
    Typ prostorové jednotky: Obec
    ČR, kraje, okresy: Česko
  Published: 2024-04-30T07:00:00Z
```

#### `custom_query`

Execute an arbitrary data query on a dataset. Returns CSV.

This is an advanced tool — prefer `get_selection_data()` when a suitable predefined table exists. The custom query API is sensitive to correct dimension placement and hierarchy level filtering.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dataset_code` | string | — | Dataset code |
| `dataset_version` | string | — | Version from `get_dataset()` |
| `columns` | list[dict] | — | Column dimensions (each needs `kodDimenze`) |
| `rows` | list[dict] | — | Row dimensions |
| `table_filters` | list[dict] | null | Filter dimensions |
| `max_rows` | int | 100 | Max CSV rows |

#### `get_dataset_metadata`

Dataset content statistics: record count, time range, publication and update timestamps.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dataset_code` | string | yes | Dataset code |
| `version` | string | yes | Version from `get_dataset()` |

## Usage examples

### Get Czech inflation rate

```
1. search_datasets("inflace")
   → CEN0101H — Míra inflace

2. get_dataset_selections("CEN0101H")
   → CEN0101HT01 — Průměrná roční míra inflace

3. get_selection_data("CEN0101HT01")
   → CSV with annual inflation rates from 1994 to present
```

### Find average wages by region

```
1. search_selections("mzdy kraje")
   → MZDQ1T2 — ... dle krajů a regionů soudržnosti

2. get_selection_data("MZDQ1T2", max_rows=20)
   → CSV with wages by region
```

### Get exact population of Prague in 2023

```
1. search_datasets("obyvatelstvo")
   → OBY01 — Obyvatelstvo podle pohlaví a věku

2. get_dataset("OBY01")
   → see dimensions and indicators

3. get_dimension_items("<territory_dim>", level="KRAJ")
   → find Prague code

4. get_value("OBY01", "<indicator>",
             ["<time_dim>", "<territory_dim>"],
             ["2023", "<prague_code>"])
   → exact value
```

## Czech vocabulary for search

The database is in Czech. Common search terms:

| Czech | English | Example datasets |
|-------|---------|-----------------|
| obyvatelstvo | population | OBY01, OBY02 |
| mzdy | wages | MZDQ1, MZD01 |
| ceny | prices | CEN01, CEN02 |
| inflace | inflation | CEN0101H |
| HDP | GDP | NUC06R, NUC06Q |
| nezaměstnanost | unemployment | ZAM04 |
| průmysl | industry | PRU01 |
| stavebnictví | construction | STA01 |
| vzdělání | education | VZD01 |
| zdraví | health | ZDR01 |
| zemědělství | agriculture | ZEM01 |
| doprava | transport | DOP01 |
| cestovní ruch | tourism | CRU01 |
| životní prostředí | environment | ZPR01 |
| kriminalita | crime | KRI01 |
| volby | elections | VOL01 |
| bytová výstavba | housing | BYT01 |
| zahraniční obchod | foreign trade | VZO01 |

## Technical details

### Architecture

Single-file Python server using [FastMCP](https://github.com/modelcontextprotocol/python-sdk) framework over stdio transport. Dependencies managed via PEP 723 inline script metadata — `uv run` installs them automatically into an isolated environment.

### Upstream API

The server wraps two DataStat REST APIs:

| API | Base URL | Purpose |
|-----|----------|---------|
| Catalog | `https://data.csu.gov.cz/api/katalog/v1` | Dataset/selection/dimension/indicator metadata |
| Data | `https://data.csu.gov.cz/api/dotaz/v1` | Data retrieval (CSV, JSON-STAT) |

API documentation:
- [General info](https://csu.gov.cz/zakladni-informace-pro-pouziti-api-datastatu)
- [Catalog Swagger](https://data.csu.gov.cz/api/katalog/v1/swagger-ui/index.html)
- [Data Swagger](https://data.csu.gov.cz/api/dotaz/v1/swagger-ui/index.html)

### Rate limiting

The DataStat API does not document rate limits, but the server applies conservative throttling:

- **Max concurrent requests:** 3 (semaphore)
- **Min request interval:** 150ms (global)
- **Request timeout:** 60 seconds

### Caching

Catalog listings (`list_datasets`, `list_selections`) are cached in memory with a 10-minute TTL. These endpoints return the full catalog (700–1500 items) on every call since the API ignores pagination parameters — caching avoids repeated large transfers.

### Output formatting

- **Metadata tools** return structured text with clear labels
- **Data tools** return CSV (most compact and LLM-friendly tabular format)
- **Truncation**: data responses are limited to 100 rows by default, with total count shown. Adjustable via `max_rows` parameter
- **Language**: all API responses are in Czech (`Accept-Language: cs`)

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `mcp` | >=1.0.0 | MCP server framework (FastMCP) |
| `httpx` | >=0.27.0 | Async HTTP client |

Both installed automatically by `uv run`.

## License

MIT
