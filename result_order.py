"""Deterministic A–Z order for final results, independent of browser locale."""
import gzip
import json
import unicodedata
from pathlib import Path
from functools import lru_cache

with gzip.open(Path(__file__).with_name('pinyin_map.json.gz'), 'rt', encoding='utf-8') as f:
    PINYIN = json.load(f)

@lru_cache(maxsize=4096)
def alphabetical_key(name):
    text = unicodedata.normalize('NFKC', name).casefold()
    roman = ''.join(PINYIN.get(c, c) for c in text)
    roman = ''.join(c for c in unicodedata.normalize('NFKD', roman) if not unicodedata.combining(c) and c.isalnum())
    return roman, text

def result_key(restaurant):
    return (-restaurant.get('votes', 0), *alphabetical_key(str(restaurant.get('name', ''))), str(restaurant['id']))
