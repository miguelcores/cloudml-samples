# Copyright 2018 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import logging
import os
import sys

from . import model
from . import utils

import numpy as np
import tensorflow as tf

from tensorflow.contrib.training.python.training import hparam


def get_args():
	"""Argument parser.

	Returns:
		Dictionary of arguments.
	"""
	parser = argparse.ArgumentParser()
	parser.add_argument(
		'--job-dir',
		type=str,
		help='GCS location to write checkpoints and export models')
	parser.add_argument(
		'--train-file',
		type=str,
		required=True,
		help='Dataset file local or GCS')
	parser.add_argument(
		'--test-split',
		type=float,
		default=0.2,
		help='Split between training and test, default=0.2')
	parser.add_argument(
		'--num-epochs',
		type=float,
		default=500,
		help='number of times to go through the data, default=500')
	parser.add_argument(
		'--batch-size',
		type=int,
		default=128,
		help='number of records to read during each training step, default=128')
	parser.add_argument(
		'--learning-rate',
		type=float,
		default=.001,
		help='learning rate for gradient descent, default=.001')

	return parser.parse_args()


def _setup_logging():
	"""Sets up logging."""
	logger = logging.getLogger()
	logger.setLevel(logging.INFO)
	# Set tf logging to avoid duplicate logging. If the handlers are not removed,
	# then we will have duplicate logging :
	# From tf loggging written to stderr stream, and
	# From python logger written to stdout stream.
	tf_logger = logging.getLogger('tensorflow')
	while tf_logger.handlers:
		tf_logger.removeHandler(tf_logger.handlers[0])

	# Redirect INFO logs to stdout
	stdout_handler = logging.StreamHandler(sys.stdout)
	stdout_handler.setLevel(logging.INFO)
	logger.addHandler(stdout_handler)

	# Suppress C++ level warnings.
	os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


def train_and_evaluate(hparams):
	"""Helper function: Trains and evaluate model.

	Args:
		hparams: (dict) Command line parameters passed from task.py
	"""
	# Load data.
	(train_data,
	 train_labels), (test_data,
									 test_labels) = utils.load_data(path=hparams.train_file)

	# Shuffle data.
	order = np.argsort(np.random.random(train_labels.shape))
	train_data = train_data[order]
	train_labels = train_labels[order]

	# Normalize features with different scales and ranges.
	train_data, test_data = utils.normalize_data(train_data, test_data)

	# Running configuration.
	run_config = tf.estimator.RunConfig(save_checkpoints_steps=500)

	# Training steps
	train_steps = hparams.num_epochs * len(train_data) / hparams.batch_size
	# Reshape Label numpy array.
	train_labels = np.asarray(train_labels).astype('float32').reshape((-1, 1))
	# Create TrainSpec.
	train_spec = tf.estimator.TrainSpec(
		input_fn=lambda: model.input_fn(
			train_data,
			train_labels,
			hparams.batch_size,
			mode=tf.estimator.ModeKeys.TRAIN),
		max_steps=train_steps)

	# Create exporter information.
	exporter = tf.estimator.LatestExporter('exporter', model.serving_input_fn)
	# Reshape Label numpy array.
	test_labels = np.asarray(test_labels).astype('float32').reshape((-1, 1))
	# Create EvalSpec.
	eval_spec = tf.estimator.EvalSpec(
		input_fn=lambda: model.input_fn(
			test_data,
			test_labels,
			hparams.batch_size,
			mode=tf.estimator.ModeKeys.EVAL),
		steps=None,
		exporters=[exporter],
		start_delay_secs=10,
		throttle_secs=10)

	# Create estimator.
	estimator = model.keras_estimator(
		model_dir=hparams.job_dir,
		config=run_config,
		params={'learning_rate': hparams.learning_rate,
						'num_features': train_data.shape[1]})

	# Start training.
	tf.estimator.train_and_evaluate(estimator, train_spec, eval_spec)


if __name__ == '__main__':

	args = get_args()
	_setup_logging()

	# Run the training job
	hparams = hparam.HParams(**args.__dict__)
	train_and_evaluate(hparams)
