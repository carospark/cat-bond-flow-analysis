# data/

**Empty by design.** Nothing here is tracked except this file and `.gitkeep`.

Expected layout once populated locally:

```
data/
  raw/tier1/<pull-date>/<source-id>/    publisher payloads (gitignored)
  raw/wrds/<query-date>/                licensed exports (gitignored)
  MANIFEST.local.md                     exact provenance (gitignored)
  *.csv                                 derived tables (gitignored)
```

See `../DATA_POLICY.md` for what may and may not be committed, and
`../docs/SOURCES.md` for what each source is.
