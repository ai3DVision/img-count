"""
Trainer functions.
"""
from __future__ import division

import cv2
import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import os
import sys

from data_api.cvppp import CVPPP
from data_api.kitti import KITTI
from data_api import synth_shape

from utils import logger
from utils import plot_utils as pu

import assign_model_id

log = logger.get()


def add_train_args(parser):
    parser.add_argument('--model_id', default=None)
    parser.add_argument('--num_steps', default=500000, type=int)
    parser.add_argument('--steps_per_ckpt', default=1000, type=int)
    parser.add_argument('--steps_per_valid', default=250, type=int)
    parser.add_argument('--steps_per_trainval', default=100, type=int)
    parser.add_argument('--steps_per_plot', default=50, type=int)
    parser.add_argument('--steps_per_log', default=20, type=int)
    parser.add_argument('--batch_size', default=32, type=int)
    parser.add_argument('--results', default='../results')
    parser.add_argument('--logs', default='../results')
    parser.add_argument('--localhost', default='localhost')
    parser.add_argument('--restore', default=None)
    parser.add_argument('--gpu', default=-1, type=int)
    parser.add_argument('--num_samples_plot', default=10, type=int)
    parser.add_argument('--save_ckpt', action='store_true')
    parser.add_argument('--no_valid', action='store_true')

    pass


def add_data_args(parser):
    parser.add_argument('--dataset', default='synth_shape')
    parser.add_argument('--dataset_folder', default=None)
    parser.add_argument('--height', default=224, type=int)
    parser.add_argument('--width', default=224, type=int)
    parser.add_argument('--radius_upper', default=15, type=int)
    parser.add_argument('--radius_lower', default=45, type=int)
    parser.add_argument('--border_thickness', default=3, type=int)
    parser.add_argument('--num_ex', default=1000, type=int)
    parser.add_argument('--max_num_objects', default=6, type=int)
    parser.add_argument('--num_object_types', default=1, type=int)
    parser.add_argument('--center_var', default=20, type=float)
    parser.add_argument('--size_var', default=20, type=float)

    pass


def make_train_opt(args):
    return {
        'model_id': args.model_id,
        'num_steps': args.num_steps,
        'steps_per_ckpt': args.steps_per_ckpt,
        'steps_per_valid': args.steps_per_valid,
        'steps_per_trainval': args.steps_per_trainval,
        'steps_per_plot': args.steps_per_plot,
        'steps_per_log': args.steps_per_log,
        'has_valid': not args.no_valid,
        'results': args.results,
        'restore': args.restore,
        'save_ckpt': args.save_ckpt,
        'logs': args.logs,
        'gpu': args.gpu,
        'localhost': args.localhost
    }


def make_data_opt(args):
    inp_height, inp_width, timespan = get_inp_dim(args.dataset)
    if args.dataset == 'synth_shape':
        timespan = args.max_num_objects + 1

    if args.dataset == 'synth_shape':
        data_opt = {
            'height': inp_height,
            'width': inp_width,
            'timespan': timespan,
            'radius_upper': args.radius_upper,
            'radius_lower': args.radius_lower,
            'border_thickness': args.border_thickness,
            'max_num_objects': args.max_num_objects,
            'num_object_types': args.num_object_types,
            'center_var': args.center_var,
            'size_var': args.size_var,
            'num_train': args.num_ex,
            'num_valid': int(args.num_ex / 10),
            'has_valid': True
        }
    elif args.dataset == 'cvppp':
        data_opt = {
            'folder': args.dataset_folder,
            'height': inp_height,
            'width': inp_width,
            'timespan': timespan,
            'num_train': None,
            'num_valid': None,
            'has_valid': not args.no_valid
        }
    elif args.dataset == 'kitti':
        data_opt = {
            'folder': args.dataset_folder,
            'height': inp_height,
            'width': inp_width,
            'timespan': timespan,
            'num_train': args.num_ex,
            'num_valid': args.num_ex,
            'has_valid': True
        }

    return data_opt


def get_inp_dim(dataset):
    kSynthShapeInpHeight = 224
    kSynthShapeInpWidth = 224
    kCvpppInpHeight = 224
    kCvpppInpWidth = 224
    kCvpppNumObj = 20
    kKittiInpHeight = 128
    kKittiInpWidth = 448
    kKittiNumObj = 19
    if dataset == 'synth_shape':
        timespan = None
        inp_height = kSynthShapeInpHeight
        inp_width = kSynthShapeInpWidth
    elif dataset == 'kitti':
        timespan = kKittiNumObj + 1
        inp_height = kKittiInpHeight
        inp_width = kKittiInpWidth
    elif dataset == 'cvppp':
        timespan = kCvpppNumObj + 1
        inp_height = kCvpppInpHeight
        inp_width = kCvpppInpWidth

    return inp_height, inp_width, timespan


def get_inp_transform(dataset):
    if dataset == 'synth_shape':
        rnd_hflip = True
        rnd_vflip = True
        rnd_transpose = True
        rnd_colour = False
    elif dataset == 'cvppp':
        rnd_hflip = True
        rnd_vflip = True
        rnd_transpose = True
        rnd_colour = False
    elif dataset == 'kitti':
        rnd_hflip = True
        rnd_vflip = False
        rnd_transpose = False
        rnd_colour = False

    return rnd_hflip, rnd_vflip, rnd_transpose, rnd_colour


def get_dataset(dataset_name, opt):
    """Get train-valid split dataset for instance segmentation.

    Args:
        opt
    Returns:
        dataset
            'train'
            'valid'
    """

    dataset = {}
    if dataset_name == 'synth_shape':
        opt['num_examples'] = opt['num_train']
        dataset['train'] = synth_shape.get_dataset(opt, seed=2)
        opt['num_examples'] = opt['num_valid']
        dataset['valid'] = synth_shape.get_dataset(opt, seed=3)
    elif dataset_name == 'cvppp':
        dataset_folder = opt['folder']
        if dataset_folder is None:
            if os.path.exists('/u/mren'):
                dataset_folder = '/ais/gobi3/u/mren/data/lsc/A1'
            else:
                dataset_folder = '/home/mren/data/LSCData/A1'

        if opt['has_valid']:
            dataset['train'] = CVPPP(
                dataset_folder, opt, split='train').get_dataset()
            dataset['valid'] = CVPPP(
                dataset_folder, opt, split='valid').get_dataset()
        else:
            dataset['train'] = CVPPP(
                dataset_folder, opt, split=None).get_dataset()
    elif dataset_name == 'kitti':
        dataset_folder = opt['folder']
        if dataset_folder is None:
            if os.path.exists('/u/mren'):
                dataset_folder = '/ais/gobi3/u/mren/data/kitti/object'
            else:
                dataset_folder = '/home/mren/data/kitti'
        opt['timespan'] = 20
        opt['num_examples'] = -1
        dataset['train'] = KITTI(
            dataset_folder, opt, split='train').get_dataset()
        dataset['valid'] = KITTI(
            dataset_folder, opt, split='valid').get_dataset()
    else:
        raise Exception('Unknown dataset name')

    return dataset


def plot_double_attention(fname, x, glimpse_map, max_items_per_row=9):
    """Plot double attention.

    Args:
        fname: str, image output filename.
        x: [B, H, W, 3], input image.
        glimpse_map: [B, T, T2, H', W']: glimpse attention map.
    """
    num_ex = x.shape[0]
    timespan = glimpse_map.shape[1]
    im_height = x.shape[1]
    im_width = x.shape[2]
    num_glimpse = glimpse_map.shape[2]
    num_items = num_glimpse
    num_row, num_col, calc = pu.calc_row_col(
        num_ex * timespan, num_items, max_items_per_row=max_items_per_row)

    f1, axarr = plt.subplots(num_row, num_col, figsize=(10, num_row))
    pu.set_axis_off(axarr, num_row, num_col)

    for ii in xrange(num_ex):
        for tt in xrange(timespan):
            for jj in xrange(num_glimpse):
                row, col = calc(ii * timespan + tt, jj)
                total_img = np.zeros([im_height, im_width, 3])
                total_img += x[ii] * 0.5
                glimpse = glimpse_map[ii, tt, jj]
                glimpse = cv2.resize(glimpse, (im_width, im_height))
                glimpse = np.expand_dims(glimpse, 2)
                glimpse_norm = glimpse / glimpse.max() * 0.5
                total_img += glimpse_norm
                axarr[row, col].imshow(total_img)
                axarr[row, col].text(0, -0.5, '[{:.2g}, {:.2g}]'.format(
                    glimpse.min(), glimpse.max()), color=(0, 0, 0), size=8)

    plt.tight_layout(pad=2.0, w_pad=0.0, h_pad=0.0)
    plt.savefig(fname, dpi=150)
    plt.close('all')

    pass


def plot_output(fname, y_out, s_out, match, attn=None, max_items_per_row=9):
    """Plot some test samples.

    Args:
        fname: str, image output filename.
        y_out: [B, T, H, W, D], segmentation output of the model.
        s_out: [B, T], confidence score output of the model.
        match: [B, T, T], matching matrix.
        attn: ([B, T, 2], [B, T, 2]), top left and bottom right coordinates of
        the attention box.
    """
    num_ex = y_out.shape[0]
    num_items = y_out.shape[1]
    num_row, num_col, calc = pu.calc_row_col(
        num_ex, num_items, max_items_per_row=max_items_per_row)

    f1, axarr = plt.subplots(num_row, num_col, figsize=(10, num_row))
    cmap = ['r', 'y', 'c', 'g', 'm']

    if attn:
        attn_top_left_y = attn[0][:, :, 0]
        attn_top_left_x = attn[0][:, :, 1]
        attn_bot_right_y = attn[1][:, :, 0]
        attn_bot_right_x = attn[1][:, :, 1]

    pu.set_axis_off(axarr, num_row, num_col)

    for ii in xrange(num_ex):
        for jj in xrange(num_items):
            row, col = calc(ii, jj)
            axarr[row, col].imshow(y_out[ii, jj])
            matched = match[ii, jj].nonzero()[0]
            axarr[row, col].text(0, 0, '{:.2f} {}'.format(
                s_out[ii, jj], matched),
                color=(0, 0, 0), size=8)

            if attn:
                # Plot attention box.
                axarr[row, col].add_patch(patches.Rectangle(
                    (attn_top_left_x[ii, jj], attn_top_left_y[ii, jj]),
                    attn_bot_right_x[ii, jj] - attn_top_left_x[ii, jj],
                    attn_bot_right_y[ii, jj] - attn_top_left_y[ii, jj],
                    fill=False,
                    color='m'))

    plt.tight_layout(pad=2.0, w_pad=0.0, h_pad=0.0)
    plt.savefig(fname, dpi=150)
    plt.close('all')

    pass


def plot_total_instances(fname, y_out, s_out, max_items_per_row=9):
    """Plot cumulative image with different colour at each timestep.

    Args:
        y_out: [B, T, H, W]
    """
    num_ex = y_out.shape[0]
    num_items = y_out.shape[1]
    num_row, num_col, calc = pu.calc_row_col(
        num_ex, num_items, max_items_per_row=max_items_per_row)

    f1, axarr = plt.subplots(num_row, num_col, figsize=(10, num_row))
    pu.set_axis_off(axarr, num_row, num_col)

    cmap2 = np.array([[192, 57, 43],
                      [243, 156, 18],
                      [26, 188, 156],
                      [41, 128, 185],
                      [142, 68, 173],
                      [44, 62, 80],
                      [127, 140, 141],
                      [17, 75, 95],
                      [2, 128, 144],
                      [228, 253, 225],
                      [69, 105, 144],
                      [244, 91, 105],
                      [91, 192, 235],
                      [253, 231, 76],
                      [155, 197, 61],
                      [229, 89, 52],
                      [250, 121, 33]], dtype='uint8')

    for ii in xrange(num_ex):
        total_img = np.zeros([y_out.shape[2], y_out.shape[3], 3])
        for jj in xrange(num_items):
            row, col = calc(ii, jj)
            if s_out[ii, jj] > 0.5:
                total_img += np.expand_dims(
                    (y_out[ii, jj] > 0.5).astype('uint8'), 2) * \
                    cmap2[jj % cmap2.shape[0]]
            axarr[row, col].imshow(total_img)
            total_img = np.copy(total_img)

    plt.tight_layout(pad=2.0, w_pad=0.0, h_pad=0.0)
    plt.savefig(fname, dpi=150)
    plt.close('all')

    pass


def plot_input(fname, x, y_gt, s_gt, max_items_per_row=9):
    """Plot input, transformed input and output groundtruth sequence.
    """
    num_ex = y_gt.shape[0]
    num_items = y_gt.shape[1]
    num_row, num_col, calc = pu.calc_row_col(
        num_ex, num_items, max_items_per_row=max_items_per_row)

    f1, axarr = plt.subplots(num_row, num_col, figsize=(10, num_row))
    pu.set_axis_off(axarr, num_row, num_col)
    cmap = ['r', 'y', 'c', 'g', 'm']

    for ii in xrange(num_ex):
        for jj in xrange(num_items):
            row, col = calc(ii, jj)
            axarr[row, col].imshow(x[ii])
            nz = y_gt[ii, jj].nonzero()
            if nz[0].size > 0:
                top_left_x = nz[1].min()
                top_left_y = nz[0].min()
                bot_right_x = nz[1].max() + 1
                bot_right_y = nz[0].max() + 1
                axarr[row, col].add_patch(patches.Rectangle(
                    (top_left_x, top_left_y),
                    bot_right_x - top_left_x,
                    bot_right_y - top_left_y,
                    fill=False,
                    color=cmap[jj % len(cmap)]))
                axarr[row, col].add_patch(patches.Rectangle(
                    (top_left_x, top_left_y - 25),
                    25, 25,
                    fill=True,
                    color=cmap[jj % len(cmap)]))
                axarr[row, col].text(
                    top_left_x + 5, top_left_y - 5,
                    '{}'.format(jj), size=5)

    plt.tight_layout(pad=2.0, w_pad=0.0, h_pad=0.0)
    plt.savefig(fname, dpi=150)
    plt.close('all')

    pass


def register_raw_logs(log_manager, log, model_opt, saver):
    log_manager.register(log.filename, 'plain', 'Raw logs')
    cmd_fname = os.path.join(log_manager.folder, 'cmd.log')
    with open(cmd_fname, 'w') as f:
        f.write(' '.join(sys.argv))
    log_manager.register(cmd_fname, 'plain', 'Command-line arguments')
    model_opt_fname = os.path.join(log_manager.folder, 'model_opt.yaml')
    saver.save_opt(model_opt_fname, model_opt)
    log_manager.register(model_opt_fname, 'plain', 'Model hyperparameters')

    pass


def run_model(sess, model, names, feed_dict):
    symbol_list = [model[r] for r in names]
    results = sess.run(symbol_list, feed_dict=feed_dict)
    results_dict = {}
    for rr, name in zip(results, names):
        results_dict[name] = rr

    return results_dict


def run_stats(step, sess, model, num_batch, batch_iter, outputs, write_log, phase_train):
    """Validation"""
    bat_sz_total = 0
    r = {}

    for bb in xrange(num_batch):
        _x, _y, _s = batch_iter.next()
        _feed_dict = {model['x']: _x, model['phase_train']: phase_train,
                      model['y_gt']: _y, model['s_gt']: _s}
        _r = run_model(sess, model, outputs, _feed_dict)
        bat_sz = _x.shape[0]
        bat_sz_total += bat_sz

        for key in _r.iterkeys():
            if key in r:
                r[key] += _r[key] * bat_sz
            else:
                r[key] = _r[key] * bat_sz

    for key in r.iterkeys():
        r[key] = r[key] / bat_sz_total

    log.info('{:d} loss {:.4f}'.format(step, r['loss']))
    write_log(step, r)

    pass


def preprocess(inp, label_segmentation, label_score):
    """Preprocess training data."""
    return (inp.astype('float32') / 255,
            label_segmentation.astype('float32'),
            label_score.astype('float32'))


def get_batch_fn(dataset):
    """
    Preprocess mini-batch data given start and end indices.
    """
    def get_batch(idx):
        x_bat = dataset['input'][idx]
        y_bat = dataset['label_segmentation'][idx]
        s_bat = dataset['label_score'][idx]
        x_bat, y_bat, s_bat = preprocess(x_bat, y_bat, s_bat)

        return x_bat, y_bat, s_bat

    return get_batch


def get_max_items_per_row(inp_height, inp_width):
    if inp_height == inp_width:
        return 8
    else:
        return 5


def get_num_batch_valid(dataset_name):
    if dataset_name == 'synth_shape':
        return 5
    elif dataset_name == 'cvppp':
        return 5
    elif dataset_name == 'kitti':
        return 10
    else:
        raise Exception('Unknown dataset name')


def get_model_id(task_name):
    return '{}-{}'.format(task_name, assign_model_id.get_id())


def sort_by_segm_size(y):
    """Sort the input/output sequence by the groundtruth size.

    Args:
        y: [B, T, H, W]
    """
    # [B, T]
    y_size = np.sum(np.sum(y, 3), 2)
    # [B, T, H, W]
    y_sort = np.zeros(y.shape, dtype=y.dtype)
    for ii in xrange(y.shape[0]):
        idx = np.argsort(y_size[ii])[::-1]
        y_sort[ii, :, :, :] = y[ii, idx, :, :]

    return y_sort
