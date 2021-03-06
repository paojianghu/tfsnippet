# -*- coding: utf-8 -*-
import os
import re
import time
import unittest

import numpy as np
import tensorflow as tf

from tfsnippet.scaffold import train_loop, SummaryWriter
from tfsnippet.utils import (ensure_variables_initialized, set_variable_values,
                             get_variable_values, TemporaryDirectory)
from tests.helper import TestCase


class TrainLoopTestCase(TestCase):

    def assertMatches(self, a, b):
        self.assertTrue(
            not not re.match(b, a),
            msg='%r should match %r' % (b, a)
        )

    def test_counter_attributes(self):
        with train_loop([]) as loop:
            self.assertEqual(loop.epoch, 0)
            self.assertEqual(loop.step, 0)
            self.assertIsNone(loop.max_epoch)
            self.assertIsNone(loop.max_step)

        with train_loop([], initial_epoch=1, initial_step=3,
                        max_epoch=2, max_step=10) as loop:
            self.assertEqual(loop.epoch, 1)
            self.assertEqual(loop.step, 3)
            self.assertEqual(loop.max_epoch, 2)
            self.assertEqual(loop.max_step, 10)
            loop.max_epoch = 20
            loop.max_step = 100
            self.assertEqual(loop.max_epoch, 20)
            self.assertEqual(loop.max_step, 100)

    def test_counters(self):
        # test loop with configured `max_epoch`
        with train_loop([], max_epoch=2) as loop:
            epoch_counter = 0
            step_counter = 0
            for epoch in loop.iter_epochs():
                epoch_counter += 1
                self.assertEqual(epoch, epoch_counter)
                x_ans = 0
                for step, x in loop.iter_steps(np.arange(4)):
                    self.assertEqual(step, loop.step)
                    self.assertEqual(epoch, loop.epoch)
                    self.assertEqual(x, x_ans)
                    x_ans += 1
                    step_counter += 1
                    self.assertEqual(step, step_counter)
                self.assertEqual(step_counter, loop.step)
                self.assertEqual(epoch, loop.epoch)
            self.assertEqual(epoch_counter, 2)
            self.assertEqual(step_counter, 8)

        # test loop with configured `max_step`
        with train_loop([], max_step=10) as loop:
            epoch_counter = 0
            step_counter = 0
            for epoch in loop.iter_epochs():
                epoch_counter += 1
                self.assertEqual(epoch, epoch_counter)
                for step in loop.iter_steps():
                    step_counter += 1
                    self.assertEqual(step, step_counter)
            self.assertEqual(epoch_counter, 1)
            self.assertEqual(step_counter, 10)

        # test loop with configured `max_step` with payload
        with train_loop([], max_step=10) as loop:
            epoch_counter = 0
            step_counter = 0
            for epoch in loop.iter_epochs():
                epoch_counter += 1
                self.assertEqual(epoch, epoch_counter)
                x_ans = 0
                for step, x in loop.iter_steps(np.arange(4)):
                    self.assertEqual(x, x_ans)
                    x_ans += 1
                    step_counter += 1
                    self.assertEqual(step, step_counter)
            self.assertEqual(epoch_counter, 3)
            self.assertEqual(step_counter, 10)

        # test loop with configured `max_step` and `max_epoch`,
        # while `max_epoch` finishes first
        with train_loop([], max_step=10, max_epoch=2) as loop:
            epoch_counter = 0
            step_counter = 0
            for epoch in loop.iter_epochs():
                epoch_counter += 1
                self.assertEqual(epoch, epoch_counter)
                for step, _ in loop.iter_steps(np.arange(4)):
                    step_counter += 1
                    self.assertEqual(step, step_counter)
            self.assertEqual(epoch_counter, 2)
            self.assertEqual(step_counter, 8)

        # test loop with configured `max_step` and `max_epoch`,
        # while `max_step` finishes first
        with train_loop([], max_step=10, max_epoch=3) as loop:
            epoch_counter = 0
            step_counter = 0
            for epoch in loop.iter_epochs():
                epoch_counter += 1
                self.assertEqual(epoch, epoch_counter)
                for step, _ in loop.iter_steps(np.arange(4)):
                    step_counter += 1
                    self.assertEqual(step, step_counter)
            self.assertEqual(epoch_counter, 3)
            self.assertEqual(step_counter, 10)

    def test_logs(self):
        logs = []
        with train_loop([], max_step=6, print_function=logs.append) as loop:
            for epoch in loop.iter_epochs():
                for step, x in loop.iter_steps(np.arange(4)):
                    time.sleep(0.01)
                    loop.add_metrics(x=x)
                    if step % 2 == 0:
                        loop.print_logs()
                loop.add_metrics(y=epoch)
                loop.print_logs()
        self.assertMatches('\n'.join(logs), re.compile(
            r'^'
            r'\[Epoch 1, Step 2/6\] step time: 0\.01\d* sec \(±[^ ]+ sec\); '
            r'x: 0\.5 \(±0\.5\)\n'
            r'\[Epoch 1, Step 4/6\] step time: 0\.01\d* sec \(±[^ ]+ sec\); '
            r'x: 2\.5 \(±0\.5\)\n'
            r'\[Epoch 1\] epoch time: 0\.0[456]\d* sec; '
            r'step time: 0\.01\d* sec \(±[^ ]+ sec\); x: 1\.5 \(±1\.11803\); '
            r'y: 1\n'
            r'\[Epoch 2, Step 6/6\] step time: 0\.01\d* sec \(±[^ ]+ sec\); '
            r'x: 0\.5 \(±0\.5\)\n'
            r'\[Epoch 2\] epoch time: 0\.0[23]\d* sec; '
            r'step time: 0\.01\d* sec \(±[^ ]+ sec\); x: 0\.5 \(±0\.5\); y: 2'
            r'$'
        ))

    def test_valid_metric(self):
        # test default "valid_loss"
        logs = []
        with train_loop([], print_function=logs.append) as loop:
            self.assertEqual(loop._valid_metric, 'valid_loss')
            self.assertTrue(loop._valid_metric_smaller_is_better)
            for _ in loop.iter_epochs():
                best_metric = 1.
                for _, valid_loss in loop.iter_steps([0.8, 0.6, 0.7]):
                    loop.add_metrics(valid_loss=valid_loss)
                    best_metric = min(best_metric, valid_loss)
                    self.assertAlmostEqual(loop.best_valid_metric, best_metric)
                    loop.print_logs()
                loop.print_logs()
                break
        self.assertAlmostEqual(loop.best_valid_metric, 0.6)
        self.assertMatches('\n'.join(logs), re.compile(
            r'^'
            r'\[Epoch 1, Step 1\] step time: [^ ]+ sec; '
            r'valid loss: 0\.8 \(\*\)\n'
            r'\[Epoch 1, Step 2\] step time: [^ ]+ sec; '
            r'valid loss: 0\.6 \(\*\)\n'
            r'\[Epoch 1, Step 3\] step time: [^ ]+ sec; '
            r'valid loss: 0\.7\n'
            r'\[Epoch 1\] epoch time: [^ ]+ sec; step time: [^ ]+ sec '
            r'\(±[^ ]+ sec\); valid loss: 0\.7 \(±0\.0816497\)'
            r'$'
        ))

        # test customized valid setting
        logs = []
        with train_loop([], print_function=logs.append,
                        valid_metric=('y', False)) as loop:
            self.assertEqual(loop._valid_metric, 'y')
            self.assertFalse(loop._valid_metric_smaller_is_better)
            for _ in loop.iter_epochs():
                best_metric = 0.
                for _, y in loop.iter_steps([0.7, 0.6, 0.8]):
                    loop.add_metrics(y=y)
                    best_metric = max(best_metric, y)
                    self.assertAlmostEqual(loop.best_valid_metric, best_metric)
                    loop.print_logs()
                loop.print_logs()
                break
        self.assertAlmostEqual(loop.best_valid_metric, 0.8)
        self.assertMatches('\n'.join(logs), re.compile(
            r'^'
            r'\[Epoch 1, Step 1\] step time: [^ ]+ sec; '
            r'y: 0\.7 \(\*\)\n'
            r'\[Epoch 1, Step 2\] step time: [^ ]+ sec; '
            r'y: 0\.6\n'
            r'\[Epoch 1, Step 3\] step time: [^ ]+ sec; '
            r'y: 0\.8 \(\*\)\n'
            r'\[Epoch 1\] epoch time: [^ ]+ sec; step time: [^ ]+ sec '
            r'\(±[^ ]+ sec\); y: 0\.7 \(±0\.0816497\)'
            r'$'
        ))

        # test the setting of "valid_acc"
        with train_loop([], print_function=logs.append,
                        valid_metric='valid_acc') as loop:
            self.assertEqual(loop._valid_metric, 'valid_acc')
            self.assertFalse(loop._valid_metric_smaller_is_better)

        # test the setting of "y"
        with train_loop([], print_function=logs.append,
                        valid_metric='y') as loop:
            self.assertEqual(loop._valid_metric, 'y')
            self.assertTrue(loop._valid_metric_smaller_is_better)

    def test_training_summary(self):
        a = tf.get_variable('a', dtype=tf.float32, shape=(2, 3))
        b = tf.get_variable('b', dtype=tf.float32, shape=(4,))
        c = tf.get_variable('c', dtype=tf.float32, shape=())

        # test param variables in list
        logs = []
        with train_loop([a, b], print_function=logs.append) as loop:
            self.assertEqual(loop.param_vars, [a, b])
            loop.print_training_summary()
        self.assertEqual('\n'.join(logs), (
            'Trainable Parameters (10 in total)\n'
            '----------------------------------\n'
            'a  (2, 3)  6\n'
            'b  (4,)    4\n'
        ))

        # test param variables in dict
        logs = []
        with train_loop({'aa': a, 'bb': b},
                        print_function=logs.append) as loop:
            self.assertEqual(loop.param_vars, {'aa': a, 'bb': b})
            loop.print_training_summary()
        self.assertEqual('\n'.join(logs), (
            'Trainable Parameters (10 in total)\n'
            '----------------------------------\n'
            'aa  (2, 3)  6\n'
            'bb  (4,)    4\n'
        ))

    def test_timeit(self):
        logs = []
        with train_loop([], max_epoch=1, print_function=logs.append) as loop:
            for _ in loop.iter_epochs():
                with loop.timeit('x_timer'):
                    time.sleep(0.01)
                with loop.timeit('y_time'):
                    time.sleep(0.02)
                loop.print_logs()
        self.assertMatches('\n'.join(logs), re.compile(
            r'^'
            r'\[Epoch 1/1\] epoch time: 0\.0[345]\d* sec; '
            r'x timer: 0\.01\d* sec; y time: 0\.0[23]\d* sec'
            r'$'
        ))

    def test_accumulator(self):
        logs = []
        with train_loop([], max_epoch=1, print_function=logs.append) as loop:
            for _ in loop.iter_epochs():
                with loop.accumulator('x') as acc:
                    acc.add(2)
                    acc.add(3, weight=3)
                loop.print_logs()
        self.assertMatches('\n'.join(logs), re.compile(
            r'^'
            r'\[Epoch 1/1\] epoch time: [^ ]+ sec; x: 2\.75'
            r'$'
        ))

    def test_summary_writer(self):
        def read_summary(summary_dir):
            # read the metric summary
            loss_steps = []
            loss_values = []
            valid_loss_steps = []
            valid_loss_values = []
            x_steps = []
            x_values = []
            tags = set()

            event_file_path = os.path.join(
                summary_dir, os.listdir(summary_dir)[0])
            for e in tf.train.summary_iterator(event_file_path):
                for v in e.summary.value:
                    tags.add(v.tag)
                    if v.tag == 'loss':
                        loss_steps.append(e.step)
                        loss_values.append(v.simple_value)
                    elif v.tag == 'valid_loss':
                        valid_loss_steps.append(e.step)
                        valid_loss_values.append(v.simple_value)
                    elif v.tag == 'x':
                        x_steps.append(e.step)
                        x_values.append(v.simple_value)

            return (tags, loss_steps, loss_values, valid_loss_steps,
                    valid_loss_values, x_steps, x_values)

        # test enable summary with `summary_dir`
        with TemporaryDirectory() as tempdir:
            with train_loop([], max_epoch=2, summary_dir=tempdir) as loop:
                self.assertIsNone(loop._early_stopping)
                for epoch in loop.iter_epochs():
                    for _, loss in loop.iter_steps([0.7, 0.6, 0.8]):
                        loop.add_metrics(loss=epoch + loss)
                    loop.add_metrics(valid_loss=epoch)

                with self.get_session():
                    summary_op = tf.summary.scalar('x', tf.constant(1.23))
                    loop.add_summary(summary_op.eval())

            obj = read_summary(tempdir)
            self.assertEqual(
                sorted(obj[0]),
                ['epoch_time', 'loss', 'step_time', 'valid_loss', 'x']
            )
            np.testing.assert_equal(obj[1], [1, 2, 3, 4, 5, 6])
            np.testing.assert_almost_equal(
                obj[2],
                [1.7, 1.6, 1.8, 2.7, 2.6, 2.8]
            )
            np.testing.assert_equal(obj[3], [3, 6])
            np.testing.assert_almost_equal(obj[4], [1, 2])
            np.testing.assert_equal(obj[5], [6])
            np.testing.assert_almost_equal(obj[6], [1.23])

        # test enable summary with `summary_writer`
        with TemporaryDirectory() as tempdir:
            sw = tf.summary.FileWriter(tempdir)
            with train_loop([], max_epoch=2, summary_writer=sw) as loop:
                self.assertIsNone(loop._early_stopping)
                self.assertIs(loop._summary_writer._writer, sw)
                for epoch in loop.iter_epochs():
                    for _, loss in loop.iter_steps([0.7, 0.6, 0.8]):
                        loop.add_metrics(loss=epoch + loss)
                    loop.add_metrics(valid_loss=epoch)
            sw.close()
            self.assertEqual(
                sorted(read_summary(tempdir)[0]),
                ['epoch_time', 'loss', 'step_time', 'valid_loss']
            )

        with TemporaryDirectory() as tempdir:
            sw = SummaryWriter(tf.summary.FileWriter(tempdir))
            with train_loop([], max_epoch=2, summary_writer=sw) as loop:
                self.assertIsNone(loop._early_stopping)
                self.assertIs(loop._summary_writer, sw)
                for epoch in loop.iter_epochs():
                    for _, loss in loop.iter_steps([0.7, 0.6, 0.8]):
                        loop.add_metrics(loss=epoch + loss)
                    loop.add_metrics(valid_loss=epoch)
            sw.close()
            self.assertEqual(
                sorted(read_summary(tempdir)[0]),
                ['epoch_time', 'loss', 'step_time', 'valid_loss']
            )

    def test_early_stopping(self):
        with self.get_session():
            a = tf.get_variable('a', shape=(), dtype=tf.int32)
            b = tf.get_variable('b', shape=(), dtype=tf.int32)

            # test early-stopping with no valid metric committed
            set_variable_values([a, b], [1, 2])
            self.assertEqual(get_variable_values([a, b]), [1, 2])
            with train_loop([a], early_stopping=True):
                set_variable_values([a, b], [10, 20])
            self.assertEqual(get_variable_values([a, b]), [10, 20])

            # test early-stopping with smaller-better metric
            set_variable_values([a, b], [1, 2])
            self.assertEqual(get_variable_values([a, b]), [1, 2])
            with train_loop([a], max_epoch=1, early_stopping=True) as loop:
                for _ in loop.iter_epochs():
                    for step, valid_loss in loop.iter_steps([0.7, 0.6, 0.8]):
                        set_variable_values([a, b], [10 + step, 20 + step])
                        loop.add_metrics(valid_loss=valid_loss)
            self.assertAlmostEqual(loop.best_valid_metric, 0.6)
            self.assertEqual(get_variable_values([a, b]), [12, 23])

            # test early-stopping with larger-better metric
            set_variable_values([a, b], [1, 2])
            self.assertEqual(get_variable_values([a, b]), [1, 2])
            with train_loop([a], max_epoch=1, valid_metric=('y', False),
                            early_stopping=True) as loop:
                for _ in loop.iter_epochs():
                    for step, y in loop.iter_steps([0.7, 0.6, 0.8]):
                        set_variable_values([a, b], [10 + step, 20 + step])
                        loop.add_metrics(y=y)
            self.assertAlmostEqual(loop.best_valid_metric, 0.8)
            self.assertEqual(get_variable_values([a, b]), [13, 23])

    def test_tensor_arguments(self):
        with self.get_session():
            a = tf.get_variable('a', initializer=0, dtype=tf.int32)
            ensure_variables_initialized()
            with train_loop([a],
                            early_stopping=True,
                            initial_valid_metric=tf.constant(1.23),
                            initial_epoch=tf.constant(4),
                            initial_step=tf.constant(5),
                            max_epoch=tf.constant(6),
                            max_step=tf.constant(7)) as loop:
                self.assertAlmostEqual(loop._early_stopping._best_metric, 1.23)
                self.assertEqual(loop.epoch, 4)
                self.assertEqual(loop.step, 5)
                self.assertEqual(loop.max_epoch, 6)
                self.assertEqual(loop.max_step, 7)

    def test_errors(self):
        with self.assertRaisesRegex(
                RuntimeError, 'Another epoch loop has been opened.'):
            with train_loop([], max_epoch=10) as loop:
                for _ in loop.iter_epochs():
                    for _ in loop.iter_epochs():
                        pass

        with self.assertRaisesRegex(
                RuntimeError, 'Step loop must be opened within active epoch '
                              'loop.'):
            with train_loop([], max_step=10) as loop:
                for _ in loop.iter_steps():
                    pass

        with self.assertRaisesRegex(
                RuntimeError, 'Another step loop has been opened.'):
            with train_loop([], max_epoch=10, max_step=10) as loop:
                for _ in loop.iter_epochs():
                    for _ in loop.iter_steps():
                        for _ in loop.iter_steps():
                            pass

        with self.assertRaisesRegex(
                RuntimeError, 'Neither an epoch nor a step loop has been '
                              'opened.'):
            with train_loop([]) as loop:
                with loop.timeit('timer'):
                    pass

        with self.assertRaisesRegex(
                RuntimeError, 'Neither an epoch nor a step loop has been '
                              'opened.'):
            with train_loop([]) as loop:
                with loop.accumulator('metric'):
                    pass

        with self.assertRaisesRegex(
                RuntimeError, 'Neither an epoch nor a step loop has been '
                              'opened.'):
            with train_loop([]) as loop:
                loop.add_metrics(loss=1.)

        with self.assertRaisesRegex(
                RuntimeError, 'Neither an epoch nor a step loop has been '
                              'opened.'):
            with train_loop([]) as loop:
                loop.print_logs()

        with self.assertRaisesRegex(
                RuntimeError, '`data_generator` is required when `max_step` '
                              'is not configured, so as to prevent an '
                              'unstoppable step loop.'):
            with train_loop([], max_epoch=10) as loop:
                for _ in loop.iter_epochs():
                    for _ in loop.iter_steps():
                        pass

        with self.assertRaisesRegex(
                TypeError, '`metrics` should be a dict.'):
            with train_loop([], max_epoch=10) as loop:
                for _ in loop.iter_epochs():
                    loop.add_metrics(())

        with self.assertRaisesRegex(
                TypeError, '`summary_writer` is expected to be '
                           '`SummaryWriter`, but got .*'):
            with train_loop([], max_epoch=1, summary_writer=()):
                pass


if __name__ == '__main__':
    unittest.main()
