import json
import logging
import re
from datetime import datetime

import pytz
import requests
from feedgen.feed import FeedGenerator

from utils import get_feeds_dir, setup_feed_links, sort_posts_for_feed

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BLOG_URL = "https://www.pwc.com/jp/ja/knowledge/thoughtleadership.html"
FEED_NAME = "pwc_japan"


def fetch_blog_content(url):
    """Fetch blog content from the given URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return response.text


def extract_articles_from_embedded_json(html_content):
    """Extract articles from the embedded JSON in loadFacetedNavigation calls.

    PwC uses Angular with inline JSON data that is triple-escaped in the HTML.
    This function extracts article metadata from the first collection (main reports).
    """
    articles = []

    # Find lines containing loadFacetedNavigation with numberHits (article data)
    # The first collection contains the main thought leadership reports
    lines = html_content.split("\n")

    for line in lines:
        if "numberHits" not in line or "elements" not in line:
            continue

        # Extract the JSON argument containing article data
        # The data is inside a JS string with \x22 escaping for quotes
        idx = line.find("numberHits")
        if idx == -1:
            continue

        # Find the start of this JSON argument (opening quote)
        start = line.rfind('"', 0, idx) + 1
        # Find the end (closing quote before next argument or closing paren)
        end_match = re.search(r'"\s*[,)]', line[start:])
        if not end_match:
            continue
        raw = line[start : start + end_match.start()]

        # Level 1 unescape: \x22 -> "
        s = raw.replace("\\x22", '"')

        # Extract numberHits to identify the main collection (100 items)
        num_match = re.search(r'"numberHits":(\d+)', s)
        if not num_match:
            continue
        num_hits = int(num_match.group(1))

        # Only process the main collection (larger set)
        if num_hits < 30:
            continue

        # Extract individual article data using regex on the escaped content
        # Each article has: href, title, text, publishDate, isPage
        # The data has additional escaping: \\\\" for nested quotes
        article_blocks = re.split(r'\\\\\\x22index\\\\\\x22:\d+', line)

        for block in article_blocks[1:]:  # Skip first (before first article)
            href_m = re.search(r'\\\\\\x22href\\\\\\x22:\\\\\\x22(.*?)\\\\\\x22', block)
            title_m = re.search(r'\\\\\\x22title\\\\\\x22:\\\\\\x22(.*?)\\\\\\x22', block)
            text_m = re.search(r'\\\\\\x22text\\\\\\x22:\\\\\\x22(.*?)\\\\\\x22', block)
            date_m = re.search(r'\\\\\\x22publishDate\\\\\\x22:\\\\\\x22(.*?)\\\\\\x22', block)
            ispage_m = re.search(r'\\\\\\x22isPage\\\\\\x22:(true|false)', block)

            if not (href_m and title_m):
                continue

            href = href_m.group(1).replace("\\/", "/").replace("\\u002D", "-")
            title = title_m.group(1).replace("\\u002D", "-").replace("\\u2015", "\u2015")
            text = text_m.group(1).replace("\\u002D", "-") if text_m else ""
            date_str = date_m.group(1).replace("\\u002D", "-") if date_m else ""
            is_page = ispage_m.group(1) == "true" if ispage_m else True

            # Only include page-type articles (not PDFs)
            if is_page and title and href:
                articles.append({
                    "title": title,
                    "url": href,
                    "date": date_str,
                    "description": text[:200] if text else "",
                })

        if articles:
            break  # Only process the first matching collection

    logger.info(f"Extracted {len(articles)} articles from embedded JSON")
    return articles


def parse_date(date_str):
    """Parse PwC date format (YY/MM/DD or YYYY-MM-DD)."""
    formats = ["%y/%m/%d", "%Y-%m-%d", "%Y/%m/%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def generate_rss_feed(articles):
    """Generate RSS feed from articles."""
    fg = FeedGenerator()
    fg.title("PwC Japan 調査／レポート")
    fg.description("PwC Japanグループによる調査レポート・ソートリーダーシップ")
    fg.language("ja")
    fg.author({"name": "PwC Japan"})
    fg.logo("https://www.pwc.com/etc/designs/pwc/images/favicon.ico")
    fg.subtitle("PwC Japan Thought Leadership")
    setup_feed_links(fg, blog_url=BLOG_URL, feed_name=FEED_NAME)

    sorted_articles = sort_posts_for_feed(articles, date_field="date")

    for article in sorted_articles:
        fe = fg.add_entry()
        fe.title(article["title"])
        fe.link(href=article["url"])
        fe.id(article["url"])

        if article.get("description"):
            fe.description(article["description"])

        if article.get("date"):
            dt = parse_date(article["date"])
            if dt:
                fe.published(dt.replace(tzinfo=pytz.timezone("Asia/Tokyo")))

    logger.info(f"Generated RSS feed with {len(sorted_articles)} entries")
    return fg


def save_rss_feed(feed_generator):
    """Save the RSS feed to a file."""
    feeds_dir = get_feeds_dir()
    output_file = feeds_dir / f"feed_{FEED_NAME}.xml"
    feed_generator.rss_file(str(output_file), pretty=True)
    logger.info(f"Saved RSS feed to {output_file}")
    return output_file


def main():
    """Main function to generate PwC Japan RSS feed."""
    html_content = fetch_blog_content(BLOG_URL)
    articles = extract_articles_from_embedded_json(html_content)
    feed = generate_rss_feed(articles)
    save_rss_feed(feed)
    logger.info("Done!")
    return True


if __name__ == "__main__":
    main()
