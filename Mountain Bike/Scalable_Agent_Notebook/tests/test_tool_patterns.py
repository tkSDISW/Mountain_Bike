import pytest
from rag_manager.tools.tool_patterns import ImportTool, ExportTool, TransformTool, GenerativeTool

# Dummy implementations for testing
class DummyImport(ImportTool):
    def __init__(self):
        super().__init__("dummy_import", "Test import tool")
    def load(self, input_data):
        return {"dummy": "data"}, {"source": "test.csv"}

class DummyExport(ExportTool):
    def __init__(self):
        super().__init__("dummy_export", "Test export tool")
    def save(self, artifact, target, **kwargs):
        return f"saved to {target}"

class DummyTransform(TransformTool):
    def __init__(self):
        super().__init__("dummy_transform", "Test transform tool")
    def transform(self, artifact, params):
        return {"transformed": True}

class DummyGenerative(GenerativeTool):
    def __init__(self):
        super().__init__("dummy_generate", "Test generative tool")
    def generate(self, prompt, context=None):
        return f"Generated content from: {prompt}"


@pytest.mark.parametrize("tool_class,expected_category", [
    (DummyImport, "import"),
    (DummyExport, "export"),
    (DummyTransform, "transform"),
    (DummyGenerative, "generate"),
])
def test_tool_categories(tool_class, expected_category):
    tool = tool_class()
    assert tool.category == expected_category
    assert hasattr(tool, "run")
    assert callable(tool.run)
