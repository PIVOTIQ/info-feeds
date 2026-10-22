import logging
import os
import re
from datetime import datetime

import requests
from feedgen.feed import FeedGenerator

from utils import get_feeds_dir, setup_feed_links, sort_posts_for_feed

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

GITHUB_REPO = "openai/codex"
TAGS_URL = f"https://github.com/{GITHUB_REPO}/tags"
FEED_NAME = "openai_codex_tags"


RELEASES_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    releases(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { name tagName url publishedAt description isPrerelease isDraft }
    }
  }
}
"""


def fetch_stable_releases(repo=GITHUB_REPO):
    """Fetch stable (non-prerelease) releases from the GitHub GraphQL API.

    The REST releases endpoint returns every asset of every release (about 50 MB per 100 releases
    for openai/codex), which times out with 504 and caps out at 1,000 results. GraphQL returns only
    the fields the feed needs, but it requires a token.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required (locally: export GITHUB_TOKEN=$(gh auth token))")
    headers = {"Authorization": f"bearer {token}"}
    owner, name = repo.split("/")

    releases = []
    cursor = None
    while True:
        response = requests.post(
            "https://api.github.com/graphql",
            headers=headers,
            json={"query": RELEASES_QUERY, "variables": {"owner": owner, "name": name, "cursor": cursor}},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if "errors" in payload:
            raise RuntimeError(f"GraphQL errors: {payload['errors']}")
        connection = payload["data"]["repository"]["releases"]
        for r in connection["nodes"]:
            if not r["isPrerelease"] and not r["isDraft"]:
                releases.append(
                    {
                        "name": r["name"],
                        "tag_name": r["tagName"],
                        "html_url": r["url"],
                        "body": r["description"],
                        "published_at": r["publishedAt"],
                    }
                )
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]

    logger.info(f"Fetched {len(releases)} stable releases from {repo}")
    return releases


def strip_changelog_section(body):
    """Remove ## Changelog section and everything after it from markdown body."""
    if not body:
        return ""
    result = re.sub(r"(?:^|\n)##\s*changelog\b.*", "", body, flags=re.DOTALL | re.IGNORECASE)
    return result.strip()


def generate_rss_feed(releases, feed_name=FEED_NAME):
    """Generate RSS feed from GitHub releases."""
    fg = FeedGenerator()
    fg.title("OpenAI Codex Tags")
    fg.description("Stable releases from the OpenAI Codex repository")
    fg.language("en")
    fg.author({"name": "OpenAI"})
    setup_feed_links(fg, blog_url=TAGS_URL, feed_name=feed_name)

    items = []
    for r in releases:
        body = strip_changelog_section(r.get("body") or "")
        published_at = r.get("published_at")
        dt = None
        if published_at:
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        items.append(
            {
                "title": r.get("name") or r.get("tag_name"),
                "link": r.get("html_url"),
                "description": body,
                "date": dt,
            }
        )

    items_with_date = [i for i in items if i["date"]]
    items_without_date = [i for i in items if not i["date"]]
    items_with_date.sort(key=lambda x: x["date"])
    sorted_items = items_with_date + items_without_date

    for item in sorted_items:
        fe = fg.add_entry()
        fe.title(item["title"])
        fe.description(item["description"] or "No description available")
        fe.link(href=item["link"])
        fe.id(item["link"])
        if item["date"]:
            fe.published(item["date"])

    return fg


def main():
    releases = fetch_stable_releases()
    if not releases:
        logger.warning("No stable releases found")
        return False

    fg = generate_rss_feed(releases)
    output_file = get_feeds_dir() / f"feed_{FEED_NAME}.xml"
    fg.rss_file(str(output_file), pretty=True)
    logger.info(f"Saved {len(releases)} entries to {output_file}")
    return True


if __name__ == "__main__":
    main()
