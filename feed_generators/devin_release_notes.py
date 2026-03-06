import re
import time
import logging
from datetime import datetime
from pathlib import Path

import pytz
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from utils import sort_posts_for_feed

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent


def ensure_feeds_directory():
    """Ensure the feeds directory exists."""
    feeds_dir = get_project_root() / "feeds"
    feeds_dir.mkdir(exist_ok=True)
    return feeds_dir


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


def fetch_release_notes_selenium(url="https://docs.devin.ai/release-notes/overview"):
    """Fetch the fully loaded HTML content of the release notes page using Selenium."""
    driver = None
    try:
        logger.info(f"Fetching content from URL: {url}")
        driver = setup_selenium_driver()
        driver.get(url)

        # Wait for the page to fully load
        wait_time = 10
        logger.info(f"Waiting {wait_time} seconds for the page to fully load...")
        time.sleep(wait_time)

        # Wait for content to render
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article, main, [class*='content']"))
            )
            logger.info("Page content loaded successfully")
        except Exception:
            logger.warning("Could not confirm content loaded, proceeding anyway...")

        html_content = driver.page_source
        logger.info("Successfully fetched HTML content")
        return html_content

    except Exception as e:
        logger.error(f"Error fetching content: {e}")
        raise
    finally:
        if driver:
            driver.quit()


def parse_date(date_text):
    """Parse a date string using multiple format fallbacks."""
    date_formats = [
        "%B %d, %Y",
        "%b %d, %Y",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%B %d %Y",
        "%b %d %Y",
    ]
    cleaned = date_text.strip()
    for fmt in date_formats:
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=pytz.UTC)
        except ValueError:
            continue
    return None


def parse_release_notes_html(html_content):
    """Parse the release notes HTML content and extract update entries."""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        entries = []

        # Date pattern to identify date headings/labels in the rendered HTML
        date_pattern = re.compile(
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
            r"\s+\d{1,2},?\s+\d{4}"
        )

        # Strategy 1: Look for elements with date-like text that act as section headers.
        # The React <Update label="..."> components render with the label as visible text.
        # Find all text nodes matching date patterns and group content under them.
        all_text_elements = soup.find_all(string=date_pattern)
        logger.info(f"Found {len(all_text_elements)} date-matching text nodes")

        if all_text_elements:
            entries = _extract_entries_from_date_nodes(all_text_elements, date_pattern)

        # Strategy 2: If no date text nodes found, try looking for heading elements
        if not entries:
            logger.info("Trying heading-based extraction...")
            entries = _extract_entries_from_headings(soup, date_pattern)

        # Strategy 3: Broader search - any element containing a date pattern
        if not entries:
            logger.info("Trying broad element search...")
            entries = _extract_entries_from_broad_search(soup, date_pattern)

        logger.info(f"Successfully parsed {len(entries)} release note entries")
        return entries

    except Exception as e:
        logger.error(f"Error parsing HTML content: {str(e)}")
        raise


def _extract_entries_from_date_nodes(text_nodes, date_pattern):
    """Extract entries by finding date text nodes and collecting content below them."""
    entries = []
    seen_dates = set()

    for text_node in text_nodes:
        match = date_pattern.search(str(text_node))
        if not match:
            continue

        date_text = match.group(0)
        date = parse_date(date_text)
        if not date:
            continue

        # Get the parent element containing this date
        parent = text_node.parent if text_node.parent else None
        if not parent:
            continue

        # Find the section container - walk up to find a meaningful container
        section = _find_section_container(parent)

        # Extract title and description from the section content
        title, description = _extract_title_and_description(section, date_text)

        if not title:
            title = f"Release Notes - {date_text}"

        date_key = date_text
        if date_key in seen_dates:
            continue
        seen_dates.add(date_key)

        entries.append(
            {
                "title": title,
                "link": f"https://docs.devin.ai/release-notes/overview#{date_text.lower().replace(' ', '-').replace(',', '')}",
                "date": date,
                "description": description or title,
            }
        )

    return entries


def _extract_entries_from_headings(soup, date_pattern):
    """Extract entries by looking at heading elements for dates."""
    entries = []
    seen_dates = set()

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = heading.get_text(strip=True)
        match = date_pattern.search(text)
        if not match:
            continue

        date_text = match.group(0)
        date = parse_date(date_text)
        if not date or date_text in seen_dates:
            continue
        seen_dates.add(date_text)

        # Collect sibling content until next heading
        description_parts = []
        title = None
        for sibling in heading.find_next_siblings():
            if sibling.name and sibling.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                break
            sib_text = sibling.get_text(strip=True)
            if sib_text:
                if not title and (sibling.find("strong") or sibling.find("b")):
                    bold = sibling.find("strong") or sibling.find("b")
                    title = bold.get_text(strip=True)
                description_parts.append(sib_text)

        description = " ".join(description_parts[:5]) if description_parts else ""
        if not title:
            title = f"Release Notes - {date_text}"

        entries.append(
            {
                "title": title,
                "link": f"https://docs.devin.ai/release-notes/overview#{date_text.lower().replace(' ', '-').replace(',', '')}",
                "date": date,
                "description": description or title,
            }
        )

    return entries


def _extract_entries_from_broad_search(soup, date_pattern):
    """Broad search for any elements containing date patterns."""
    entries = []
    seen_dates = set()

    # Look for any element whose direct text matches a date pattern
    for elem in soup.find_all(True):
        # Only check direct text content, not nested children
        direct_text = elem.find(string=date_pattern, recursive=False)
        if not direct_text:
            # Check element's own text if it has no children with text
            if not elem.find_all(True):
                text = elem.get_text(strip=True)
                match = date_pattern.search(text)
                if not match:
                    continue
                date_text = match.group(0)
            else:
                continue
        else:
            match = date_pattern.search(str(direct_text))
            if not match:
                continue
            date_text = match.group(0)

        date = parse_date(date_text)
        if not date or date_text in seen_dates:
            continue
        seen_dates.add(date_text)

        # Try to extract content from parent or sibling elements
        section = _find_section_container(elem)
        title, description = _extract_title_and_description(section, date_text)

        if not title:
            title = f"Release Notes - {date_text}"

        entries.append(
            {
                "title": title,
                "link": f"https://docs.devin.ai/release-notes/overview#{date_text.lower().replace(' ', '-').replace(',', '')}",
                "date": date,
                "description": description or title,
            }
        )

    return entries


def _find_section_container(element):
    """Walk up the DOM to find a meaningful section container."""
    current = element
    for _ in range(5):
        parent = current.parent
        if not parent:
            break
        tag = parent.name or ""
        if tag in ["section", "article", "div"] and len(parent.get_text(strip=True)) > len(
            current.get_text(strip=True)
        ):
            current = parent
        else:
            break
    return current


def _extract_title_and_description(section, date_text):
    """Extract title and description from a section element."""
    title = None
    description_parts = []

    # Look for bold/strong text as title
    bold = section.find(["strong", "b"])
    if bold:
        bold_text = bold.get_text(strip=True)
        if bold_text and len(bold_text) >= 5 and bold_text != date_text:
            title = bold_text

    # Look for headings as title fallback
    if not title:
        for heading in section.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            heading_text = heading.get_text(strip=True)
            if heading_text and heading_text != date_text and len(heading_text) >= 5:
                title = heading_text
                break

    # Collect description from paragraphs and list items
    for elem in section.find_all(["p", "li"]):
        text = elem.get_text(strip=True)
        if text and text != date_text and text != title:
            description_parts.append(text)

    description = " ".join(description_parts[:5]) if description_parts else ""
    # Truncate long descriptions
    if len(description) > 500:
        description = description[:497] + "..."

    return title, description


def generate_rss_feed(entries, feed_name="devin_release_notes"):
    """Generate RSS feed from release note entries."""
    try:
        fg = FeedGenerator()
        fg.title("Devin Release Notes")
        fg.description("Latest release notes and updates from Devin AI")
        fg.language("en")

        # Set feed metadata
        fg.author({"name": "Cognition"})
        fg.subtitle("Latest release notes and updates from Devin AI")

        # Set feed links (self first, alternate last)
        fg.link(
            href=f"https://raw.githubusercontent.com/PIVOTIQ/info-feeds/main/feeds/feed_{feed_name}.xml",
            rel="self",
        )
        fg.link(href="https://docs.devin.ai/release-notes/overview", rel="alternate")

        # Sort entries for correct feed order (newest first in output)
        entries_sorted = sort_posts_for_feed(entries, date_field="date")

        # Add entries
        for entry in entries_sorted:
            fe = fg.add_entry()
            fe.title(entry["title"])
            fe.description(entry["description"])
            fe.link(href=entry["link"])

            if entry["date"]:
                fe.published(entry["date"])

            fe.id(entry["link"])

        logger.info("Successfully generated RSS feed")
        return fg

    except Exception as e:
        logger.error(f"Error generating RSS feed: {str(e)}")
        raise


def save_rss_feed(feed_generator, feed_name="devin_release_notes"):
    """Save the RSS feed to a file in the feeds directory."""
    try:
        feeds_dir = ensure_feeds_directory()
        output_filename = feeds_dir / f"feed_{feed_name}.xml"
        feed_generator.rss_file(str(output_filename), pretty=True)
        logger.info(f"Successfully saved RSS feed to {output_filename}")
        return output_filename

    except Exception as e:
        logger.error(f"Error saving RSS feed: {str(e)}")
        raise


def main(feed_name="devin_release_notes"):
    """Main function to generate RSS feed from Devin's release notes page."""
    try:
        # Fetch release notes content using Selenium
        html_content = fetch_release_notes_selenium()

        # Parse entries from HTML
        entries = parse_release_notes_html(html_content)

        if not entries:
            logger.warning("No entries found. Please check the HTML structure.")
            return False

        # Generate RSS feed
        feed = generate_rss_feed(entries, feed_name)

        # Save feed to file
        output_file = save_rss_feed(feed, feed_name)

        logger.info(f"Successfully generated RSS feed with {len(entries)} entries")
        return True

    except Exception as e:
        logger.error(f"Failed to generate RSS feed: {str(e)}")
        return False


if __name__ == "__main__":
    main()
