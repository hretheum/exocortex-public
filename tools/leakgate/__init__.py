"""leakgate: a publishing gate that stops client material from leaving.

The gate checks text, files, build artifacts and git metadata for names on a
private denylist (compared through HMAC hashes, so the public repository never
contains the names themselves), personal data, and file metadata.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
