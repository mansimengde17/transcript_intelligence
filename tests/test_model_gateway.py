import unittest

from ti.model_gateway import BudgetExceeded, BudgetPolicy, DeterministicGateway


class ModelGatewayTests(unittest.TestCase):
    def test_deterministic_gateway_has_zero_cost(self):
        result = DeterministicGateway().generate_json("system", "summarize this evidence", BudgetPolicy())
        self.assertEqual(result.estimated_cost_usd, 0.0)
        self.assertEqual(result.model, "deterministic")

    def test_budget_blocks_oversized_input(self):
        with self.assertRaises(BudgetExceeded):
            DeterministicGateway().generate_json("system", "x" * 20, BudgetPolicy(max_input_characters=10))


if __name__ == "__main__":
    unittest.main()
