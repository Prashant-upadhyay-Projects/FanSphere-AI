"""Reddit scraper.

Uses PRAW (Python Reddit API Wrapper) to pull recent hot posts and their
top-level comments from the configured subreddits. Output is a single flat
DataFrame ready for sentiment scoring.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List

import pandas as pd
import praw
from prawcore.exceptions import PrawcoreException
from tqdm import tqdm

from .config import SETTINGS, get_logger

LOG = get_logger(__name__)


def _get_client() -> praw.Reddit:
    """Return an authenticated read-only PRAW client."""
    if not (SETTINGS.reddit_client_id and SETTINGS.reddit_client_secret):
        raise RuntimeError(
            "Reddit credentials are missing — set REDDIT_CLIENT_ID and "
            "REDDIT_CLIENT_SECRET in your .env file."
        )
    client = praw.Reddit(
        client_id=SETTINGS.reddit_client_id,
        client_secret=SETTINGS.reddit_client_secret,
        user_agent=SETTINGS.reddit_user_agent,
    )
    client.read_only = True
    return client


def scrape_subreddits(
    subreddits: Iterable[str] | None = None,
    post_limit: int | None = None,
    comment_limit: int | None = None,
) -> pd.DataFrame:
    """Scrape hot posts + top-level comments from the given subreddits.

    Returns a DataFrame with columns: source, external_id, comment, upvotes,
    posted_at.  Posts and comments are interleaved; `comment` holds the text.
    """
    subreddits = list(subreddits or SETTINGS.subreddits)
    post_limit = post_limit or SETTINGS.reddit_post_limit
    comment_limit = comment_limit or SETTINGS.reddit_comment_limit

    client = _get_client()
    rows: List[dict] = []

    for sub_name in subreddits:
        LOG.info("Scraping r/%s (posts=%d, comments=%d)", sub_name, post_limit, comment_limit)
        try:
            subreddit = client.subreddit(sub_name)
            for post in tqdm(subreddit.hot(limit=post_limit), total=post_limit, desc=sub_name):
                # The post itself ----------------------------------------
                rows.append(
                    {
                        "source": f"reddit:{sub_name}",
                        "external_id": f"t3_{post.id}",
                        "comment": f"{post.title}\n\n{post.selftext or ''}".strip(),
                        "upvotes": int(post.score or 0),
                        "posted_at": datetime.fromtimestamp(post.created_utc, tz=timezone.utc),
                    }
                )
                # Top-level comments --------------------------------------
                post.comments.replace_more(limit=0)
                for comment in post.comments[:comment_limit]:
                    body = getattr(comment, "body", "") or ""
                    if not body or body in {"[deleted]", "[removed]"}:
                        continue
                    rows.append(
                        {
                            "source": f"reddit:{sub_name}",
                            "external_id": f"t1_{comment.id}",
                            "comment": body,
                            "upvotes": int(getattr(comment, "score", 0) or 0),
                            "posted_at": datetime.fromtimestamp(
                                comment.created_utc, tz=timezone.utc
                            ),
                        }
                    )
        except PrawcoreException as exc:
            LOG.error("Reddit error for r/%s — %s", sub_name, exc)
            continue

    df = pd.DataFrame(rows).drop_duplicates(subset=["source", "external_id"])
    LOG.info("Collected %d Reddit items from %d subreddit(s)", len(df), len(subreddits))
    return df
