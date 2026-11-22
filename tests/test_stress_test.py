import unittest

from fastapi.testclient import TestClient

from backend.api import app
from backend.stress_test import stress_test_portfolio


class StressTestTests(unittest.TestCase):

    def setUp(self):
        self.weights = {
            "VTI": 0.6,
            "NVDA": 0.4
        }

        self.client = TestClient(app)

    def test_default_scenarios(self):
        result = stress_test_portfolio(
            self.weights,
            10000
        )

        self.assertEqual(
            len(result["scenarios"]),
            4
        )

        for scenario, loss in zip(
            result["scenarios"],
            (0.10, 0.20, 0.35, 0.50)
        ):
            self.assertAlmostEqual(
                scenario["portfolio_return"],
                -loss
            )

            self.assertAlmostEqual(
                scenario["ending_value"],
                10000 * (1 - loss)
            )

            self.assertAlmostEqual(
                scenario["value_change"],
                -10000 * loss
            )

    def test_asset_specific_shocks(self):
        result = stress_test_portfolio(
            self.weights,
            10000,
            {
                "Mixed shock": {
                    "NVDA": -0.40,
                    "VTI": 0.10
                }
            }
        )["scenarios"][0]

        self.assertAlmostEqual(
            result["portfolio_return"],
            -0.10
        )

        self.assertAlmostEqual(
            result["ending_value"],
            9000
        )

        self.assertAlmostEqual(
            result["assets"][0]["value_change"],
            600
        )

        self.assertAlmostEqual(
            result["assets"][1]["value_change"],
            -1600
        )

        self.assertAlmostEqual(
            sum(
                asset["value_change"]
                for asset in result["assets"]
            ),
            result["value_change"]
        )

    def test_total_loss_and_gain(self):

        for shock, expected in (
            (-1, 0),
            (1, 2000),
            (0, 1000)
        ):
            with self.subTest(shock=shock):

                result = stress_test_portfolio(
                    {"VTI": 1.0},
                    1000,
                    {
                        "Scenario": {
                            "VTI": shock
                        }
                    }
                )["scenarios"][0]

                self.assertAlmostEqual(
                    result["ending_value"],
                    expected
                )

    def test_invalid_shocks(self):

        for shock in (
            -1.01,
            1.01,
            float("nan"),
            float("inf"),
            True,
            "0.2"
        ):
            with self.subTest(shock=shock):

                with self.assertRaises(ValueError):
                    stress_test_portfolio(
                        self.weights,
                        1000,
                        {
                            "Invalid": {
                                "VTI": shock,
                                "NVDA": 0
                            }
                        }
                    )

    def test_invalid_scenarios(self):

        for scenarios in (
            {},
            {"Missing": {"VTI": -0.1}},
            {
                "Extra": {
                    "VTI": 0,
                    "NVDA": 0,
                    "AMZN": 0
                }
            },
            {"": {"VTI": 0, "NVDA": 0}},
            {
                str(i): {"VTI": 0, "NVDA": 0}
                for i in range(11)
            }
        ):
            with self.subTest(scenarios=scenarios):

                with self.assertRaises(ValueError):
                    stress_test_portfolio(
                        self.weights,
                        1000,
                        scenarios
                    )

    def test_invalid_portfolio(self):

        for value in (
            0,
            -1,
            float("nan"),
            True,
            1e10
        ):
            with self.subTest(value=value):

                with self.assertRaises(ValueError):
                    stress_test_portfolio(
                        self.weights,
                        value
                    )

        with self.assertRaises(ValueError):
            stress_test_portfolio({
                "VTI": 0.4,
                "NVDA": 0.4
            })

    def test_endpoint_returns_custom_scenario(self):

        response = self.client.post(
            "/api/stress-test",
            json={
                "weights": self.weights,

                "initial_value": 10000,

                "scenarios": {
                    "Mixed shock": {
                        "VTI": 0.1,
                        "NVDA": -0.4
                    }
                }
            }
        )

        self.assertEqual(
            response.status_code,
            200
        )

        self.assertAlmostEqual(
            response.json()["scenarios"][0]["ending_value"],
            9000
        )

    def test_endpoint_normalizes_aliases_and_rounding(self):

        response = self.client.post(
            "/api/stress-test",
            json={
                "weights": {
                    "brk.b": 0.5001,
                    "vti": 0.5
                },

                "scenarios": {
                    "Shock": {
                        "BRK-B": -0.2,
                        "VTI": -0.1
                    }
                }
            }
        )

        self.assertEqual(
            response.status_code,
            200
        )

        body = response.json()

        self.assertEqual(
            set(body["weights"]),
            {"BRK-B", "VTI"}
        )

        self.assertAlmostEqual(
            sum(body["weights"].values()),
            1.0
        )

    def test_endpoint_rejects_incomplete_scenarios(self):

        response = self.client.post(
            "/api/stress-test",
            json={
                "weights": self.weights,

                "scenarios": {
                    "Invalid": {
                        "VTI": -0.1
                    }
                }
            }
        )

        self.assertEqual(
            response.status_code,
            422
        )

    def test_endpoint_default_scenarios(self):

        response = self.client.post(
            "/api/stress-test",
            json={
                "weights": self.weights
            }
        )

        self.assertEqual(
            response.status_code,
            200
        )

        self.assertEqual(
            len(response.json()["scenarios"]),
            4
        )


if __name__ == "__main__":
    unittest.main()