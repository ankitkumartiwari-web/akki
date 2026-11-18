import logging
import tempfile
import unittest
from pathlib import Path

from akki.logsetup import configure_logging


class LoggingTests(unittest.TestCase):
    def test_writes_to_rotating_file(self) -> None:
        logger = logging.getLogger("akki")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "akki.log"
            configured = configure_logging(target)
            try:
                logger.info("hello audit")
                for handler in logger.handlers:
                    handler.flush()
                text = target.read_text(encoding="utf-8")
            finally:
                handler = getattr(logger, "_akki_handler", None)
                if handler is not None:
                    logger.removeHandler(handler)
                    handler.close()
                    delattr(logger, "_akki_handler")
        self.assertEqual(configured, target)
        self.assertIn("hello audit", text)


if __name__ == "__main__":
    unittest.main()
