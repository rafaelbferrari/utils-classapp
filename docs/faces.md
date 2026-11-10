# Group photos by similar faces

[Home](../README.md) · [Português (Brasil)](../README.pt-BR.md)

1. Run **Install face recognition.command** to install dependencies and download public models.
2. Wait until downloads and date corrections have finished.
3. Run **Group photos by person.command**, drag your source directory into the Terminal window, and press Enter.
4. Open `PESSOAS.html` in the separate output directory next to the source.

```sh
.venv-pessoas/bin/python separar_pessoas.py /path/to/photos --max-photos 30
```

The result contains numbered `Pessoa_0001` directories. Each has a `PRINCIPAL.jpg` representative face crop, a `PRINCIPAL-origem.txt` source reference, and a `fotos` directory containing full-photo copies. Larger, sharper face appearances can replace the reference crop as processing continues. Only reference crops are converted; full photos are copied unchanged with modification dates preserved. Group photos are copied into multiple matching directories and may require substantial extra disk space.

The local YuNet/SFace models run offline after installation. No photos or descriptors are uploaded to a service. A hidden `.pessoas.sqlite3` database stores associations and face descriptors for resume; keep it private and do not delete it when resuming. Tiny or undetected faces are excluded, and images with no usable faces go to `Sem_rosto_detectado`.

## Review the groups

Groups indicate similarity, not verified identities. Similar-looking people, twins, side views, and blurry faces may cause mixed or split groups. Review all groups, including those without a review marker. Ambiguous matches create groups marked “review similarity” in the gallery. The incremental algorithm depends on image order and does not automatically merge existing groups.

The same group is not assigned two separate faces in one photo. The default similarity threshold is 0.48, with a 0.05 margin between candidates. A higher threshold tends to split more groups. To change settings, choose a fresh destination:

```sh
.venv-pessoas/bin/python separar_pessoas.py /path/to/photos --threshold 0.55 --destination /path/to/new_output
```

## Resume

Press Control+C and rerun with the same source and destination. Registered unchanged photos are skipped. The gallery refreshes every 25 photos and at exit. A lock prevents concurrent use of the same output. If source files change after analysis or you delete output copies, choose a new destination to rebuild.

Keep numbered directory names while processing or resuming. Rename them only after you no longer intend to resume; gallery links use the original names. The database and filenames retain legacy names for compatibility, while generated gallery text is English.

Models come from a fixed revision of the official OpenCV repository with SHA-256 verification. Dependencies are isolated in `.venv-pessoas`. Validated with Python 3.9 on macOS Apple Silicon. [OpenCV model documentation](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html).

## Name and merge groups

Run **Manage face groups.command** and select the result directory containing `PESSOAS.html`. A local browser interface opens with these controls:

- Enter a name and select **Save name**. The name persists in the local grouping database and appears in the static gallery as well.
- Select two or more groups showing the same person, choose **Merge selected groups**, select which numbered group to retain, and enter the name to keep.
- **View photos** opens the complete photos in that group for comparison.
- **Undo last change** restores the most recent naming or merge operation.

A merge collects unique photo paths into the retained group, combines its descriptors, and keeps the best reference crop. Shared photos are copied once. Names are labels: they do not verify an identity or retrain the recognition model. Original input photos are never changed.

The manager serves only on `127.0.0.1` and keeps names, images, and backups on the Mac. Keep its process running while editing. It holds the same output lock as the grouping script, so they cannot modify a result simultaneously. A local `MANAGE.html` shortcut points to the active editing interface; if its address expires, restart the launcher.

Before each change, a database snapshot is saved under `.management-history`. Merges archive the original group directories there. Undo is allowed only while the database still matches the latest managed action, preventing it from overwriting a newer analysis. Backups can require additional disk space. Do not delete them if you need undo. Keep these private along with the result database.
