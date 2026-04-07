def choose_route(options: list[str]) -> str:
    """Return the first route for the fixture project."""
    return options[0] if options else "none"
