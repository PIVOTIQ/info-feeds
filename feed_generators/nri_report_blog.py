import logging
from datetime import datetime

import pytz
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

from utils import get_feeds_dir, setup_feed_links, sort_posts_for_feed

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BLOG_URL = "https://www.nri.com/jp/knowledge/report"
FEED_NAME = "nri_report"


def fetch_blog_content(url):
    """Fetch blog content from the given URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return response.text


def parse_blog_html(html_content):
    """Parse the NRI report HTML and extract report information."""
    soup = BeautifulSoup(html_content, "html.parser")
    reports = []

    card_list = soup.find("ul", id="target-category")
    if not card_list:
        logger.warning("Could not find report list (ul#target-category)")
        return reports

    for li in card_list.find_all("li", recursive=False):
        a_tag = li.find("a")
        if not a_tag or not a_tag.get("href"):
            continue

        href = a_tag["href"]
        if not href.startswith("http"):
            href = f"https://www.nri.com{href}"

        title_el = a_tag.find("h3", class_="--title")
        title = title_el.get_text(strip=True) if title_el else ""

        time_el = a_tag.find("time", class_="--date")
        date_str = time_el.get("datetime", "") if time_el else ""

        category_el = a_tag.find("span", class_="lbl-category")
        category = category_el.get_text(strip=True) if category_el else ""

        if title:
            reports.append({
                "title": title,
                "url": href,
                "date": date_str,
                "category": category,
            })

    logger.info(f"Parsed {len(reports)} reports")
    return reports


def generate_rss_feed(reports):
    """Generate RSS feed from reports."""
    fg = FeedGenerator()
    fg.title("野村総合研究所(NRI) レポート")
    fg.description("野村総合研究所グループの提言・調査レポート")
    fg.language("ja")
    fg.author({"name": "野村総合研究所"})
    fg.logo("https://www.nri.com/favicon.ico")
    fg.subtitle("NRI ナレッジ・インサイト レポート")
    setup_feed_links(fg, blog_url=BLOG_URL, feed_name=FEED_NAME)

    sorted_reports = sort_posts_for_feed(reports, date_field="date")

    for report in sorted_reports:
        fe = fg.add_entry()
        fe.title(report["title"])
        fe.link(href=report["url"])
        fe.id(report["url"])

        if report.get("date"):
            try:
                dt = datetime.strptime(report["date"], "%Y-%m-%d")
                fe.published(dt.replace(tzinfo=pytz.timezone("Asia/Tokyo")))
            except ValueError:
                pass

        if report.get("category"):
            fe.category(term=report["category"])

    logger.info(f"Generated RSS feed with {len(sorted_reports)} entries")
    return fg


def save_rss_feed(feed_generator):
    """Save the RSS feed to a file."""
    feeds_dir = get_feeds_dir()
    output_file = feeds_dir / f"feed_{FEED_NAME}.xml"
    feed_generator.rss_file(str(output_file), pretty=True)
    logger.info(f"Saved RSS feed to {output_file}")
    return output_file


def main():
    """Main function to generate NRI report RSS feed."""
    html_content = fetch_blog_content(BLOG_URL)
    reports = parse_blog_html(html_content)
    feed = generate_rss_feed(reports)
    save_rss_feed(feed)
    logger.info("Done!")
    return True


if __name__ == "__main__":
    main()
