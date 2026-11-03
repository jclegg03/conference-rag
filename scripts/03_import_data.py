"""
Step 3: Import Talk Data to Supabase
======================================
Reads scripts/output/talks.json, splits each talk into sentences,
imports the text records to Supabase (without embeddings), and
saves the sentence records locally for the embedding step.

After this step, KEYWORD SEARCH will light up green on your site!
Embeddings are added in the next step to enable semantic search.

Usage:
    python scripts/03_import_data.py

Input:
    scripts/output/talks.json  — from Step 2 (scraping)

Output:
    scripts/output/sentences.json  — sentence records with talk_id + sentence_num

Prerequisites:
    - config.public.json with Supabase URL and anon key
    - config.secret.json with Supabase service key
    - Database schema created (Step 1)
    - Talks scraped (Step 2)
"""

import json
import os
import re
import sys
import time
import uuid

import requests
from supabase import create_client
from tqdm import tqdm


INPUT_FILE = os.path.join('scripts', 'output', 'talks.json')
OUTPUT_FILE = os.path.join('scripts', 'output', 'sentences.json')
BATCH_SIZE = 100


def load_config():
    with open('config.public.json', 'r') as f:
        public_config = json.load(f)
    with open('config.secret.json', 'r') as f:
        secrets = json.load(f)
    return public_config, secrets


def truncate_table(secrets):
    """Empty the table with SQL TRUNCATE (via the Management API, like 01_create_schema.py).
    A REST delete of every row is too slow once the vector index exists and times out."""
    resp = requests.post(
        f"https://api.supabase.com/v1/projects/{secrets['SUPABASE_PROJECT_REF']}/database/query",
        headers={"Authorization": f"Bearer {secrets['SUPABASE_ACCESS_TOKEN']}"},
        json={"query": "TRUNCATE sentence_embeddings;"},
        timeout=60,
    )
    if resp.status_code >= 300:
        # Stop rather than import on top of the old rows and create duplicates
        print(f"   ❌ Could not truncate table: {resp.status_code} {resp.text[:300]}")
        sys.exit(1)


def insert_with_retry(client, batch, batch_num, attempts=3):
    """Insert one batch, retrying on transient errors (e.g. a 502 from the gateway)."""
    for attempt in range(1, attempts + 1):
        try:
            client.table('sentence_embeddings').insert(batch).execute()
            return True
        except Exception as e:
            if attempt == attempts:
                print(f"\nError at batch {batch_num}: {e}")
                return False
            time.sleep(2 * attempt)


def split_into_sentences(text):
    """Split text into sentences using a simple heuristic."""
    sentences = re.split(r'\. (?=[A-Z])', text)
    sentences = [s.strip() + '.' if not s.endswith('.') else s.strip() for s in sentences]
    return [s for s in sentences if len(s) > 20]


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ {INPUT_FILE} not found. Run scripts/02_scrape_data.py first.")
        sys.exit(1)

    # Load talks
    print("=" * 60)
    print("Importing Talk Data to Supabase")
    print("=" * 60)

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        talks = json.load(f)
    print(f"   Loaded {len(talks)} talks\n")

    # Split into sentence records (no embeddings yet)
    print("Splitting talks into sentences...")
    sentence_records = []
    for talk in tqdm(talks, desc="Splitting"):
        talk_id = str(uuid.uuid4())
        # Split within each paragraph so every sentence knows which paragraph it came from
        paragraphs = talk.get('paragraphs') or [{'id': None, 'anchor': None, 'text': talk['text']}]
        sentences = [
            (paragraph['id'], paragraph['anchor'], sentence)
            for paragraph in paragraphs
            for sentence in split_into_sentences(paragraph['text'])
        ]
        for i, (paragraph_id, anchor_id, sentence) in enumerate(sentences, 1):
            sentence_records.append({
                'talk_id': talk_id,
                'title': talk['title'],
                'speaker': talk['speaker'],
                'calling': talk['calling'],
                'year': int(talk['year']) if talk['year'] else None,
                'season': talk['season'],
                'url': talk['url'],
                'sentence_num': i,
                'paragraph_id': paragraph_id,
                'anchor_id': anchor_id,
                'text': sentence
                # No 'embedding' field — added in next step
            })

    print(f"✅ Split {len(talks)} talks into {len(sentence_records):,} sentences")
    print(f"   Average: {len(sentence_records) / len(talks):.1f} sentences per talk\n")

    # Save sentences locally (for embedding step to use)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(sentence_records, f, ensure_ascii=False)
    file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"💾 Saved {len(sentence_records):,} sentences to {OUTPUT_FILE} ({file_size_mb:.1f} MB)")

    # Connect to Supabase
    public_config, secrets = load_config()
    client = create_client(public_config['SUPABASE_URL'], secrets['SUPABASE_SERVICE_KEY'])

    # Check for existing data and truncate if needed
    print("\n" + "=" * 60)
    print("Checking for existing data...")
    print("=" * 60)

    result = client.table('sentence_embeddings').select('id', count='exact').limit(1).execute()
    existing_count = result.count or 0
    if existing_count > 0:
        print(f"   Found {existing_count:,} existing rows. Truncating table...")
        truncate_table(secrets)
        print("   ✅ Table truncated.")
    else:
        print("   Table is empty — ready for import.")

    # Import in batches
    print("\n" + "=" * 60)
    print(f"Importing {len(sentence_records):,} records to Supabase")
    print("=" * 60)
    print("   (Text only — embeddings will be added in the next step)\n")

    success = 0
    errors = 0

    for i in tqdm(range(0, len(sentence_records), BATCH_SIZE), desc="Importing"):
        batch = sentence_records[i:i + BATCH_SIZE]
        if insert_with_retry(client, batch, i // BATCH_SIZE):
            success += len(batch)
        else:
            errors += len(batch)
        time.sleep(0.1)

    print(f"\n✅ Import complete!")
    print(f"   Success: {success:,}")
    if errors:
        print(f"   Errors:  {errors:,}")

    # Final verification
    result = client.table('sentence_embeddings').select('id', count='exact').limit(1).execute()
    print(f"\n   Total rows in database: {result.count or 0:,}")

    print(f"\n🎉 Keyword Search is now ready!")
    print(f"   Refresh your site — the 🔍 Keyword Search panel should turn GREEN.")
    print(f"\nNext: python scripts/04_embed_data.py")


if __name__ == '__main__':
    main()
