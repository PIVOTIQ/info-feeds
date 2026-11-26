import sys
import requests
from feedgen.feed import FeedGenerator
import logging
from pathlib import Path

from utils import parse_anthropic_listing, sort_posts_for_feed

# red.anthropic.com now redirects (301) to this team page on anthropic.com
BLOG_URL = "https://www.anthropic.com/research/team/frontier-red-team"

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent


def ensure_feeds_directory():
    """Ensure the feeds directory exists."""
    feeds_dir = get_project_root() / "feeds"
    feeds_dir.mkdir(exist_ok=True)
    return feeds_dir


def fetch_red_content(url=BLOG_URL):
    """Fetch content from Anthropic's red team blog."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Error fetching red team blog content: {str(e)}")
        raise


def parse_red_html(html_content):
    """Parse the Frontier Red Team listing and return (articles, problems).

    The page uses the shared anthropic.com listing (one <article> row per post, the
    date in a <time> next to the link). Rows without a readable date go to problems.
    """
    articles, problems = parse_anthropic_listing(html_content, BLOG_URL)
    for problem in problems:
        logger.error(f"Unreadable listing row: {problem}")
    logger.info(f"Parsed {len(articles)} articles, {len(problems)} unreadable rows")
    return articles, problems


def generate_rss_feed(articles, feed_name="anthropic_red"):
    """Generate RSS feed from red team blog articles."""
    try:
        fg = FeedGenerator()
        fg.title("Anthropic Frontier Red Team Blog")
        fg.description(
            "Research from Anthropic's Frontier Red Team on what frontier AI models mean for national security"
        )
        fg.link(href="https://red.anthropic.com/")
        fg.language("en")

        # Set feed metadata
        fg.author({"name": "Anthropic Frontier Red Team"})
        fg.logo("https://www.anthropic.com/images/icons/apple-touch-icon.png")
        fg.subtitle(
            "Evidence-based analysis about AI's implications for cybersecurity, biosecurity, and autonomous systems"
        )
        fg.link(href="https://red.anthropic.com/", rel="alternate")
        fg.link(href=f"https://anthropic.com/feed_{feed_name}.xml", rel="self")

        # Sort articles for correct feed order (newest first in output)
        sorted_articles = sort_posts_for_feed(articles, date_field="date")

        # Add entries
        for article in sorted_articles:
            fe = fg.add_entry()
            fe.title(article["title"])
            fe.description(article["description"])
            fe.link(href=article["link"])
            fe.published(article["date"])
            fe.id(article["link"])

        logger.info("Successfully generated RSS feed")
        return fg

    except Exception as e:
        logger.error(f"Error generating RSS feed: {str(e)}")
        raise


def save_rss_feed(feed_generator, feed_name="anthropic_red"):
    """Save the RSS feed to a file in the feeds directory."""
    try:
        # Ensure feeds directory exists and get its path
        feeds_dir = ensure_feeds_directory()

        # Create the output file path
        output_filename = feeds_dir / f"feed_{feed_name}.xml"

        # Save the feed
        feed_generator.rss_file(str(output_filename), pretty=True)
        logger.info(f"Successfully saved RSS feed to {output_filename}")
        return output_filename

    except Exception as e:
        logger.error(f"Error saving RSS feed: {str(e)}")
        raise


def main(feed_name="anthropic_red"):
    """Main function to generate RSS feed from Anthropic's red team blog."""
    try:
        # Fetch blog content
        html_content = fetch_red_content()

        # Parse articles from HTML
        articles, problems = parse_red_html(html_content)

        # Fail (exit 1) instead of publishing a feed with missing or made-up dates
        if problems:
            logger.error(
                f"{len(problems)} listing row(s) could not be read; the listing's "
                "structure or date format may have changed. Feed not updated."
            )
            return False
        if not articles:
            logger.error(
                "No articles parsed from the listing; the HTML structure may "
                "have changed. Feed not updated."
            )
            return False

        # Generate RSS feed
        feed = generate_rss_feed(articles, feed_name)

        # Save feed to file
        output_file = save_rss_feed(feed, feed_name)

        logger.info(f"Successfully generated RSS feed with {len(articles)} articles")
        return True

    except Exception as e:
        logger.error(f"Failed to generate RSS feed: {str(e)}")
        return False


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
