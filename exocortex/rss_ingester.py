# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/rss_ingester.py — run as cron every 12 hours

"""
RSS feeds → metadata + AI scoring.

COPYRIGHT POLICY:
- Fetches RSS feed metadata (title, author, URL, date)
- Fetches max 150-word excerpt for AI scoring ONLY
- Excerpt is NEVER persisted to database
- Stores: URL + metadata in raw_sources
- AI score stored in content_queue
"""



def ingest_rss_feeds(tenant_id: str, config_path: str = 'config/wiki_schema.yaml') -> dict:
    """
    Process all RSS feeds defined in wiki_schema.yaml.

    For each feed entry:
    1. Fetch RSS metadata (title, author, URL, published_at)
    2. Deduplicate by URL
    3. Fetch 150-word excerpt (for AI scoring only, not persisted)
    4. Score via AI (accessibility, horizon, consequence)
    5. Insert to raw_sources + content_queue

    Returns: {processed: int, new: int, skipped: int}
    """
    # TODO: Implement with feedparser + wiki_schema.yaml config
    raise NotImplementedError("Implement with feedparser and Anthropic API")


def fetch_metadata_only(url: str) -> dict:
    """
    Fetch metadata from a URL without storing full text.

    Returns: {title, author, word_count, published_at, source_name, tags}
    """
    raise NotImplementedError


def fetch_excerpt(url: str, max_words: int = 150) -> str:
    """
    Fetch a short excerpt for AI scoring purposes only.
    This excerpt is NEVER persisted to the database.
    """
    raise NotImplementedError


def ai_score_from_metadata_and_excerpt(metadata: dict, excerpt: str) -> dict:
    """
    Score content using Anthropic API (Commercial Terms).

    Input: metadata + max 150-word excerpt
    Output: {accessibility, horizon, consequence, total, decision,
             suggested_prompt, tags, rejection_reason}

    The excerpt is discarded after scoring.
    """
    raise NotImplementedError


if __name__ == '__main__':
    from exocortex.settings import get_tenant_id
    tenant = get_tenant_id()
    result = ingest_rss_feeds(tenant)
    print(f"RSS ingest complete: {result}")
