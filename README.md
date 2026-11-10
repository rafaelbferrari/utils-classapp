# Utils ClassApp

[English](README.md) · [Português (Brasil)](README.pt-BR.md)

Local macOS tools to back up and organize photos from **Moments** that your own ClassApp account can already access. Download a date range, keep useful photo dates, and group photos by similar faces.

Downloads use direct HTTP requests. Face grouping runs locally. No cloud AI service or AI tokens are required. This is an independent project, not affiliated with ClassApp.

**The repository contains code, documentation, and synthetic tests only. Photos, account sessions, credentials, reports, models, and face descriptors are not included.**

## Choose a tool

| Task | macOS launcher | Why it is useful |
| --- | --- | --- |
| Download photos | **[Download photos turbo.command](Download%20photos%20turbo.command)** | Latest downloader: up to 32 concurrent images, 12 by default, date filters, resume, and automatic recovery. |
| Find the start of your history | [Find oldest date.command](Find%20oldest%20date.command) | Finds the oldest accessible publication and oldest publication with photos without downloading images. |
| Correct dates in an existing collection | [Fix photo dates.command](Fix%20photo%20dates.command) | Uses `YYYY-MM-DD` directories to update EXIF/XMP and Finder dates, without contacting ClassApp. |
| Group photos by person | [Group photos by person.command](Group%20photos%20by%20person.command) | Copies photos into face-similarity groups and creates a representative face crop and a gallery for review. |
| Install face grouping dependencies | [Install face recognition.command](Install%20face%20recognition.command) | Installs an isolated environment and downloads official public models. Does not process photos. |

### Download versions

| Version | Python script | Features |
| --- | --- | --- |
| v1 | `baixar_momentos.py` | Sequential downloads, publication-date filters, and index-based resume. |
| v2 | `baixar_momentos_v2.py` | Adds EXIF/XMP and macOS file dates; can also copy and correct v1 downloads. |
| v3 | `baixar_momentos_v3.py` | Up to 16 concurrent downloads, default 12, coordinated index writes, and recovery timer. |
| **v4** | **`baixar_momentos_v4.py`** | **Up to 32 concurrent downloads, default 12. Recommended for new downloads.** |

Existing Python filenames, Portuguese launchers/CLI aliases, output directory names, and index fields remain compatible with earlier installations. Code comments, help text, terminal messages, and generated gallery text are in English. V2–v4 still use `fotos_v2` by default so existing downloads can be resumed.

## Quick start

Validated with macOS Apple Silicon and Python 3.9. Downloading requires Python and [ExifTool](https://exiftool.org/); OpenCV and the face models are only needed for face grouping.

```sh
brew install exiftool
git clone https://github.com/rafaelbferrari/utils-classapp.git
cd utils-classapp
python3 --version
```

### Set up your own session

1. Sign into ClassApp in Chrome and open **Moments** for the intended profile.
2. Open Developer Tools (`Option + Command + I`), select **Network**, reload the page, and filter by `graphql`.
3. Find the **POST** request whose Payload contains `operationName: EntityMomentsQuery`.
4. Right-click it and choose **Copy → Copy as cURL**.

To run without saving credentials to disk:

```sh
pbpaste | python3 baixar_momentos_v4.py --curl - --from 2025-01-01 --to 2025-12-31
```

The `.command` launchers read `.private/session.curl`. To use them, save the request locally:

```sh
mkdir -p .private
chmod 700 .private
(umask 077; pbpaste > .private/session.curl)
```

**This request authorizes access to your account. Never paste it into an issue, chat, or commit.** `.gitignore` excludes it. Sessions expire; copy a fresh request when needed. The scripts parse the cURL text without executing it as a shell command. Login and session refresh are not automated.

### Download a date range

Double-click **Download photos turbo.command**, enter the dates and concurrency, or run:

```sh
python3 baixar_momentos_v4.py --curl .private/session.curl \
  --from 2025-01-01 --to 2025-12-31 --concurrent 12
```

Date limits are inclusive and refer to **publication dates** in the Sao Paulo time zone. Either limit can be omitted. Photos are saved under `fotos_v2/YYYY-MM-DD/`; the local index records paths and hashes for resume.

Press Control+C to stop. Active requests may need time to finish. Running again skips registered files whose hashes still match. Stop the previous downloader before changing versions; never run two downloaders against the same output directory.

## Organize the results

- **Find the oldest date:** run `python3 consultar_primeira_data.py`. It scans publication metadata and saves a local report, not images. [History guide](docs/history.md).
- **Preserve useful photo dates:** v2–v4 retain an existing EXIF capture date or fall back to the publication date. The index records which source was used. [Download and metadata guide](docs/downloads.md).
- **Fix dates from directory names:** run `python3 ajustar_datas_pastas.py /path/to/collection --dry-run`, then remove `--dry-run` to apply. This explicitly overwrites dates with the directory day at noon, creating `_original` backups by default. [Date correction guide](docs/dates.md).
- **Group similar faces:** install dependencies, then launch **Group photos by person.command** after downloads finish. A separate output directory contains `Pessoa_0001`, a `PRINCIPAL.jpg` reference crop for each group, and a local `PESSOAS.html` gallery. Originals are preserved. [Face grouping guide](docs/faces.md).

Face groups are approximate, not confirmed identities. Similar-looking people, small or blurry faces, and side views may cause mixed or duplicate groups. Review the gallery before naming people. The private local database contains face descriptors; do not publish it. Group photos may be copied into multiple directories, requiring additional disk space.

## Automatic recovery

V3/v4 retry transient failures. After six initial network attempts, they wait 60 seconds and retry the same operation. By default, this continues until recovery or Control+C. Other workers can continue while one image waits.

```sh
python3 baixar_momentos_v4.py --curl .private/session.curl \
  --concurrent 12 --retry-delay 60 --max-restarts 5
```

Authentication, disk, permission, configuration, and permanent HTTP errors stop execution. The local diagnostic log does not print account credentials. Higher concurrency does not guarantee higher throughput; history pagination remains sequential.

## Known limitations

- Downloads photos from **Moments** only, not videos or message attachments.
- The observed query uses `w1280`; original resolution is not guaranteed.
- Publication dates do not prove when a photo was taken.
- The website API can change; this is not an official stable integration.
- Queries request no read-status updates or notification deletion; this does not prevent server-side logs.
- Do not correct dates or analyze faces in a directory that is still being downloaded.
- The scripts and launchers target macOS; Windows and Linux are not validated.

## Tests

Tests use artificial images, simulated requests, and temporary directories. They do not need a ClassApp account or read your photo collection. ExifTool is required for metadata tests.

```sh
python3 -m venv .venv-pessoas
.venv-pessoas/bin/python -m pip install -r requirements-pessoas.txt
.venv-pessoas/bin/python separar_pessoas.py --prepare-models
.venv-pessoas/bin/python -m unittest discover -s tests -v
```

One test runs the real models on an artificial blank image; grouping tests use simulated descriptors. These tests verify workflow and resume, not recognition accuracy on real children’s photos. Face models: official [OpenCV YuNet/SFace](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html).
