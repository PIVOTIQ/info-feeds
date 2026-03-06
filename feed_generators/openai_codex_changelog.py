import logging
from datetime import datetime
from pathlib import Path

import pytz
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

from utils import setup_feed_links, sort_posts_for_feed

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BLOG_URL = "https://developers.openai.com/codex/changelog/"
FEED_NAME = "openai_codex_changelog"


def get_project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent


def ensure_feeds_directory():
    """Ensure the feeds directory exists and return its path."""
    feeds_dir = get_project_root() / "feeds"
    feeds_dir.mkdir(exist_ok=True)
    return feeds_dir


def fetch_changelog_page(url=BLOG_URL):
    """Fetch the changelog page HTML."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Error fetching changelog page: {str(e)}")
        raise


def parse_changelog_entries(html_content):
    """Parse changelog entries from the HTML page.

    Each entry is an <li class="scroll-mt-28"> containing:
    - <time> element with YYYY-MM-DD date text
    - <h3> element with the entry title
    - <article class="prose-content"> or <div class="prose-content"> with description HTML
    """
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        entries = soup.select("li.scroll-mt-28")
        items = []

        for entry in entries:
            # Extract date from <time> element
            time_elem = entry.select_one("time")
            date_str = time_elem.get_text(strip=True) if time_elem else None

            # Extract title from <h3> element
            h3_elem = entry.select_one("h3")
            if not h3_elem:
                continue
            title = h3_elem.get_text(strip=True)

            # Extract description from prose-content (article or div)
            prose_elem = entry.select_one(".prose-content")
            description = ""
            if prose_elem:
                description = prose_elem.decode_contents().strip()

            # Build a unique link for each entry using date and title slug
            entry_id = f"{BLOG_URL}#{date_str}-{title}" if date_str else f"{BLOG_URL}#{title}"

            items.append(
                {
                    "title": title,
                    "link": entry_id,
                    "description": description,
                    "date": date_str,
                }
            )

        logger.info(f"Successfully parsed {len(items)} changelog entries")
        return items

    except Exception as e:
        logger.error(f"Error parsing changelog entries: {str(e)}")
        raise


def generate_rss_feed(items, feed_name=FEED_NAME):
    """Generate RSS feed from parsed changelog entries."""
    try:
        fg = FeedGenerator()
        fg.title("OpenAI Codex Changelog")
        fg.description("Latest updates and changes from OpenAI Codex")
        fg.language("en")

        fg.author({"name": "OpenAI"})
        fg.subtitle("OpenAI Codex Changelog")
        setup_feed_links(fg, blog_url=BLOG_URL, feed_name=feed_name)

        # Sort ascending (oldest first) - feedgen reverses to newest first
        sorted_items = sort_posts_for_feed(items, date_field="date")

        for item in sorted_items:
            fe = fg.add_entry()
            fe.title(item["title"])
            fe.description(item["description"])
            fe.link(href=item["link"])
            fe.id(item["link"])

            if item.get("date"):
                try:
                    dt = datetime.strptime(item["date"], "%Y-%m-%d")
                    fe.published(dt.replace(tzinfo=pytz.UTC))
                except ValueError:
                    pass

        logger.info(f"Successfully generated RSS feed with {len(sorted_items)} entries")
        return fg

    except Exception as e:
        logger.error(f"Error generating RSS feed: {str(e)}")
        raise


def save_rss_feed(feed_generator, feed_name=FEED_NAME):
    """Save the RSS feed to a file."""
    try:
        feeds_dir = ensure_feeds_directory()
        output_file = feeds_dir / f"feed_{feed_name}.xml"
        feed_generator.rss_file(str(output_file), pretty=True)
        logger.info(f"Successfully saved RSS feed to {output_file}")
        return output_file
    except Exception as e:
        logger.error(f"Error saving RSS feed: {str(e)}")
        raise


def main(feed_name=FEED_NAME):
    """Main function to generate RSS feed from OpenAI Codex changelog."""
    try:
        html_content = fetch_changelog_page()
        items = parse_changelog_entries(html_content)

        if not items:
            logger.warning("No changelog entries found")
            return False

        feed = generate_rss_feed(items, feed_name)
        save_rss_feed(feed, feed_name)

        logger.info(f"Successfully generated RSS feed with {len(items)} items")
        return True

    except Exception as e:
        logger.error(f"Failed to generate RSS feed: {str(e)}")
        return False


if __name__ == "__main__":
    main()
