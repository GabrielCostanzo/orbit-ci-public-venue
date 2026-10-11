# pcic-venue-sample

This repository is a disposable CI venue. It exists so that one GitHub Actions job can publish one
throwaway Python package to a test registry. Nothing here is a product, and nothing here is
supported.

- `pyproject.toml` declares the package `pcic-venue-sample` and the registry workspace source
  `pcic/venue`.
- `.github/workflows/packages.yml`, when present, is the workflow a test registry generated for one
  connection. It is committed unchanged.

The repository may be emptied or deleted at any time.
