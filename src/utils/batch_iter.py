"""
A batch iterator.

Usage:
    for idx in BatchIterator(num=1000, batch_size=25):
        inp_batch = inp_all[idx]
        labels_batch = labels_all[idx]
        train(inp_batch, labels_batch)
"""

import numpy as np
import progress_bar as pb


class BatchIterator(object):

    def __init__(self, num, batch_size=1, progress_bar=False):
        """Construct a batch iterator.

        Args:
            data: numpy.ndarray, (N, D), N is the number of examples, D is the
            feature dimension.
            labels: numpy.ndarray, (N), N is the number of examples.
            batch_size: int, batch size.
        """

        self._num = num
        self._batch_size = batch_size
        self._step = 0
        self._num_steps = np.ceil(self._num / batch_size)
        self._pb = None
        if progress_bar:
            self._pb = pb.get(num)

        pass

    def __iter__(self):
        """Get iterable."""
        return self

    def __len__(self):
        """Get iterable length."""
        return self._num_steps

    def next(self):
        """Iterate next element."""
        if self._pb:
            self._pb.increment()
        if self._step < self._num_steps:
            start = self._batch_size * self._step
            end = min(self._num, self._batch_size * (self._step + 1))
            self._step += 1
            return (start, end)
        else:
            raise StopIteration()

        pass