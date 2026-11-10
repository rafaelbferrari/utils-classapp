# Correct photo dates from directory names

[Home](../README.md) · [Português (Brasil)](../README.pt-BR.md)

Copy `ajustar_datas_pastas.py` and **Fix photo dates.command** into the directory containing the dated subdirectories, then double-click the launcher. Alternatively:

```sh
python3 ajustar_datas_pastas.py /path/to/collection --dry-run
python3 ajustar_datas_pastas.py /path/to/collection
```

The script scans recursively and uses the nearest valid `YYYY-MM-DD` parent directory. It overwrites EXIF/XMP dates and macOS creation/modification dates with that day at **12:00 in the Sao Paulo time zone**. Noon is a convention: the directory does not contain the real capture time. Existing EXIF dates are overwritten in this operation.

The first edit creates an ExifTool `photo.jpg_original` backup. Repeating the operation preserves and ignores these backups. `--no-backup` disables backup creation. Images are not recompressed. The `--dry-run` option lists counts without changing files.

Supported formats: JPEG, PNG, WebP, HEIC/HEIF, and TIFF. Hidden directories, symbolic links, videos, temporary files, and images without a valid dated parent are ignored. No ClassApp access or network connection is required.

Run after the downloader has finished. When the scanned tree contains a downloader index, the script reconciles hashes so edited files are not downloaded again. The index’s original publication timestamp remains unchanged. Run one correction process at a time.

Dependencies: Python 3 and ExifTool (`brew install exiftool`).
