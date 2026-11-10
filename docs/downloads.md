# Downloads and date metadata

[Home](../README.md) · [Português (Brasil)](../README.pt-BR.md)

## Versions and output

| Version | Launcher | Output | Concurrency |
| --- | --- | --- | --- |
| v1 | Download photos.command | `fotos` | Sequential |
| v2 | Download photos v2.command | `fotos_v2` | Sequential |
| v3 | Download photos fast.command | `fotos_v2` | 1–16, default 12 |
| v4 | Download photos turbo.command | `fotos_v2` | 1–32, default 12 |

All versions accept `--curl FILE`, `--from YYYY-MM-DD`, `--to YYYY-MM-DD`, `--destination DIRECTORY`, `--max-photos N`, and `--count-only`. Original Portuguese option names remain accepted for compatibility. Limits include both boundary dates in the Sao Paulo time zone.

The launchers expect `.private/session.curl`; see the [session setup instructions](../README.md#set-up-your-own-session). Do not share this file. Sessions expire and must be refreshed manually. The captured DPoP header worked during validation but could require fresh capture if the provider changes validation.

```sh
python3 baixar_momentos_v4.py --curl .private/session.curl --from 2025-01-01 --to 2025-12-31 --concurrent 12
python3 baixar_momentos_v4.py --curl .private/session.curl --count-only
```

## Metadata

V2–v4 preserve a valid existing EXIF capture date. When absent, they write the Moment publication date into EXIF/XMP and update macOS creation/modification dates. Capture time without an offset is interpreted as Sao Paulo time. The index records the chosen source. A publication may be later than the actual photo capture.

To copy and correct files already saved by v1 without contacting the API:

```sh
python3 baixar_momentos_v2.py --import-v1 fotos
```

Copies go to `fotos_v2`; originals remain intact. If v1 is still downloading, run the import again after it finishes. Registered corrected files are skipped.

## Recovery and concurrency

V3/v4 use independent HTTP connections and temporary files, with a single coordinator writing the index every ten completions and at page boundaries. Transient failures receive six initial attempts, with up to 120 seconds per request. After exhaustion, the same operation restarts after a 60-second countdown. `--retry-delay` changes this interval; `--max-restarts 0` means unlimited retries, while a positive value limits restarts per operation.

Stop with Control+C. Existing requests may need time to finish. Authentication and permanent configuration/disk failures are not retried. An abrupt interruption may leave a small batch of completed files unregistered; these may be downloaded again on resume. Index replacement is atomic.

Do not run v1/v2 while v3/v4 uses the same output. V3/v4 share a destination lock and reject an active legacy downloader. More workers do not necessarily improve throughput, and history queries remain sequential. Reduce concurrency if failures increase.

Diagnostics are written to the local `erros_download.log`. Neither signed photo URLs nor account credentials are printed. Only `image/*` media from Moments are downloaded, using the observed `w1280` size; original resolution is not guaranteed.
