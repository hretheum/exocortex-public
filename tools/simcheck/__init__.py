"""simcheck: is this text similar to anything in the private corpus?

Runs next to the private corpus (on the private server) and answers only
"similar / not similar" with a score. It never returns corpus content.
Two checks: a literal one (MinHash over word and character shingles, which
survives removed names and small edits) and an optional semantic one
(paragraph embeddings, which survives rewording).
"""
