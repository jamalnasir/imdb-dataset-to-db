# imdb-dataset-to-db

Tools for importing public datasets into normalized relational databases.

This repository currently focuses on loading the official IMDb TSV datasets into a MySQL database using a single Python script. It is designed for developers, students, PhD researchers, and database researchers who need a real-world relational dataset for database experiments, query analysis, indexing tests, and performance evaluation.

For researchers who typically use benchmark datasets such as TPC-H, this repository provides a practical alternative based on real IMDb data. The generated schema supports common relational database operations such as joins, filters, aggregations, foreign-key relationships, and indexed lookups.

## What this does
- Creates a normalized MySQL schema for IMDb data (titles, people, ratings, akas, crew, episodes, principals, and helper tables for genres/professions/known-for).
- Efficiently parses large IMDb `.tsv` or `.tsv.gz` files in batches.
- Safely inserts data with keys and indexes, and runs table analysis at the end for better query performance.

## Prerequisites
- Python 3.8+ (tested with modern Python versions)
- MySQL Server 8.0+ (recommended)
- IMDb dataset files (TSV or TSV.GZ) downloaded locally

## Installation
```
python -m pip install -r requirements.txt
```
This installs `mysql-connector-python` used by the importer.

(Optional but recommended)
```
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
python -m pip install -r requirements.txt
```

## Get the IMDb data
Download the latest IMDb datasets (TSV or compressed TSV.GZ) from:
- https://datasets.imdbws.com/

Place the files into a directory (e.g., `data/`). The importer accepts either the plain `.tsv` file or the `.tsv.gz` variant.

Required/Supported base file names (any may be compressed with `.gz`):
- title.basics.tsv
- title.akas.tsv
- title.crew.tsv
- title.episode.tsv
- title.principals.tsv
- title.ratings.tsv
- name.basics.tsv

Note: If a file is missing, the script will print a message and skip that dataset.

## Quick start
1) Ensure MySQL is running and you know the host/port and have a user/password with permission to create a database and tables.
2) Put the IMDb files into a folder, for example `data/`.
3) Run the importer:

Windows example:
```
python imdb_to_mysql.py --host 127.0.0.1 --port 3306 --user root --password secret --database imdb --data-dir .\data --reset
```

macOS/Linux example:
```
python imdb_to_mysql.py --host 127.0.0.1 --port 3306 --user root --password secret --database imdb --data-dir ./data --reset
```

The `--reset` flag drops and recreates the IMDb tables if they already exist. If you omit `--reset`, the existing tables will be preserved/created as needed, and inserts use `INSERT IGNORE` to avoid duplicates.

## Command reference
The script accepts the following arguments:
- --host (default: 127.0.0.1)
- --port (default: 3306)
- --user (required)
- --password (optional, default: empty)
- --database (default: imdb)
- --data-dir (default: current directory; folder containing the IMDb .tsv or .tsv.gz files)
- --reset (flag; drop and recreate IMDb tables before loading)

Example minimal usage (using defaults where possible):
```
python imdb_to_mysql.py --user myuser --password mypass --data-dir ./data
```

## What gets created (schema overview)
Tables created in the target database (if not present):
- titles (tconst PK, title metadata)
- title_genres (per-title genres with position)
- title_akas (alternate titles by region/language)
- title_ratings (IMDb ratings and vote counts)
- people (nconst PK, person metadata)
- person_professions (per-person professions with position)
- person_known_for_titles (person-to-title links with position)
- title_directors (many-to-many directors for titles)
- title_writers (many-to-many writers for titles)
- title_episodes (episode relationships and numbering)
- title_principals (principal cast/crew per title)

Foreign keys and indexes are created to support relational joins and common filters. During the load, foreign key checks are temporarily disabled to improve speed, and re-enabled afterward. The script also runs `ANALYZE TABLE` on all IMDb tables at the end.

## Load order
The script attempts to load these files in this order (skipping any that are missing):
1) title.basics.tsv
2) name.basics.tsv
3) title.ratings.tsv
4) title.akas.tsv
5) title.crew.tsv
6) title.episode.tsv
7) title.principals.tsv

## Performance tips
- Use the `.tsv.gz` compressed files to save disk space; the script reads them transparently.
- Ensure MySQL has sufficient `innodb_buffer_pool_size` and I/O capacity.
- Run with `--reset` when re-importing from scratch to avoid fragmentation.
- The script batches inserts (default batch size: 5000 rows).

## Troubleshooting
- Authentication errors: verify `--user`, `--password`, `--host`, and `--port` and that the user can create databases and tables.
- Missing files: you will see "Skipping missing file: ..."; verify the `--data-dir` folder and filenames match the list above.
- Character encoding: tables use `utf8mb4` with `utf8mb4_unicode_ci` collation.
- Connection issues to MySQL: ensure the server is reachable and not blocking remote connections, and that MySQL 8.0+ is installed.

## Development
- Main script: `imdb_to_mysql.py`
- Dependencies: see `requirements.txt`

## License
This project is licensed under the terms of the LICENSE file included in this repository.

## Acknowledgements
IMDb datasets are provided by IMDb. Use of the data must comply with IMDb's terms: https://www.imdb.com/interfaces/
