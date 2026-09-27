# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# scripts/backfill_embeddings.py — one-shot backfill embeddings for existing thoughts

from __future__ import annotations
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / 'config' / '.env')

from exocortex.db import query, update_where, get_embeddings_batch

TENANT_ID = os.environ['TENANT_ID']
BATCH_SIZE = 100


def main() -> None:
    rows = query(
        'SELECT id, body FROM thoughts WHERE tenant_id = %s AND embedding IS NULL',
        TENANT_ID,
    )

    if not rows:
        print('Brak rekordów bez embeddingu.')
        return

    print(f'Znaleziono {len(rows)} rekordów bez embeddingu. Generuję...')
    ok = error = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        texts = [r['body'] for r in batch]
        embeddings = get_embeddings_batch(texts)

        for row, emb in zip(batch, embeddings):
            if emb is None:
                error += 1
                print(f'  ERROR: {row["id"]}')
                continue
            update_where('thoughts', {'embedding': emb}, 'id = %s', row['id'])
            ok += 1

        print(f'  [{min(i + BATCH_SIZE, len(rows))}/{len(rows)}] ok={ok} error={error}')

    print(f'\nDONE: ok={ok}  error={error}  total={len(rows)}')


if __name__ == '__main__':
    main()
