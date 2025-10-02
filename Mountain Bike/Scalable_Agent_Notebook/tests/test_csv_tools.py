import os
import pytest
from rag_manager.core.agent import AgentCore


@pytest.fixture
def agent():
    return AgentCore()


def test_write_and_read_csv(agent, tmp_path):
    filename = tmp_path / "test_simple.csv"
    data = [{"ReqID": "R1", "Text": "System shall brake"}, {"ReqID": "R2", "Text": "System shall steer"}]

    agent.run("write_csv", input_data={"filename": str(filename), "data": data})
    result = agent.run("read_csv", input_data={"filename": str(filename)})

    assert result["rows"] == 2
    assert "ReqID" in result["columns"]


def test_write_and_read_leveled_csv(agent, tmp_path):
    filename = tmp_path / "mtb_hierarchy.csv"
    hierarchy = [
        {"level": 1, "name": "Mountain Bike"},
        {"level": 2, "name": "Frame", "parent": "Mountain Bike"},
        {"level": 3, "name": "Front Fork", "parent": "Suspension"},
    ]

    agent.run("write_leveled_csv", input_data={"filename": str(filename), "hierarchy": hierarchy})
    result = agent.run("read_leveled_csv", input_data={"filename": str(filename)})

    assert result["rows"] == 3
    assert any(node["name"] == "Mountain Bike" for node in result["hierarchy_full"])