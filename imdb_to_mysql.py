#!/usr/bin/env python3
"""
Import IMDb TSV files into a normalized MySQL relational database.

Expected files in --data-dir, either .tsv or .tsv.gz:
- title.basics.tsv[.gz]
- title.akas.tsv[.gz]
- title.crew.tsv[.gz]
- title.episode.tsv[.gz]
- title.principals.tsv[.gz]
- title.ratings.tsv[.gz]
- name.basics.tsv[.gz]

Install dependency:
    pip install mysql-connector-python

Example:
    python imdb_to_mysql.py --user root --password secret --database imdb --data-dir ./imdb --reset
"""

from __future__ import annotations

import argparse
import csv
import gzip
import os
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import mysql.connector
from mysql.connector.connection import MySQLConnection

NULL_VALUE = r"\N"
BATCH_SIZE = 5000


def clean(value: Optional[str]) -> Optional[str]:
    if value is None or value == NULL_VALUE or value == "":
        return None
    return value


def to_int(value: Optional[str]) -> Optional[int]:
    value = clean(value)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def to_float(value: Optional[str]) -> Optional[float]:
    value = clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def split_array(value: Optional[str]) -> List[str]:
    value = clean(value)
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def open_tsv(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8", newline="")
    return open(path, mode="r", encoding="utf-8", newline="")


def iter_tsv(path: Path) -> Iterator[Dict[str, str]]:
    with open_tsv(path) as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            yield row


def find_file(data_dir: Path, base_name: str) -> Optional[Path]:
    candidates = [data_dir / f"{base_name}.gz", data_dir / base_name]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def execute_many(conn: MySQLConnection, sql: str, rows: Sequence[Tuple], label: str) -> None:
    if not rows:
        return
    cursor = conn.cursor()
    cursor.executemany(sql, rows)
    conn.commit()
    cursor.close()


def create_database(args: argparse.Namespace) -> MySQLConnection:
    server_conn = mysql.connector.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        allow_local_infile=True,
    )
    cur = server_conn.cursor()
    cur.execute(
        f"CREATE DATABASE IF NOT EXISTS `{args.database}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cur.close()
    server_conn.close()

    return mysql.connector.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        allow_local_infile=True,
    )


def create_schema(conn: MySQLConnection, reset: bool = False) -> None:
    cur = conn.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")

    if reset:
        for table in [
            "person_known_for_titles",
            "person_professions",
            "title_principals",
            "title_episodes",
            "title_writers",
            "title_directors",
            "title_ratings",
            "title_akas",
            "title_genres",
            "people",
            "titles",
        ]:
            cur.execute(f"DROP TABLE IF EXISTS `{table}`")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS titles (
            tconst VARCHAR(20) PRIMARY KEY,
            title_type VARCHAR(50),
            primary_title TEXT,
            original_title TEXT,
            is_adult TINYINT(1),
            start_year SMALLINT,
            end_year SMALLINT,
            runtime_minutes INT,
            INDEX idx_titles_type (title_type),
            INDEX idx_titles_start_year (start_year)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS title_genres (
            tconst VARCHAR(20) NOT NULL,
            genre VARCHAR(80) NOT NULL,
            position_no TINYINT NOT NULL,
            PRIMARY KEY (tconst, genre),
            INDEX idx_title_genres_genre (genre),
            CONSTRAINT fk_title_genres_title
                FOREIGN KEY (tconst) REFERENCES titles(tconst) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS title_akas (
            title_id VARCHAR(20) NOT NULL,
            ordering INT NOT NULL,
            title TEXT,
            region VARCHAR(20),
            language VARCHAR(20),
            types TEXT,
            attributes TEXT,
            is_original_title TINYINT(1),
            PRIMARY KEY (title_id, ordering),
            INDEX idx_akas_region (region),
            INDEX idx_akas_language (language),
            CONSTRAINT fk_akas_title
                FOREIGN KEY (title_id) REFERENCES titles(tconst) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS title_ratings (
            tconst VARCHAR(20) PRIMARY KEY,
            average_rating DECIMAL(3,1),
            num_votes INT,
            INDEX idx_ratings_average (average_rating),
            INDEX idx_ratings_votes (num_votes),
            CONSTRAINT fk_ratings_title
                FOREIGN KEY (tconst) REFERENCES titles(tconst) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS people (
            nconst VARCHAR(20) PRIMARY KEY,
            primary_name VARCHAR(255),
            birth_year SMALLINT,
            death_year SMALLINT,
            INDEX idx_people_name (primary_name),
            INDEX idx_people_birth_year (birth_year)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS person_professions (
            nconst VARCHAR(20) NOT NULL,
            profession VARCHAR(120) NOT NULL,
            position_no TINYINT NOT NULL,
            PRIMARY KEY (nconst, profession),
            INDEX idx_profession (profession),
            CONSTRAINT fk_professions_person
                FOREIGN KEY (nconst) REFERENCES people(nconst) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS person_known_for_titles (
            nconst VARCHAR(20) NOT NULL,
            tconst VARCHAR(20) NOT NULL,
            position_no TINYINT NOT NULL,
            PRIMARY KEY (nconst, tconst),
            INDEX idx_known_for_title (tconst),
            CONSTRAINT fk_known_person
                FOREIGN KEY (nconst) REFERENCES people(nconst) ON DELETE CASCADE,
            CONSTRAINT fk_known_title
                FOREIGN KEY (tconst) REFERENCES titles(tconst) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS title_directors (
            tconst VARCHAR(20) NOT NULL,
            nconst VARCHAR(20) NOT NULL,
            position_no INT NOT NULL,
            PRIMARY KEY (tconst, nconst),
            INDEX idx_director_person (nconst),
            CONSTRAINT fk_directors_title
                FOREIGN KEY (tconst) REFERENCES titles(tconst) ON DELETE CASCADE,
            CONSTRAINT fk_directors_person
                FOREIGN KEY (nconst) REFERENCES people(nconst) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS title_writers (
            tconst VARCHAR(20) NOT NULL,
            nconst VARCHAR(20) NOT NULL,
            position_no INT NOT NULL,
            PRIMARY KEY (tconst, nconst),
            INDEX idx_writer_person (nconst),
            CONSTRAINT fk_writers_title
                FOREIGN KEY (tconst) REFERENCES titles(tconst) ON DELETE CASCADE,
            CONSTRAINT fk_writers_person
                FOREIGN KEY (nconst) REFERENCES people(nconst) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS title_episodes (
            tconst VARCHAR(20) PRIMARY KEY,
            parent_tconst VARCHAR(20),
            season_number INT,
            episode_number INT,
            INDEX idx_episode_parent (parent_tconst),
            CONSTRAINT fk_episode_title
                FOREIGN KEY (tconst) REFERENCES titles(tconst) ON DELETE CASCADE,
            CONSTRAINT fk_episode_parent
                FOREIGN KEY (parent_tconst) REFERENCES titles(tconst) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS title_principals (
            tconst VARCHAR(20) NOT NULL,
            ordering INT NOT NULL,
            nconst VARCHAR(20),
            category VARCHAR(120),
            job TEXT,
            characters TEXT,
            PRIMARY KEY (tconst, ordering),
            INDEX idx_principals_person (nconst),
            INDEX idx_principals_category (category),
            CONSTRAINT fk_principals_title
                FOREIGN KEY (tconst) REFERENCES titles(tconst) ON DELETE CASCADE,
            CONSTRAINT fk_principals_person
                FOREIGN KEY (nconst) REFERENCES people(nconst) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()
    cur.close()


def load_titles(conn: MySQLConnection, path: Path) -> None:
    title_sql = """
        INSERT IGNORE INTO titles
        (tconst, title_type, primary_title, original_title, is_adult, start_year, end_year, runtime_minutes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """
    genre_sql = """
        INSERT IGNORE INTO title_genres (tconst, genre, position_no)
        VALUES (%s,%s,%s)
    """
    title_rows, genre_rows = [], []
    total = 0

    for row in iter_tsv(path):
        tconst = row["tconst"]
        title_rows.append((
            tconst,
            clean(row.get("titleType")),
            clean(row.get("primaryTitle")),
            clean(row.get("originalTitle")),
            to_int(row.get("isAdult")),
            to_int(row.get("startYear")),
            to_int(row.get("endYear")),
            to_int(row.get("runtimeMinutes")),
        ))
        for pos, genre in enumerate(split_array(row.get("genres")), start=1):
            genre_rows.append((tconst, genre, pos))

        if len(title_rows) >= BATCH_SIZE:
            execute_many(conn, title_sql, title_rows, "titles")
            execute_many(conn, genre_sql, genre_rows, "title_genres")
            total += len(title_rows)
            print(f"Loaded titles: {total:,}")
            title_rows, genre_rows = [], []

    execute_many(conn, title_sql, title_rows, "titles")
    execute_many(conn, genre_sql, genre_rows, "title_genres")
    total += len(title_rows)
    print(f"Loaded titles: {total:,}")


def load_people(conn: MySQLConnection, path: Path) -> None:
    people_sql = """
        INSERT IGNORE INTO people (nconst, primary_name, birth_year, death_year)
        VALUES (%s,%s,%s,%s)
    """
    profession_sql = """
        INSERT IGNORE INTO person_professions (nconst, profession, position_no)
        VALUES (%s,%s,%s)
    """
    known_sql = """
        INSERT IGNORE INTO person_known_for_titles (nconst, tconst, position_no)
        VALUES (%s,%s,%s)
    """
    people_rows, profession_rows, known_rows = [], [], []
    total = 0

    for row in iter_tsv(path):
        nconst = row["nconst"]
        people_rows.append((
            nconst,
            clean(row.get("primaryName")),
            to_int(row.get("birthYear")),
            to_int(row.get("deathYear")),
        ))
        for pos, profession in enumerate(split_array(row.get("primaryProfession")), start=1):
            profession_rows.append((nconst, profession, pos))
        for pos, tconst in enumerate(split_array(row.get("knownForTitles")), start=1):
            known_rows.append((nconst, tconst, pos))

        if len(people_rows) >= BATCH_SIZE:
            execute_many(conn, people_sql, people_rows, "people")
            execute_many(conn, profession_sql, profession_rows, "person_professions")
            execute_many(conn, known_sql, known_rows, "person_known_for_titles")
            total += len(people_rows)
            print(f"Loaded people: {total:,}")
            people_rows, profession_rows, known_rows = [], [], []

    execute_many(conn, people_sql, people_rows, "people")
    execute_many(conn, profession_sql, profession_rows, "person_professions")
    execute_many(conn, known_sql, known_rows, "person_known_for_titles")
    total += len(people_rows)
    print(f"Loaded people: {total:,}")


def load_akas(conn: MySQLConnection, path: Path) -> None:
    sql = """
        INSERT IGNORE INTO title_akas
        (title_id, ordering, title, region, language, types, attributes, is_original_title)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """
    rows, total = [], 0
    for row in iter_tsv(path):
        rows.append((
            row["titleId"],
            to_int(row.get("ordering")),
            clean(row.get("title")),
            clean(row.get("region")),
            clean(row.get("language")),
            clean(row.get("types")),
            clean(row.get("attributes")),
            to_int(row.get("isOriginalTitle")),
        ))
        if len(rows) >= BATCH_SIZE:
            execute_many(conn, sql, rows, "title_akas")
            total += len(rows)
            print(f"Loaded akas: {total:,}")
            rows = []
    execute_many(conn, sql, rows, "title_akas")
    total += len(rows)
    print(f"Loaded akas: {total:,}")


def load_ratings(conn: MySQLConnection, path: Path) -> None:
    sql = """
        INSERT IGNORE INTO title_ratings (tconst, average_rating, num_votes)
        VALUES (%s,%s,%s)
    """
    rows, total = [], 0
    for row in iter_tsv(path):
        rows.append((row["tconst"], to_float(row.get("averageRating")), to_int(row.get("numVotes"))))
        if len(rows) >= BATCH_SIZE:
            execute_many(conn, sql, rows, "title_ratings")
            total += len(rows)
            print(f"Loaded ratings: {total:,}")
            rows = []
    execute_many(conn, sql, rows, "title_ratings")
    total += len(rows)
    print(f"Loaded ratings: {total:,}")


def load_crew(conn: MySQLConnection, path: Path) -> None:
    director_sql = """
        INSERT IGNORE INTO title_directors (tconst, nconst, position_no)
        VALUES (%s,%s,%s)
    """
    writer_sql = """
        INSERT IGNORE INTO title_writers (tconst, nconst, position_no)
        VALUES (%s,%s,%s)
    """
    director_rows, writer_rows = [], []
    total = 0
    for row in iter_tsv(path):
        tconst = row["tconst"]
        for pos, nconst in enumerate(split_array(row.get("directors")), start=1):
            director_rows.append((tconst, nconst, pos))
        for pos, nconst in enumerate(split_array(row.get("writers")), start=1):
            writer_rows.append((tconst, nconst, pos))

        total += 1
        if total % BATCH_SIZE == 0:
            execute_many(conn, director_sql, director_rows, "title_directors")
            execute_many(conn, writer_sql, writer_rows, "title_writers")
            print(f"Processed crew rows: {total:,}")
            director_rows, writer_rows = [], []

    execute_many(conn, director_sql, director_rows, "title_directors")
    execute_many(conn, writer_sql, writer_rows, "title_writers")
    print(f"Processed crew rows: {total:,}")


def load_episodes(conn: MySQLConnection, path: Path) -> None:
    sql = """
        INSERT IGNORE INTO title_episodes (tconst, parent_tconst, season_number, episode_number)
        VALUES (%s,%s,%s,%s)
    """
    rows, total = [], 0
    for row in iter_tsv(path):
        rows.append((
            row["tconst"],
            clean(row.get("parentTconst")),
            to_int(row.get("seasonNumber")),
            to_int(row.get("episodeNumber")),
        ))
        if len(rows) >= BATCH_SIZE:
            execute_many(conn, sql, rows, "title_episodes")
            total += len(rows)
            print(f"Loaded episodes: {total:,}")
            rows = []
    execute_many(conn, sql, rows, "title_episodes")
    total += len(rows)
    print(f"Loaded episodes: {total:,}")


def load_principals(conn: MySQLConnection, path: Path) -> None:
    sql = """
        INSERT IGNORE INTO title_principals
        (tconst, ordering, nconst, category, job, characters)
        VALUES (%s,%s,%s,%s,%s,%s)
    """
    rows, total = [], 0
    for row in iter_tsv(path):
        rows.append((
            row["tconst"],
            to_int(row.get("ordering")),
            clean(row.get("nconst")),
            clean(row.get("category")),
            clean(row.get("job")),
            clean(row.get("characters")),
        ))
        if len(rows) >= BATCH_SIZE:
            execute_many(conn, sql, rows, "title_principals")
            total += len(rows)
            print(f"Loaded principals: {total:,}")
            rows = []
    execute_many(conn, sql, rows, "title_principals")
    total += len(rows)
    print(f"Loaded principals: {total:,}")


def optimize_tables(conn: MySQLConnection) -> None:
    cur = conn.cursor()
    for table in [
        "titles", "title_genres", "title_akas", "title_ratings", "people",
        "person_professions", "person_known_for_titles", "title_directors",
        "title_writers", "title_episodes", "title_principals",
    ]:
        print(f"Analyzing {table}...")
        cur.execute(f"ANALYZE TABLE `{table}`")
        cur.fetchall()
    cur.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import IMDb TSV files into MySQL.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=False, default="")
    parser.add_argument("--database", default="imdb")
    parser.add_argument("--data-dir", default=".", help="Folder containing IMDb .tsv or .tsv.gz files")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate IMDb tables")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir).resolve()

    required = {
        "title.basics.tsv": load_titles,
        "name.basics.tsv": load_people,
        "title.ratings.tsv": load_ratings,
        "title.akas.tsv": load_akas,
        "title.crew.tsv": load_crew,
        "title.episode.tsv": load_episodes,
        "title.principals.tsv": load_principals,
    }

    conn = create_database(args)
    create_schema(conn, reset=args.reset)

    # Disable FK checks during loading so child tables can load faster.
    # Data is still structured by keys and indexed for relational joins.
    cur = conn.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    cur.close()

    load_order = [
        "title.basics.tsv",
        "name.basics.tsv",
        "title.ratings.tsv",
        "title.akas.tsv",
        "title.crew.tsv",
        "title.episode.tsv",
        "title.principals.tsv",
    ]

    for base_name in load_order:
        path = find_file(data_dir, base_name)
        if not path:
            print(f"Skipping missing file: {base_name} or {base_name}.gz")
            continue
        print(f"\nImporting {path.name}...")
        required[base_name](conn, path)

    cur = conn.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    cur.close()

    optimize_tables(conn)
    conn.close()
    print("\nIMDb import completed.")


if __name__ == "__main__":
    main()
