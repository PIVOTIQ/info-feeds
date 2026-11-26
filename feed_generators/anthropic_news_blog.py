import argparse
import json
import logging
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import pytz
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from utils import sort_posts_for_feed, missing_date

FEED_NAME = "anthropic_news"
BLOG_URL = "https://www.anthropic.com/news"

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


def get_cache_file():
    """Get the cache file path."""
    cache_dir = get_project_root() / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / f"{FEED_NAME}_posts.json"


def load_cache():
    """Load existing cache or return empty structure."""
    cache_file = get_cache_file()
    if cache_file.exists():
        with open(cache_file, "r") as f:
            data = json.load(f)
            logger.info(f"Loaded cache with {len(data.get('articles', []))} articles")
            return data
    logger.info("No cache file found, will do full fetch")
    return {"last_updated": None, "articles": []}


def save_cache(articles):
    """Save articles to cache file."""
    cache_file = get_cache_file()
    # Convert datetime objects to ISO strings for JSON serialization
    serializable_articles = []
    for article in articles:
        article_copy = article.copy()
        if isinstance(article_copy.get("date"), datetime):
            article_copy["date"] = article_copy["date"].isoformat()
        serializable_articles.append(article_copy)

    data = {
        "last_updated": datetime.now(pytz.UTC).isoformat(),
        "articles": serializable_articles,
    }
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved cache with {len(articles)} articles to {cache_file}")


def deserialize_articles(articles):
    """Convert cached articles back to proper format with datetime objects."""
    result = []
    for article in articles:
        article_copy = article.copy()
        if isinstance(article_copy.get("date"), str):
            try:
                article_copy["date"] = datetime.fromisoformat(article_copy["date"])
            except ValueError:
                article_copy["date"] = missing_date(
                    article_copy.get("link", "")
                )
        result.append(article_copy)
    return result


def merge_articles(new_articles, cached_articles):
    """Merge new articles into cache, dedupe by link, sort by date desc."""
    existing_links = {a["link"] for a in cached_articles}
    merged = list(cached_articles)

    added_count = 0
    for article in new_articles:
        if article["link"] not in existing_links:
            merged.append(article)
            existing_links.add(article["link"])
            added_count += 1

    logger.info(f"Added {added_count} new articles to cache")

    # Sort for correct feed order (newest first in output)
    return sort_posts_for_feed(merged, date_field="date")


def setup_selenium_driver():
    """Set up Selenium WebDriver with undetected-chromedriver."""
    options = uc.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    return uc.Chrome(options=options)


def fetch_news_content(url=BLOG_URL, max_clicks=20):
    """Fetch the fully loaded HTML content of the news page using Selenium.

    Args:
        url: The URL to fetch
        max_clicks: Maximum number of "See more" button clicks.
                   Use 20 for full fetch, 2-3 for incremental updates.
    """
    driver = None
    try:
        logger.info(f"Fetching content from URL: {url} (max_clicks={max_clicks})")
        driver = setup_selenium_driver()
        driver.get(url)

        # Wait for initial page load
        wait_time = 5
        logger.info(f"Waiting {wait_time} seconds for the page to fully load...")
        time.sleep(wait_time)

        # Wait for news articles to be present
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/news/']"))
            )
            logger.info("News articles loaded successfully")
        except Exception:
            logger.warning("Could not confirm articles loaded, proceeding anyway...")

        # Click "See more" button repeatedly until it's no longer available
        clicks = 0
        while clicks < max_clicks:
            try:
                # Look for the "See more" button using multiple selectors
                see_more_button = None
                selectors = [
                    "[class*='seeMore']",
                    "[class*='see-more']",
                    "button[class*='More']",
                ]
                for selector in selectors:
                    try:
                        see_more_button = driver.find_element(By.CSS_SELECTOR, selector)
                        if see_more_button and see_more_button.is_displayed():
                            break
                        see_more_button = None
                    except Exception:
                        continue

                # Also try finding by text content using XPath
                if not see_more_button:
                    try:
                        see_more_button = driver.find_element(
                            By.XPATH,
                            "//*[contains(text(), 'See more') or contains(text(), 'Load more')]",
                        )
                    except Exception:
                        pass

                if see_more_button and see_more_button.is_displayed():
                    logger.info(f"Clicking 'See more' button (click {clicks + 1})...")
                    driver.execute_script("arguments[0].click();", see_more_button)
                    clicks += 1
                    time.sleep(2)  # Wait for content to load
                else:
                    logger.info(
                        f"No more 'See more' button found after {clicks} clicks"
                    )
                    break
            except Exception as e:
                # No more "See more" button found
                logger.info(
                    f"No more 'See more' button found after {clicks} clicks: {e}"
                )
                break

        html_content = driver.page_source
        logger.info("Successfully fetched HTML content")
        return html_content

    except Exception as e:
        logger.error(f"Error fetching content: {e}")
        raise
    finally:
        if driver:
            driver.quit()


DATE_FORMATS = ["%b %d, %Y", "%B %d, %Y"]


def parse_date(text):
    """Parse a listing date such as 'Nov 20, 2026'. Returns None if it does not parse."""
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), date_format).replace(tzinfo=pytz.UTC)
        except ValueError:
            continue
    return None


HEADINGS = ["h2", "h3", "h4"]


def parse_news_html(html_content):
    """Parse the news listing and return (articles, problems).

    Each article is one <li> row of the listing: a heading inside a link, and a
    <time> that sits next to the link (not inside it). Model launches link
    outside /news/ (e.g. /claude-opus-5-5), so rows are not filtered by href.
    Dates are never made up: a row without a parseable <time>, or with more
    than one article link, is returned in problems so the caller can fail loudly.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []
    problems = []
    seen_links = set()

    for row in soup.find_all("li"):
        heading_links = [a for a in row.find_all("a", href=True) if a.find(HEADINGS)]
        if not heading_links:
            continue

        article_hrefs = {a["href"] for a in heading_links}
        if len(article_hrefs) != 1:
            problems.append(f"row with {len(article_hrefs)} article links")
            continue

        link = urljoin(BLOG_URL, article_hrefs.pop())
        if link in seen_links:
            continue
        seen_links.add(link)

        title = heading_links[0].find(HEADINGS).get_text(" ", strip=True)
        time_elem = row.find("time")
        date = parse_date(time_elem.get_text()) if time_elem else None
        if not date:
            date_text = time_elem.get_text() if time_elem else None
            problems.append(f"no parseable date ({date_text!r}): {title}")
            continue

        category_link = next(
            (
                a
                for a in row.find_all("a", href=True)
                if urljoin(BLOG_URL, a["href"]) != link
            ),
            None,
        )
        category = category_link.get_text(strip=True) if category_link else "News"

        articles.append(
            {
                "title": title,
                "link": link,
                "date": date,
                "category": category,
                "description": title,
            }
        )

    for problem in problems:
        logger.error(f"Unreadable listing row: {problem}")
    logger.info(f"Parsed {len(articles)} articles, {len(problems)} unreadable rows")
    return articles, problems


def generate_rss_feed(articles, feed_name="anthropic_news"):
    """Generate RSS feed from news articles."""
    try:
        fg = FeedGenerator()
        fg.title("Anthropic News")
        fg.description("Latest news and updates from Anthropic")
        fg.language("en")

        # Set feed metadata
        fg.author({"name": "Anthropic News"})
        fg.logo("https://www.anthropic.com/images/icons/apple-touch-icon.png")
        fg.subtitle("Latest updates from Anthropic's newsroom")
        # Set links - self link first, then alternate (which becomes the main <link>)
        fg.link(
            href=f"https://www.anthropic.com/feeds/feed_{feed_name}.xml", rel="self"
        )
        fg.link(href="https://www.anthropic.com/news", rel="alternate")

        # Sort articles for correct feed order (newest first in output)
        articles_sorted = sort_posts_for_feed(articles, date_field="date")

        # Add entries
        for article in articles_sorted:
            fe = fg.add_entry()
            fe.title(article["title"])
            fe.description(article["description"])
            fe.link(href=article["link"])
            fe.published(article["date"])
            fe.category(term=article["category"])
            fe.id(article["link"])

        logger.info("Successfully generated RSS feed")
        return fg

    except Exception as e:
        logger.error(f"Error generating RSS feed: {str(e)}")
        raise


def save_rss_feed(feed_generator, feed_name="anthropic_news"):
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


def get_existing_links_from_feed(feed_path):
    """Parse the existing RSS feed and return a set of all article links."""
    existing_links = set()
    try:
        if not feed_path.exists():
            return existing_links
        tree = ET.parse(feed_path)
        root = tree.getroot()
        # RSS 2.0: items under channel/item
        for item in root.findall("./channel/item"):
            link_elem = item.find("link")
            if link_elem is not None and link_elem.text:
                existing_links.add(link_elem.text.strip())
    except Exception as e:
        logger.warning(f"Failed to parse existing feed for deduplication: {str(e)}")
    return existing_links


def main(full_reset=False):
    """Main function to generate RSS feed from Anthropic's news page.

    Args:
        full_reset: If True, fetch all articles (click "See more" up to 20 times).
                   If False, do incremental update (click 2-3 times, merge with cache).
    """
    try:
        cache = load_cache()
        cached_articles = deserialize_articles(cache.get("articles", []))

        if full_reset or not cached_articles:
            mode = "full reset" if full_reset else "no cache exists"
            logger.info(f"Running full fetch ({mode})")
            html_content = fetch_news_content(max_clicks=20)
        else:
            logger.info("Running incremental update (2 clicks only)")
            html_content = fetch_news_content(max_clicks=2)

        new_articles, problems = parse_news_html(html_content)

        # Fail (exit 1) instead of publishing a feed with missing or made-up dates
        if problems:
            logger.error(
                f"{len(problems)} listing row(s) could not be read; the listing's "
                "structure or date format may have changed. Feed not updated."
            )
            return False
        if not new_articles:
            logger.error(
                "No articles parsed from the listing; the HTML structure may "
                "have changed. Feed not updated."
            )
            return False

        if full_reset or not cached_articles:
            articles = new_articles
        else:
            articles = merge_articles(new_articles, cached_articles)

        # Save to cache
        save_cache(articles)

        # Generate RSS feed with all articles
        feed = generate_rss_feed(articles, FEED_NAME)

        # Save feed to file
        output_file = save_rss_feed(feed, FEED_NAME)

        logger.info(f"Successfully generated RSS feed with {len(articles)} articles")
        return True

    except Exception as e:
        logger.error(f"Failed to generate RSS feed: {str(e)}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Anthropic News RSS feed")
    parser.add_argument(
        "--full", action="store_true", help="Force full reset (fetch all articles)"
    )
    args = parser.parse_args()
    sys.exit(0 if main(full_reset=args.full) else 1)
