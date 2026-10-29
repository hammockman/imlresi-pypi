"""
Exhaustive parity tests for to_deltalake variants comparing REAL Python (delta-rs)
and REAL PySpark (Delta Spark engine) execution outputs side-by-side.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import pytest

deltalake = pytest.importorskip('deltalake')
from deltalake import DeltaTable

from imlresi.dotresi import ResiResult, ResiResultSet, DeltaMergeResult

# Ensure JAVA_HOME points to installed JDK 17 for PySpark
JDK17_PATH = Path("/home/jh/.local/share/jdk17")
if JDK17_PATH.exists():
    os.environ["JAVA_HOME"] = str(JDK17_PATH)
    os.environ["PATH"] = f"{JDK17_PATH / 'bin'}:{os.environ.get('PATH', '')}"

try:
    from pyspark.sql import SparkSession
    from delta import configure_spark_with_delta_pip
    PYSPARK_AVAILABLE = True
except ImportError:
    PYSPARK_AVAILABLE = False


def create_sample_resultset():
    """Helper to create a populated ResiResultSet with sample records."""
    rs = ResiResultSet()
    rs.results.append(
        ResiResult(
            filename="trace1.rgp",
            descriptors={
                "FileName": "trace1.rgp",
                "TreeID": "Tree-101",
                "DBHOB": 32.5,
                "RPMCoef.a": 1.25,
            }
        )
    )
    rs.results.append(
        ResiResult(
            filename="trace2.rgp",
            descriptors={
                "FileName": "trace2.rgp",
                "TreeID": "Tree-102",
                "DBHOB": 41.0,
                "RPMCoef.a": 0.98,
            }
        )
    )
    return rs


def create_updated_resultset():
    """Helper to create updated/new records for merge testing."""
    rs = ResiResultSet()
    # Update trace1.rgp
    rs.results.append(
        ResiResult(
            filename="trace1.rgp",
            descriptors={
                "FileName": "trace1.rgp",
                "TreeID": "Tree-101-Updated",
                "DBHOB": 34.0,
                "RPMCoef.a": 1.30,
            }
        )
    )
    # Insert trace3.rgp
    rs.results.append(
        ResiResult(
            filename="trace3.rgp",
            descriptors={
                "FileName": "trace3.rgp",
                "TreeID": "Tree-103",
                "DBHOB": 28.0,
                "RPMCoef.a": 1.10,
            }
        )
    )
    return rs


class TestToDeltalakeRealParity(unittest.TestCase):
    """Real end-to-end parity tests comparing Real PySpark vs Real Python deltalake outputs."""

    @classmethod
    def setUpClass(cls):
        if not PYSPARK_AVAILABLE:
            raise unittest.SkipTest("PySpark or Delta-Spark is not installed.")
        try:
            builder = (
                SparkSession.builder
                .appName("DeltaParityTest")
                .master("local[2]")
                .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
                .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
                .config("spark.sql.shuffle.partitions", "1")
            )
            cls.spark = configure_spark_with_delta_pip(builder).getOrCreate()
        except Exception as err:
            raise unittest.SkipTest(f"Could not initialize PySpark session: {err}")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "spark") and cls.spark:
            cls.spark.stop()

    def test_real_merge_mode_parity(self):
        """Test mode='merge' produces identical Delta table results in Python vs PySpark."""
        rs1 = create_sample_resultset()

        with tempfile.TemporaryDirectory() as tmpdir:
            py_table = Path(tmpdir) / "py_merge"
            spark_table = Path(tmpdir) / "spark_merge"

            # 1. Initial merge creation
            res_py1 = rs1.to_deltalake(py_table, mode="merge", merge_key="FileName", engine="deltalake")
            res_sp1 = rs1.to_deltalake(spark_table, mode="merge", merge_key="FileName", spark=self.spark)

            self.assertEqual(res_py1.num_inserted, res_sp1.num_inserted)
            self.assertEqual(res_py1.num_updated, res_sp1.num_updated)

            df_py1 = DeltaTable(str(py_table)).to_pandas().sort_values("FileName").reset_index(drop=True)
            df_sp1 = DeltaTable(str(spark_table)).to_pandas().sort_values("FileName").reset_index(drop=True)

            pd.testing.assert_frame_equal(df_py1, df_sp1, check_like=True)

            # 2. Subsequent merge update & insert
            rs2 = create_updated_resultset()
            res_py2 = rs2.to_deltalake(py_table, mode="merge", merge_key="FileName", engine="deltalake")
            res_sp2 = rs2.to_deltalake(spark_table, mode="merge", merge_key="FileName", spark=self.spark)

            self.assertEqual(res_py2.num_inserted, res_sp2.num_inserted)
            self.assertEqual(res_py2.num_updated, res_sp2.num_updated)

            df_py2 = DeltaTable(str(py_table)).to_pandas().sort_values("FileName").reset_index(drop=True)
            df_sp2 = DeltaTable(str(spark_table)).to_pandas().sort_values("FileName").reset_index(drop=True)

            pd.testing.assert_frame_equal(df_py2, df_sp2, check_like=True)

    def test_real_append_mode_parity(self):
        """Test mode='append' produces identical Delta table results in Python vs PySpark."""
        rs = create_sample_resultset()

        with tempfile.TemporaryDirectory() as tmpdir:
            py_table = Path(tmpdir) / "py_append"
            spark_table = Path(tmpdir) / "spark_append"

            # Initial write
            rs.to_deltalake(py_table, mode="overwrite", engine="deltalake")
            rs.to_deltalake(spark_table, mode="overwrite", spark=self.spark)

            # Append run
            res_py = rs.to_deltalake(py_table, mode="append", engine="deltalake")
            res_sp = rs.to_deltalake(spark_table, mode="append", spark=self.spark)

            self.assertEqual(res_py.num_inserted, res_sp.num_inserted)

            df_py = DeltaTable(str(py_table)).to_pandas().sort_values(["FileName", "TreeID"]).reset_index(drop=True)
            df_sp = DeltaTable(str(spark_table)).to_pandas().sort_values(["FileName", "TreeID"]).reset_index(drop=True)

            pd.testing.assert_frame_equal(df_py, df_sp, check_like=True)

    def test_real_overwrite_mode_parity(self):
        """Test mode='overwrite' produces identical Delta table results in Python vs PySpark."""
        rs1 = create_sample_resultset()
        rs2 = create_updated_resultset()

        with tempfile.TemporaryDirectory() as tmpdir:
            py_table = Path(tmpdir) / "py_overwrite"
            spark_table = Path(tmpdir) / "spark_overwrite"

            # Initial write rs1
            rs1.to_deltalake(py_table, mode="overwrite", engine="deltalake")
            rs1.to_deltalake(spark_table, mode="overwrite", spark=self.spark)

            # Overwrite with rs2
            res_py = rs2.to_deltalake(py_table, mode="overwrite", engine="deltalake")
            res_sp = rs2.to_deltalake(spark_table, mode="overwrite", spark=self.spark)

            self.assertEqual(res_py.num_inserted, res_sp.num_inserted)

            df_py = DeltaTable(str(py_table)).to_pandas().sort_values("FileName").reset_index(drop=True)
            df_sp = DeltaTable(str(spark_table)).to_pandas().sort_values("FileName").reset_index(drop=True)

            pd.testing.assert_frame_equal(df_py, df_sp, check_like=True)

    def test_real_lowercase_columns_and_mapping_parity(self):
        """Test lowercasing and column mapping parity in Python vs PySpark."""
        rs = create_sample_resultset()

        with tempfile.TemporaryDirectory() as tmpdir:
            py_table = Path(tmpdir) / "py_mapped"
            spark_table = Path(tmpdir) / "spark_mapped"

            rs.to_deltalake(
                py_table,
                mode="overwrite",
                lowercase_columns=True,
                column_mapping={"TreeID": "tree_identifier"},
                engine="deltalake",
            )

            rs.to_deltalake(
                spark_table,
                mode="overwrite",
                lowercase_columns=True,
                column_mapping={"TreeID": "tree_identifier"},
                spark=self.spark,
            )

            df_py = DeltaTable(str(py_table)).to_pandas().sort_values("tracefilename").reset_index(drop=True)
            df_sp = DeltaTable(str(spark_table)).to_pandas().sort_values("tracefilename").reset_index(drop=True)

            self.assertIn("tracefilename", df_py.columns)
            self.assertIn("tree_identifier", df_py.columns)
            self.assertIn("rpmcoefa", df_py.columns)

            pd.testing.assert_frame_equal(df_py, df_sp, check_like=True)

    def test_real_compound_merge_key_parity(self):
        """Test compound merge key parity in Python vs PySpark."""
        rs1 = create_sample_resultset()

        with tempfile.TemporaryDirectory() as tmpdir:
            py_table = Path(tmpdir) / "py_compound"
            spark_table = Path(tmpdir) / "spark_compound"

            rs1.to_deltalake(py_table, mode="overwrite", engine="deltalake")
            rs1.to_deltalake(spark_table, mode="overwrite", spark=self.spark)

            rs2 = ResiResultSet()
            rs2.results.append(
                ResiResult(
                    filename="trace1.rgp",
                    descriptors={
                        "FileName": "trace1.rgp",
                        "TreeID": "Tree-101",
                        "DBHOB": 99.0,
                    }
                )
            )

            res_py = rs2.to_deltalake(py_table, mode="merge", merge_key=["FileName", "TreeID"], engine="deltalake")
            res_sp = rs2.to_deltalake(spark_table, mode="merge", merge_key=["FileName", "TreeID"], spark=self.spark)

            self.assertEqual(res_py.num_inserted, res_sp.num_inserted)
            self.assertEqual(res_py.num_updated, res_sp.num_updated)

            df_py = DeltaTable(str(py_table)).to_pandas().sort_values("FileName").reset_index(drop=True)
            df_sp = DeltaTable(str(spark_table)).to_pandas().sort_values("FileName").reset_index(drop=True)

            pd.testing.assert_frame_equal(df_py, df_sp, check_like=True)


    def _engine(self, path):
        info = DeltaTable(str(path)).history(1)[0]
        return 'spark' if 'Spark' in str(info.get('engineInfo', '')) else 'deltalake'

    def test_engine_choice(self):
        """With a session active, engine and storage_options decide the engine."""
        rs = create_sample_resultset()
        with tempfile.TemporaryDirectory() as tmpdir:
            for name, kwargs, expected in [
                ("auto", {}, 'spark'),
                ("rs", {"engine": "deltalake"}, 'deltalake'),
                ("opts", {"storage_options": {"timeout": "120s"}}, 'deltalake'),
            ]:
                path = Path(tmpdir) / name
                rs.to_deltalake(path, mode="merge", merge_key="FileName", **kwargs)
                self.assertEqual(self._engine(path), expected, name)

    def test_schema_evolution_leaves_session_setting(self):
        """A schema-merging merge adds columns without changing the session."""
        key = "spark.databricks.delta.schema.autoMerge.enabled"
        before = self.spark.conf.get(key, None)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "evolve"
            create_sample_resultset().to_deltalake(path, mode="merge", spark=self.spark)
            rs = ResiResultSet()
            rs.results.append(ResiResult(filename="trace9.rgp",
                                         descriptors={"FileName": "trace9.rgp", "NewColumn": 1.5}))
            rs.to_deltalake(path, mode="merge", spark=self.spark)
            df = DeltaTable(str(path)).to_pandas()
            self.assertIn("NewColumn", df.columns)
            self.assertEqual(df.loc[df.FileName == "trace9.rgp", "NewColumn"].iloc[0], 1.5)
        self.assertEqual(self.spark.conf.get(key, None), before)

if __name__ == "__main__":
    unittest.main()
