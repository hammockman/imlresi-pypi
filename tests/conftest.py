import os
import sys

# PySpark starts worker processes with whatever "python" is on PATH unless
# told otherwise; a different minor version than the driver makes every
# Spark test fail with PYTHON_VERSION_MISMATCH.
os.environ.setdefault('PYSPARK_PYTHON', sys.executable)
os.environ.setdefault('PYSPARK_DRIVER_PYTHON', sys.executable)
