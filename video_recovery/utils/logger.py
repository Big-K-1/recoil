"""
Logger module — background debug logging
"""
import logging
import os
from datetime import datetime

LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, f"process_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logger = logging.getLogger("video_recovery")
logger.setLevel(logging.DEBUG)

# File handler - detailed logs
fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(fh)

# Console handler - minimal output (only INFO and above)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(ch)
