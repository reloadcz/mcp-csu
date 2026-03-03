# mcp-csu

MCP server for the Czech Statistical Office (ČSÚ) DataStat API.
Single-file Python server (`mcp_csu/server.py`), runs via `uvx mcp-csu`.

## For AI agents using this MCP server

### Quick start

```
search_datasets("obyvatelstvo")  →  find dataset code
get_dataset("OBY01")             →  see dimensions + indicators
get_dataset_selections("OBY01")  →  find predefined table code
get_selection_data("OBY01T01")   →  get CSV data
```

### Tool overview

**Find data:**
- `search_datasets(query)` — full-text search across 700+ datasets
- `search_selections(query)` — full-text search across 1500+ predefined tables
- `list_datasets(offset, limit)` — browse all datasets
- `list_selections(offset, limit)` — browse all predefined tables

**Understand structure:**
- `get_dataset(code)` — dimensions, indicators, keywords, update frequency
- `get_dataset_selections(code)` — predefined tables for a dataset
- `get_dimension_items(code, level)` — possible values (years, regions, categories)
- `get_indicator(code)` — indicator definition

**Get data:**
- `get_selection_data(code, max_rows)` — **primary tool**, fetches CSV from a predefined table
- `get_value(dataset, indicator, dim_codes, item_codes)` — single precise value
- `custom_query(...)` — advanced, arbitrary dataset query
- `get_dataset_metadata(code, version)` — record count, time range, last update

### Critical rules

1. **Always search in Czech.** The database is Czech-language. Use the vocabulary below.
2. **Prefer `get_selection_data`** over `custom_query`. Selections are reliable and pre-configured. `custom_query` is fragile with hierarchical dimensions.
3. **Start with search, not list.** `search_datasets` and `search_selections` are faster and more targeted than browsing.
4. **Inspect before querying.** Always call `get_dataset()` before `get_value()` or `custom_query()` to learn dimension codes and indicator codes.
5. **Respect max_rows.** Default is 100. Increase only when the user needs more. Set to 0 only if explicitly asked for all data.

### Czech search vocabulary

| Czech | English |
|-------|---------|
| obyvatelstvo | population |
| mzdy, platy | wages, salaries |
| ceny | prices |
| inflace | inflation |
| HDP | GDP |
| nezaměstnanost | unemployment |
| zaměstnanost | employment |
| průmysl | industry |
| stavebnictví | construction |
| vzdělání | education |
| zdraví, zdravotnictví | health |
| zemědělství | agriculture |
| doprava | transport |
| cestovní ruch | tourism |
| životní prostředí | environment |
| kriminalita | crime |
| volby | elections |
| bytová výstavba | housing construction |
| zahraniční obchod | foreign trade |
| důchody | pensions |
| energie | energy |
| věda, výzkum | science, research |
| demografická statistika | demographic statistics |
| sčítání lidu | census |
| příjmy, výdaje | income, expenditure |
| domácnosti | households |

### Data model

```
Dataset (sada)          — raw multidimensional data, code like RSO01
├── Dimensions          — axes: time (CasR), territory (Uz0), categories
│   └── Items           — specific values: "2024", "CZ", "501"
├── Indicators          — what is measured: code like 3971b
└── Selections (výběry) — predefined table views, code like RSO001
```

### Common dimension types

| Type code | Meaning | Example codes |
|-----------|---------|---------------|
| REF_CAS | Time | CasR (years), CasM (months), CasQ (quarters) |
| VUZEMI | Territory | Uz0, UZ023H2U (hierarchical: STAT > KRAJ > OKRES) |
| POHLAVI | Gender | POHLNAR |
| VEK | Age | various |

### Territory hierarchy levels

| Level | Czech | English | Count |
|-------|-------|---------|-------|
| STAT | Stát | Country | 1 (CZ) |
| REGION | Region soudržnosti | Cohesion region | 8 |
| KRAJ | Kraj | Region | 14 |
| OKRES | Okres | District | 77 |
| ORP | Obec s rozšířenou působností | Municipality with extended powers | 206 |
| OBEC | Obec | Municipality | ~6250 |

### `get_value` workflow

```
1. get_dataset("RSO01")
   → dimensions: CasR, TYPPROSJED, UZ023H2U
   → indicators: 3971b

2. get_dimension_items("TYPPROSJED")
   → 501 = Obec (municipality)

3. get_dimension_items("UZ023H2U", level="STAT")
   → CZ = Česko

4. get_value("RSO01", "3971b",
             ["CasR", "TYPPROSJED", "UZ023H2U"],
             ["2023", "501", "CZ"])
   → Value: 6 258 (number of municipalities in CZ in 2023)
```

### Error patterns

- `API error 400: Chybný požadavek` — bad request (wrong codes or query structure)
- `API error 404: Nenalezeno` — dataset/selection/indicator not found
- Empty CSV (header only) — filter returned no matching data, usually wrong dimension item codes

## For developers modifying this server

- `mcp_csu/server.py` — single file, all code. Published to PyPI as `mcp-csu`.
- Upstream APIs: Catalog (`katalog/v1`), Data (`dotaz/v1`)
- OpenAPI specs: `https://data.csu.gov.cz/api/{katalog,dotaz}/v1/api-docs`
- Catalog API ignores `start`/`pocet` pagination params — always returns full list. Pagination is client-side.
- `custom_query` maps to `POST /data/sady/{code}/vlastni`. Tricky with multi-time-dimension datasets and hierarchical territory dimensions. Predefined selections are more reliable.
- The search endpoints are `POST /sady/hledani`, `POST /vybery/hledani` with body `{podminky: {polozkyFiltru: [{typPodminky: "TEXTOVE_HLEDANI", textoveHledani: {text: "..."}}], vztahPolozek: "VSE"}}`.
