"""Disabled legacy website sync command; NEMSU website ingestion is turned off."""


def main():
    raise SystemExit("NEMSU website collection is disabled. Use the provided campus datasets.")


if __name__ == "__main__":
    main()
