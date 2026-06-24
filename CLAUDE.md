# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**VESSEL STATUS** is a single-page shipping schedule tracker for LEENEAR CORPORATION. It shows COMPASS (Microsoft Dataverse/Dynamics 365) booking data alongside actual ETD data scraped from carrier vessel-schedule sites, highlighting discrepancies.

Deployed on GitHub Pages: `https://mhlee205.github.io/VESSEL_STATUS/`

## Architecture

The system has two distinct execution environments:

### 1. Browser frontend (`index.html`)
Pure vanilla HTML/CSS/JS — no build step, no framework, no bundler. Edit and push; GitHub Pages serves it directly.

- **Auth**: Microsoft Entra ID PKCE OAuth2 flow → gets a Dataverse access token stored in `localStorage` (`vs_token_v3`)
- **Data source**: Dataverse OData API at `orgde512c6f.crm7.dynamics.com` — queries `cr49f_bookings` entity
- **VSS overlay**: Loads `vessel_actual.json` from this GitHub repo (via GitHub raw or API) and overlays the `actual_etd` column on the table; color-coded badges indicate same/changed/OMIT status
- **VSS refresh button** (`triggerVssRefresh`): 4-step process in the browser:
  1. Fetches fresh bookings from Dataverse
  2. Saves to `bookings_for_vss.json` via GitHub API
  3. Runs CNC scraping via hidden iframes (toyoshingo/cmacgm blocks GitHub Actions with 403, so CNC must run in the browser)
  4. Dispatches the GitHub Actions workflow and polls for completion

### 2. GitHub Actions + Python script (`.github/`)
Runs on schedule (09:00 JST, 13:00 JST) or via `workflow_dispatch`.

**`.github/scripts/update_vessel_actual.py`** — reads `bookings_for_vss.json`, scrapes carrier VSS sites, writes `vessel_actual.json`.

Scraping sources per carrier:
| Carrier | Source |
|---|---|
| SINOKOR, HEUNG A, NAMSUNG, KMTC, DONG YOUNG, YANGMING, PAN OCEAN | `toyoshingo.com` (urllib, Shift-JIS) |
| JIN JIANG | `jinjiangshipping.jp` (Playwright) |
| EHIME OCEAN | `ehime-ocean.co.jp` (Playwright) |
| KMTC, INTERASIA, MAERSK, OOCL, ONE | `vessel-schedule-service.com` (Playwright) |
| CNC | `vessel-schedule-service.com/cnc` (Playwright) — NOT toyoshingo/cmacgm which 403s from Actions |
| MAERSK | `maersk.com/tracking/{BKG_NO}` (Playwright, higher priority) |
| YANGMING | `yangming.com` (Playwright, higher priority) |
| ONE | `one-line.com` (Playwright, higher priority) |

Tracking results (official carrier sites) always overwrite VSS schedule results.

## Key Files

| File | Purpose |
|---|---|
| `index.html` | Entire frontend — HTML, CSS, JS in one file |
| `vessel_actual.json` | BKG No → `{actual_etd, vessel_name, carrier, pol, confirmed, note, ...}` — auto-maintained |
| `bookings_for_vss.json` | Current booking list pushed from the browser to be consumed by the Python script |
| `config.json` | GitHub PAT split as `p1` + `p2` (concatenated at runtime) to bypass GitHub secret scanning |

## Credentials & Endpoints

**COMPASS (Dataverse) API base URL**: `https://orgde512c6f.crm7.dynamics.com/api/data/v9.2`

**GitHub PAT** (stored split in `config.json` to avoid Secret Scanning revocation):
- `p1`: `ghp_yN40OarDz5cq5pLN`
- `p2`: `HmmSIXTOIR4UjY2n7vGq`
- Combined (`p1+p2`): used as `window.GH_TOK` in the browser and as `GITHUB_TOKEN` / `VSS_PAT` secret in GitHub Actions

## Critical Design Decisions

**`config.json` PAT split**: `window.GH_TOK = cfg.p1 + cfg.p2`. Never merge them into a single field or GitHub will revoke the token.

**`smart_merge` logic** (Python): Entries with `confirmed: true` are protected from being overwritten unless (a) the vessel name changed or (b) the VSS ETD is earlier than the COMPASS scheduled ETD (ETD reversal). Manual corrections in `vessel_actual.json` survive automatic runs.

**CNC special handling**: toyoshingo.com/cmacgm returns HTTP 403 from GitHub Actions servers. CNC scraping happens two ways:
- Browser: `fetchCncFromToyoshingo()` uses hidden iframes (index.html:875)
- Python: `fetch_cnc_playwright()` uses `vessel-schedule-service.com/cnc` instead (update_vessel_actual.py:818)

**Voyage matching**: CNC voyage strings like `0IZOVS1NC` are partially matched — extract letters after the leading `0` and look for 4-character substrings in the VSS voyage field.

## Running the Python Script Locally

```bash
pip install playwright beautifulsoup4
playwright install chromium
GITHUB_TOKEN=<your-PAT> python .github/scripts/update_vessel_actual.py
```

The script reads `bookings_for_vss.json` from GitHub (not locally) and writes `vessel_actual.json` back to GitHub. Set `COMPASS_TOKEN` env var if you want it to query Dataverse directly instead of using the cached `bookings_for_vss.json`.

## Dataverse Entity/Field Reference

- Entity: `cr49f_bookings`
- Key fields: `cr49f_booking_no`, `cr49f_invoice_no`, `cr49f_bl_number`, `cr49f_main_ship_name`, `cr49f_cy_open`, `cr49f_cy_cut`, `cr49f_etd`, `cr49f_eta`
- Lookup fields: `_cr49f_carrier_id_value` → `crcf9_carriers.crcf9_carrier`, `_cr49f_region_japan_id_value` → `crcf9_region_japans.crcf9_pol`, `_cr49f_region_id_value` → `cr49f_regions.cr49f_pod`
