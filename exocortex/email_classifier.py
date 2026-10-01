# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/email_classifier.py — F6.4.3: classify an email thread → domain/client/project.
#
# Three-tier classification (in priority order):
#   1. Sender email domain → primary domain (`@example.com → work` etc.)
#   2. Subject + body keyword overlay → upgrade or sharpen domain
#   3. Entity match against existing F4 entities → client/project routing
#
# F3-style LLM augmentation can be added later for edge cases — for now this
# is purely deterministic + entity-DB lookup.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from exocortex.db import query
from exocortex.settings import get_tenant_id

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECTS_PATH = REPO_ROOT / 'config' / 'projects.yaml'
TENANT_ID = get_tenant_id()

# Sender-domain → primary domain map.
#
# F8.8 cleanup (2026-05-03):
#   - example.com REMOVED. Work email is NOT in scope for capture-via-Gmail
#     anymore (gmail adapter mode=newsletter, label=Read Later). User's Gmail
#     filter rules ensure work email never gets the Read Later label, so
#     classifier never sees it. Keeping the entry would mislabel any rare
#     mismatch as `work` when it should be `news`.
#   - Client domains kept for historical email_thread routing (still used
#     when mode=thread is invoked manually).
SENDER_DOMAIN_TO_DOMAIN: dict[str, str] = {
    # Clients (verified working domains; thread mode legacy — F8.8 newsletter
    # mode does not see work email because of Gmail filter rules).
    'betabank.example.com': 'work',
    'waynebank.pl': 'work',
    'acmebank.example.com': 'work',
    'oscorp.pl': 'work',
    'voltaic.pl': 'work',
    'stratus.pl': 'work',
    'initech.com': 'work',
    'umbrella.pl': 'work',
    'hooli-bank.pl': 'work',
    'cyberdyne.pl': 'work',
    'vandelay.pl': 'work',
    'soylent.com': 'work',
    'docmost.com': 'work',
    # Personal services
    'gmail.com': 'priv',          # default — entity match may upgrade
    'apple.com': 'priv',
    'icloud.com': 'priv',
}

# Common 3D printing / cooking / SF outlet domains push into specific verticals.
SENDER_DOMAIN_OVERRIDES: dict[str, str] = {
    'printables.com': '3d',
    'thingiverse.com': '3d',
    'makerworld.com': '3d',
    'bambulab.com': '3d',
    'prusa3d.com': '3d',
    'clarkesworldmagazine.com': 'frp',
    '365tomorrows.com': 'frp',
    'solarpunkmagazine.com': 'frp',
    'arxiv.org': 'papers',
}

# F8.8 — newsletter platform domains. Substack/beehiiv/etc. spread newsletters
# across many subdomains (e.g. newsletter@example.com), so we match the
# parent domain via _is_newsletter_sender() below rather than exact-match here.
NEWSLETTER_PLATFORM_DOMAINS: tuple[str, ...] = (
    'substack.com',
    'beehiiv.com',
    'mailchimp.com',
    'mailchimpapp.com',
    'convertkit.com',
    'mailerlite.com',
    'kit.com',
    'revue.email',
    'buttondown.email',
    'ghost.io',
)

# F8.8 — known direct newsletter sender domains (no subdomain wildcard needed).
NEWSLETTER_DIRECT_DOMAINS: tuple[str, ...] = (
    'daily.therundown.ai',
    'mail.theresanaiforthat.com',
    'theresanaiforthat.com',
    'mail.beehiiv.com',
    'newsletter.openai.com',
    'newsletter.anthropic.com',
)

# F8.8 — sender display-name regex (case-insensitive). When the From header
# display name contains one of these tokens, treat as newsletter.
NEWSLETTER_NAME_TOKENS = re.compile(
    r'\b(newsletter|digest|weekly|daily|update|report|briefing|recap)\b',
    re.IGNORECASE,
)

# Domain hint keywords scanned in subject + first 1000 chars of body.
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    'work': ['migration', 'sprint', 'roadmap', 'invoice', 'kickoff', 'rfp',
             'proposal', 'deliverable', 'wks', 'standup'],
    '3d':   ['filament', 'print bed', 'layer height', 'fdm', 'sla',
             'support', 'g-code', 'printer'],
    'cook': ['recipe', 'ingredient', 'menu', 'meal plan', 'grocery'],
    'frp':  ['scenario', 'reading prompt', 'frame', 'futures'],
}


# ─────────────────────────── Output dataclass ───────────────────────────

@dataclass
class EmailClassification:
    domains: list[str] = field(default_factory=list)   # ordered, primary first
    client: Optional[str] = None
    project: Optional[str] = None
    sender_slug: Optional[str] = None
    sender_domain: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)   # debug breadcrumb


# ─────────────────────────── Sender helpers ───────────────────────────

EMAIL_RE = re.compile(r'([A-Za-z0-9_.+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})')


def _extract_address(raw_sender: str) -> tuple[Optional[str], Optional[str]]:
    """Sender field can be 'Name <email>' or just 'email'. Returns (email, domain)."""
    if not raw_sender:
        return None, None
    m = EMAIL_RE.search(raw_sender)
    if not m:
        return None, None
    email = m.group(0).lower()
    domain = m.group(2).lower()
    return email, domain


def _slug_from_email(email: str) -> str:
    """email local-part → slug (matches F2 person slug convention)."""
    local = email.split('@', 1)[0]
    return re.sub(r'[^a-z0-9-]+', '-', local.lower()).strip('-') or 'unknown'


def _is_newsletter_sender(*, sender_email: Optional[str], sender_domain: Optional[str],
                          sender_name: Optional[str]) -> bool:
    """F8.8 heuristic: does this sender look like an industry newsletter?

    Three positive signals:
      1. Domain is on NEWSLETTER_DIRECT_DOMAINS (exact match).
      2. Domain ends with one of NEWSLETTER_PLATFORM_DOMAINS (substack/beehiiv/...).
      3. Display name contains a newsletter-keyword token (digest/weekly/...).
    Any of the three returns True. Used as additional signal in classify_email_thread.
    """
    if sender_domain:
        if sender_domain in NEWSLETTER_DIRECT_DOMAINS:
            return True
        for platform in NEWSLETTER_PLATFORM_DOMAINS:
            if sender_domain == platform or sender_domain.endswith('.' + platform):
                return True
    if sender_name and NEWSLETTER_NAME_TOKENS.search(sender_name):
        return True
    return False


# ─────────────────────────── Project + client config ───────────────────────────

_projects_cfg: Optional[dict] = None


def _load_projects() -> dict:
    global _projects_cfg
    if _projects_cfg is None:
        with PROJECTS_PATH.open() as f:
            _projects_cfg = yaml.safe_load(f) or {}
    return _projects_cfg


# ─────────────────────────── Entity DB lookups ───────────────────────────

def _client_from_entity_db(text: str) -> Optional[str]:
    """Match text against client entities (canonical_name) in DB."""
    rows = query(
        "SELECT canonical_name FROM entities "
        "WHERE tenant_id = %s AND type = 'client'",
        TENANT_ID,
    )
    text_l = text.lower()
    for r in rows:
        slug = r['canonical_name']
        if not slug:
            continue
        # match as standalone token in the text body
        if re.search(rf'\b{re.escape(slug.lower())}\b', text_l):
            return slug
    return None


def _project_from_entity_db(text: str, client: Optional[str]) -> Optional[str]:
    """Match against project entities. If client known, prefer projects under it."""
    rows = query(
        "SELECT canonical_name FROM entities "
        "WHERE tenant_id = %s AND type = 'project'",
        TENANT_ID,
    )
    text_l = text.lower()
    matches = []
    for r in rows:
        slug = r['canonical_name']
        if not slug:
            continue
        if re.search(rf'\b{re.escape(slug.lower())}\b', text_l):
            matches.append(slug)
    if not matches:
        return None
    if client:
        # Prefer ones with the client prefix.
        for m in matches:
            if m.startswith(f'{client}-'):
                return m
    return matches[0]


# ─────────────────────────── Public API ───────────────────────────

def classify_email_thread(*, sender: Optional[str], subject: str = '',
                          body_excerpt: str = '',
                          recipients: Optional[list[str]] = None,
                          sender_name: Optional[str] = None) -> EmailClassification:
    """Classify an email thread. All inputs are best-effort; missing fields tolerated.

    F8.8: `sender_name` (display name from RFC 2822 From header) is now an
    explicit input — used by `_is_newsletter_sender` as a signal beyond the
    sender domain.
    """
    out = EmailClassification()
    sender_email, sender_domain = _extract_address(sender or '')
    out.sender_domain = sender_domain
    if sender_email:
        out.sender_slug = _slug_from_email(sender_email)

    text = f'{subject}\n{body_excerpt}'

    # 0. F8.8 newsletter detection — runs first so it wins over fallback `work`.
    if _is_newsletter_sender(
        sender_email=sender_email,
        sender_domain=sender_domain,
        sender_name=sender_name,
    ):
        out.domains.append('news')
        out.reasons.append('newsletter_heuristic')

    # 1. Sender domain → primary domain.
    if sender_domain:
        primary = SENDER_DOMAIN_OVERRIDES.get(sender_domain) \
            or SENDER_DOMAIN_TO_DOMAIN.get(sender_domain)
        if primary and primary not in out.domains:
            out.domains.append(primary)
            out.reasons.append(f'sender_domain:{sender_domain}→{primary}')

    # 2. Subject + body keyword overlay.
    text_l = text.lower()
    for domain, kws in DOMAIN_KEYWORDS.items():
        if any(re.search(rf'\b{re.escape(kw)}\b', text_l) for kw in kws):
            if domain not in out.domains:
                out.domains.append(domain)
                out.reasons.append(f'keyword:{domain}')

    if not out.domains:
        out.domains.append('work')
        out.reasons.append('default:work')

    # 3. Entity DB lookup (if we have any work signal).
    if 'work' in out.domains:
        client = _client_from_entity_db(text)
        if client:
            out.client = client
            out.reasons.append(f'entity_client:{client}')
            project = _project_from_entity_db(text, client)
            if project:
                out.project = project
                out.reasons.append(f'entity_project:{project}')

    return out
