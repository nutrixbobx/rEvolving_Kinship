"""
Build the local NCBI taxonomy database, with a route that avoids network SSL
problems.

Normally the pipeline downloads the taxonomy by itself on first run. If your
network or Python install blocks that download with an SSL certificate error,
download the file once in your web browser instead. Open this address and save
the file (it is about 66 MB):

    https://ftp.ncbi.nih.gov/pub/taxonomy/taxdump.tar.gz

then point this script at wherever it landed:

    python -m src.build_taxonomy ~/Downloads/taxdump.tar.gz

That builds the database ete3 uses, in its default location, so a normal
pipeline run afterward finds it and skips the download. ete3 does not touch the
network at all when you give it the file directly.

With no argument it just attempts the normal download.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    from ete3 import NCBITaxa

    if len(sys.argv) > 1:
        taxdump = str(Path(sys.argv[1]).expanduser().resolve())
        if not Path(taxdump).exists():
            print(f"file not found: {taxdump}")
            raise SystemExit(1)
        print(f"building the NCBI taxonomy database from your file: {taxdump}")
        print("this parses a few million taxa and takes a few minutes.")
        NCBITaxa(taxdump_file=taxdump)
    else:
        print("building the NCBI taxonomy database via download...")
        NCBITaxa()

    print("\ndone. the database is ready. run the pipeline normally now:")
    print('  python -m src.pipeline "<Your Tree Name>"')


if __name__ == "__main__":
    main()
