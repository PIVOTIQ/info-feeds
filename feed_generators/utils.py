"""Shared utilities for feed generators."""

import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from feedgen.feed import FeedGenerator


def get_project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent


def get_cache_dir():
    """Get the cache directory path, creating it if needed."""
    cache_dir = get_project_root() / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


def get_feeds_dir():
    """Get the feeds directory path, creating it if needed."""
    feeds_dir = get_project_root() / "feeds"
    feeds_dir.mkdir(exist_ok=True)
    return feeds_dir


def setup_feed_links(fg: FeedGenerator, blog_url: str, feed_name: str) -> None:
    """Set up feed links correctly so <link> points to the blog, not the feed.

    In feedgen, link order matters:
    - rel="self" must be set FIRST (becomes <atom:link rel="self">)
    - rel="alternate" must be set LAST (becomes the main <link>)

    Args:
        fg: FeedGenerator instance
        blog_url: URL to the original blog (e.g., "https://dagster.io/blog")
        feed_name: Feed name for the self link (e.g., "dagster")
    """
    # Self link first - this becomes <atom:link rel="self">
    fg.link(
        href=f"https://raw.githubusercontent.com/PIVOTIQ/info-feeds/main/feeds/feed_{feed_name}.xml",
        rel="self",
    )
    # Alternate link last - this becomes the main <link>
    fg.link(href=blog_url, rel="alternate")


def sort_posts_for_feed(posts: list[dict[str, Any]], date_field: str = "date") -> list[dict[str, Any]]:
    """Sort posts so newest appears first in the final RSS feed.

    IMPORTANT: feedgen reverses the order when writing entries to XML.
    So we sort ASCENDING (oldest first) here, which becomes DESCENDING
    (newest first) in the final feed output.

    Args:
        posts: List of post dicts with date fields
        date_field: Key name for the date field (default: "date")

    Returns:
        Sorted list with posts ordered for correct feed output
    """
    # Separate posts with and without dates
    posts_with_date = [p for p in posts if p.get(date_field) is not None]
    posts_without_date = [p for p in posts if p.get(date_field) is None]

    # Sort ascending (oldest first) - feedgen will reverse this
    posts_with_date.sort(key=lambda x: x[date_field], reverse=False)

    # Posts without dates go at the end
    return posts_with_date + posts_without_date


def load_published_dates(feed_name: str) -> dict[str, datetime]:
    """Map each item's guid to the pubDate already written in feeds/feed_{feed_name}.xml.

    For feeds dated by when an item first reaches the feed rather than by the source's date.
    Feed readers such as Slack's /feed skip items dated before their previous fetch, and a
    source date (CISA KEV's dateAdded is midnight UTC) is often older than that fetch by the
    time the hourly run publishes the item. Keeping the stored date also stops already
    published items from moving on every run.
    """
    path = get_feeds_dir() / f"feed_{feed_name}.xml"
    if not path.exists():
        return {}
    dates = {}
    for item in ET.parse(path).getroot().iter("item"):
        guid, pub_date = item.findtext("guid"), item.findtext("pubDate")
        if guid and pub_date:
            dates[guid] = parsedate_to_datetime(pub_date)
    return dates
