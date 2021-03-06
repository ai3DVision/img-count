import cslab_environ

import numpy as np
import tensorflow as tf
import unittest


class HungarianTests(unittest.TestCase):
    
    def test_min_weighted_bp_cover_1(self):
        W = np.array([[3, 2, 2],
                      [1, 2, 0],
                      [2, 2, 1]])
        M, c_0, c_1 = tf.user_ops.hungarian(W)
        with tf.Session() as sess:
            M = M.eval()
            c_0 = c_0.eval()
            c_1 = c_1.eval()
        c_0_t = np.array([2, 1, 1])
        c_1_t = np.array([1, 1, 0])
        M_t = np.array([[1, 0, 0],
                        [0, 1, 0],
                        [0, 0, 1]])
        print M
        print c_0
        print c_1
        self.assertTrue((c_0.flatten() == c_0_t.flatten()).all())
        self.assertTrue((c_1.flatten() == c_1_t.flatten()).all())
        self.assertTrue((M == M_t).all())

        pass

    def test_min_weighted_bp_cover_2(self):
        W = np.array([[5, 0, 4, 0],
                      [0, 4, 6, 8],
                      [4, 0, 5, 7]])
        M, c_0, c_1 = tf.user_ops.hungarian(W)
        with tf.Session() as sess:
            M = M.eval()
            c_0 = c_0.eval()
            c_1 = c_1.eval()
        c_0_t = np.array([5, 6, 5])
        c_1_t = np.array([0, 0, 0, 2])
        M_t = np.array([[1, 0, 0, 0],
                        [0, 0, 1, 0],
                        [0, 0, 0, 1]])
        print M
        print c_0
        print c_1
        self.assertTrue((c_0.flatten() == c_0_t.flatten()).all())
        self.assertTrue((c_1.flatten() == c_1_t.flatten()).all())
        self.assertTrue((M == M_t).all())

        pass

    def test_min_weighted_bp_cover_3(self):
        W = np.array([[5, 0, 2],
                      [3, 1, 0],
                      [0, 5, 0]])
        M, c_0, c_1 = tf.user_ops.hungarian(W)
        with tf.Session() as sess:
            M = M.eval()
            c_0 = c_0.eval()
            c_1 = c_1.eval()
        c_0_t = np.array([2, 0, 4])
        c_1_t = np.array([3, 1, 0])
        M_t = np.array([[0, 0, 1],
                        [1, 0, 0],
                        [0, 1, 0]])
        print M
        print c_0
        print c_1
        self.assertTrue((c_0.flatten() == c_0_t.flatten()).all())
        self.assertTrue((c_1.flatten() == c_1_t.flatten()).all())
        self.assertTrue((M == M_t).all())

        pass

    def test_min_weighted_bp_cover_4(self):
        W = np.array([
                      [[5, 0, 2],
                       [3, 1, 0],
                       [0, 5, 0]],

                      [[3, 2, 2],
                       [1, 2, 0],
                       [2, 2, 1]]
                    ])
        M, c_0, c_1 = tf.user_ops.hungarian(W)
        with tf.Session() as sess:
            M = M.eval()
            c_0 = c_0.eval()
            c_1 = c_1.eval()
        c_0_t = np.array([[2, 0, 4], [2, 1, 1]])
        c_1_t = np.array([[3, 1, 0], [1, 1, 0]])
        M_t = np.array([[[0, 0, 1],
                         [1, 0, 0],
                         [0, 1, 0]],
                        [[1, 0, 0],
                         [0, 1, 0],
                         [0, 0, 1]]])
        print M
        print c_0
        print c_1
        self.assertTrue((c_0.flatten() == c_0_t.flatten()).all())
        self.assertTrue((c_1.flatten() == c_1_t.flatten()).all())
        self.assertTrue((M == M_t).all())

        pass


    def test_real_values_1(self):
        # Test the while loop terminates with real values.
        W = np.array(
[[0.90, 0.70, 0.30, 0.20, 0.40, 0.001, 0.001, 0.001, 0.001, 0.001],
 [0.80, 0.75, 0.92, 0.10, 0.15, 0.001, 0.001, 0.001, 0.001, 0.001],
 [0.78, 0.85, 0.66, 0.29, 0.21, 0.001, 0.001, 0.001, 0.001, 0.001],
 [0.42, 0.55, 0.23, 0.43, 0.33, 0.002, 0.001, 0.001, 0.001, 0.001],
 [0.64, 0.44, 0.33, 0.33, 0.34, 0.001, 0.002, 0.001, 0.001, 0.001],
 [0.22, 0.55, 0.43, 0.43, 0.14, 0.001, 0.001, 0.002, 0.001, 0.001],
 [0.43, 0.33, 0.34, 0.22, 0.14, 0.001, 0.001, 0.001, 0.002, 0.001],
 [0.33, 0.42, 0.23, 0.13, 0.43, 0.001, 0.001, 0.001, 0.001, 0.002],
 [0.39, 0.24, 0.53, 0.56, 0.89, 0.001, 0.001, 0.001, 0.001, 0.001],
 [0.12, 0.34, 0.82, 0.82, 0.77, 0.001, 0.001, 0.001, 0.001, 0.001]])
        M, c_0, c_1 = tf.user_ops.hungarian(W)
        with tf.Session() as sess:
            M = M.eval()

        M_t = np.array(
[[1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 [0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
 [0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
 [0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
 [0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
 [0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 [0, 0, 0, 0, 0, 0, 0, 0, 1, 0],
 [0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
 [0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
 [0, 0, 0, 1, 0, 0, 0, 0, 0, 0]])

        print M
        self.assertTrue((M == M_t).all())

        pass

    def test_real_values_2(self):
        W = np.array(
[[0.00604139, 0.0126045, 0.0117373,   0.01245, 0.00808836, 0.0162662, 0.0137996, 0.00403898, 0.0123786, 1e-05],
 [0.00604229, 0.0126071, 0.0117400, 0.0124528, 0.00808971, 0.0162703, 0.0138028, 0.00403935, 0.0123812, 1e-05],
 [0.00604234, 0.0126073, 0.0117402,  0.012453, 0.00808980, 0.0162706, 0.0138030, 0.00403937, 0.0123814, 1e-05],
 [0.00604235, 0.0126073, 0.0117402,  0.012453, 0.00808981, 0.0162706, 0.0138030, 0.00403938, 0.0123814, 1e-05],
 [0.00604235, 0.0126073, 0.0117402,  0.012453, 0.00808981, 0.0162706, 0.0138030, 0.00403938, 0.0123814, 1e-05],
 [0.00604235, 0.0126073, 0.0117402,  0.012453, 0.00808981, 0.0162706, 0.0138030, 0.00403938, 0.0123814, 1e-05],
 [0.00604235, 0.0126073, 0.0117402,  0.012453, 0.00808981, 0.0162706, 0.0138030, 0.00403938, 0.0123814, 1e-05],
 [0.00604235, 0.0126073, 0.0117402,  0.012453, 0.00808981, 0.0162706, 0.0138030, 0.00403938, 0.0123814, 1e-05],
 [0.00604235, 0.0126073, 0.0117402,  0.012453, 0.00808981, 0.0162706, 0.0138030, 0.00403938, 0.0123814, 1e-05],
 [0.00604235, 0.0126073, 0.0117402,  0.012453, 0.00808981, 0.0162706, 0.0138030, 0.00403938, 0.0123814, 1e-05]])
        M, c_0, c_1 = tf.user_ops.hungarian(W)
        with tf.Session() as sess:
            M = M.eval()

        print M

        pass

    def test_real_values_3(self):
        W = np.array(
[[0.00302646, 0.00321431,  0.0217552, 0.00836773,  0.0256353,  0.0177026,  0.0289461,  0.0214768,  0.0101898,      1e-05],
[0.00302875 , 0.003217  ,  0.0217628, 0.00836405,  0.0256229,  0.0177137,  0.0289468,  0.0214719,  0.0101904,      1e-05],
[0.00302897 , 0.00321726,  0.0217636, 0.00836369,  0.0256217,  0.0177148,  0.0289468,  0.0214714,  0.0101905,      1e-05],
[0.003029   , 0.0032173 ,  0.0217637, 0.00836364,  0.0256216,  0.0177149,  0.0289468,  0.0214713,  0.0101905,      1e-05],
[0.003029   , 0.0032173 ,  0.0217637, 0.00836364,  0.0256216,  0.0177149,  0.0289468,  0.0214713,  0.0101905,      1e-05],
[0.003029   , 0.0032173 ,  0.0217637, 0.00836364,  0.0256216,   0.017715,  0.0289468,  0.0214713,  0.0101905,      1e-05],
[0.003029   , 0.0032173 ,  0.0217637, 0.00836364,  0.0256216,   0.017715,  0.0289468,  0.0214713,  0.0101905,      1e-05],
[0.003029   , 0.0032173 ,  0.0217637, 0.00836364,  0.0256216,   0.017715,  0.0289468,  0.0214713,  0.0101905,      1e-05],
[0.003029   , 0.0032173 ,  0.0217637, 0.00836364,  0.0256216,   0.017715,  0.0289468,  0.0214713,  0.0101905,      1e-05],
[0.003029   , 0.0032173 ,  0.0217637, 0.00836364,  0.0256216,   0.017715,  0.0289468,  0.0214713,  0.0101905,      1e-05]])
        M, c_0, c_1 = tf.user_ops.hungarian(W)
        with tf.Session() as sess:
            M = M.eval()

        print M
        
        pass

    def test_real_values_4(self):
        W = np.array(
[[      1e-05,   0.0634311,       1e-05, 4.76687e-05, 1.00079e-05, 1.00378e-05,       1e-05,       1e-05,       1e-05,  3.9034e-05],
[      1e-05, 3.42696e-05,       1e-05,       1e-05,       1e-05,       1e-05,       1e-05,  1.0122e-05, 3.43236e-05,       1e-05],
[      1e-05,   0.0426792,    0.031155,  1.0008e-05,  0.00483961,   0.0228187,       1e-05,       1e-05,       1e-05,    0.102463],
[      1e-05,       1e-05,       1e-05, 1.07065e-05,       1e-05, 1.00185e-05,       1e-05,       1e-05,       1e-05, 1.00007e-05],
[      1e-05, 4.22947e-05,  0.00062168,    0.623917, 1.03468e-05,  0.00588984, 1.00004e-05, 1.44433e-05, 1.00014e-05, 0.000213425],
[      1e-05, 1.01764e-05,       1e-05, 0.000667249,       1e-05, 0.000485082,       1e-05,       1e-05, 1.00002e-05,       1e-05],
[      1e-05,       1e-05, 1.50331e-05,       1e-05,     0.11269,       1e-05,       1e-05,       1e-05,       1e-05, 1.13251e-05],
[ 1.0001e-05,       1e-05,       1e-05,       1e-05,       1e-05,       1e-05,   0.0246974,       1e-05,       1e-05,       1e-05],
[      1e-05, 2.89144e-05,       1e-05, 1.05147e-05,       1e-05, 0.000894762, 1.03587e-05,    0.150301,       1e-05, 1.00045e-05],
[      1e-05, 3.97901e-05,       1e-05, 1.11641e-05,       1e-05, 2.34249e-05,  1.0007e-05, 2.42828e-05,       1e-05, 1.10529e-05]])
        
        p = 1e6
        W = np.round(W * p) / p
        M, c_0, c_1 = tf.user_ops.hungarian(W)
        with tf.Session() as sess:
            M = M.eval()

        print M
        
        pass

    def test_real_values_5(self):
        W = np.array(
[[1.4e-05  ,  1e-05  ,  1e-05  , 0.053306, 0.044139,    1e-05,  1.2e-05,    1e-05,    1e-05,    1e-05],
 [ 0.001234,    1e-05,    1e-05,  2.1e-05,    1e-05, 0.001535, 0.019553,    1e-05,    1e-05,    1e-05],
 [ 0.002148,    1e-05,    1e-05,  1.6e-05, 0.651536,    2e-05,  7.4e-05, 0.002359,    1e-05,    1e-05],
 [  3.8e-05,    1e-05, 0.000592,  4.7e-05,  0.09173,    1e-05,    1e-05,    1e-05,    1e-05,    1e-05],
 [    1e-05,    1e-05,    1e-05, 0.213736,    1e-05,  4.5e-05, 0.000768,    1e-05,    1e-05,    1e-05],
 [    1e-05,    1e-05,    1e-05, 0.317609,    1e-05,    1e-05, 0.002151,    1e-05,    1e-05,    1e-05],
 [ 0.002802,    1e-05,  1.2e-05,    1e-05,    1e-05, 0.002999,  4.8e-05,  1.1e-05, 0.000919,    1e-05],
 [    1e-05,    1e-05,    1e-05,    1e-05,    1e-05,    1e-05,    1e-05,    1e-05, 0.028816,    1e-05],
 [    1e-05,    1e-05, 0.047335,    1e-05,  1.2e-05,    1e-05,    1e-05,    1e-05,    1e-05,    1e-05],
 [    1e-05,    1e-05,    1e-05,    1e-05,    1e-05,    1e-05,    1e-05,    1e-05,    1e-05,    1e-05]])
 
        p = 1e6
        W = np.round(W * p) / p
        M, c_0, c_1 = tf.user_ops.hungarian(W)
        with tf.Session() as sess:
            M = M.eval()

        print M
        
        pass

    def test_real_values_6(self):
        W = np.array(
[[0.003408, 0.010531, 0.002795,    1e-05, 0.019786, 0.010435, 0.002743, 0.023617, 0.010436, 0.003116],
 [0.003408, 0.010531, 0.002795,    1e-05, 0.019786, 0.010435, 0.002743, 0.023617, 0.010436, 0.003116],
 [0.003408, 0.010531, 0.002795,    1e-05, 0.019786, 0.010435, 0.002743, 0.023617, 0.010436, 0.003116],
 [0.003408, 0.010531, 0.002795,    1e-05, 0.019786, 0.010435, 0.002743, 0.023617, 0.010436, 0.003116],
 [0.003408, 0.010531, 0.002795,    1e-05, 0.019786, 0.010435, 0.002743, 0.023617, 0.010436, 0.003116],
 [0.003408, 0.010531, 0.002795,    1e-05, 0.019786, 0.010435, 0.002743, 0.023617, 0.010436, 0.003116],
 [0.003408, 0.010531, 0.002795,    1e-05, 0.019786, 0.010435, 0.002743, 0.023617, 0.010436, 0.003116],
 [0.003408, 0.010531, 0.002795,    1e-05, 0.019786, 0.010435, 0.002743, 0.023617, 0.010436, 0.003116],
 [0.003408, 0.010531, 0.002795,    1e-05, 0.019786, 0.010435, 0.002743, 0.023617, 0.010436, 0.003116],
 [0.003408, 0.010531, 0.002795,    1e-05, 0.019786, 0.010435, 0.002743, 0.023617, 0.010436, 0.003116]])
     
        p = 1e6
        W = np.round(W * p) / p
        M, c_0, c_1 = tf.user_ops.hungarian(W)
        with tf.Session() as sess:
            M = M.eval()

        print M
        
        pass


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(HungarianTests)
    # suite = unittest.TestSuite()
    # suite.addTest(HungarianTests('test_real_values'))
    unittest.TextTestRunner(verbosity=2).run(suite)
