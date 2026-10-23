import logging
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from feedgen.feed import FeedGenerator

from utils import get_feeds_dir, setup_feed_links, sort_posts_for_feed

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

RSS_URL = "https://www.jpcert.or.jp/rss/jpcert.rdf"
ALERTS_URL = "https://www.jpcert.or.jp/at/"
FEED_NAME = "jpcert_alerts"
TITLE_PREFIX = "注意喚起:"

NS = {
    "rss": "http://purl.org/rss/1.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def fetch_rss(url=RSS_URL):
    """Fetch the JPCERT/CC RSS 1.0 (RDF) feed."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def parse_alerts(rdf_content):
    """Keep only 注意喚起 items (the feed also carries Weekly Report items)."""
    root = ET.fromstring(rdf_content)
    alerts = []
    for item in root.findall("rss:item", NS):
        title = item.findtext("rss:title", default="", namespaces=NS).strip()
        if not title.startswith(TITLE_PREFIX):
            continue
        date_text = item.findtext("dc:date", namespaces=NS)
        alerts.append(
            {
                "title": title,
                "link": item.findtext("rss:link", namespaces=NS).strip(),
                "date": datetime.fromisoformat(date_text) if date_text else None,
            }
        )
    logger.info(f"Found {len(alerts)} alerts")
    return alerts


def generate_rss_feed(alerts, feed_name=FEED_NAME):
    """Generate RSS feed from JPCERT/CC alerts."""
    fg = FeedGenerator()
    fg.title("JPCERT/CC 注意喚起")
    fg.description("JPCERT/CC の注意喚起（Weekly Report を除く）")
    fg.language("ja")
    fg.author({"name": "JPCERT/CC"})
    setup_feed_links(fg, blog_url=ALERTS_URL, feed_name=feed_name)

    for alert in sort_posts_for_feed(alerts):
        fe = fg.add_entry()
        fe.title(alert["title"])
        fe.description(alert["title"])
        fe.link(href=alert["link"])
        fe.id(alert["link"])
        if alert["date"]:
            fe.published(alert["date"])

    return fg


def main():
    alerts = parse_alerts(fetch_rss())
    fg = generate_rss_feed(alerts)
    output_file = get_feeds_dir() / f"feed_{FEED_NAME}.xml"
    fg.rss_file(str(output_file), pretty=True)
    logger.info(f"Saved {len(alerts)} entries to {output_file}")


if __name__ == "__main__":
    main()
