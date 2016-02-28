from __future__ import division

import cslab_environ

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import os
import pickle as pkl
import tensorflow as tf
import time

from data_api import synth_shape
from data_api import cvppp

from utils import logger

import rec_ins_segm_models as models

log = logger.get()


def _get_attn(y, attn_size):
    ctr = np.zeros([y.shape[0], y.shape[1], 2])
    delta = np.zeros([y.shape[0], y.shape[1], 2])
    lg_var = np.zeros([y.shape[0], y.shape[1], 2])
    for ii in xrange(y.shape[0]):
        for jj in xrange(y.shape[1]):
            nz = y_gt_val[ii, jj].nonzero()
            if nz[0].size > 0:
                top_left_x = nz[1].min()
                top_left_y = nz[0].min()
                bot_right_x = nz[1].max() + 1
                bot_right_y = nz[0].max() + 1
                ctr[ii, jj, 0] = (bot_right_y + top_left_y) / 2
                ctr[ii, jj, 1] = (bot_right_x + top_left_x) / 2
                delta[ii, jj, 0] = (bot_right_y - top_left_y) / attn_size
                delta[ii, jj, 1] = (bot_right_x - top_left_x) / attn_size
                lg_var[ii, jj, 0] = 1.0
                lg_var[ii, jj, 1] = 1.0

    return ctr, delta, lg_var


def get_dataset(dataset_name, opt, num_train, num_valid):
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
    if dataset_name == 'synth_shape':
        opt['num_examples'] = num_train
        dataset['train'] = synth_shape.get_dataset(opt, seed=2)
        opt['num_examples'] = num_valid
        dataset['valid'] = synth_shape.get_dataset(opt, seed=3)
    elif dataset_name == 'cvppp':
        if os.path.exists('/u/mren'):
            dataset_folder = '/ais/gobi3/u/mren/data/lsc/A1'
        else:
            dataset_folder = '/home/mren/data/LSCData/A1'
        _all_data = cvppp.get_dataset(dataset_folder, opt)
        split = 103
        random = np.random.RandomState(2)
        idx = np.arange(_all_data['input'].shape[0])
        random.shuffle(idx)
        train_idx = idx[: split]
        valid_idx = idx[split:]
        log.info('Train index: {}'.format(train_idx))
        log.info('Valid index: {}'.format(valid_idx))
        dataset['train'] = {
            'input': _all_data['input'][train_idx],
            'label_segmentation': _all_data['label_segmentation'][train_idx],
            'label_score': _all_data['label_score'][train_idx]
        }
        dataset['valid'] = {
            'input': _all_data['input'][valid_idx],
            'label_segmentation': _all_data['label_segmentation'][valid_idx],
            'label_score': _all_data['label_score'][valid_idx]
        }

    return dataset


def _get_batch_fn(dataset):
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


def preprocess(inp, label_segmentation, label_score):
    """Preprocess training data."""
    return (inp.astype('float32') / 255,
            label_segmentation.astype('float32'),
            label_score.astype('float32'))


def _parse_args():
    """Parse input arguments."""
    # Default dataset options
    kDataset = 'synth_shape'
    kHeight = 224
    kWidth = 224
    kPadding = 16
    # (Below are only valid options for synth_shape dataset)
    kRadiusLower = 15
    kRadiusUpper = 45
    kBorderThickness = 3
    kNumExamples = 1000
    kMaxNumObjects = 6
    kNumObjectTypes = 1
    kSizeVar = 20
    kCenterVar = 20

    # Default model options
    # [224, 224,  3]
    # [112, 112,  4]
    # [56,  56,   8]
    # [28,  28,   8]
    # [14,  14,  12]
    # [7,   7,   16]
    # [7,   7,   12]
    # [7,   7,    6]
    # [14,  14, 8+12]
    # [28,  28,  6+8]
    # [56,  56,  4+8]
    # [112, 112, 4+4]
    # [224, 224, 2+3]
    # [224, 224,   1]

    kWeightDecay = 5e-5
    kBaseLearnRate = 1e-3
    kLearnRateDecay = 0.96
    kStepsPerDecay = 5000
    kStepsPerLog = 10
    kLossMixRatio = 1.0
    kNumConv = 5
    kCnnFilterSize = [3, 3, 3, 3, 3]
    kCnnDepth = [4, 8, 8, 12, 16]
    kRnnType = 'conv_lstm'                  # {"conv_lstm", "lstm", "gru"}
    kConvLstmFilterSize = 3
    kConvLstmHiddenDepth = 12
    kRnnHiddenDim = 512

    kNumMlpLayers = 2
    kMlpDepth = 6
    kMlpDropout = 0.5
    kDcnnFilterSize = [3, 3, 3, 3, 3, 3]
    kDcnnDepth = [1, 2, 4, 4, 6, 8]
    kScoreMaxpool = 1

    # Default training options
    kNumSteps = 500000
    kStepsPerCkpt = 1000
    kStepsPerValid = 250
    kBatchSize = 32

    parser = argparse.ArgumentParser(
        description='Recurrent Instance Segmentation')

    # Dataset options
    parser.add_argument('-dataset', default=kDataset,
                        help='Name of the dataset')
    parser.add_argument('-height', default=kHeight, type=int,
                        help='Image height')
    parser.add_argument('-width', default=kWidth, type=int,
                        help='Image width')
    parser.add_argument('-padding', default=kPadding, type=int,
                        help='Apply additional padding for random cropping')

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
    parser.add_argument('-base_learn_rate', default=kBaseLearnRate,
                        type=float, help='Model learning rate')
    parser.add_argument('-learn_rate_decay', default=kLearnRateDecay,
                        type=float, help='Model learning rate decay')
    parser.add_argument('-steps_per_decay', default=kStepsPerDecay,
                        type=int, help='Steps every learning rate decay')
    parser.add_argument('-loss_mix_ratio', default=kLossMixRatio, type=float,
                        help='Mix ratio between segmentation and score loss')
    parser.add_argument('-num_conv', default=kNumConv,
                        type=int, help='Number of convolutional layers')

    for ii in xrange(kNumConv):
        parser.add_argument('-cnn_{}_filter_size'.format(ii + 1),
                            default=kCnnFilterSize[ii], type=int,
                            help='CNN layer {} filter size'.format(ii + 1))
        parser.add_argument('-cnn_{}_depth'.format(ii + 1),
                            default=kCnnDepth[ii], type=int,
                            help='CNN layer {} depth'.format(ii + 1))

    for ii in xrange(kNumConv + 1):
        parser.add_argument('-dcnn_{}_filter_size'.format(ii),
                            default=kDcnnFilterSize[ii], type=int,
                            help='DCNN layer {} filter size'.format(ii))
        parser.add_argument('-dcnn_{}_depth'.format(ii),
                            default=kDcnnDepth[ii], type=int,
                            help='DCNN layer {} depth'.format(ii))

    parser.add_argument('-rnn_hid_dim', default=kRnnHiddenDim,
                        type=int, help='RNN hidden dimension')
    parser.add_argument('-num_mlp_layers', default=kNumMlpLayers,
                        type=int, help='Number of MLP layers')
    parser.add_argument('-mlp_depth', default=kMlpDepth,
                        type=int, help='MLP depth')
    parser.add_argument('-mlp_dropout', default=kMlpDropout,
                        type=float, help='MLP dropout')

    # Extra model options (beta)
    parser.add_argument('-segm_loss_fn', default='iou',
                        help='Segmentation loss function, "iou" or "bce"')
    parser.add_argument('-use_bn', action='store_true',
                        help='Whether to use batch normalization.')

    # Training options
    parser.add_argument('-num_steps', default=kNumSteps,
                        type=int, help='Number of steps to train')
    parser.add_argument('-steps_per_ckpt', default=kStepsPerCkpt,
                        type=int, help='Number of steps per checkpoint')
    parser.add_argument('-steps_per_valid', default=kStepsPerValid,
                        type=int, help='Number of steps per validation')
    parser.add_argument('-steps_per_log', default=kStepsPerLog,
                        type=int, help='Number of steps per log')
    parser.add_argument('-batch_size', default=kBatchSize,
                        type=int, help='Size of a mini-batch')
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
    saver = None

    # Restore previously saved checkpoints.
    if args.restore:
        saver = Saver(args.restore)
        ckpt_info = saver.get_ckpt_info()
        model_opt = ckpt_info['model_opt']
        data_opt = ckpt_info['data_opt']
        ckpt_fname = ckpt_info['ckpt_fname']
        step = ckpt_info['step']
        model_id = ckpt_info['model_id']
        exp_folder = args.restore
    else:
        model_id = get_model_id('rec_ins_segm')

        cnn_filter_size_all = [args.cnn_1_filter_size,
                               args.cnn_2_filter_size,
                               args.cnn_3_filter_size,
                               args.cnn_4_filter_size,
                               args.cnn_5_filter_size]
        cnn_depth_all = [args.cnn_1_depth,
                         args.cnn_2_depth,
                         args.cnn_3_depth,
                         args.cnn_4_depth,
                         args.cnn_5_depth]
        dcnn_filter_size_all = [args.dcnn_0_filter_size,
                                args.dcnn_1_filter_size,
                                args.dcnn_2_filter_size,
                                args.dcnn_3_filter_size,
                                args.dcnn_4_filter_size,
                                args.dcnn_5_filter_size]
        dcnn_depth_all = [args.dcnn_0_depth,
                          args.dcnn_1_depth,
                          args.dcnn_2_depth,
                          args.dcnn_3_depth,
                          args.dcnn_4_depth,
                          args.dcnn_5_depth]

        if args.dataset == 'synth_shape':
            timespan = args.max_num_objects + 1
        elif args.dataset == 'cvppp':
            timespan = 21
        else:
            raise Exception('Unknown dataset name')

        model_opt = {
            'inp_height': args.height,
            'inp_width': args.width,
            'inp_depth': 3,
            'padding': args.padding,
            'timespan': timespan,
            'weight_decay': args.weight_decay,
            'base_learn_rate': args.base_learn_rate,
            'learn_rate_decay': args.learn_rate_decay,
            'steps_per_decay': args.steps_per_decay,
            'loss_mix_ratio': args.loss_mix_ratio,
            'cnn_filter_size': cnn_filter_size_all[: args.num_conv],
            'cnn_depth': cnn_depth_all[: args.num_conv],
            'dcnn_filter_size': dcnn_filter_size_all[: args.num_conv + 1][::-1],
            'dcnn_depth': dcnn_depth_all[: args.num_conv + 1][::-1],
            'rnn_hid_dim': args.rnn_hid_dim,
            'mlp_depth': args.mlp_depth,
            'num_mlp_layers': args.num_mlp_layers,
            'mlp_dropout': args.mlp_dropout,

            # Test arguments
            'segm_loss_fn': args.segm_loss_fn,
            'use_bn': args.use_bn
        }
        data_opt = {
            'height': args.height,
            'width': args.width,
            'padding': args.padding,
            'radius_upper': args.radius_upper,
            'radius_lower': args.radius_lower,
            'border_thickness': args.border_thickness,
            'max_num_objects': args.max_num_objects,
            'num_object_types': args.num_object_types,
            'center_var': args.center_var,
            'size_var': args.size_var
        }
        step = 0
        exp_folder = os.path.join(args.results, model_id)
        saver = Saver(exp_folder, model_opt=model_opt, data_opt=data_opt)

    # Logger
    if args.logs:
        logs_folder = args.logs
        logs_folder = os.path.join(logs_folder, model_id)
        log = logger.get(os.path.join(logs_folder, 'raw'))
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
        'steps_per_ckpt': args.steps_per_ckpt,
        'steps_per_valid': args.steps_per_valid,
        'steps_per_log': args.steps_per_log
    }

    log.info('Building model')
    m = models.get_model(args.model, model_opt, device=device)

    log.info('Loading dataset')
    dataset = get_dataset(args.dataset, data_opt,
                          args.num_ex, args.num_ex / 10)

    ctr, delta, lg_var = _get_attn()

    sess = tf.Session()

    if args.restore:
        saver.restore(sess, ckpt_fname)
    else:
        sess.run(tf.initialize_all_variables())

    # Create time series logger
    if args.logs:
        loss_logger = TimeSeriesLogger(
            os.path.join(logs_folder, 'loss.csv'), ['train', 'valid'],
            name='Loss',
            buffer_size=1)
        iou_logger = TimeSeriesLogger(
            os.path.join(logs_folder, 'iou.csv'),
            ['train soft', 'valid soft', 'train hard', 'valid hard'],
            name='IoU',
            buffer_size=1)
        count_acc_logger = TimeSeriesLogger(
            os.path.join(logs_folder, 'count_acc.csv'),
            ['train', 'valid'],
            name='Count accuracy',
            buffer_size=1)
        learn_rate_logger = TimeSeriesLogger(
            os.path.join(logs_folder, 'learn_rate.csv'),
            'learning rate',
            name='Learning rate',
            buffer_size=10)
        step_time_logger = TimeSeriesLogger(
            os.path.join(logs_folder, 'step_time.csv'), 'step time (ms)',
            name='Step time',
            buffer_size=10)

        log_manager.register(log.filename, 'plain', 'Raw logs')

        model_opt_fname = os.path.join(logs_folder, 'model_opt.yaml')
        saver.save_opt(model_opt_fname, model_opt)
        log_manager.register(model_opt_fname, 'plain', 'Model hyperparameters')

        valid_sample_img = LazyRegisterer(os.path.join(
            logs_folder, 'valid_sample_img.png'),
            'image', 'Validation samples')
        train_sample_img = LazyRegisterer(os.path.join(
            logs_folder, 'train_sample_img.png'),
            'image', 'Training samples')
        log.info(
            ('Visualization can be viewed at: '
             'http://{}/deep-dashboard?id={}').format(
                args.localhost, model_id))

    num_ex_train = dataset['train']['input'].shape[0]
    num_ex_valid = dataset['valid']['input'].shape[0]
    get_batch_train = _get_batch_fn(dataset['train'])
    get_batch_valid = _get_batch_fn(dataset['valid'])
    batch_size = args.batch_size
    log.info('Number of validation examples: {}'.format(num_ex_valid))
    log.info('Number of training examples: {}'.format(num_ex_train))
    log.info('Batch size: {}'.format(batch_size))

    def run_samples(x, y, s, phase_train, fname):
        x2, y2, y_out, s_out, match = sess.run(
            [m['x_trans'], m['y_gt_trans'], m['y_out'], m['s_out'],
             m['match']], feed_dict={
                m['x']: x,
                m['phase_train']: phase_train,
                m['y_gt']: y,
                m['s_gt']: s
            })
        plot_samples(fname, x_orig=x, x=x2, y_out=y_out, s_out=s_out, y_gt=y2,
                     s_gt=s, match=match)

    def run_validation():
        # Validation
        loss = 0.0
        iou_hard = 0.0
        iou_soft = 0.0
        count_acc = 0.0
        segm_loss = 0.0
        conf_loss = 0.0
        log.info('Running validation')
        for _x, _y, _s in BatchIterator(num_ex_valid,
                                        batch_size=batch_size,
                                        get_fn=get_batch_valid,
                                        progress_bar=False):
            results = sess.run([m['loss'], m['segm_loss'], m['conf_loss'],
                                m['iou_soft'], m['iou_hard'], m['count_acc']],
                               feed_dict={
                m['x']: _x,
                m['phase_train']: False,
                m['y_gt']: _y
            })
            _loss = results[0]
            _segm_loss = results[1]
            _conf_loss = results[2]
            _iou_soft = results[3]
            _iou_hard = results[4]
            _count_acc = results[5]
            num_ex_batch = _x.shape[0]
            loss += _loss * num_ex_batch / float(num_ex_valid)
            segm_loss += _segm_loss * num_ex_batch / float(num_ex_valid)
            conf_loss += _conf_loss * num_ex_batch / float(num_ex_valid)
            iou_soft += _iou_soft * num_ex_batch / float(num_ex_valid)
            iou_hard += _iou_hard * num_ex_batch / float(num_ex_valid)
            count_acc += _count_acc * num_ex_batch / float(num_ex_valid)

        log.info(('{:d} valid loss {:.4f} segm_loss {:.4f} conf_loss {:.4f} '
                  'iou soft {:.4f} iou hard {:.4f} count acc {:.4f}').format(
            step, loss, segm_loss, conf_loss, iou_soft, iou_hard, count_acc))

        if args.logs:
            loss_logger.add(step, ['', loss])
            iou_logger.add(step, ['', iou_soft, '', iou_hard])
            count_acc_logger.add(step, ['', count_acc])

            # Plot some samples.
            _x, _y, _s = get_batch_valid(np.arange(args.num_samples_plot))
            run_samples(_x, _y, _s, False, valid_sample_img.get_fname())
            if not valid_sample_img.is_registered():
                valid_sample_img.register()

            _x, _y, _s = get_batch_train(np.arange(args.num_samples_plot))
            run_samples(_x, _y, _s, True, train_sample_img.get_fname())
            if not train_sample_img.is_registered():
                train_sample_img.register()

        pass

    # Train loop
    for x_bat, y_bat, s_bat in BatchIterator(num_ex_train,
                                             batch_size=batch_size,
                                             get_fn=get_batch_train,
                                             cycle=True,
                                             progress_bar=False):
        # Run validation
        if step % train_opt['steps_per_valid'] == 0:
            run_validation()

        # Train step
        start_time = time.time()
        r = sess.run([m['loss'], m['segm_loss'], m['conf_loss'],
                      m['iou_soft'], m['iou_hard'], m['count_acc'],
                      m['learn_rate'], m['train_step']], feed_dict={
            m['x']: x_bat,
            m['phase_train']: True,
            m['global_step']: step,
            m['y_gt']: y_bat,
            m['s_gt']: s_bat
        })

        # Print statistics
        if step % train_opt['steps_per_log'] == 0:
            loss = r[0]
            segm_loss = r[1]
            conf_loss = r[2]
            iou_soft = r[3]
            iou_hard = r[4]
            count_acc = r[5]
            learn_rate = r[6]
            step_time = (time.time() - start_time) * 1000
            log.info('{:d} train loss {:.4f} {:.4f} {:.4f} t {:.2f}ms'.format(
                step, loss, segm_loss, conf_loss, step_time))

            if args.logs:
                loss_logger.add(step, [loss, ''])
                iou_logger.add(step, [iou_soft, '', iou_hard, ''])
                count_acc_logger.add(step, [count_acc, ''])
                learn_rate_logger.add(step, learn_rate)
                step_time_logger.add(step, step_time)

        # Model ID reminder
        if step % (10 * train_opt['steps_per_log']) == 0:
            log.info('model id {}'.format(model_id))

        # Save model
        if step % train_opt['steps_per_ckpt'] == 0:
            saver.save(sess, global_step=step)

        step += 1

        # Termination
        if step > train_opt['num_steps']:
            break

    sess.close()
    loss_logger.close()
    iou_logger.close()
    count_acc_logger.close()
    learn_rate_logger.close()
    step_time_logger.close()

    pass