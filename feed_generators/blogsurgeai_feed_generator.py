#!/usr/bin/env python3
"""
RSS Feed Generator for Surge AI Blog
Scrapes https://www.surgehq.ai/blog and generates an RSS feed
"""

import sys
import logging

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime
from dateutil import parser
import pytz

from utils import missing_date, MissingDateError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def generate_blogsurgeai_feed():
    """Generate RSS feed for Surge AI blog"""

    # Initialize feed generator
    fg = FeedGenerator()
    fg.id("https://www.surgehq.ai/blog")
    fg.title("Surge AI Blog")
    fg.author({"name": "Surge AI", "email": "team@surgehq.ai"})
    fg.link(href="https://www.surgehq.ai/blog", rel="alternate")
    fg.link(
        href="https://raw.githubusercontent.com/PIVOTIQ/info-feeds/main/feeds/feed_blogsurgeai.xml",
        rel="self",
    )
    fg.language("en")
    fg.description(
        "New methods, current trends & software infrastructure for NLP. Articles written by our senior engineering leads from Google, Facebook, Twitter, Harvard, MIT, and Y Combinator"
    )

    # Fetch the blog page
    url = "https://www.surgehq.ai/blog"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Error fetching blog page: {e}")
        return False

    # Parse HTML
    soup = BeautifulSoup(response.content, "html.parser")

    # Find all blog post items
    blog_items = soup.find_all("div", class_="blog-hero-cms-item")

    logger.info(f"Found {len(blog_items)} blog posts")
    if not blog_items:
        logger.error("No blog posts found; the page structure may have changed")
        return False

    # Process each blog post
    added = 0
    for item in blog_items:
        try:
            # Find the title
            title_element = item.find("div", class_="blog-hero-cms-item-title")
            if not title_element:
                continue

            title = title_element.get_text(strip=True)

            # Find the link
            link_element = item.find("a", class_="blog-hero-cms-item-link")
            if not link_element:
                continue

            link = link_element.get("href")
            if not link.startswith("http"):
                link = "https://www.surgehq.ai" + link

            # Find the description
            desc_element = item.find("div", class_="blog-hero-cms-item-desc")
            description = desc_element.get_text(strip=True) if desc_element else title

            # Find the date
            date_element = item.find("div", class_="blog-hero-cms-item-date")
            pub_date = None  # Will be set by parsing or fallback

            if date_element:
                # Find the visible date element (the one without w-condition-invisible)
                date_texts = date_element.find_all("div", class_="txt fs-12 inline")
                for date_text in date_texts:
                    if "w-condition-invisible" not in date_text.get("class", []):
                        date_str = date_text.get_text(strip=True)
                        try:
                            # Parse the date string (e.g., "October 10, 2025")
                            pub_date = parser.parse(date_str)
                            # Make timezone-aware
                            if pub_date.tzinfo is None:
                                pub_date = pytz.UTC.localize(pub_date)
                            break
                        except Exception as e:
                            logger.warning(f"Could not parse date '{date_str}': {e}")

            # Use stable fallback if no date was parsed
            if pub_date is None:
                pub_date = missing_date(link)

            # Create feed entry
            fe = fg.add_entry()
            fe.id(link)
            fe.title(title)
            fe.link(href=link)
            fe.published(pub_date)

            # Set description
            fe.description(description)

            logger.info(f"Added: {title}")
            added += 1

        except MissingDateError:
            raise
        except Exception as e:
            logger.error(f"Error processing blog item: {e}")
            continue

    if added == 0:
        logger.error("No blog post could be read; the page structure may have changed")
        return False

    # Generate RSS feed
    output_path = "feeds/feed_blogsurgeai.xml"
    fg.rss_file(output_path, pretty=True)
    logger.info(f"RSS feed generated successfully: {output_path}")
    return True


if __name__ == "__main__":
    sys.exit(0 if generate_blogsurgeai_feed() else 1)
