"""Shared utilities for feed generators."""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
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


ANTHROPIC_LISTING_DATE_FORMATS = ["%b %d, %Y", "%B %d, %Y"]
ANTHROPIC_LISTING_HEADINGS = ["h2", "h3", "h4"]


def parse_anthropic_listing(html_content: str, base_url: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse an anthropic.com article listing (/research, /engineering, /research/team/...).

    Returns (articles, problems). Each <article> element is one listing row: a <header>
    with a category link and a <time> ("Nov 25, 2026"), then a heading that wraps the
    article link, then a <p> summary. Dates are never made up: a row without exactly one
    heading link, or without a parseable <time>, goes to problems so the caller can fail.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    problems = []
    seen_links = set()

    for row in soup.find_all("article"):
        heading_links = [
            a
            for heading in row.find_all(ANTHROPIC_LISTING_HEADINGS)
            for a in heading.find_all("a", href=True)
            if a["href"].strip()
        ]
        links = {urljoin(base_url, a["href"].strip()) for a in heading_links}
        if len(links) != 1:
            problems.append(f"row with {len(links)} article links")
            continue

        link = links.pop()
        title = heading_links[0].get_text(" ", strip=True)
        time_elem = row.find("time")
        date_text = time_elem.get_text(strip=True) if time_elem else None
        date = None
        for date_format in ANTHROPIC_LISTING_DATE_FORMATS:
            try:
                date = datetime.strptime(date_text or "", date_format).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        if not date:
            problems.append(f"no parseable date ({date_text!r}): {title}")
            continue

        if link in seen_links:
            continue
        seen_links.add(link)

        header = row.find("header")
        category_link = (
            next((a for a in header.find_all("a", href=True) if urljoin(base_url, a["href"]) != link), None)
            if header
            else None
        )
        summary = heading_links[0].find_parent(ANTHROPIC_LISTING_HEADINGS).find_next_sibling("p")
        articles.append(
            {
                "title": title,
                "link": link,
                "date": date,
                "category": category_link.get_text(strip=True) if category_link else None,
                "description": summary.get_text(" ", strip=True) if summary else title,
            }
        )

    return articles, problems


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


class MissingDateError(Exception):
    """A post has no readable date. Generators fail instead of making one up."""


def missing_date(identifier: str) -> datetime:
    """Raise MissingDateError for a post whose date could not be read."""
    raise MissingDateError(f"No readable date for {identifier}")
