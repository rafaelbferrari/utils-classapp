# Update dates and move photos from fotos to fotos_v2

[Home](../README.md) · [Português (Brasil)](../README.pt-BR.md)

Run **Fix photo dates.command** from the project directory after all downloaders have stopped. The default operation is:

1. Read photos under `fotos/YYYY-MM-DD/` (including nested subdirectories).
2. Use the nearest valid dated directory to set EXIF/XMP and macOS creation/modification dates to that day at **12:00 in the Sao Paulo time zone**.
3. Move the photos into the matching directory under `fotos_v2` without copying them or creating image backups.
4. Update both local downloader indexes and remove empty dated source directories.

```sh
# Preview counts; no files or directories are modified
python3 ajustar_datas_pastas.py --dry-run

# Update and move using the default fotos -> fotos_v2 directories
python3 ajustar_datas_pastas.py

# Explicit source and destination
python3 ajustar_datas_pastas.py fotos --destination fotos_v2
```

The destination may already contain dated directories. Identical same-path files are deduplicated: the destination is updated and retained, and the identical source is removed. Different same-path files, or index entries using another path for the same media ID, are reported as conflicts and left in place. Existing destination files are never silently overwritten by different photos.

This is a move, not a backup. Source and destination must be on the same filesystem; cross-device copying is disabled. No `_original` image backups are created in migration mode. Processing can be rerun after interruption; registered moves are reconciled and completed files no longer exist in the source.

Stop all downloaders before running. The script refuses migration while a downloader is active and uses the v3/v4 destination lock. Do not change source or destination files during migration. No ClassApp access or network connection is used.

The folder only supplies a date, not a capture time. Noon is conventional, and this operation overwrites existing EXIF dates. It cannot determine when a photo was actually taken. Supported formats: JPEG, PNG, WebP, HEIC/HEIF, and TIFF. Symbolic links, hidden directories, videos, and files without dated ancestors are ignored. Non-photo files and previous backups remain in the source.

## Legacy in-place mode

To update dates without moving files, explicitly select the older behavior:

```sh
python3 ajustar_datas_pastas.py --in-place /path/to/collection --dry-run
python3 ajustar_datas_pastas.py --in-place /path/to/collection
```

In-place mode creates ExifTool `_original` backups by default. Add `--no-backup` to disable them. It reconciles downloader hashes within the scanned directory. Neither mode recompresses the images.

Dependencies: Python 3 and ExifTool (`brew install exiftool`).
