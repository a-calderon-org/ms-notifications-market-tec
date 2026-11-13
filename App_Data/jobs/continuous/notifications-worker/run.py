import os
import sys
from pathlib import Path


def main() -> None:
    web_root = Path(__file__).resolve().parents[4]
    os.chdir(web_root)
    sys.path.insert(0, str(web_root / ".python_packages" / "lib" / "site-packages"))
    sys.path.insert(0, str(web_root / "src"))

    from ms_notifications.worker import main as run_worker

    run_worker()


if __name__ == "__main__":
    main()
