"""Unit tests for pure state reducers."""

import unittest
from agentic_workflow.domain.models import WorkflowMessage
from agentic_workflow.domain.reducers import append_messages, increment_counter, merge_dicts


class TestReducers(unittest.TestCase):
    def test_append_messages(self):
        msg1 = WorkflowMessage(role="user", content="Hello")
        msg2 = WorkflowMessage(role="assistant", content="Hi")
        
        # Test initial append
        result = append_messages(None, msg1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].content, "Hello")

        # Test subsequent append
        result2 = append_messages(result, [msg2])
        self.assertEqual(len(result2), 2)
        self.assertEqual(result2[1].content, "Hi")

    def test_increment_counter(self):
        self.assertEqual(increment_counter(None), 1)
        self.assertEqual(increment_counter(5), 6)
        self.assertEqual(increment_counter(5, increment_by=3), 8)

    def test_merge_dicts(self):
        d1 = {"a": 1, "b": 2}
        d2 = {"b": 99, "c": 3}
        merged = merge_dicts(d1, d2)
        self.assertEqual(merged, {"a": 1, "b": 99, "c": 3})
        # Verify immutability of original
        self.assertEqual(d1, {"a": 1, "b": 2})


if __name__ == "__main__":
    unittest.main()
