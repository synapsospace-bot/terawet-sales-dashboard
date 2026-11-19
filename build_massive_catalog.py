#!/usr/bin/env python3
"""
Massive European Agricultural Domain Catalog Builder for TERAWET-ORIGINAL.
Expands the verified B2B reservoir across 17 European target markets:
Spain, Italy, France, Portugal, Greece, Germany, Austria, Romania, Bulgaria,
Poland, Hungary, Croatia, Slovenia, Slovakia, Czechia, Serbia.

Verifies 100% active DNS MX records in parallel threads before saving.
"""

import dns.resolver
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

MEGA_CATALOG_FILE = Path("/Users/anastasiia/.gemini/antigravity/scratch/terawet_sales_agent/verified_mega_catalog.json")

resolver = dns.resolver.Resolver()
resolver.nameservers = ['8.8.8.8', '1.1.1.1', '8.8.4.4']
resolver.timeout = 1.0
resolver.lifetime = 1.5

def check_domain_mx(dom: str):
    d = dom.lower().strip()
    if not d or '.' not in d:
        return d, False
    try:
        ans = resolver.resolve(d, "MX")
        if ans and len(ans) > 0:
            return d, True
    except Exception:
        pass
    return d, False

def verify_and_merge(candidates_by_country: dict, max_workers: int = 50):
    current_catalog = {}
    if MEGA_CATALOG_FILE.exists():
        try:
            with open(MEGA_CATALOG_FILE, "r", encoding="utf-8") as f:
                current_catalog = json.load(f)
        except Exception as e:
            print(f"Error loading existing catalog: {e}")

    # Gather all candidate domains
    all_candidates = []
    for c_code, doms in candidates_by_country.items():
        all_candidates.extend(doms)
    
    unique_candidates = list(dict.fromkeys(d.lower().strip() for d in all_candidates if d and '.' in d))
    print(f"Testing {len(unique_candidates)} unique candidate domains across Europe via parallel DNS MX...")
    
    start_time = time.time()
    valid_domains = set()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for dom, is_valid in executor.map(check_domain_mx, unique_candidates):
            if is_valid:
                valid_domains.add(dom)
                
    elapsed = time.time() - start_time
    print(f"DNS MX check completed in {elapsed:.2f}s! Found {len(valid_domains)} working mail domains.")

    # Merge into catalog by country
    added_total = 0
    for c_code, doms in candidates_by_country.items():
        existing = current_catalog.get(c_code, [])
        existing_set = set(d.lower().strip() for d in existing)
        
        new_for_country = [d.lower().strip() for d in doms if d.lower().strip() in valid_domains and d.lower().strip() not in existing_set]
        merged = existing + new_for_country
        current_catalog[c_code] = list(dict.fromkeys(merged))
        added_total += len(new_for_country)
        print(f"  {c_code}: {len(current_catalog[c_code])} total (+{len(new_for_country)} fresh)")

    # Save to file
    with open(MEGA_CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(current_catalog, f, indent=2, ensure_ascii=False)
        
    total_domains = sum(len(v) for v in current_catalog.values())
    print(f"Catalog successfully updated! Total verified domains: {total_domains} (Added: {added_total})")
    return current_catalog

if __name__ == "__main__":
    print("Massive Catalog Builder ready.")
