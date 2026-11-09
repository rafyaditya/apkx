import io
import logging
import unittest

from apk_extractor.logger import logger


class TestLogger(unittest.TestCase):
    def test_logger_instance(self):
        self.assertEqual(logger.name, "apkx")
        self.assertTrue(any(isinstance(h, logging.NullHandler) for h in logger.handlers))

    def test_logger_streams_to_stderr(self):
        stderr_buf = io.StringIO()
        handler = logging.StreamHandler(stderr_buf)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            logger.debug("Debug diagnostic message")
            logger.info("Info message")
            logger.warning("Warning message")

            output = stderr_buf.getvalue()
            self.assertIn("[DEBUG] Debug diagnostic message", output)
            self.assertIn("[INFO] Info message", output)
            self.assertIn("[WARNING] Warning message", output)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(logging.NOTSET)


if __name__ == "__main__":
    unittest.main()
