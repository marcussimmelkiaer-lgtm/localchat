"""Entry point for the packaged (frozen) application.

PyInstaller freezes this module. It simply hands off to the normal backend
`main()`, which runs first-launch bootstrap, starts the server, and opens the
window. Kept at the repo root (not inside the package) so the import path is the
same frozen or not.
"""

from backend.main import main

if __name__ == "__main__":
    main()
