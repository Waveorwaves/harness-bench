# logreport

Summarises a web server's access log. Python 3.11 or later, standard library only.

```
python3 -m logreport access.log [--top N]
```

Each log line is

```
<time> <method> <path> <status> <duration>ms
```

for example `2026-03-01T12:00:03+00:00 GET /api/items 200 123ms`. The time is ISO 8601; a time without an offset is UTC. Methods are GET, POST, PUT, PATCH and DELETE.

The report gives the number of entries, a count per status class, and the busiest paths (most entries first, ties in alphabetical order, `--top` paths at most, 5 by default):

```
total: 5
2xx: 3
3xx: 0
4xx: 1
5xx: 1
top paths:
  /api/items 3
  /health 2
```

A log that cannot be opened is reported on standard error, and the exit code is 1.

## Layout

- `logreport/parse.py`: turns lines into `Entry` objects.
- `logreport/stats.py`: counting.
- `logreport/cli.py`: arguments and printing.
- `tests/`: `python3 -m unittest discover -s tests`.
