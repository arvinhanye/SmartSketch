"""``python -m app.workers``：常驻 worker（K08），实现见 ``app.workers.runner``。"""

import sys

from app.workers.runner import main

if __name__ == "__main__":
    sys.exit(main())
