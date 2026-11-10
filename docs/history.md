# Find the oldest available publication

[Home](../README.md) · [Português (Brasil)](../README.pt-BR.md)

Double-click **Find oldest date.command**, or run:

```sh
python3 consultar_primeira_data.py
```

It reports the oldest accessible Moment, the oldest Moment containing photos, and the suggested downloader start date. It writes a local `datas_disponiveis.json` report. No images or download indexes are modified.

The script scans all pages and computes the minimum date because ascending order was not reliable during validation. Only IDs, dates, and media types are requested; a large history may take several minutes. Dates refer to publication in the Sao Paulo time zone, rather than proven capture times. The result only covers the authenticated profile.

The script imports authentication and recovery helpers from `baixar_momentos_v3.py`; keep both files together. The default session file is `.private/session.curl`. `--curl -` reads a request from standard input, and `--output FILE` changes the report path. Refresh expired sessions using the [setup instructions](../README.md#set-up-your-own-session).

On failure, a previous report is not replaced; check its modification time before reusing it. Queries request no read updates or notification deletion, but the provider may still log access.
