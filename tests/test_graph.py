import pytest

# Adjust the import path based on your project structure and how 'app' is discoverable.
# This assumes that the 'MB-Sparrow-main' directory is the project root and is in PYTHONPATH,
# or that pytest is run from 'MB-Sparrow-main'.
try:
    from app.agents_v2.orchestration import app as compiled_graph
except ImportError as e:
    # Fallback for different execution contexts or if PYTHONPATH is not set up as expected
    # This might happen if tests are run from within the 'tests' directory directly
    import sys
    import os
    # Add the project root to sys.path
    # This assumes 'tests' is directly under the project root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    try:
        from app.agents_v2.orchestration import app as compiled_graph
    except ImportError:
        # If it still fails, raise the original error for clarity
        raise e

def test_graph_compiles_successfully():
    """Tests that the LangGraph graph compiles without errors."""
    try:
        # The 'compiled_graph' is imported from orchestration.__init__.py
        # which should already be the result of workflow.compile()
        # So, the act of importing it (if compilation happens at import time)
        # or simply having it means it's compiled.
        assert compiled_graph is not None, "Graph did not compile or is None."
        # Optionally, you could check its type if you know what LangGraph's compile() returns
        # For example, if it's a `CompiledGraph` instance or similar.
        # from langgraph.graph.graph import CompiledGraph # This is a guess, actual class may vary
        # assert isinstance(compiled_graph, CompiledGraph), "Graph is not a CompiledGraph instance."
        print("Graph imported/compiled successfully.")
    except Exception as e:
        pytest.fail(f"Graph compilation failed with an exception: {e}")

# To run this test, navigate to the project root in your terminal and run:
# python -m pytest
# Or simply: pytest (if your environment is set up for it)
