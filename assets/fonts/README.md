# Fonts

Everything in this folder gets registered twice over: once with matplotlib
(the tree drawings and composites) and once with ReportLab (the press PDF).
Both read the folder itself, so **adding a script is just dropping the .ttf
in here and pushing.** There is no list to update and no code to touch.

`packages.txt` is empty on purpose, so nothing is apt-installed on Streamlit
Cloud. These files are the only fonts the app can count on.

## What is here

| File | Covers |
| --- | --- |
| `NotoSans-Regular.ttf` | Latin, Latin Extended (ā ī ū ō, the romanized names), Greek, Cyrillic |
| `NotoSansArmenian-Regular.ttf` | Armenian |

## What is missing, and what to add

Any character no font here can draw comes out as a box. The Library and the
press PDF both say which characters are missing when that happens.

To add a script, download the **static TTF** (not the variable font, not the
.ttc collection) from Google's Noto repo and drop it in:

<https://github.com/notofonts/notofonts.github.io/tree/main/fonts>

The ones this collective's data is waiting on:

| Script | File to download | Needed for |
| --- | --- | --- |
| Gurmukhi | `NotoSansGurmukhi-Regular.ttf` | Punjabi names in the deerpreet tree |
| Devanagari | `NotoSansDevanagari-Regular.ttf` | Hindi, Nepali, Marathi names |
| Thai | `NotoSansThai-Regular.ttf` | Thai names |
| Arabic | `NotoNaskhArabic-Regular.ttf` | Arabic, Urdu, Persian names |

Each is roughly 150 to 400 KB.

### Han, Kana and Hangul are the awkward one

ReportLab cannot embed PostScript/CFF outlines, which is what Noto's CJK
`.ttc` collections use, and those files are about 19 MB besides. For Chinese,
Japanese or Korean names in the PDF, use a TrueType-outline font such as
`NotoSansSC-Regular.ttf` from the link above. The code skips the `.ttc`
files quietly, so there is no harm in a system that happens to have them.

All Noto fonts are under the SIL Open Font License, so they are fine to
commit here and ship.
