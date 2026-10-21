from django.test import SimpleTestCase

from classifier.baseline_training import predict_baseline, train_baseline
from classifier.catalog import FIELDS
from classifier.splitting import split_dataset
from core.tests.classifier_fixtures import keyword_dataset


class BaselineTrainingTests(SimpleTestCase):
    def test_should_train_one_model_per_field_on_the_training_rows_only(self):
        dataset = keyword_dataset()
        split = split_dataset(dataset)

        pipelines = train_baseline(dataset, split)

        self.assertEqual(list(pipelines), list(FIELDS))
        for name in FIELDS:
            train_classes = sorted({dataset.labels[name][index] for index in split.train})
            self.assertEqual(list(pipelines[name].classes_), train_classes)

    def test_should_predict_every_field_for_unseen_rows(self):
        dataset = keyword_dataset()
        split = split_dataset(dataset)
        pipelines = train_baseline(dataset, split)
        test_texts = [dataset.texts[index] for index in split.test]

        predictions = predict_baseline(pipelines, test_texts)

        for name in FIELDS:
            expected = [dataset.labels[name][index] for index in split.test]
            self.assertEqual(predictions[name], expected)
