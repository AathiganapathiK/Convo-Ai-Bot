import unittest
import io
import sys
from semantic.diagnostic_trace import PipelineDiagnosticTracer


class TestPipelineDiagnosticTracer(unittest.TestCase):
    """
    Focused unit tests for temporary backend pipeline diagnostic tracer.
    """

    def test_start_trace_and_recording(self):
        question = "Show last year cotton sales"
        PipelineDiagnosticTracer.start_trace(question=question, session_id=123, connection_id="conn_abc")

        # Record clarification
        PipelineDiagnosticTracer.record_clarification(required=False)

        # Record semantic
        sem_res = {
            "metric_objects": [{
                "business_name": "Sales",
                "metric_name": "py",
                "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                "column_name": "PY",
                "aggregation_type": "SUM"
            }],
            "dimension_objects": [],
            "value_matches": [{
                "business_name": "ProdGrp2",
                "dimension": "ProdGrp2",
                "table_name": "QB_MDJMD_SALES_5YRS_SUMMARY",
                "column_name": "ProdGrp2",
                "operator": "=",
                "value": "WHITE SHIRT 100% COTTON",
                "provenance": "EXPLICIT_THIS_TURN"
            }]
        }
        PipelineDiagnosticTracer.record_semantic(sem_res)

        # Record SQL stages
        PipelineDiagnosticTracer.record_sql("generated", "SELECT SUM(PY) FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE ProdGrp2 = 'WHITE SHIRT 100% COTTON'")
        PipelineDiagnosticTracer.record_sql("validated", "SELECT TOP 100 SUM(PY) FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE ProdGrp2 = 'WHITE SHIRT 100% COTTON'")
        PipelineDiagnosticTracer.record_sql("executed", "SELECT TOP 100 SUM(PY) FROM QB_MDJMD_SALES_5YRS_SUMMARY WHERE ProdGrp2 = 'WHITE SHIRT 100% COTTON'")

        # Record Result
        PipelineDiagnosticTracer.record_result(row_count=1, col_count=1, status="SUCCESS")

        # Record Timings
        PipelineDiagnosticTracer.record_timing("semantic", 0.32)
        PipelineDiagnosticTracer.record_timing("temporal", 0.11)
        PipelineDiagnosticTracer.record_timing("prompt", 0.19)
        PipelineDiagnosticTracer.record_timing("examples", 0.08)
        PipelineDiagnosticTracer.record_timing("ollama", 8.42)
        PipelineDiagnosticTracer.record_timing("validation", 0.075)
        PipelineDiagnosticTracer.record_timing("sql_execution", 0.18)
        PipelineDiagnosticTracer.record_timing("summary", 2.10)

        # Record memory
        PipelineDiagnosticTracer.record_memory(source="DATABASE", count=2)

        # Record context
        history = [
            {
                "question": "Show white shirts",
                "sql_query": "SELECT * FROM sales",
                "semantic_context": {
                    "resolved_values": [{"dimension": "ProdGrp2", "value": "WHITE SHIRT"}],
                    "metrics": [{"business_name": "Sales"}],
                    "dimensions": [{"business_name": "ProdGrp2"}]
                }
            }
        ]
        PipelineDiagnosticTracer.record_context(history)

        # Capture output of print_final_trace
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            PipelineDiagnosticTracer.print_final_trace()
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()

        # Verify required headers and sections
        self.assertIn("================ TEMPORARY PIPELINE TRACE — REMOVE AFTER STABILIZATION ================", output)
        self.assertIn("================ END TEMPORARY PIPELINE TRACE ================", output)
        self.assertIn("Show last year cotton sales", output)
        self.assertIn("CLARIFICATION:", output)
        self.assertIn("SEMANTIC:", output)
        self.assertIn("TEMPORAL:", output)
        self.assertIn("FILTERS:", output)
        self.assertIn("TABLE:", output)
        self.assertIn("SQL:", output)
        self.assertIn("RESULT:", output)
        self.assertIn("CONTEXT:", output)
        self.assertIn("TIMING:", output)

        self.assertIn("Generated:", output)
        self.assertIn("Validated:", output)
        self.assertIn("Executed:", output)

        self.assertIn("Sales", output)
        self.assertIn("PY", output)
        self.assertIn("QB_MDJMD_SALES_5YRS_SUMMARY", output)
        self.assertNotIn("password", output.lower())
        self.assertNotIn("secret", output.lower())

    def test_marker_presence(self):
        """
        Verify TEMP_PIPELINE_TRACE_REMOVE_LATER is present in diagnostic_trace.py.
        """
        from semantic import diagnostic_trace
        import inspect
        source = inspect.getsource(diagnostic_trace)
        self.assertIn("TEMP_PIPELINE_TRACE_REMOVE_LATER", source)
