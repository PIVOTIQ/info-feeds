"""Parser tests for thinkingmachines_blog against a saved copy of the real listing.

tests/fixtures/thinkingmachines_blog.html is https://thinkingmachines.ai/blog/ as
served on 2026-11-27. Expected dates come from the articles' own pages, not from
the parser.
"""

from datetime import date
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

import thinkingmachines_blog
from utils import MissingDateError

LISTING = (Path(__file__).parent / "fixtures" / "thinkingmachines_blog.html").read_text(encoding="utf-8")


def test_newest_article_has_its_publish_date():
    articles = thinkingmachines_blog.parse_html(LISTING)

    newest = max(articles, key=lambda a: a["pub_date"])
    assert newest["link"] == "https://thinkingmachines.ai/blog/end-to-end-4-bit-training/"
    assert newest["title"] == "End‑to‑End 4‑Bit Training"
    assert newest["pub_date"].date() == date(2026, 11, 13)


def test_row_without_time_raises():
    listing = LISTING.replace(
        '<time datetime="2026-11-13" data-astro-cid-jcsiju5y>Nov 13, 2026</time>', "", 1
    )
    assert listing != LISTING

    with pytest.raises(MissingDateError):
        thinkingmachines_blog.extract_articles(BeautifulSoup(listing, "html.parser"))


def test_listing_without_rows_raises():
    with pytest.raises(ValueError):
        thinkingmachines_blog.extract_articles(BeautifulSoup("<main></main>", "html.parser"))
