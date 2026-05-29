"""
load_reddit_archive.py
======================

Ingestion layer for Stage 3.

This module defines the connector abstraction that decouples the rest of the
pipeline from any specific Reddit data source. The pipeline operates on a
canonical `Comment` schema; concrete connectors are responsible for producing
that schema from whatever underlying source they wrap.

Currently shipped:
    ArchiveConnector — reads Pushshift-format zstandard-compressed NDJSON dumps
                       (the de-facto historical Reddit archive standard, available
                       via Academic Torrents and HuggingFace mirrors).

Future-compatible (interface only):
    LiveConnector    — would wrap PRAW / Devvit / any future official API.
                       Implementers must yield the same canonical Comment dataclass.

Design rationale
----------------
Reddit's developer surface has been unstable for several years (API pricing
changes 2023, Devvit pivot, OAuth flow churn). Treating the source as a
swappable adapter is a deliberate engineering hedge: when the source changes,
only this file changes. The linking, sentiment, and engagement layers remain
untouched. This is the ports-and-adapters (hexagonal) pattern.

CLI usage
---------
    python -m src.load_reddit_archive \\
        --input data/raw/reddit \\
        --output data/interim/reddit_comments.parquet \\
        --start 2020-01-01 \\
        --end 2024-12-31 \\
        --min-body-length 15
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional

import pandas as pd

try:
    import zstandard as zstd
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "zstandard is required to read Pushshift dumps. Install with: pip install zstandard"
    ) from e


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Comment:
    """
    Canonical comment record.

    Every connector — archive, live, or otherwise — must yield records that
    conform to this schema. Downstream modules (linking, sentiment, engagement)
    are coded against this contract and have no knowledge of the underlying
    source format.
    """
    id: str                 # Reddit base36 comment id (or synthetic id for non-Reddit sources)
    author: str             # author username or "[deleted]"
    body: str               # raw comment text
    created_utc: int        # epoch seconds, UTC
    subreddit: str          # subreddit name (lowercase, no r/ prefix)
    score: int              # net upvotes at time of capture; 0 if unknown
    link_id: str            # parent submission id (Reddit "t3_xxxxx" or "")
    source: str             # adapter identifier, e.g. "pushshift_archive" / "live_praw"


# ---------------------------------------------------------------------------
# Connector contract
# ---------------------------------------------------------------------------

class BaseRedditConnector(ABC):
    """
    Abstract base class for any Reddit data source.

    Subclasses implement `iter_comments` and inherit the convenience methods
    (`materialize`, `to_dataframe`). This keeps the swap-cost low: a future
    live connector only has to implement one method.
    """

    source_name: str = "base"

    @abstractmethod
    def iter_comments(self) -> Iterator[Comment]:
        """Yield Comment records one at a time. Implementations should be lazy."""
        ...

    def to_dataframe(self) -> pd.DataFrame:
        """Materialize all comments into a pandas DataFrame. Use with care on large sources."""
        return pd.DataFrame(asdict(c) for c in self.iter_comments())

    def materialize(self, out_path: Path, batch_size: int = 100_000) -> int:
        """
        Stream comments to parquet in batches. Returns the number of rows written.

        Parquet is chosen for the interim format because (a) it preserves dtypes,
        (b) it's ~10x smaller than CSV for this schema, and (c) downstream
        readers can column-prune.
        """
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        total = 0
        batch: list[dict] = []
        writer = None
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as e:  # pragma: no cover
            raise ImportError("pyarrow is required for parquet output. pip install pyarrow") from e

        try:
            for comment in self.iter_comments():
                batch.append(asdict(comment))
                if len(batch) >= batch_size:
                    table = pa.Table.from_pylist(batch)
                    if writer is None:
                        writer = pq.ParquetWriter(out_path, table.schema, compression="snappy")
                    writer.write_table(table)
                    total += len(batch)
                    logger.info("Wrote batch: %d total rows", total)
                    batch.clear()
            if batch:
                table = pa.Table.from_pylist(batch)
                if writer is None:
                    writer = pq.ParquetWriter(out_path, table.schema, compression="snappy")
                writer.write_table(table)
                total += len(batch)
        finally:
            if writer is not None:
                writer.close()

        logger.info("Materialized %d comments to %s", total, out_path)
        return total


# ---------------------------------------------------------------------------
# Archive connector — Pushshift zstandard NDJSON dumps
# ---------------------------------------------------------------------------

class ArchiveConnector(BaseRedditConnector):
    """
    Reads Pushshift-format historical Reddit dumps.

    Expected input layout: a directory containing one or more `.zst` files,
    each a zstandard-compressed NDJSON stream where every line is one comment.
    The per-subreddit Pushshift split torrent produces filenames such as
    `soccer_comments.zst`, `reddevils_comments.zst`, etc. Monthly dumps like
    `RC_2023-05.zst` work identically.

    Parameters
    ----------
    input_dir : Path
        Directory to walk for .zst files.
    start_utc, end_utc : int | None
        Optional epoch-seconds bounds; comments outside are skipped at read time.
    subreddits : set[str] | None
        Optional allowlist (case-insensitive). Comments from other subs are skipped.
    min_body_length : int
        Reject comments shorter than this. Stage 3 default is 15 chars — filters
        out "lol", "this", and bot-like one-word noise.
    include_deleted : bool
        Whether to keep [deleted] / [removed] bodies. Default False.
    """

    source_name = "pushshift_archive"

    # zstandard window size: pushshift dumps use a large compression window
    # (the default 0 means unlimited; the dumps require ~2GiB max window).
    _DCTX = zstd.ZstdDecompressor(max_window_size=2**31)

    def __init__(
        self,
        input_dir: Path | str,
        start_utc: Optional[int] = None,
        end_utc: Optional[int] = None,
        subreddits: Optional[Iterable[str]] = None,
        min_body_length: int = 15,
        include_deleted: bool = False,
    ) -> None:
        self.input_dir = Path(input_dir)
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory does not exist: {self.input_dir}")
        self.start_utc = start_utc
        self.end_utc = end_utc
        self.subreddits = {s.lower() for s in subreddits} if subreddits else None
        self.min_body_length = min_body_length
        self.include_deleted = include_deleted

    # -- file discovery -----------------------------------------------------

    # Supported archive formats. .zst = Pushshift / Academic Torrents dumps;
    # .jsonl / .ndjson = uncompressed exports (e.g. arctic-shift web tool).
    _SUPPORTED_SUFFIXES = {".zst", ".jsonl", ".ndjson"}

    def _input_files(self) -> list[Path]:
        files = sorted(
            p for p in self.input_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in self._SUPPORTED_SUFFIXES
        )
        if not files:
            logger.warning(
                "No input files (.zst/.jsonl/.ndjson) found under %s", self.input_dir,
            )
        return files

    # -- core reader --------------------------------------------------------

    def _iter_file(self, path: Path) -> Iterator[dict]:
        """Stream one archive file and yield parsed JSON dicts.

        Handles two formats transparently:
          * .zst — zstandard-compressed NDJSON (Pushshift dumps)
          * .jsonl / .ndjson — plain UTF-8 NDJSON (arctic-shift exports)

        We stream in either case because the largest dumps don't fit in memory.
        """
        suffix = path.suffix.lower()
        if suffix == ".zst":
            fh = path.open("rb")
            text_stream = io.TextIOWrapper(
                self._DCTX.stream_reader(fh), encoding="utf-8", errors="replace",
            )
            close_targets = (text_stream, fh)
        else:
            text_stream = path.open("r", encoding="utf-8", errors="replace")
            close_targets = (text_stream,)

        try:
            line_no = 0
            for line in text_stream:
                line_no += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # Pushshift / arctic-shift dumps occasionally have malformed lines; skip them.
                    if line_no % 10_000 == 0:
                        logger.debug("Malformed JSON at %s line %d", path.name, line_no)
                    continue
        finally:
            for h in close_targets:
                try:
                    h.close()
                except Exception:
                    pass

    # -- canonicalization & filtering --------------------------------------

    def _accept(self, raw: dict) -> bool:
        body = raw.get("body", "")
        if not body or len(body) < self.min_body_length:
            return False
        if not self.include_deleted and body in ("[deleted]", "[removed]"):
            return False

        # Subreddit filter (case-insensitive). Pushshift stores lowercase but
        # we normalize defensively.
        if self.subreddits is not None:
            sub = (raw.get("subreddit") or "").lower()
            if sub not in self.subreddits:
                return False

        # Time filter — created_utc may be int or string depending on dump vintage.
        created = raw.get("created_utc")
        if created is None:
            return False
        try:
            created = int(created)
        except (TypeError, ValueError):
            return False
        if self.start_utc is not None and created < self.start_utc:
            return False
        if self.end_utc is not None and created > self.end_utc:
            return False

        return True

    @staticmethod
    def _to_comment(raw: dict) -> Comment:
        return Comment(
            id=str(raw.get("id", "")),
            author=str(raw.get("author", "[deleted]")),
            body=str(raw.get("body", "")),
            created_utc=int(raw.get("created_utc", 0)),
            subreddit=str(raw.get("subreddit", "")).lower(),
            score=int(raw.get("score", 0) or 0),
            link_id=str(raw.get("link_id", "")),
            source="pushshift_archive",
        )

    # -- public iterator ----------------------------------------------------

    def iter_comments(self) -> Iterator[Comment]:
        files = self._input_files()
        for path in files:
            logger.info("Reading %s", path.name)
            kept = 0
            for raw in self._iter_file(path):
                if self._accept(raw):
                    yield self._to_comment(raw)
                    kept += 1
            logger.info("  kept %d comments from %s", kept, path.name)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> int:
    """Parse YYYY-MM-DD into UTC epoch seconds."""
    return int(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Materialize Pushshift Reddit archives into a parquet file for Stage 3.",
    )
    parser.add_argument("--input", required=True, type=Path,
                        help="Directory containing .zst files (Pushshift dumps).")
    parser.add_argument("--output", required=True, type=Path,
                        help="Output parquet path.")
    parser.add_argument("--start", type=_parse_date, default=None,
                        help="Start date YYYY-MM-DD (UTC). Comments earlier are skipped.")
    parser.add_argument("--end", type=_parse_date, default=None,
                        help="End date YYYY-MM-DD (UTC). Comments later are skipped.")
    parser.add_argument("--subreddits", nargs="*", default=None,
                        help="Optional allowlist of subreddits (case-insensitive).")
    parser.add_argument("--min-body-length", type=int, default=15)
    parser.add_argument("--include-deleted", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    connector = ArchiveConnector(
        input_dir=args.input,
        start_utc=args.start,
        end_utc=args.end,
        subreddits=args.subreddits,
        min_body_length=args.min_body_length,
        include_deleted=args.include_deleted,
    )
    n = connector.materialize(args.output)
    print(f"Wrote {n:,} comments to {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
