import unittest
from unittest.mock import patch, MagicMock
from app.agents_v2.primary_agent.agent import run_primary_agent
from app.agents_v2.primary_agent.schemas import PrimaryAgentState
from langchain_core.messages import HumanMessage, AIMessageChunk, ToolCall

class TestPrimaryAgent(unittest.TestCase):

    @patch('app.agents_v2.primary_agent.agent.model_with_tools')
    @patch('app.agents_v2.primary_agent.agent.find_similar_documents')
    def test_run_primary_agent_tool_call(self, mock_find_docs, mock_model_with_tools):
        """
        Tests that the primary agent correctly identifies the need for a tool, returns a tool call,
        and does not execute it directly.
        """
        # Arrange
        # 1. Mock context-providing functions to simulate a scenario requiring a web search.
        mock_find_docs.return_value = []  # No internal documents found

        # 2. Mock the response from the LLM's stream to simulate a tool call.
        tool_call = ToolCall(
            name="tavily_web_search",
            args={"query": "how to setup email"},
            id="tool_call_123"
        )
        mock_chunk = AIMessageChunk(content="", tool_calls=[tool_call])
        mock_model_with_tools.stream.return_value = iter([mock_chunk])

        # 3. Create a valid PrimaryAgentState instance.
        initial_state = PrimaryAgentState(
            messages=[HumanMessage(content="how to setup email")]
        )

        # Act
        # The agent returns a dictionary containing a message stream (generator).
        result_dict = run_primary_agent(initial_state)

        # Assert
        # 1. Check that context-providing functions were called.
        mock_find_docs.assert_called_once_with("how to setup email", top_k=4)

        # 2. Check that the LLM was called.
        mock_model_with_tools.stream.assert_called_once()

        # 3. Verify the result dictionary and the message stream it contains.
        self.assertIn("messages", result_dict)
        self.assertIn("reflection_feedback", result_dict)
        
        # Consume the generator to get the message chunks
        message_stream = result_dict["messages"]
        final_messages = list(message_stream)

        self.assertEqual(len(final_messages), 1)
        last_message = final_messages[0]
        self.assertIsInstance(last_message, AIMessageChunk)
        self.assertTrue(last_message.tool_calls)
        self.assertEqual(last_message.tool_calls[0]['name'], "tavily_web_search")
        self.assertEqual(last_message.tool_calls[0]['id'], "tool_call_123")

if __name__ == '__main__':
    unittest.main()