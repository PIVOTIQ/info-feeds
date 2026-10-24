import logging
from datetime import datetime, timezone

import requests
from feedgen.feed import FeedGenerator

from utils import get_feeds_dir, load_published_dates, setup_feed_links

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

KEV_JSON_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
CATALOG_URL = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
FEED_NAME = "cisa_kev"
MAX_ITEMS = 100


def fetch_vulnerabilities(url=KEV_JSON_URL):
    """Fetch the CISA Known Exploited Vulnerabilities catalog (JSON)."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    vulnerabilities = response.json()["vulnerabilities"]
    logger.info(f"Fetched {len(vulnerabilities)} vulnerabilities from {url}")
    return vulnerabilities


def latest_vulnerabilities(vulnerabilities, limit=MAX_ITEMS):
    """Return the newest entries by dateAdded (newest first).

    The sort is stable, so entries added on the same day keep the catalog's own order.
    """
    return sorted(vulnerabilities, key=lambda v: v["dateAdded"], reverse=True)[:limit]


def build_description(v):
    return "\n".join(
        [
            v.get("shortDescription", ""),
            "",
            f"Required action: {v.get('requiredAction', '')}",
            f"Due date: {v.get('dueDate', '')}",
            f"Known ransomware campaign use: {v.get('knownRansomwareCampaignUse', '')}",
        ]
    )


def generate_rss_feed(vulnerabilities, published_dates, now, feed_name=FEED_NAME):
    """Generate RSS feed with one item per CVE.

    pubDate is when the CVE first reached this feed (see load_published_dates); new CVEs get now.
    """
    fg = FeedGenerator()
    fg.title("CISA Known Exploited Vulnerabilities")
    fg.description("Latest additions to the CISA Known Exploited Vulnerabilities (KEV) catalog")
    fg.language("en")
    fg.author({"name": "CISA"})
    setup_feed_links(fg, blog_url=CATALOG_URL, feed_name=feed_name)

    entries = []
    for v in reversed(vulnerabilities):
        link = f"https://nvd.nist.gov/vuln/detail/{v['cveID']}"
        entries.append((published_dates.get(link, now), link, v))
    # Order by pubDate so a CVE first seen now sits on top even if its dateAdded is older.
    # feedgen prepends each entry, so add oldest first; the stable sort keeps catalog order on ties
    entries.sort(key=lambda e: e[0])

    for published, link, v in entries:
        fe = fg.add_entry()
        fe.title(f"{v['cveID']}: {v['vendorProject']} {v['product']} — {v['vulnerabilityName']}")
        fe.description(build_description(v))
        fe.link(href=link)
        fe.id(link)
        fe.published(published)

    return fg


def main():
    vulnerabilities = latest_vulnerabilities(fetch_vulnerabilities())
    fg = generate_rss_feed(vulnerabilities, load_published_dates(FEED_NAME), datetime.now(timezone.utc))
    output_file = get_feeds_dir() / f"feed_{FEED_NAME}.xml"
    fg.rss_file(str(output_file), pretty=True)
    logger.info(f"Saved {len(vulnerabilities)} entries to {output_file}")


if __name__ == "__main__":
    main()
