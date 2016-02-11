"""
This code implements Recurrent Instance Segmentation [1].

Author: Mengye Ren (m.ren@cs.toronto.edu)

Usage: python rec_ins_segm.py --help

Reference:
[1] B. Romera-Paredes, P. Torr. Recurrent Instance Segmentation. arXiv preprint
arXiv:1511.08250, 2015.
"""
import cslab_environ

from data_api import mnist
from tensorflow.python.framework import ops
from utils import log_manager
from utils import logger
from utils import saver
from utils.batch_iter import BatchIterator
from utils.grad_clip_optim import GradientClipOptimizer
from utils.time_series_logger import TimeSeriesLogger
import argparse
import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os
import pickle as pkl
import syncount_gen_data as data
import tensorflow as tf
import time


def plot_samples(fname, x, y_out, s_out):
    """Plot some test samples."""

    num_row = y_out.shape[0]
    num_col = y_out.shape[1] + 1
    f1, axarr = plt.subplots(num_row, num_col, figsize=(10, num_row))

    for ii in xrange(num_row):
        for jj in xrange(num_col):
            axarr[ii, jj].set_axis_off()
            if jj == 0:
                axarr[ii, jj].imshow(x[ii])
            else:
                axarr[ii, jj].imshow(y_out[ii, jj - 1])
                axarr[ii, jj].text(0, 0, '{:.2f}'.format(s_out[ii, jj - 1]),
                                   color=(0, 0, 0), size=8)

    plt.tight_layout(pad=0.0, w_pad=0.0, h_pad=0.0)
    plt.savefig(fname, dpi=80)


def get_dataset(opt, num_train, num_valid):
    """Get train-valid split dataset for instance segmentation.

    Args:
        opt
        num_train
        num_valid
    Returns:
        dataset
            train
            valid
    """
    dataset = {}
    opt['num_examples'] = num_train
    raw_data = data.get_raw_data(opt, seed=2)
    image_data = data.get_image_data(opt, raw_data)
    segm_data = data.get_instance_segmentation_data(opt, image_data)
    dataset['train'] = segm_data

    opt['num_examples'] = num_valid
    raw_data = data.get_raw_data(opt, seed=3)
    image_data = data.get_image_data(opt, raw_data)
    segm_data = data.get_instance_segmentation_data(opt, image_data)
    dataset['valid'] = segm_data

    return dataset


def _get_device_fn(device):
    """Choose device for different ops."""
    OPS_ON_CPU = set(['ResizeBilinear', 'ResizeBilinearGrad', 'CumMin',
                      'CumMinGrad', 'Hungarian', 'Reverse'])

    def _device_fn(op):
        if op.type in OPS_ON_CPU:
            return "/cpu:0"
        else:
            # Other ops will be placed on GPU if available, otherwise
            # CPU.
            return device

    return _device_fn


def _get_batch_fn(dataset):
    """
    Preprocess mini-batch data given start and end indices.
    """
    def get_batch(start, end):
        x_bat = dataset['input'][start: end]
        y_bat = dataset['label_segmentation'][start: end]
        s_bat = dataset['label_score'][start: end]
        x_bat, y_bat, s_bat = preprocess(x_bat, y_bat, s_bat)

        return x_bat, y_bat, s_bat

    return get_batch


def preprocess(inp, label_segmentation, label_score):
    """Preprocess training data."""
    return (inp.astype('float32') / 255,
            label_segmentation.astype('float32'),
            label_score.astype('float32'))


def _conv2d(x, w):
    """2-D convolution."""
    return tf.nn.conv2d(x, w, strides=[1, 1, 1, 1], padding='SAME')


def _max_pool_2x2(x):
    """2 x 2 max pooling."""
    return tf.nn.max_pool(x, ksize=[1, 2, 2, 1],
                          strides=[1, 2, 2, 1], padding='SAME')


def _max_pool_4x4(x):
    """2 x 2 max pooling."""
    return tf.nn.max_pool(x, ksize=[1, 4, 4, 1],
                          strides=[1, 4, 4, 1], padding='SAME')


def _weight_variable(shape, wd=None, name=None):
    """Initialize weights."""
    initial = tf.truncated_normal(shape, stddev=0.01)
    var = tf.Variable(initial, name=name)
    if wd:
        weight_decay = tf.mul(tf.nn.l2_loss(var), wd, name='weight_loss')
        tf.add_to_collection('losses', weight_decay)
    return var


def _add_conv_lstm(model, timespan, inp_height, inp_width, inp_depth, filter_size, hid_depth, c_init, h_init, wd=None, name=''):
    """Adds a Conv-LSTM component.

    Args:
        model: Model dictionary
        timespan: Maximum length of the LSTM
        inp_height: Input image height
        inp_width: Input image width
        inp_depth: Input image depth
        filter_size: Conv gate filter size
        hid_depth: Hidden state depth
        c_init: Cell state initialization
        h_init: Hidden state initialization
        wd: Weight decay
        name: Prefix
    """
    g_i = [None] * timespan
    g_f = [None] * timespan
    g_o = [None] * timespan
    u = [None] * timespan
    c = [None] * (timespan + 1)
    h = [None] * (timespan + 1)
    c[-1] = c_init
    h[-1] = h_init

    # Input gate
    w_xi = _weight_variable([filter_size, filter_size, inp_depth, hid_depth],
                            wd=wd, name='w_xi_{}'.format(name))
    w_hi = _weight_variable([filter_size, filter_size, hid_depth, hid_depth],
                            wd=wd, name='w_hi_{}'.format(name))
    b_i = _weight_variable([hid_depth],
                           wd=wd, name='b_i_{}'.format(name))

    # Forget gate
    w_xf = _weight_variable([filter_size, filter_size, inp_depth, hid_depth],
                            wd=wd, name='w_xf_{}'.format(name))
    w_hf = _weight_variable([filter_size, filter_size, hid_depth, hid_depth],
                            wd=wd, name='w_hf_{}'.format(name))
    b_f = _weight_variable([hid_depth],
                           wd=wd, name='b_f_{}'.format(name))

    # Input activation
    w_xu = _weight_variable([filter_size, filter_size, inp_depth, hid_depth],
                            wd=wd, name='w_xu_{}'.format(name))
    w_hu = _weight_variable([filter_size, filter_size, hid_depth, hid_depth],
                            wd=wd, name='w_hu_{}'.format(name))
    b_u = _weight_variable([hid_depth],
                           wd=wd, name='b_u_{}'.format(name))

    # Output gate
    w_xo = _weight_variable([filter_size, filter_size, inp_depth, hid_depth],
                            wd=wd, name='w_xo_{}'.format(name))
    w_ho = _weight_variable([filter_size, filter_size, hid_depth, hid_depth],
                            wd=wd, name='w_ho_{}'.format(name))
    b_o = _weight_variable([hid_depth], name='b_o_{}'.format(name))

    def unroll(inp, time):
        t = time
        g_i[t] = tf.sigmoid(_conv2d(inp, w_xi) + _conv2d(h[t - 1], w_hi) + b_i)
        g_f[t] = tf.sigmoid(_conv2d(inp, w_xf) + _conv2d(h[t - 1], w_hf) + b_f)
        g_o[t] = tf.sigmoid(_conv2d(inp, w_xo) + _conv2d(h[t - 1], w_ho) + b_o)
        u[t] = tf.tanh(_conv2d(inp, w_xu) + _conv2d(h[t - 1], w_hu) + b_u)
        c[t] = g_f[t] * c[t - 1] + g_i[t] * u[t]
        h[t] = g_o[t] * tf.tanh(c[t])

        pass

    model['g_i_{}'.format(name)] = g_i
    model['g_f_{}'.format(name)] = g_f
    model['g_o_{}'.format(name)] = g_o
    model['u_{}'.format(name)] = u
    model['c_{}'.format(name)] = c
    model['h_{}'.format(name)] = h

    return unroll


# Register gradient for Hungarian algorithm.
ops.NoGradient("Hungarian")


# Register gradient for cumulative minimum operation.
@ops.RegisterGradient("CumMin")
def _cum_min_grad(op, grad):
    """The gradients for `cum_min`.

    Args:
        op: The `cum_min` `Operation` that we are differentiating, which we can
        use to find the inputs and outputs of the original op.
        grad: Gradient with respect to the output of the `cum_min` op.

    Returns:
        Gradients with respect to the input of `cum_min`.
    """
    x = op.inputs[0]
    return [tf.user_ops.cum_min_grad(grad, x)]


def _f_iou(a, b, timespan, pairwise=False):
    """
    Computes IOU score.

    Args:
        a: [B, N, H, W], or [N, H, W], or [H, W]
        b: [B, N, H, W], or [N, H, W], or [H, W]
           in pairwise mode, the second dimension can be different,
           e.g. [B, M, H, W], or [M, H, W], or [H, W]
        pairwise: whether the inputs are already aligned, outputs [B, N] or
                  the inputs are orderless, outputs [B, N, M].
    """
    eps = 1e-5

    def _get_reduction_indices(a):
        """Gets the list of axes to sum over."""
        dim = len(a.get_shape())

        return [dim - 2, dim - 1]

    def _inter(a, b):
        """Computes intersection."""
        reduction_indices = _get_reduction_indices(a)
        return tf.reduce_sum(a * b, reduction_indices=reduction_indices)

    def _union(a, b):
        """Computes union."""
        reduction_indices = _get_reduction_indices(a)
        return tf.reduce_sum(a + b - (a * b) + eps,
                             reduction_indices=reduction_indices)
    if pairwise:
        # b_shape = tf.shape(b)
        # # [1, 1, M, 1, 1]
        # a_shape2 = tf.concat(0, [tf.constant([1, 1]),
        #                          b_shape[1: 2],
        #                          tf.constant([1, 1])])
        # # [B, N, H, W] => [B, N, 1, H, W] => [B, N, M, H, W]
        # a = tf.expand_dims(a, 2)
        # # [B, M, H, W] => [B, 1, M, H, W]
        # b = tf.expand_dims(b, 1)
        # a = tf.tile(a, a_shape2)
        # return _inter(a, b) / _union(a, b)

        y_list = [None] * timespan
        a_list = [None] * timespan
        # [B, N, H, W] => [B, N, 1, H, W]
        a = tf.expand_dims(a, 2)
        # [B, N, 1, H, W] => N * [B, 1, 1, H, W]
        a_list = tf.split(1, timespan, a)
        # [B, M, H, W] => [B, 1, M, H, W]
        b = tf.expand_dims(b, 1)

        for ii in xrange(timespan):
            # [B, 1, M]
            y_list[ii] = _inter(a_list[ii], b) / _union(a_list[ii], b)

        # N * [B, 1, M] => [B, N, M]
        return tf.concat(1, y_list)

    else:
        return _inter(a, b) / _union(a, b)


def _cum_min(s, d):
    """Calculates cumulative minimum.

    Args:
        s: Input matrix [B, D].
        d: Second dim.

    Returns:
        s_min: [B, D], cumulative minimum accross the second dim.
    """
    s_min_list = [None] * d
    s_min_list[0] = s[:, 0: 1]
    for ii in xrange(1, d):
        s_min_list[ii] = tf.minimum(s_min_list[ii - 1], s[:, ii: ii + 1])

    return tf.concat(1, s_min_list)


def _add_ins_segm_loss(model, y_out, y_gt, s_out, s_gt, r, timespan, use_cum_min=True, has_segm=True, segm_loss_fn='iou'):
    """
    Instance segmentation loss.

    Args:
        y_out: [B, N, H, W], output segmentations.
        y_gt: [B, M, H, W], groundtruth segmentations.
        s_out: [B, N], output confidence score.
        s_gt: [B. M], groundtruth confidence score.
        r: float, mixing coefficient for combining segmentation loss and
        confidence score loss.
    """

    def _bce(y_out, y_gt):
        """Binary cross entropy."""
        eps = 1e-7
        return -y_gt * tf.log(y_out + eps) - \
            (1 - y_gt) * tf.log(1 - y_out + eps)

    def _match_bce(y_out, y_gt, match, match_count, timespan):
        """Binary cross entropy with matching.

        Args:
            y_out: [B, N, H, W]
            y_gt: [B, N, H, W]
            match: [B, N, N]
            match_count: [B]
            num_ex: [1]
            timespan: N
        """
        # N * [B, 1, H, W]
        y_out_list = tf.split(1, timespan, y_out)
        # N * [B, 1, N]
        match_list = tf.split(1, timespan, match)
        bce_list = [None] * timespan
        bce_tmp = [None] * timespan
        shape = tf.shape(y_out)
        num_ex = tf.to_float(shape[0])
        height = tf.to_float(shape[2])
        width = tf.to_float(shape[3])

        for ii in xrange(timespan):
            # [B, N, H, W] * [B, 1, H, W] => [B, N, H, W] => [B, N]
            # [B, N] * [B, N] => [B]
            # [B] => [B, 1]
            bce_list[ii] = tf.expand_dims(tf.reduce_sum(tf.reduce_sum(
                _bce(y_gt, y_out_list[ii]), reduction_indices=[2, 3]) *
                tf.reshape(match_list[ii], [-1, timespan]),
                reduction_indices=[1]), 1)

        # N * [B, 1] => [B, N] => [B]
        bce_total = tf.reduce_sum(
            tf.concat(1, bce_list), reduction_indices=[1])
        return tf.reduce_sum(bce_total / match_count) / num_ex / height / width

    # IOU score, [B, N, M]
    iou_soft = _f_iou(y_out, y_gt, timespan, pairwise=True)

    # Matching score, [B, N, M]
    # Add small epsilon because the matching algorithm only accepts complete
    # bipartite graph with positive weights.
    # Mask out the items beyond the total groudntruth count.
    # Mask X, [B, M] => [B, 1, M]
    mask_x = tf.expand_dims(s_gt, dim=1)
    # Mask Y, [B, M] => [B, N, 1]
    mask_y = tf.expand_dims(s_gt, dim=2)
    iou_mask = iou_soft * mask_x * mask_y

    # Keep certain precision so that we can get optimal matching within
    # reasonable time.
    eps = 1e-5
    precision = 1e6
    iou_mask = tf.round(iou_mask * precision) / precision
    match_eps = tf.user_ops.hungarian(iou_mask + eps)[0]

    # [1, N, 1, 1]
    y_out_shape = tf.shape(y_out)
    num_segm_out = y_out_shape[1: 2]
    num_segm_out_mul = tf.concat(
        0, [tf.constant([1]), num_segm_out, tf.constant([1])])
    # Mask the graph algorithm output.
    match = match_eps * mask_x * mask_y
    model['match'] = match
    # [B, N, M] => [B, N]
    match_sum = tf.reduce_sum(match, reduction_indices=[2])
    # [B, N] => [B]
    match_count = tf.reduce_sum(match_sum, reduction_indices=[1])

    # Loss for confidence scores.
    if use_cum_min:
        # [B, N]
        s_out_min = _cum_min(s_out, timespan)
        # [B, N]
        s_bce = _bce(s_out_min, match_sum)
        model['s_out_min'] = s_out_min
    else:
        # Try simply do binary xent for matching sequence.
        s_bce = _bce(s_out, match_sum)
    model['s_bce'] = s_bce

    # Loss normalized by number of examples.
    y_gt_shape = tf.shape(y_gt)
    num_ex = tf.to_float(y_gt_shape[0])
    max_num_obj = tf.to_float(y_gt_shape[1])

    # IOU
    iou_hard = _f_iou(tf.to_float(y_out > 0.5), y_gt, timespan, pairwise=True)
    # [B, M, N] * [B, M, N] => [B] * [B] => [1]
    iou_hard = tf.reduce_sum(tf.reduce_sum(
        iou_hard * match, reduction_indices=[1, 2]) / match_count) / num_ex
    iou_soft = tf.reduce_sum(tf.reduce_sum(
        iou_soft * match, reduction_indices=[1, 2]) / match_count) / num_ex
    model['iou_hard'] = iou_hard
    model['iou_soft'] = iou_soft

    # [B, N, M] => scalar
    conf_loss = r * tf.reduce_sum(s_bce) / num_ex / max_num_obj
    if segm_loss_fn == 'iou':
        segm_loss = -iou_soft
    elif segm_loss_fn == 'bce':
        segm_loss = _match_bce(
            y_out, y_gt, match, match_count, timespan)

    model['segm_loss'] = segm_loss
    if has_segm:
        loss = segm_loss + conf_loss
    else:
        loss = conf_loss

    model['conf_loss'] = conf_loss
    model['loss'] = loss

    # Counting accuracy
    count_out = tf.reduce_sum(tf.to_float(s_out > 0.5), reduction_indices=[1])
    count_gt = tf.reduce_sum(s_gt, reduction_indices=[1])
    count_acc = tf.reduce_sum(tf.to_float(
        tf.equal(count_out, count_gt))) / num_ex
    model['count_out'] = count_out
    model['count_gt'] = count_gt
    model['count_acc'] = count_acc

    return loss


def get_model(opt, device='/cpu:0', train=True):
    """Get model."""
    model = {}
    timespan = opt['timespan']
    inp_height = opt['inp_height']
    inp_width = opt['inp_width']
    conv_lstm_filter_size = opt['conv_lstm_filter_size']
    conv_lstm_hid_depth = opt['conv_lstm_hid_depth']
    wd = opt['weight_decay']
    has_segm = ('has_segm' not in opt) or opt['has_segm']
    store_segm_map = ('store_segm_map' not in opt) or opt['store_segm_map']

    with tf.device(_get_device_fn(device)):
        # Input image, [B, H, W, 3]
        x = tf.placeholder('float', [None, inp_height, inp_width, 3])
        # Groundtruth segmentation maps, [B, T, H, W]
        y_gt = tf.placeholder('float', [None, timespan, inp_height, inp_width])
        # Groundtruth confidence score, [B, T]
        s_gt = tf.placeholder('float', [None, timespan])
        y_gt_list = tf.split(1, timespan, y_gt)
        model['x'] = x
        model['y_gt'] = y_gt
        model['s_gt'] = s_gt

        # Possibly add random image transformation layers here in training time.
        # Need to combine x and y together to crop.
        # Other operations on x only.
        # x = tf.image.random_crop()
        # x = tf.image.random_flip()

        # 1st convolution layer
        # [B, H, W, 3] => [B, H / 2, W / 2, 16]
        w_conv1 = _weight_variable([3, 3, 3, 16])
        b_conv1 = _weight_variable([16])
        h_conv1 = tf.nn.relu(_conv2d(x, w_conv1) + b_conv1)
        h_pool1 = _max_pool_2x2(h_conv1)

        # 2nd convolution layer
        # [B, H / 2, W / 2, 16] => [B, H / 4, W / 4, 32]
        w_conv2 = _weight_variable([3, 3, 16, 32])
        b_conv2 = _weight_variable([32])
        h_conv2 = tf.nn.relu(_conv2d(h_pool1, w_conv2) + b_conv2)
        h_pool2 = _max_pool_2x2(h_conv2)

        # 3rd convolution layer
        # [B, H / 4, W / 4, 32] => [B, H / 8, W / 8, 64]
        w_conv3 = _weight_variable([3, 3, 32, 64])
        b_conv3 = _weight_variable([64])
        h_conv3 = tf.nn.relu(_conv2d(h_pool2, w_conv3) + b_conv3)
        h_pool3 = _max_pool_2x2(h_conv3)

        if store_segm_map:
            lstm_inp_depth = 65
        else:
            lstm_inp_depth = 64
        lstm_depth = 16
        lstm_height = inp_height / 8
        lstm_width = inp_width / 8

        # ConvLSTM hidden state initialization
        # [B, LH, LW, LD]
        x_shape = tf.shape(x)
        num_ex = x_shape[0: 1]
        c_init = tf.zeros(tf.concat(
            0, [num_ex, tf.constant([lstm_height, lstm_width, lstm_depth])]))
        h_init = tf.zeros(tf.concat(
            0, [num_ex, tf.constant([lstm_height, lstm_width, lstm_depth])]))

        # Segmentation network
        # 4th convolution layer (on ConvLSTM output).
        w_conv4 = _weight_variable([3, 3, lstm_depth, 1])
        b_conv4 = _weight_variable([1])

        # Bias towards segmentation output.
        b_5 = _weight_variable([lstm_height * lstm_width])

        # Confidence network
        # Linear layer for output confidence score.
        w_6 = _weight_variable(
            [lstm_height * lstm_width / 16 * lstm_depth, 1])
        b_6 = _weight_variable([1])

        unroll_conv_lstm = _add_conv_lstm(
            model=model,
            timespan=timespan,
            inp_height=lstm_height,
            inp_width=lstm_width,
            inp_depth=lstm_inp_depth,
            filter_size=conv_lstm_filter_size,
            hid_depth=lstm_depth,
            c_init=c_init,
            h_init=h_init,
            wd=wd,
            name='lstm'
        )
        h_lstm = model['h_lstm']

        h_conv4 = [None] * timespan
        segm_lo = [None] * timespan
        # segm_out = [None] * timespan
        score = [None] * timespan
        h_pool4 = [None] * timespan
        segm_canvas = [None] * timespan
        segm_canvas[0] = tf.zeros(tf.concat(
            0, [num_ex, tf.constant([lstm_height, lstm_width, 1])]))
        lstm_inp = [None] * timespan
        y_out = [None] * timespan

        for t in xrange(timespan):
            # If we also send the cumulative output maps.
            if store_segm_map:
                lstm_inp[t] = tf.concat(3, [h_pool3, segm_canvas[t]])
            else:
                lstm_inp[t] = h_pool3
            unroll_conv_lstm(lstm_inp[t], time=t)

            # Segmentation network
            # [B, LH, LW, 1]
            h_conv4 = tf.nn.relu(_conv2d(h_lstm[t], w_conv4) + b_conv4)
            # [B, LH * LW]
            h_conv4_reshape = tf.reshape(
                h_conv4, [-1, lstm_height * lstm_width])
            # [B, LH * LW] => [B, LH, LW] => [B, 1, LH, LW]
            # [B, LH * LW] => [B, LH, LW] => [B, LH, LW, 1]
            segm_lo[t] = tf.expand_dims(tf.reshape(tf.sigmoid(
                tf.log(tf.nn.softmax(h_conv4_reshape)) + b_5),
                [-1, lstm_height, lstm_width]), dim=3)
            # [B, LH, LW, 1]
            if t != timespan - 1:
                segm_canvas[t + 1] = segm_canvas[t] + segm_lo[t]

            # Objectness network
            # [B, LH, LW, LD] => [B, LLH, LLW, LD] => [B, LLH * LLW * LD]
            h_pool4[t] = tf.reshape(_max_pool_4x4(h_lstm[t]),
                                    [-1,
                                     lstm_height * lstm_width / 16 * lstm_depth])
            # [B, LLH * LLW * LD] => [B, 1]
            score[t] = tf.sigmoid(tf.matmul(h_pool4[t], w_6) + b_6)

        # [B * T, LH, LW, 1]
        segm_lo_all = tf.concat(0, segm_lo)

        # [B * T, LH, LW, 1] => [B * T, H, W, 1] => [B, T, H, W]
        y_out = tf.reshape(
            tf.image.resize_bilinear(segm_lo_all, [inp_height, inp_width]),
            [-1, timespan, inp_height, inp_width])

        model['y_out'] = y_out

        # T * [B, 1] = [B, T]
        s_out = tf.concat(1, score)
        model['s_out'] = s_out

        model['h_lstm_0'] = h_lstm[0]
        model['h_pool4_0'] = h_pool4[0]
        model['s_0'] = score[0]

        # Loss function
        if train:
            r = opt['loss_mix_ratio']
            lr = opt['learning_rate']
            use_cum_min = ('cum_min' not in opt) or opt['cum_min']
            eps = 1e-7
            loss = _add_ins_segm_loss(
                model, y_out, y_gt, s_out, s_gt, r, timespan,
                use_cum_min=use_cum_min, has_segm=has_segm,
                segm_loss_fn=opt['segm_loss_fn'])
            tf.add_to_collection('losses', loss)
            total_loss = tf.add_n(tf.get_collection(
                'losses'), name='total_loss')
            model['total_loss'] = total_loss

            train_step = GradientClipOptimizer(
                tf.train.AdamOptimizer(lr, epsilon=eps),
                clip=1.0).minimize(total_loss)
            # train_step = tf.train.GradientDescentOptimizer(
            #         lr).minimize(total_loss)
            model['train_step'] = train_step

    return model


def _parse_args():
    """Parse input arguments."""
    # Default dataset options
    # Full image height.
    kHeight = 224
    # Full image width.
    kWidth = 224
    # Object radius lower bound.
    kRadiusLower = 15
    # Object radius upper bound.
    kRadiusUpper = 45
    # Object border thickness.
    kBorderThickness = 3
    # Number of examples.
    kNumExamples = 1000
    # Maximum number of objects.
    kMaxNumObjects = 6
    # Number of object types, currently support up to three types (circles,
    # triangles, and squares).
    kNumObjectTypes = 1
    # Random window size variance.
    kSizeVar = 20
    # Random window center variance.
    kCenterVar = 20
    # Resample window size (segmentation output unisize).
    kOutputWindowSize = 128
    # Ratio of negative and positive examples for segmentation data.
    kNegPosRatio = 5

    # Default model options
    kWeightDecay = 5e-5
    kLearningRate = 1e-3
    kLossMixRatio = 1.0
    kConvLstmFilterSize = 5
    kConvLstmHiddenDepth = 64

    # Default training options
    # Number of steps
    kNumSteps = 500000
    # Number of steps per checkpoint
    kStepsPerCkpt = 1000

    parser = argparse.ArgumentParser(
        description='Train DRAW')

    # Dataset options
    parser.add_argument('-height', default=kHeight, type=int,
                        help='Image height')
    parser.add_argument('-width', default=kWidth, type=int,
                        help='Image width')
    parser.add_argument('-radius_upper', default=kRadiusUpper, type=int,
                        help='Radius upper bound')
    parser.add_argument('-radius_lower', default=kRadiusLower, type=int,
                        help='Radius lower bound')
    parser.add_argument('-border_thickness', default=kBorderThickness,
                        type=int, help='Object border thickness')
    parser.add_argument('-num_ex', default=kNumExamples, type=int,
                        help='Number of examples')
    parser.add_argument('-max_num_objects', default=kMaxNumObjects, type=int,
                        help='Maximum number of objects')
    parser.add_argument('-num_object_types', default=kNumObjectTypes, type=int,
                        help='Number of object types')
    parser.add_argument('-center_var', default=kCenterVar, type=float,
                        help='Image patch center variance')
    parser.add_argument('-size_var', default=kSizeVar, type=float,
                        help='Image patch size variance')

    # Model options
    parser.add_argument('-weight_decay', default=kWeightDecay, type=float,
                        help='Weight L2 regularization')
    parser.add_argument('-learning_rate', default=kLearningRate, type=float,
                        help='Model learning rate')
    parser.add_argument('-loss_mix_ratio', default=kLossMixRatio, type=float,
                        help='Mix ratio between segmentation and score loss')
    parser.add_argument('-conv_lstm_filter_size', default=kConvLstmFilterSize,
                        type=int, help='Conv LSTM filter size')
    parser.add_argument('-conv_lstm_hid_depth', default=kConvLstmHiddenDepth,
                        type=int, help='Conv LSTM hidden depth')

    # Test model argument.
    # To see the effect of cumulative minimum.
    parser.add_argument('-no_cum_min', action='store_true',
                        help='Whether cumulative minimum. Default yes.')
    # Only to use when only care about the count.
    # Still segment images, the segmentation loss does not get back propagated.
    parser.add_argument('-no_segm', action='store_true',
                        help='Whether has segmentation network.')
    # Stores a map that has already been segmented.
    parser.add_argument('-store_segm_map', action='store_true',
                        help='Whether to store objects that has been segmented.')
    # Segmentation loss function
    parser.add_argument('-segm_loss_fn', default='iou',
                        help='Segmentation loss function, "iou" or "bce"')

    # Training options
    parser.add_argument('-num_steps', default=kNumSteps,
                        type=int, help='Number of steps to train')
    parser.add_argument('-steps_per_ckpt', default=kStepsPerCkpt,
                        type=int, help='Number of steps per checkpoint')
    parser.add_argument('-results', default='../results',
                        help='Model results folder')
    parser.add_argument('-logs', default='../results',
                        help='Training curve logs folder')
    parser.add_argument('-localhost', default='localhost',
                        help='Local domain name')
    parser.add_argument('-restore', default=None,
                        help='Model save folder to restore from')
    parser.add_argument('-gpu', default=-1, type=int,
                        help='GPU ID, default CPU')
    parser.add_argument('-num_samples_plot', default=10, type=int,
                        help='Number of samples to plot')
    args = parser.parse_args()

    return args


def get_model_id(task_name):
    time_obj = datetime.datetime.now()
    model_id = timestr = '{}-{:04d}{:02d}{:02d}{:02d}{:02d}{:02d}'.format(
        task_name, time_obj.year, time_obj.month, time_obj.day,
        time_obj.hour, time_obj.minute, time_obj.second)

    return model_id


if __name__ == '__main__':
    # Command-line arguments
    args = _parse_args()
    tf.set_random_seed(1234)

    # Restore previously saved checkpoints.
    if args.restore:
        ckpt_info = saver.get_ckpt_info(args.restore)
        model_opt = ckpt_info['model_opt']
        data_opt = ckpt_info['data_opt']
        ckpt_fname = ckpt_info['ckpt_fname']
        step = ckpt_info['step']
        model_id = ckpt_info['model_id']
    else:
        log.info('Initializing new model')
        model_id = get_model_id('rec_ins_segm')
        model_opt = {
            'inp_height': args.height,
            'inp_width': args.width,
            'timespan': args.max_num_objects + 1,
            'weight_decay': args.weight_decay,
            'learning_rate': args.learning_rate,
            'loss_mix_ratio': args.loss_mix_ratio,
            'conv_lstm_filter_size': args.conv_lstm_filter_size,
            'conv_lstm_hid_depth': args.conv_lstm_hid_depth,

            # Test arguments
            'cum_min': not args.no_cum_min,
            'has_segm': not args.no_segm,
            'store_segm_map': args.store_segm_map,
            'segm_loss_fn': args.segm_loss_fn
        }
        data_opt = {
            'height': args.height,
            'width': args.width,
            'radius_upper': args.radius_upper,
            'radius_lower': args.radius_lower,
            'border_thickness': args.border_thickness,
            'max_num_objects': args.max_num_objects,
            'num_object_types': args.num_object_types,
            'center_var': args.center_var,
            'size_var': args.size_var
        }
        step = 0

    # Logistics
    results_folder = args.results
    exp_folder = os.path.join(results_folder, model_id)

    # Logger
    if args.logs:
        logs_folder = args.logs
        exp_logs_folder = os.path.join(logs_folder, model_id)
        log = logger.get(os.path.join(exp_logs_folder, 'raw'))
    else:
        log = logger.get()

    # Log arguments
    log.log_args()

    # Set device
    if args.gpu >= 0:
        device = '/gpu:{}'.format(args.gpu)
    else:
        device = '/cpu:0'

    # Train loop options
    train_opt = {
        'num_steps': args.num_steps,
        'steps_per_ckpt': args.steps_per_ckpt
    }

    dataset = get_dataset(data_opt, args.num_ex, args.num_ex / 10)
    m = get_model(model_opt, device=device)
    sess = tf.Session()
    # sess = tf.Session(config=tf.ConfigProto(log_device_placement=True))

    if args.restore:
        saver.restore_ckpt(sess, ckpt_fname)
    else:
        sess.run(tf.initialize_all_variables())

    # Create time series logger
    if args.logs:
        train_loss_logger = TimeSeriesLogger(
            os.path.join(exp_logs_folder, 'train_loss.csv'), 'train loss',
            name='Training loss',
            buffer_size=10)
        valid_loss_logger = TimeSeriesLogger(
            os.path.join(exp_logs_folder, 'valid_loss.csv'), 'valid loss',
            name='Validation loss',
            buffer_size=1)
        valid_iou_hard_logger = TimeSeriesLogger(
            os.path.join(exp_logs_folder, 'valid_iou_hard.csv'), 'valid iou',
            name='Validation IoU hard',
            buffer_size=1)
        valid_iou_soft_logger = TimeSeriesLogger(
            os.path.join(exp_logs_folder, 'valid_iou_soft.csv'), 'valid iou',
            name='Validation IoU soft',
            buffer_size=1)
        valid_count_acc_logger = TimeSeriesLogger(
            os.path.join(exp_logs_folder, 'valid_count_acc.csv'),
            'valid count acc',
            name='Validation count accuracy',
            buffer_size=1)
        step_time_logger = TimeSeriesLogger(
            os.path.join(exp_logs_folder, 'step_time.csv'), 'step time (ms)',
            name='Step time',
            buffer_size=10)
        log_manager.register(log.filename, 'plain', 'Raw logs')
        valid_sample_img_fname = os.path.join(
            exp_logs_folder, 'valid_sample_img.png')
        registered_image = False
        log.info(
            'Visualization can be viewed at: http://{}/visualizer?id={}'.format(
                args.localhost, model_id))

    num_ex_train = dataset['train']['input'].shape[0]
    num_ex_valid = dataset['valid']['input'].shape[0]
    get_batch_train = _get_batch_fn(dataset['train'])
    get_batch_valid = _get_batch_fn(dataset['valid'])
    batch_size_train = 32
    batch_size_valid = 32
    log.info('Number of validation examples: {}'.format(num_ex_valid))
    log.info('Validation batch size: {}'.format(batch_size_valid))
    log.info('Number of training examples: {}'.format(num_ex_train))
    log.info('Training batch size: {}'.format(batch_size_train))

    # Train loop
    while step < train_opt['num_steps']:
        # Validation
        loss = 0.0
        iou_hard = 0.0
        iou_soft = 0.0
        count_acc = 0.0
        segm_loss = 0.0
        conf_loss = 0.0
        log.info('Running validation')
        for x_bat, y_bat, s_bat in BatchIterator(num_ex_valid,
                                                 batch_size=batch_size_valid,
                                                 get_fn=get_batch_valid,
                                                 progress_bar=False):
            _loss, _segm_loss, _conf_loss, _iou_soft, _iou_hard, _count_acc = \
                sess.run([m['loss'], m['segm_loss'], m['conf_loss'],
                          m['iou_soft'], m['iou_hard'], m['count_acc']],
                         feed_dict={
                    m['x']: x_bat,
                    m['y_gt']: y_bat,
                    m['s_gt']: s_bat
                })

            loss += _loss * batch_size_valid / float(num_ex_valid)
            segm_loss += _segm_loss * batch_size_valid / float(num_ex_valid)
            conf_loss += _conf_loss * batch_size_valid / float(num_ex_valid)
            iou_soft += _iou_soft * batch_size_valid / float(num_ex_valid)
            iou_hard += _iou_hard * batch_size_valid / float(num_ex_valid)
            count_acc += _count_acc * batch_size_valid / float(num_ex_valid)

        log.info(('{:d} valid loss {:.4f} segm_loss {:.4f} conf_loss {:.4f} '
                  'iou soft {:.4f} iou hard {:.4f} count acc {:.4f}').format(
            step, loss, segm_loss, conf_loss, iou_soft, iou_hard, count_acc))

        if args.logs:
            _x, _y_gt, _s_gt = get_batch_valid(0, args.num_samples_plot)
            _y_out, _s_out = sess.run([m['y_out'], m['s_out']], feed_dict={
                m['x']: _x
            })
            plot_samples(valid_sample_img_fname, _x, _y_out, _s_out)
            valid_loss_logger.add(step, loss)
            valid_iou_soft_logger.add(step, iou_soft)
            valid_iou_hard_logger.add(step, iou_hard)
            valid_count_acc_logger.add(step, count_acc)
            if not registered_image:
                log_manager.register(valid_sample_img_fname, 'image',
                                     'Validation samples')
                registered_image = True

        # Train
        for x_bat, y_bat, s_bat in BatchIterator(num_ex_train,
                                                 batch_size=batch_size_train,
                                                 get_fn=get_batch_train,
                                                 progress_bar=False):
            start_time = time.time()
            r = sess.run([m['loss'], m['train_step']], feed_dict={
                m['x']: x_bat,
                m['y_gt']: y_bat,
                m['s_gt']: s_bat
            })

            # Print statistics
            if step % 10 == 0:
                step_time = (time.time() - start_time) * 1000
                loss = r[0]
                log.info('{:d} train loss {:.4f} t {:.2f}ms'.format(
                    step, loss, step_time))

                if args.logs:
                    train_loss_logger.add(step, loss)
                    step_time_logger.add(step, step_time)

            if step % 100 == 0:
                log.info('model id {}'.format(model_id))

            # Save model
            if step % train_opt['steps_per_ckpt'] == 0:
                saver.save_ckpt(exp_folder, sess, model_opt=model_opt,
                                data_opt=data_opt, global_step=step)

            step += 1

    sess.close()
    train_loss_logger.close()
    valid_loss_logger.close()
    valid_iou_soft_logger.close()
    valid_iou_hard_logger.close()
    valid_count_acc_logger.close()
    step_time_logger.close()
    pass
