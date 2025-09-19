#!/usr/bin/env python3
"""
Entry point for AggFuturesMain application.
"""

import os
import sys

# Add src to path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# Import and run the main application
if __name__ == '__main__':
    from AggFuturesMain import __main__
    # The original file calls __main__() at the end, so we just need to import it