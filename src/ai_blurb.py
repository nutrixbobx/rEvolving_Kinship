"""
A short paragraph for each tree: why these species are interesting together,
and how a visitor can take care of them.

Tries Groq's free tier (OpenAI-compatible, open-source models like Llama 3.3)
when GROQ_API_KEY is set. Falls back to Hugging Face Inference if HF_TOKEN is
set. If neither is configured, a deterministic template draws on the tree's
own clades and common names so something useful still appears under the tree.

Cached per tree in outputs/ai_blurb_cache.json. The cache invalidates if the
species list changes (the cache key is a hash of the species).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

CACHE_PATH = config.OUTPUT_DIR / "ai_blurb_cache.json"

PROMPT_SYSTEM = (
    "You write short, careful, hopeful paragraphs about ecology for art "
    "gallery visitors. Use plain language. Avoid em dashes. Avoid lists of "
    "three. Avoid buzzwords. Two paragraphs maximum, eighty to one hundred "
    "and twenty words total. The first paragraph names why these species "
    "are interesting together as kin. The second paragraph names one or two "
    "concrete ways a visitor can act in their own watershed to take care of "
    "these kin."
)


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(c: dict) -> None:
    CACHE_PATH.write_text(json.dumps(c, indent=2))


def _species_signature(species_list: list[str]) -> str:
    clean = sorted(x for x in species_list if isinstance(x, str))
    return hashlib.md5("|".join(clean).encode()).hexdigest()[:12]


def _build_prompt(tree_name: str, species: list[dict],
                  dated_clades: dict) -> str:
    parts = [f"Tree name: {tree_name}", "", "Species in the tree:"]
    for s in species:
        line = f"  - {s.get('common') or s.get('scientific')}"
        if s.get("common") and s.get("scientific"):
            line += f" ({s['scientific']})"
        parts.append(line)
    if dated_clades:
        parts.append("")
        parts.append("Deep-time clades shared by these species:")
        for clade, mya in dated_clades.items():
            parts.append(f"  - {clade} approx {mya} million years ago")
    parts.append("")
    try:
        from src import usage_log
        tree_wh = usage_log.tree_total(tree_name)
        if tree_wh > 0:
            parts.append("")
            parts.append(f"Approximate energy used to build this tree so far: "
                         f"{tree_wh} watt-hours ({usage_log.relatable(tree_wh)}).")
            parts.append("End with one short sentence that names this energy "
                         "in plain language, e.g. 'this tree cost about an "
                         "LED bulb on for ten minutes.'")
    except Exception:
        pass
    parts.append("Write two short paragraphs as the system prompt instructs.")
    return "\n".join(parts)


def _call_groq(prompt: str) -> str | None:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    body = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 350,
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        d = json.loads(r.read())
        return d["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        print(f"groq failed: {exc}")
        return None


def _call_hf(prompt: str) -> str | None:
    key = os.environ.get("HF_TOKEN")
    if not key:
        return None
    body = json.dumps({
        "inputs": f"{PROMPT_SYSTEM}\n\n{prompt}",
        "parameters": {"max_new_tokens": 320, "temperature": 0.4},
    }).encode()
    req = urllib.request.Request(
        "https://api-inference.huggingface.co/models/"
        "meta-llama/Llama-3.2-3B-Instruct",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=45)
        d = json.loads(r.read())
        if isinstance(d, list) and d:
            return d[0].get("generated_text", "").strip()
        return None
    except Exception as exc:
        print(f"hf failed: {exc}")
        return None


def _template_blurb(tree_name: str, species: list[dict],
                    dated_clades: dict) -> str:
    """Deterministic, no API call. Uses the tree's actual structure."""
    commons = [s.get("common") or s.get("scientific") for s in species]
    domains = sorted({s["domain"] for s in species if s.get("domain") and isinstance(s["domain"], str)})
    # Find the deepest shared clade for the call to action
    deepest_clade = None
    numeric = [(k, v) for k, v in dated_clades.items()
               if isinstance(v, (int, float))]
    if numeric:
        deepest_clade = max(numeric, key=lambda kv: kv[1])

    lead = f"These {len(commons)} kin"
    if commons:
        if len(commons) <= 4:
            lead += f" ({', '.join(commons)})"
        else:
            sample = ", ".join(commons[:3]) + f", and {len(commons) - 3} more"
            lead += f" ({sample})"
    if len(domains) >= 2:
        lead += f" gather across {', '.join(domains).lower()} kingdoms"
    elif domains:
        lead += f" share the {domains[0].lower()} kingdom"
    lead += "."
    if deepest_clade:
        lead += (f" Their shared ancestor sits at {deepest_clade[0]}, around "
                 f"{deepest_clade[1]} million years ago, which is what the chord "
                 "you hear is rooted in.")
    lead += (" Reading them as one tree, rather than a list, reframes them as "
             "lineages you have been beside the whole time.")

    care = ("To return care to these kin: learn the watershed they share with "
            "you, find the local stewards who already protect that water, and "
            "give one afternoon a season to their work. The smallest kept "
            "promise to a creek is more than the loudest pledge to the planet.")

    try:
        from src import usage_log
        tree_wh = usage_log.tree_total(tree_name)
        relatable = usage_log.relatable(tree_wh)
        footprint = (f"\n\nBuilding this tree so far has cost about "
                     f"{tree_wh} watt-hours, {relatable}. Knowing the price "
                     "in light is part of the kinship.")
    except Exception:
        footprint = ""
    return lead + "\n\n" + care + footprint


def blurb_for_tree(tree_name: str, force_refresh: bool = False) -> dict:
    """Return {text, source, cached}. Reads species + clades from the DB +
    tree meta. Uses cache unless force_refresh."""
    from src import db

    df = db.read_tree(tree_name)

    def _s(v):
        # pandas NaN is a float; only keep real strings
        return v.strip() if isinstance(v, str) and v.strip() else None

    species = []
    for _, r in df.iterrows():
        sci = _s(r.get("scientific_name"))
        if not sci:
            continue
        species.append({
            "common": _s(r.get("common_name")),
            "scientific": sci,
            "domain": _s(r.get("domain")),
        })

    stem = tree_name.strip().replace(" ", "_").lower()
    meta_path = config.OUTPUT_DIR / f"{stem}_nodes.json"
    dated_clades = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        dated_clades = {
            k: v["mya"] for k, v in meta.items()
            if not v.get("is_leaf") and v.get("mya") is not None
        }

    sig = _species_signature([s["scientific"] for s in species if s["scientific"]])
    cache = _load_cache()
    if not force_refresh and tree_name in cache and cache[tree_name].get("sig") == sig:
        return {"text": cache[tree_name]["text"],
                "source": cache[tree_name]["source"], "cached": True}

    prompt = _build_prompt(tree_name, species, dated_clades)

    text = _call_groq(prompt)
    source = "groq" if text else None
    if not text:
        text = _call_hf(prompt)
        source = "hugging-face" if text else None
    if not text:
        text = _template_blurb(tree_name, species, dated_clades)
        source = "template"

    cache[tree_name] = {"sig": sig, "text": text, "source": source}
    _save_cache(cache)
    return {"text": text, "source": source, "cached": False}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m src.ai_blurb "Tree Name"')
        raise SystemExit(1)
    r = blurb_for_tree(sys.argv[1])
    print(f"[source: {r['source']}, cached: {r['cached']}]\n")
    print(r["text"])
