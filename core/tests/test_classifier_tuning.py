import json

from django.test import SimpleTestCase

from classifier.neural_training import TrainingConfig
from classifier.tuning import (
    DEFAULT_LABEL,
    Trial,
    best_result,
    default_grid,
    format_table,
    run_tuning,
    to_json,
)
from core.tests.classifier_fixtures import keyword_dataset


class TuningGridTests(SimpleTestCase):
    def test_should_vary_one_option_at_a_time_from_the_default(self):
        grid = default_grid()

        labels = [trial.label for trial in grid]

        self.assertEqual(labels[0], DEFAULT_LABEL)
        self.assertEqual(len(labels), 6)
        self.assertEqual(sum(trial.filter_noise for trial in grid), 1)
        self.assertEqual({trial.config.hidden_size for trial in grid}, {TrainingConfig().hidden_size})


class TuningRunTests(SimpleTestCase):
    def test_should_score_every_trial_on_validation_and_pick_the_best(self):
        dataset = keyword_dataset()
        trials = [
            Trial(DEFAULT_LABEL, TrainingConfig(max_epochs=5, patience=2)),
            Trial("filter_noise", TrainingConfig(max_epochs=5, patience=2), filter_noise=True),
        ]

        results = run_tuning(dataset, trials)
        table = format_table(results)
        payload = json.loads(to_json(results))

        self.assertEqual([result.label for result in results], [DEFAULT_LABEL, "filter_noise"])
        for result in results:
            self.assertEqual(set(result.validation_f1), {"discipline", "document_type", "area"})
            self.assertAlmostEqual(result.mean_f1, sum(result.validation_f1.values()) / 3)
        self.assertIn("best on validation:", table)
        self.assertEqual(payload[1]["filter_noise"], True)
        self.assertEqual(payload[0]["config"]["max_epochs"], 5)
        self.assertIn(best_result(results).label, (DEFAULT_LABEL, "filter_noise"))

    def test_should_prefer_the_default_trial_on_a_tie(self):
        dataset = keyword_dataset()
        config = TrainingConfig(max_epochs=3, patience=2)
        trials = [Trial("same", config), Trial(DEFAULT_LABEL, config)]

        results = run_tuning(dataset, trials)

        self.assertEqual(best_result(results).label, DEFAULT_LABEL)
