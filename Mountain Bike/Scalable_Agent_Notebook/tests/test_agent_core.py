import pytest
from pathlib import Path
from rag_manager.core.agent import AgentCore


@pytest.fixture
def agent():
    agent = AgentCore()
    return agent


def test_multiple_artifacts(agent, tmp_path):
    agent.create_package("Engine")
    agent.add_artifact("Engine", "yaml", "--- system: engine ---")
    agent.add_artifact("Engine", "reqs", ["Req-1", "Req-2"])
    agent.use_package("Engine")

    artifacts = [a.type for a in agent.artifacts.get_active_package().artifacts.values()]
    assert "yaml" in artifacts
    assert "reqs" in artifacts


def test_multiple_tools_pipeline(agent, tmp_path):
    agent.create_package("Engine")
    agent.add_artifact("Engine", "doc", "Engine must start and stop safely.")
    agent.use_package("Engine")

    r1 = agent.run("summarizer", "Engine", input_data="Summarize engine reqs")
    r2 = agent.run("wordcount", "Engine")

    assert isinstance(r1, dict)
    assert isinstance(r2, dict)

    pipeline_file = agent.export_pipeline(tmp_path / "engine_pipeline.json", package_name="Engine")
    assert pipeline_file.exists()

    results = agent.import_pipeline(pipeline_file, package_name="Engine")
    assert len(results) == 2


def test_switch_packages(agent):
    agent.create_package("LandingGear")
    agent.add_artifact("LandingGear", "doc", "Landing gear is essential for takeoff and landing.")
    agent.use_package("LandingGear")
    lg_result = agent.run("wordcount")
    assert lg_result["word_count"] > 0

    agent.create_package("Engine")
    agent.add_artifact("Engine", "doc", "Engine powers the aircraft.")
    agent.use_package("Engine")
    eng_result = agent.run("wordcount")
    assert eng_result["word_count"] > 0

    assert lg_result["word_count"] != eng_result["word_count"]


def test_export_import_package(agent, tmp_path):
    agent.create_package("Engine")
    agent.add_artifact("Engine", "doc", "Engine details.")
    agent.artifacts.export_package("Engine", tmp_path / "Engine_package.zip")

    restored = agent.artifacts.import_package(tmp_path / "Engine_package.zip")
    assert restored.name == "Engine"
    assert any(a.type == "doc" for a in restored.artifacts.values())


def test_large_input(agent):
    agent.create_package("Engine")
    long_text = "Engine data " * 5000  # ~50k chars
    agent.add_artifact("Engine", "bigdoc", long_text)

    result = agent.run("wordcount", "Engine")
    assert result["word_count"] == len(long_text.split())


def test_decision_recording(agent):
    # Setup
    agent.create_package("LandingGear")
    agent.add_artifact("LandingGear", "doc", "Landing gear is essential for safe takeoff and landing.")
    agent.use_package("LandingGear")

    # Run a tool
    wc_result = agent.run("wordcount", "LandingGear")
    assert "word_count" in wc_result

    # Simulate a decision point
    decision = agent.record_decision(rule="wordcount>5", choice="Summarize")

    # Run next tool based on decision
    if decision["choice"] == "Summarize":
        summary_result = agent.run("summarizer", "LandingGear", input_data="Summarize the landing gear doc")
        assert "summary" in summary_result

    # Verify history contains wordcount, decision, and summarizer
    history = agent.get_history()
    tools = [h["tool"] for h in history]
    assert "wordcount" in tools
    assert "decision" in tools
    assert "summarizer" in tools

def test_tool_output_captured_as_artifact(agent):
    # Setup
    agent.create_package("LandingGear")
    agent.add_artifact("LandingGear", "doc", "Landing gear is essential for safe takeoff and landing.")
    agent.use_package("LandingGear")

    # Run tool with capture_as_artifact=True
    result = agent.run("wordcount", "LandingGear", capture_as_artifact=True)
    assert "word_count" in result

    # Check that a new artifact of type "wordcount" exists
    pkg = agent.artifacts.get_active_package()
    artifact_types = [a.type for a in pkg.artifacts.values()]
    assert "wordcount" in artifact_types

    # Run tool with capture_as_artifact=False
    result2 = agent.run("summarizer", "LandingGear", input_data="Summarize doc", capture_as_artifact=False)
    assert "summary" in result2

    # Verify that "summarizer" artifact was NOT added this time
    artifact_types_after = [a.type for a in pkg.artifacts.values()]
    assert artifact_types_after.count("summarizer") == 0


def test_history_contains_state(agent):
    # Setup
    agent.create_package("LandingGear")
    agent.add_artifact("LandingGear", "doc", "Landing gear is essential for safe takeoff and landing.")
    agent.use_package("LandingGear")

    # Run a couple of tools
    wc_result = agent.run("wordcount", "LandingGear")
    sm_result = agent.run("summarizer", "LandingGear", input_data="Summarize doc")

    # Retrieve history
    history = agent.get_history()
    assert len(history) >= 2

    # Check that each record has a state entry
    for record in history:
        assert "state" in record
        assert isinstance(record["state"], dict)
        # state should mirror the tool output structure
        if isinstance(record["output"], dict):
            assert set(record["state"].keys()) == set(record["output"].keys())
