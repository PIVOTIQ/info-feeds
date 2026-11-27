"""Parser tests for deeplearningai_the_batch against a saved copy of the real listing.

tests/fixtures/the_batch.html is https://www.deeplearning.ai/the-batch/ (page 1) as
served on 2026-11-27. Expected dates come from the issues' own pages
(``datePublished``), not from the parser.
"""

from datetime import date
from pathlib import Path

import pytest

import deeplearningai_the_batch
from utils import MissingDateError

LISTING = (Path(__file__).parent / "fixtures" / "the_batch.html").read_text(encoding="utf-8")


def test_newest_issue_has_its_publish_date():
    articles = deeplearningai_the_batch.parse_articles_from_html(LISTING)

    newest = max(articles, key=lambda a: a["published"])
    assert newest["link"] == "https://www.deeplearning.ai/the-batch/issue-380"
    assert newest["published"].date() == date(2026, 11, 20)


def test_popular_sidebar_cards_are_skipped():
    articles = deeplearningai_the_batch.parse_articles_from_html(LISTING)

    links = {a["link"] for a in articles}
    assert "https://www.deeplearning.ai/the-batch/introducing-deeplearning-ai-pro" not in links
    assert "https://www.deeplearning.ai/the-batch/issue-286" not in links
    assert len(articles) == 16


def test_listing_card_without_date_tag_raises():
    listing = LISTING.replace('href="/the-batch/tag/nov-13-2026"', 'href="/the-batch/tag/research"', 1)
    assert listing != LISTING

    with pytest.raises(MissingDateError):
        deeplearningai_the_batch.parse_articles_from_html(listing)
