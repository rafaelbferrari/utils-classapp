# Group photos by similar faces

[Home](../README.md) · [Português (Brasil)](../README.pt-BR.md)

1. Run **Install face recognition.command** to install dependencies and download public models.
2. Wait until downloads and date corrections have finished.
3. Run **Group photos by person.command**, drag your source directory into the Terminal window, and press Enter.
4. Open `PESSOAS.html` in the separate output directory next to the source.

```sh
.venv-pessoas/bin/python separar_pessoas.py /path/to/photos --max-photos 30
```

The default engine uses YuNet detection, AdaFace IR-50 descriptors and global FAISS candidate search. It compares multiple diverse references per group and forbids merging faces appearing together in the same photo. This replaces the legacy one-photo-at-a-time SFace centroid algorithm. All processing stays local after model installation.

Output defaults to `SOURCE_NAME_por_pessoa_v2`, separate from legacy `SOURCE_NAME_por_pessoa`. Each confirmed-by-similarity group has a `PRINCIPAL.jpg` crop, source reference and full-photo copies under `fotos`. On supported macOS APFS volumes, independent copy-on-write clones avoid initially duplicating photo data; other filesystems use copies. Editing an output does not edit the original.

Unnamed clusters need at least two distinct photos before receiving a person directory. Isolated faces and small or blurred detections appear in `REVIEW.html` and `Needs_review`; they are not discarded merely to reduce the group count. Images without a detected face remain in the source. `analysis_summary.json` reports groups, unconfirmed faces and filtered detections. A lower folder count alone does not establish improved identity accuracy.

## Settings and resume

```sh
.venv-pessoas/bin/python separar_pessoas.py /path/to/photos --max-photos 50
.venv-pessoas/bin/python separar_pessoas.py /path/to/photos
```

Control+C stops processing. Repeating the command reuses unchanged photos from `.face-cache.sqlite3`. The global grouping and gallery are exported after feature extraction finishes. Keep the hidden cache and crops. Extraction errors are retried on the next run, before export. Changed source files require a fresh destination. Stop downloads and date correction first.

The defaults are similarity threshold `0.42`, cross-reference floor `0.25`, minimum face side `48` pixels, sharpness variance `20`, and `--min-photos 2`. These are heuristic settings, not calibrated probabilities. Higher thresholds split more groups. `--min-photos 1` also creates folders for isolated detections. Growth over years, similar classmates, twins, pose and blur can still split or mix groups. No model guarantees correct identification across childhood.

To change grouping settings without extracting features again:

```sh
.venv-pessoas/bin/python separar_pessoas.py /path/to/photos --regroup --threshold 0.45
```

Rebuilding archives the previous export under `.previous-exports`. Group numbers can change. Names from the current output and the neighboring legacy output are imported as reference portraits when one usable face is detected. Use `--labels-from /path/to/another_result` for additional named references. Distinct names cannot merge automatically. Names do not retrain the model; unnamed manual merges are not imported as constraints. Previous manual corrections remain in the archived export.

Without new photos or `--regroup`, a completed output is preserved. Close its manager before analyzing it. Never rename group folders manually. New source photos trigger global regrouping and archive the old export.

Legacy outputs and descriptors are incompatible with AdaFace. They remain untouched; re-analysis of originals is required. To explicitly continue the old algorithm, use `--engine sface` with its original settings and destination.

Models use SHA-256 verification. AdaFace IR-50 is the practical local default for this Mac, not a claim to be the newest or largest available model. Sources: [AdaFace ONNX export](https://github.com/yakhyo/adaface-onnx), [AdaFace research implementation](https://github.com/mk-minchul/AdaFace), [FAISS](https://github.com/facebookresearch/faiss), and [OpenCV YuNet](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html). Dependencies are isolated in `.venv-pessoas`, validated with Python 3.9 on Apple Silicon. Re-run the installer when upgrading.

## Name and merge groups

Run **Manage face groups.command** and select the result directory containing `PESSOAS.html`. A local browser interface opens with these controls:

- Start typing in a name field to choose from previously saved names, or enter a new name. The merge dialog offers the same suggestions. Saving one name preserves other cards, unsaved inputs and selection. Groups default to most photos first; the sort selector also offers fewest photos first and group ID.
- Enter a name and select **Save name**. The name persists in the local database and renames the directory, for example `Example Person - Pessoa_0001`. The numeric suffix prevents collisions between people with the same name. Photo paths and static gallery links are updated together. Clearing a name restores the numbered directory. Unsupported filename characters are sanitized.
- Select two or more groups showing the same person, choose **Merge selected groups**, select which numbered group to retain, and enter the name to keep.
- **View photos** opens the complete photos in that group for comparison.
- **Undo last change** restores the most recent naming or merge operation, including the previous directory name.

A merge collects unique photo paths into the retained group, combines its descriptors, and keeps the best reference crop. Shared photos are copied once. Names are labels: they do not verify an identity or retrain the recognition model. Original input photos are never changed.

The manager serves only on `127.0.0.1` and keeps names, images, and backups on the Mac. Keep its process running while editing. It holds the same output lock as the grouping script, so they cannot modify a result simultaneously. A local `MANAGE.html` shortcut points to the active editing interface; if its address expires, restart the launcher.

Before each change, a database snapshot is saved under `.management-history`. Merges archive the original group directories there. Undo is allowed only while the database still matches the latest managed action, preventing it from overwriting a newer analysis. Backups can require additional disk space. Do not delete them if you need undo. Keep these private along with the result database.

Names saved in an older manager version are retained. Select **Save name** again to apply the directory rename to an existing label.

Finder-dropped or pasted directory paths accept surrounding whitespace (including non-breaking spaces) and shell quoting. Existing paths with intentional trailing spaces are preserved. A missing source directory is reported separately from source/destination overlap.

## Private access from another network

The manager still binds only to `127.0.0.1`. To reach it from another Mac or iPad, use Tailscale on both devices with an account authorized to access the host. Tailscale Serve can proxy the manager through a private HTTPS `.ts.net` address. Do not use Funnel, which publishes the endpoint to the internet.

Once Tailscale is connected and HTTPS is enabled, start the manager with the exact HTTPS origin:

```sh
.venv-pessoas/bin/python manage_face_groups.py /path/to/result --port 56494 \
  --external-origin https://YOUR-MAC.YOUR-TAILNET.ts.net
# In another terminal, using the CLI/socket belonging to the running Tailscale daemon:
tailscale serve --bg http://127.0.0.1:56494
```

Stop the previous manager before restarting it; the output lock prevents simultaneous managers. Replace the example origin with the device's actual Tailscale DNS name. The explicit origin allows HTTPS browser edits while retaining host, origin and request-token checks. All authorized devices in the tailnet that can reach this service can view and edit the groups; use tailnet access rules if the network is shared. Keep the host Mac awake and connected. Local access remains available at its loopback URL. No photo migration or recognition run is needed.
