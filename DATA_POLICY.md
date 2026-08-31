# Data policy

**No third-party data is stored in this repository, and none ever should be.**
Only code, configuration, and descriptions of sources are tracked.

## What is excluded, and why

| Source | Restriction | Where it lives |
|---|---|---|
| Catastrophe bond deal directory | Publisher prohibits reproduction or publication without a licence, and separately prohibits AI-related use of its content | `raw/`, gitignored |
| WRDS exports (TRACE, FISD, and similar) | Licensed research data under an institutional subscription; redistribution prohibited | `data/raw/wrds/`, gitignored |
| Broker and index-provider reports | Individual publisher terms; not redistributable | `data/raw/tier1/`, gitignored |
| Anything derived from the above | A derived table can still reconstitute the source | `data/*.csv`, gitignored |

Derived tables are excluded deliberately. Extracting a licensed directory into
a CSV does not make it yours, and a table of every deal with its issuer, size
and date is the directory.

## What *is* tracked

- Code that fetches, parses, validates and joins.
- `config/tier1_sources.json` — the source registry: publisher, title, URL,
  role. Public URLs and descriptions, no payloads.
- `docs/SOURCES.md` — what each source is and why it is used.

## Provenance is recorded, locally

Reproducibility needs exact provenance, but exact provenance is itself
sensitive: vendor query identifiers are tied to an institutional account, and
checksums fingerprint licensed extracts.

The split:

- **Public** (`docs/SOURCES.md`) — what a source is, where it comes from, what
  it is used for, its coverage.
- **Local** (`data/MANIFEST.local.md`, gitignored) — query identifiers, byte
  counts, SHA-256 checksums, timestamps, row counts.

Anyone reproducing this needs their own licensed access anyway, so publishing
the identifiers buys nothing and leaks account detail.

## If you clone this

You will not be able to run the full pipeline. That is intentional. You will
need:

1. Your own access to the deal directory, obtained under its terms.
2. Your own WRDS subscription for the security-master and transaction data.

The fetchers are cache-first and rate-limited, and no script re-fetches
anything already present.

## Before committing

```bash
git status --short          # nothing under raw/, data/raw/, or data/*.csv
git ls-files | grep -cE '^raw/|^data/raw/|\.csv$'    # must print 0
```

`.gitignore` covers these, including the symlink forms — a worktree that
symlinks `raw` into a shared cache would otherwise track the link itself.
