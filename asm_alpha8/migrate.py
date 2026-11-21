"""Copy an older ASM database, then migrate it by opening it with this release."""
import argparse
import sqlite3
from pathlib import Path
from asm import ASMEngine


def copy_database(source: Path, destination: Path) -> None:
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not source.is_file():raise FileNotFoundError(source)
    # Exclusive creation prevents accidental overwrites, including same-file use.
    with destination.open('xb'):
        pass
    try:
        src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
        try:
            dst=sqlite3.connect(destination)
            try:src.backup(dst)
            finally:dst.close()
        finally:src.close()
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    copy_database(args.source,args.destination)
    a=ASMEngine(args.destination)
    print(a.stats());a.close()
    print(f'Migrated copy: {args.destination}')

if __name__=='__main__':main()
