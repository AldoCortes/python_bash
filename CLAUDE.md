# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python utility scripts for file management and data processing. Currently contains a Google Takeout media organizer. Package manager is `uv` (build backend: `uv_build`). Python 3.9+.

## Commands

```bash
# Install in editable mode
uv pip install -e .

# Run the package entry point
uv run python-bash

# Run the Takeout organizer (dry-run by default)
uv run python src/python_bash/ORGANIZE_TAKEOUT.py --base-dir /path/to/takeouts --destino ./Fotos_Organizadas

# Execute real file moves (destructive)
uv run python src/python_bash/ORGANIZE_TAKEOUT.py --base-dir /path/to/takeouts --destino ./Fotos_Organizadas --execute

# Optional: install Pillow for EXIF date extraction
uv pip install Pillow
```

## Architecture

The package lives under `src/python_bash/`. The `__init__.py` exports a stub `main()` registered as the `python-bash` CLI entry point in `pyproject.toml`.

**`ORGANIZE_TAKEOUT.py`** is a standalone CLI script (also importable). It organizes Google Takeout exports into a date-based folder hierarchy:

```
<destino>/<YEAR>/Fotos/<YEAR>-<MM>/   # photos
<destino>/<YEAR>/Videos/<YEAR>-<MM>/  # videos
```

Date resolution priority for photos: EXIF metadata (via Pillow, optional) → filename pattern matching (`YYYYMMDD`, `YYYY-MM`, `YYYY_MM`) → filesystem mtime. Videos skip EXIF and use filename/mtime only.

The script defaults to `--dry-run` (simulation mode) and requires `--execute` to actually move files. It auto-discovers all `Takeout`, `Takeout 2`, ..., `Takeout N` directories inside `--base-dir`.
