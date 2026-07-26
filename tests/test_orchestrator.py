from unittest.mock import patch
from src.orchestrator import ResearchAgent, StepStatus


@patch("src.orchestrator.search.run")
@patch("src.orchestrator.fetch.run")
def test_happy_path_all_steps_succeed(mock_fetch, mock_search):
    mock_search.return_value = {"urls": ["https://example.com"], "snippets": ["snippet"]}
    mock_fetch.return_value = {"texts": ["Kubernetes autoscaling adjusts pod replicas " * 10], "failed_urls": []}

    agent = ResearchAgent()
    with patch.object(agent.llm, "synthesize", return_value={"text": "a summary", "tokens": 50}):
        state = agent.run("benefits of Kubernetes autoscaling")

    assert state.steps[0].status == StepStatus.SUCCESS  # search
    assert state.steps[1].status == StepStatus.SUCCESS  # fetch
    assert state.steps[2].status == StepStatus.SUCCESS  # synthesize
    assert state.steps[2].output["text"] == "a summary"


@patch("src.orchestrator.search.run")
def test_search_failure_stops_pipeline_early(mock_search):
    mock_search.side_effect = Exception("search API down")

    agent = ResearchAgent()
    state = agent.run("any query")

    assert state.steps[0].status == StepStatus.FAILED
    assert len(state.steps) == 1  # pipeline should stop, not attempt fetch/synthesize


@patch("src.orchestrator.search.run")
@patch("src.orchestrator.fetch.run")
def test_offtopic_content_fails_relevance_gate(mock_fetch, mock_search):
    mock_search.return_value = {"urls": ["https://example.com"], "snippets": ["snippet"]}
    mock_fetch.return_value = {"texts": ["completely unrelated cooking content " * 10], "failed_urls": []}

    agent = ResearchAgent()
    state = agent.run("Kubernetes autoscaling")

    assert state.steps[-1].status == StepStatus.FAILED
    assert "relevance" in state.steps[-1].error