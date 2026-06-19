"""
Configuration management for disk ripping tool.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
DVDCOMPARE_CACHE_TTL = 86400  # 24 hours

# Paths
BASE_DIR = Path(__file__).parent.parent  # D:\Disk Ripping\
RIPS_DIR = BASE_DIR  # Where MakeMKV output goes (root of Disk Ripping)
COMPLETED_DIR = BASE_DIR / 'Completed'
OPERATIONAL_DIR = BASE_DIR / 'Operational'

# Matching thresholds (seconds)
CONFIDENCE_HIGH = 30      # ≤30s: high confidence
CONFIDENCE_MEDIUM = 120   # ≤120s: medium confidence
CONFIDENCE_LOW = 999999   # >120s: low confidence
MAX_DELTA = 120           # Hard cap for episode matching

# Ambiguity detection thresholds
AMBIGUITY_COLLISION_DELTA = 10    # Flag if multiple matches within 10s
AMBIGUITY_MEDIUM_CONFIDENCE = 30  # Flag if delta > 30s from best match
AMBIGUITY_LOW_CONFIDENCE = 120    # Flag if delta > 120s from best match

# Output formatting
REPORT_WIDTH = 80
