# How we record a name

The library is a record of what beings are actually called, by whom. These
rules keep it that way. They matter most when we are unsure, because an
uncertain entry that looks certain is worse than no entry at all.

## 1. The name field holds the name. Nothing else.

Never append a qualifier to the name itself: not `ਕੱਦੂ (generic)`, not
`genda (approx.)`, not a language tag. The moment a qualifier lives inside
the name, the name stops being searchable, prints wrong on the tree and in
the kinship report, and quietly becomes the name in anyone's eyes.

Scope, provenance, and doubt go in **notes**. That is what the column is
for, and it is editable in Library → Manage → Names.

## 2. If a language has no name for a being, record nothing.

No `Unknown`, no `N/A`, no blank row. Those invent a record. A row that
says "Unknown" is a claim that somebody looked and found a gap; it also
sorts, exports, and prints as though it were a name, and a later reader
cannot tell it from one.

Absence is already expressive here. Punjabi carries no name for the
Chinese water deer because that deer is not part of the landscape Punjabi
grew up in. Leaving it empty says that. A placeholder erases it.

## 3. A name that reaches wider than the species still counts. Say how wide.

ਕੱਦੂ is a real Punjabi word; it reaches pumpkins and gourds in general
rather than *Cucurbita pepo* alone. ਗੇਂਦਾ reaches all marigolds.
ਕਸਤੂਰੀ ਹਿਰਨ reaches musk deer, not the Siberian one specifically.

Record them, and put the reach in notes. Most of the world's names work
this way; pretending otherwise would impose a taxonomist's precision on
languages that never asked for it.

## 4. Never invent a name.

A translated description is not a name. "Chinese water deer" rendered word
by word into Punjabi produces a phrase no Punjabi speaker uses. If the
collective deliberately coins one, that is a real event: record it, and say
in notes that it is a coinage, who made it, and when.

## 5. `is_preferred` means the community leads with it.

Not the one we find prettiest, and not the English one by default. One
preferred name per (species, language, category).

## 6. Romanization is a separate row, not a substitute.

Record the script form (`script = Guru`, `Deva`, `Arab`, …) and the
romanized form (`script = Latn`) as two rows in the same language, and note
in the romanized row which spelling it transliterates. Readers who cannot
read the script still deserve the name, and the script form stays primary.

## Importing in bulk

Library → Manage → Names → *Import names from a CSV*. Columns:
`scientific_name`, `name_text`, and optionally `language`, `category`,
`script`, `region`, `notes`, `is_preferred`. Species are matched on
scientific name, unmatched rows are reported rather than guessed at, and
re-importing the same file changes nothing.
