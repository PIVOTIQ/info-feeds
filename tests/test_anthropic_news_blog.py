"""Parser tests for anthropic_news_blog against a saved copy of the real listing.

tests/fixtures/anthropic_news.html is https://www.anthropic.com/news as served
on 2026-11-26 (first page, before any "See more" click). Expected dates come
from the articles' own pages, not from the parser.
"""

from datetime import date
from pathlib import Path

import anthropic_news_blog

LISTING = (Path(__file__).parent / "fixtures" / "anthropic_news.html").read_text()


def test_newest_article_has_its_publish_date():
    articles, problems = anthropic_news_blog.parse_news_html(LISTING)

    assert problems == []
    newest = max(articles, key=lambda a: a["date"])
    assert newest["link"] == "https://www.anthropic.com/news/ipo-close"
    assert newest["date"].date() == date(2026, 11, 20)


def test_model_launch_outside_news_path_is_included():
    articles, _ = anthropic_news_blog.parse_news_html(LISTING)

    by_link = {a["link"]: a for a in articles}
    launch = by_link["https://www.anthropic.com/claude-fable-and-mythos-5-2"]
    assert launch["date"].date() == date(2026, 11, 9)


def test_row_without_time_is_reported_as_a_problem():
    listing = LISTING.replace("<time>Nov 20, 2026</time>", "", 1)

    articles, problems = anthropic_news_blog.parse_news_html(listing)

    assert "https://www.anthropic.com/news/ipo-close" not in {a["link"] for a in articles}
    assert len(problems) == 1
