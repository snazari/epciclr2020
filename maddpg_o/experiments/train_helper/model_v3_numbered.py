import tensorflow as tf
import math

FULLY_CONNECTED = tf.contrib.layers.fully_connected


def register_fc(fully_connected):
    global FULLY_CONNECTED
    FULLY_CONNECTED = fully_connected


def mlp_model_agent_p_numbered(input, num_outputs, scope, index, n_adv=2, n_good=5, n_land=6, num_units=64, with_action=False,
                      share_weights=False, reuse=None):
    # This model takes as input an observation and returns values of all actions
    if reuse is None:
        reuse = (tf.AUTO_REUSE if share_weights else False)
    with tf.variable_scope(scope, reuse=reuse):
        num_test = num_units // 2
        batch_size = input.shape[0].value
        self_land = input[:, 5:5 + 3 * n_land]

        if with_action:
            self_action = input[:, -5:]
        else:
            self_action = None

        # self mlp
        self_dim = 5 + 3 * n_land
        self_in = input[:, :5]
        if with_action:
            self_in = tf.concat([self_in, self_action], axis=1)
        with tf.variable_scope("self", reuse=reuse):
            self_out = FULLY_CONNECTED(
                self_in, num_outputs=num_units, scope='l1', activation_fn=tf.nn.relu)
            self_out = FULLY_CONNECTED(
                self_out, num_outputs=num_test, scope='l2', activation_fn=tf.nn.relu)
        # land mark mlp
        land_mark_input = input[:, 5:5 + 3 * n_land]
        land_outs = []
        for i in range(n_land):
            with tf.variable_scope("landmark", reuse=reuse):
                fc1_out = FULLY_CONNECTED(
                    land_mark_input[:, i * 3:(i + 1) * 3], num_outputs=num_units, scope='l1', activation_fn=tf.nn.relu)
                land_outs.append(FULLY_CONNECTED(
                    fc1_out, num_outputs=num_test, scope='l2', activation_fn=tf.nn.relu))
        land_out = tf.stack(land_outs, 2)
        land_out_attn = tf.nn.softmax(tf.matmul(tf.expand_dims(self_out, 1), land_out) / math.sqrt(num_test))
        land_out = tf.squeeze(tf.matmul(land_out_attn, tf.transpose(land_out, [0, 2, 1])), 1)
        land_out = tf.contrib.layers.layer_norm(land_out)
        land_out = tf.nn.relu(land_out)

        # sheep mlp
        if n_good != 1:
            other_good_dim = (2 + 2 + 1) * (n_good - 1)
            other_good_in = input[:, self_dim:]
            other_good_ins = []
            for i in range(n_good - 1):
                pos = other_good_in[:, 2 * n_adv + i * 2:2 * n_adv + (i + 1) * 2]
                vel = other_good_in[:,
                      2 * n_adv + 2 * (n_good - 1) + 2 * n_adv + i * 2:2 * n_adv + 2 * (n_good - 1) + 2 * n_adv + (
                                  i + 1) * 2]
                is_live = other_good_in[:, 5 * n_adv + 4 * (n_good - 1) + i:5 * n_adv + 4 * (n_good - 1) + i + 1]
                if with_action:
                    tmp = tf.concat([pos, vel, is_live], axis=1)
                else:
                    tmp = tf.concat([pos, vel, is_live], axis=1)
                other_good_ins.append(tmp)
            other_good_outs = []

            for i in range(n_good - 1):
                true_id = i if i < index - n_adv else i + 1
                with tf.variable_scope("good{}".format('0' if share_weights else true_id), reuse=reuse):
                    fc1_good = FULLY_CONNECTED(
                        other_good_ins[i], num_outputs=num_units, activation_fn=tf.nn.relu, scope="l1", reuse=reuse)
                    other_good_outs.append(FULLY_CONNECTED(
                        fc1_good, num_outputs=num_test, activation_fn=tf.nn.relu, scope="l2", reuse=reuse))
            other_good_out = tf.stack(other_good_outs, 2)
            # other_good_out = tf.reduce_mean(tf.stack(other_good_outs, 2), 2)
            # other_good_out = tf.concat([i for i in other_good_outs],1)

            other_good_out_attn = tf.nn.softmax(
                tf.matmul(tf.expand_dims(self_out, 1), other_good_out) / math.sqrt(num_test))
            # print("attn:", other_good_out_attn)
            other_good_out = tf.squeeze(tf.matmul(other_good_out_attn, tf.transpose(other_good_out, [0, 2, 1])), 1)
            other_good_out = tf.contrib.layers.layer_norm(other_good_out)
            other_good_out = tf.nn.relu(other_good_out)

        # wolf_mlp
        other_adv_dim = 5 * (n_adv)
        other_adv_beg = self_dim
        other_adv_in = input[:, other_adv_beg:]

        other_adv_ins = []
        for i in range(n_adv):
            pos = other_adv_in[:, i * 2:(i + 1) * 2]
            vel = other_adv_in[:, 2 * n_adv + 2 * (n_good - 1) + i * 2:2 * n_adv + 2 * (n_good - 1) + (i + 1) * 2]
            is_live = other_adv_in[:, 4 * n_adv + 4 * (n_good - 1) + i:4 * n_adv + 4 * (n_good - 1) + i + 1]
            if not with_action:
                tmp = tf.concat([pos, vel, is_live], axis=1)
            else:
                tmp = tf.concat([pos, vel, is_live], axis=1)
            other_adv_ins.append(tmp)

        other_adv_outs = []
        for i in range(n_adv):
            with tf.variable_scope("adv{}".format('0' if share_weights else i), reuse=reuse):
                fc1_adv = FULLY_CONNECTED(
                    other_adv_ins[i], num_outputs=num_units, activation_fn=tf.nn.relu, scope="l1", reuse=reuse)
                other_adv_outs.append(FULLY_CONNECTED(
                    fc1_adv, num_outputs=num_test, activation_fn=tf.nn.relu, scope="l2", reuse=reuse))
        if (n_adv > 0):
            other_adv_out = tf.stack(other_adv_outs, 2)
            other_adv_out_attn = tf.nn.softmax(
                tf.matmul(tf.expand_dims(self_out, 1), other_adv_out) / math.sqrt(num_test))
            other_adv_out = tf.squeeze(tf.matmul(other_adv_out_attn, tf.transpose(other_adv_out, [0, 2, 1])), 1)
            other_adv_out = tf.contrib.layers.layer_norm(other_adv_out)
            other_adv_out = tf.nn.relu(other_adv_out)
        else:
            other_adv_out = None

        # other_adv_out = tf.concat([i for i in other_adv_outs],1)

        # merge layer for all
        if n_good == 1:
            input_merge = tf.concat([self_out, land_out, other_adv_out], 1)
        elif (n_adv <= 0):
            input_merge = tf.concat([self_out, land_out, other_good_out], 1)
        else:
            input_merge = tf.concat([self_out, land_out, other_good_out, other_adv_out], 1)
        out = FULLY_CONNECTED(input_merge, num_outputs=num_units, scope='last_1',
                              activation_fn=tf.nn.relu if with_action else tf.nn.leaky_relu)
        out = FULLY_CONNECTED(out, num_outputs=num_units, scope='last_11',
                              activation_fn=tf.nn.relu if with_action else tf.nn.leaky_relu)
        out = FULLY_CONNECTED(out, num_outputs=num_outputs, scope='last_2', activation_fn=None)

        return out


def mlp_model_adv_p_numbered(input, num_outputs, scope, index, n_adv=2, n_good=5, n_land=6, num_units=64, with_action=False,
                    share_weights=False, reuse=None):
    # This model takes as input an observation and returns values of all actions
    if reuse is None:
        reuse = tf.AUTO_REUSE if share_weights else False
    with tf.variable_scope(scope, reuse=reuse):
        # self input mlp
        num_test = num_units // 2
        batch_size = input.shape[0].value
        self_dim = 5 + 3 * n_land
        self_land = input[:, 5:5 + 3 * n_land]

        if with_action:
            self_action = input[:, -5:]
        else:
            self_action = None

        self_in = input[:, :5]
        if with_action:
            self_in = tf.concat([self_in, self_action], axis=1)
        with tf.variable_scope("self", reuse=reuse):
            self_out = FULLY_CONNECTED(
                self_in, num_outputs=num_units, scope='l1', activation_fn=tf.nn.relu)
            # print("GOT")
            self_out = FULLY_CONNECTED(
                self_out, num_outputs=num_test, scope='l2', activation_fn=tf.nn.relu)
            # print("GOT2")

        # land mark mlp
        land_mark_input = input[:, 5:5 + 3 * n_land]
        land_info = []
        land_outs = []
        for i in range(n_land):
            with tf.variable_scope("landmark", reuse=reuse):
                fc1_out = FULLY_CONNECTED(
                    land_mark_input[:, i * 3:(i + 1) * 3], num_outputs=num_units, scope='l1', activation_fn=tf.nn.relu)
                land_outs.append(FULLY_CONNECTED(
                    fc1_out, num_outputs=num_test, scope='l2', activation_fn=tf.nn.relu))
        land_out = tf.stack(land_outs, 2)
        land_out_attn = tf.nn.softmax(tf.matmul(tf.expand_dims(self_out, 1), land_out) / math.sqrt(num_test))
        land_out = tf.squeeze(tf.matmul(land_out_attn, tf.transpose(land_out, [0, 2, 1])), 1)
        land_out = tf.contrib.layers.layer_norm(land_out)
        land_out = tf.nn.relu(land_out)

        # other sheep mlp
        other_good_in = input[:, self_dim:]
        other_good_ins = []
        for i in range(n_good):
            pos = other_good_in[:, 2 * (n_adv - 1) + i * 2:2 * (n_adv - 1) + (i + 1) * 2]
            vel = other_good_in[:, 4 * (n_adv - 1) + 2 * n_good + i * 2:4 * (n_adv - 1) + 2 * n_good + (i + 1) * 2]
            is_live = other_good_in[:, 5 * (n_adv - 1) + 4 * n_good + i:5 * (n_adv - 1) + 4 * n_good + i + 1]
            if with_action:
                tmp = tf.concat([pos, vel, is_live], axis=1)
            else:
                tmp = tf.concat([pos, vel, is_live], axis=1)
            other_good_ins.append(tmp)

        other_good_outs = []

        for i in range(n_good):
            with tf.variable_scope("good{}".format('0' if share_weights else i), reuse=reuse):
                # print(num_units)
                # print(other_good_ins[i])
                fc1_good = FULLY_CONNECTED(
                    other_good_ins[i], num_outputs=num_units, activation_fn=tf.nn.relu, scope="l1", reuse=reuse)
                other_good_outs.append(FULLY_CONNECTED(
                    fc1_good, num_outputs=num_test, activation_fn=tf.nn.relu, scope="l2", reuse=reuse))
        # other_good_out = tf.reduce_mean(tf.stack(other_good_outs, 2), 2)

        other_good_out = tf.stack(other_good_outs, 2)
        other_good_out_attn = tf.nn.softmax(
            tf.matmul(tf.expand_dims(self_out, 1), other_good_out) / math.sqrt(num_test))
        other_good_out = tf.squeeze(tf.matmul(other_good_out_attn, tf.transpose(other_good_out, [0, 2, 1])), 1)
        other_good_out = tf.contrib.layers.layer_norm(other_good_out)
        other_good_out = tf.nn.relu(other_good_out)

        # other_good_out = tf.concat([i for i in other_good_outs],1)

        # other wolf mlp
        if n_adv == 1:
            input_merge = tf.concat([self_out, other_good_out], 1)
            out = FULLY_CONNECTED(input_merge, num_outputs=num_units, activation_fn=tf.nn.relu)
            out = FULLY_CONNECTED(out, num_outputs=num_outputs, activation_fn=None)
            return out

        other_adv_beg = self_dim
        other_adv_in = input[:, self_dim:]

        other_adv_ins = []
        for i in range(n_adv - 1):
            pos = other_adv_in[:, i * 2:(i + 1) * 2]
            vel = other_adv_in[:, 2 * (n_adv - 1) + 2 * n_good + i * 2:2 * (n_adv - 1) + 2 * n_good + (i + 1) * 2]
            is_live = other_adv_in[:, 4 * (n_adv - 1) + 4 * n_good + i:4 * (n_adv - 1) + 4 * n_good + i + 1]
            if not with_action:
                tmp = tf.concat([pos, vel, is_live], axis=1)
            else:
                tmp = tf.concat([pos, vel, is_live], axis=1)
            other_adv_ins.append(tmp)

        other_adv_outs = []
        for i in range(n_adv - 1):
            true_id = i if i < index else i + 1
            with tf.variable_scope("adv{}".format('0' if share_weights else true_id), reuse=reuse):
                fc1_adv = FULLY_CONNECTED(
                    other_adv_ins[i], num_outputs=num_units, activation_fn=tf.nn.relu, scope="l1", reuse=reuse)
                other_adv_outs.append(FULLY_CONNECTED(
                    fc1_adv, num_outputs=num_test, activation_fn=tf.nn.relu, scope="l2", reuse=reuse))
            # other_adv_out = tf.reduce_mean(tf.stack(other_adv_outs, 2), 2)

            other_adv_out = tf.stack(other_adv_outs, 2)
        if (n_adv > 0):

            other_adv_out_attn = tf.nn.softmax(
                tf.matmul(tf.expand_dims(self_out, 1), other_adv_out) / math.sqrt(num_test))
            other_adv_out = tf.squeeze(tf.matmul(other_adv_out_attn, tf.transpose(other_adv_out, [0, 2, 1])), 1)
            other_adv_out = tf.contrib.layers.layer_norm(other_adv_out)
            other_adv_out = tf.nn.relu(other_adv_out)
        else:
            other_adv_out = None

        # other_adv_out = tf.concat([i for i in other_adv_outs],1)

        # merge layer for all
        if (n_adv <= 0):
            input_merge = tf.concat([self_out, land_out, other_good_out], 1)
        else:
            input_merge = tf.concat([self_out, land_out, other_good_out, other_adv_out], 1)

        out = FULLY_CONNECTED(input_merge, num_outputs=num_units, scope='last_1',
                              activation_fn=tf.nn.relu if with_action else tf.nn.leaky_relu)
        # out = FULLY_CONNECTED(out, num_outputs=num_units, scope='last_11', activation_fn=tf.nn.leaky_relu)
        out = FULLY_CONNECTED(out, num_outputs=num_outputs, scope='last_2', activation_fn=None)
        return out


def mlp_model_agent_q_numbered(input, num_outputs, scope, index, n_adv=3, n_good=5, n_land=6, num_units=64, share_weights=False,
                      reuse=None):
    if reuse is None:
        reuse = tf.AUTO_REUSE if share_weights else False
    # This model takes as input an observation and returns values of all actions
    with tf.variable_scope(scope, reuse=reuse):
        basic = 0
        shorton = 1
        # split actions
        num_test = num_units // 2

        batch_size = input.shape[0].value
        input_action = input[:, -5 * (n_adv + n_good):]
        self_action = input_action[:, index * 5: (index + 1) * 5]
        good_action = input_action[:, n_adv * 5:]
        other_good_action = tf.concat([input_action[:, 5 * n_adv:5 * index], input_action[:, 5 * (index + 1):]], 1)
        other_adv_action = input_action[:, :n_adv * 5]

        # split self obs
        length_wolf = (n_land) * 3 + (n_good + n_adv) * 5
        length_sheep = length_wolf
        self_start = n_adv * length_wolf + (index - n_adv) * length_sheep

        self_dim = length_sheep

        # self mlp

        input_obs_self = input[:, self_start:self_start + length_sheep]
        self_in = input_obs_self
        self_in = tf.concat([self_in, self_action], 1)
        with tf.variable_scope("self", reuse=reuse):
            self_out = mlp_model_agent_p_numbered(self_in, num_test, 'mlp', index, n_adv=n_adv, n_good=n_good, n_land=n_land,
                                         share_weights=share_weights, num_units=num_units, with_action=True,
                                         reuse=reuse)

        # sheep mlp
        if n_good != 1:
            other_good_ins = []
            for i in range(n_good):
                if i == index - n_adv:
                    continue
                other_good_beg = n_adv * length_wolf + i * length_sheep
                other_good_in = input[:, other_good_beg:other_good_beg + length_sheep]
                tmp = tf.concat([other_good_in, good_action[:, i * 5:(i + 1) * 5]], 1)
                other_good_ins.append(tmp)
            other_good_outs = []

            if basic:
                other_good_out = tf.concat([i for i in other_good_ins], 1)
            else:
                for i in range(n_good - 1):
                    true_id = i if i < index - n_adv else i + 1
                    with tf.variable_scope("good{}".format('0' if share_weights else true_id), reuse=reuse):
                        out = mlp_model_agent_p_numbered(other_good_ins[i], num_test, 'mlp', true_id + n_adv, n_adv=n_adv,
                                                n_good=n_good, n_land=n_land, share_weights=share_weights,
                                                num_units=num_units,
                                                with_action=True, reuse=reuse)
                        other_good_outs.append(out)
        else:
            other_good_outs = []

        # wolf_mlp
        other_adv_ins = []
        for i in range(n_adv):
            other_adv_beg = length_wolf * i
            other_adv_in = input[:, other_adv_beg:other_adv_beg + length_wolf]
            tmp = tf.concat([other_adv_in, other_adv_action[:, i * 5:(i + 1) * 5]], 1)
            other_adv_ins.append(tmp)

        other_adv_outs = []
        if basic:
            other_adv_out = tf.concat([i for i in other_adv_ins], 1)
        else:
            for i in range(n_adv):
                with tf.variable_scope("adv{}".format('0' if share_weights else i), reuse=reuse):
                    out = mlp_model_adv_p_numbered(other_adv_ins[i], num_test, 'mlp', i, n_adv=n_adv, n_good=n_good,
                                          n_land=n_land, reuse=reuse, num_units=num_units, with_action=True,
                                          share_weights=share_weights)
                    other_adv_outs.append(out)

        theta_out = []
        phi_out = []
        g_out = []

        theta_out.append(
            FULLY_CONNECTED(self_out, num_outputs=num_test, scope='theta_f', reuse=tf.AUTO_REUSE, activation_fn=None))
        phi_out.append(
            FULLY_CONNECTED(self_out, num_outputs=num_test, scope='phi_f', reuse=tf.AUTO_REUSE, activation_fn=None))
        g_out.append(
            FULLY_CONNECTED(self_out, num_outputs=num_test, scope='g_f', reuse=tf.AUTO_REUSE, activation_fn=None))
        for i, out in enumerate(other_good_outs):
            theta_out.append(
                FULLY_CONNECTED(out, num_outputs=num_test, scope='theta_f', reuse=tf.AUTO_REUSE, activation_fn=None))
            phi_out.append(
                FULLY_CONNECTED(out, num_outputs=num_test, scope='phi_f', reuse=tf.AUTO_REUSE, activation_fn=None))
            g_out.append(
                FULLY_CONNECTED(out, num_outputs=num_test, scope='g_f', reuse=tf.AUTO_REUSE, activation_fn=None))
        for i, out in enumerate(other_adv_outs):
            theta_out.append(
                FULLY_CONNECTED(out, num_outputs=num_test, scope='theta_f', reuse=tf.AUTO_REUSE, activation_fn=None))
            phi_out.append(
                FULLY_CONNECTED(out, num_outputs=num_test, scope='phi_f', reuse=tf.AUTO_REUSE, activation_fn=None))
            g_out.append(
                FULLY_CONNECTED(out, num_outputs=num_test, scope='g_f', reuse=tf.AUTO_REUSE, activation_fn=None))

        theta_outs = tf.stack(theta_out, 2)
        # print(theta_outs.get_shape(),'theta_outs')
        # print(theta_out[0].get_shape(),'theta')
        phi_outs = tf.stack(phi_out, 2)
        g_outs = tf.stack(g_out, 2)
        self_attention = tf.nn.softmax(tf.matmul(theta_outs, tf.transpose(phi_outs, [0, 2, 1])) / math.sqrt(num_test))
        # print(self_attention.get_shape(),'self_attention')
        input_all = tf.matmul(self_attention, g_outs)
        input_all_new = []
        for i in range(n_adv + n_good):
            input_all_new.append(
                tf.contrib.layers.layer_norm(input_all[:, :, i], scope='qlayernorm1', reuse=tf.AUTO_REUSE))
        input_all = tf.stack(input_all_new, 2)
        # input_all = tf.contrib.layers.layer_norm(input_all)
        input_all = tf.nn.relu(input_all)

        self_out_new = input_all[:, :, 0]
        good_out_new = input_all[:, :, 1:n_good]
        adv_out_new = input_all[:, :, n_good:]
        if (n_adv > 0):
            other_adv_out_attn = tf.nn.softmax(
                tf.matmul(tf.expand_dims(self_out_new, 1), adv_out_new) / math.sqrt(num_test))
            other_adv_out = tf.squeeze(tf.matmul(other_adv_out_attn, tf.transpose(adv_out_new, [0, 2, 1])), 1)
            other_adv_out = tf.contrib.layers.layer_norm(other_adv_out)
            other_adv_out = tf.nn.relu(other_adv_out)

        other_good_out_attn = tf.nn.softmax(
            tf.matmul(tf.expand_dims(self_out_new, 1), good_out_new) / math.sqrt(num_test))
        other_good_out = tf.squeeze(tf.matmul(other_good_out_attn, tf.transpose(good_out_new, [0, 2, 1])), 1)
        other_good_out = tf.contrib.layers.layer_norm(other_good_out)
        other_good_out = tf.nn.relu(other_good_out)
        # merge layer for all
        if n_good == 1:
            input_merge = tf.concat([self_out, other_adv_out], 1)
        elif (n_adv <= 0):
            input_merge = tf.concat([self_out, other_good_out], 1)
        else:
            input_merge = tf.concat([self_out, other_good_out, other_adv_out], 1)

        out = FULLY_CONNECTED(input_merge, num_outputs=num_units, scope='last_1', activation_fn=tf.nn.leaky_relu)
        out = FULLY_CONNECTED(out, num_outputs=num_units, scope='last_11', activation_fn=tf.nn.leaky_relu)
        out = FULLY_CONNECTED(out, num_outputs=num_outputs, scope='last_2', activation_fn=None)

        # print("mlp_model_agent_q",
        #       len(tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope=tf.get_variable_scope().name)))

        return out


def mlp_model_adv_q_numbered(input, num_outputs, scope, index, n_adv=3, n_good=5, n_land=6, share_weights=False, num_units=64,
                    reuse=None):
    if reuse is None:
        reuse = tf.AUTO_REUSE if share_weights else False
    # This model takes as input an observation and returns values of all actions
    with tf.variable_scope(scope, reuse=reuse):
        # split actions
        basic = 0
        self_dim = n_land * 3 + 5
        shorton = 1
        num_test = num_units // 2
        input_action = input[:, -5 * (n_adv + n_good):]
        self_action = input_action[:, index * 5: (index + 1) * 5]
        other_good_action = input_action[:, 5 * n_adv:]
        adv_action = input_action[:, :5 * n_adv]
        other_adv_action = tf.concat([input_action[:, :5 * index], input_action[:, 5 * (index + 1):5 * n_adv]], 1)

        # split self obs
        length_wolf = (n_land) * 3 + (n_good + n_adv) * 5
        length_sheep = length_wolf

        ## self input mlp
        self_start = index * length_wolf
        input_obs_self = input[:, self_start:self_start + length_wolf]
        batch_size = input.shape[0].value
        self_in = tf.concat([input_obs_self, self_action], 1)
        with tf.variable_scope("self", reuse=reuse):
            self_out = mlp_model_adv_p_numbered(self_in, num_test, 'mlp', index, n_adv=n_adv, n_good=n_good, n_land=n_land,
                                       share_weights=share_weights, num_units=num_units, with_action=True, reuse=reuse)

        # other sheep mlp
        other_good_ins = []
        for i in range(n_good):
            other_good_beg = n_adv * length_wolf + i * length_sheep
            other_good_in = input[:, other_good_beg:other_good_beg + length_sheep]
            tmp = tf.concat([other_good_in, other_good_action[:, i * 5:(i + 1) * 5]], axis=1)
            other_good_ins.append(tmp)

        other_good_outs = []
        if basic:
            other_good_out = tf.concat([i for i in other_good_ins], 1)
        else:
            for i in range(n_good):
                with tf.variable_scope("good{}".format('0' if share_weights else i), reuse=reuse):
                    out = mlp_model_agent_p_numbered(other_good_ins[i], num_test, 'mlp', i + n_adv, n_adv=n_adv, n_good=n_good,
                                            n_land=n_land, share_weights=share_weights, num_units=num_units,
                                            with_action=True, reuse=reuse)
                    other_good_outs.append(out)

        if n_adv != 1:

            other_adv_ins = []
            for i in range(n_adv):
                if i == index:
                    continue
                other_adv_beg = length_wolf * i
                other_adv_in = input[:, other_adv_beg:other_adv_beg + length_wolf]
                tmp = tf.concat([other_adv_in, adv_action[:, i * 5:(i + 1) * 5]], 1)
                other_adv_ins.append(tmp)

            other_adv_outs = []
            if basic:
                other_adv_out = tf.concat([i for i in other_adv_ins], 1)
            else:
                for i in range(n_adv - 1):
                    true_id = i if i < index else i + 1
                    with tf.variable_scope("adv{}".format('0' if share_weights else true_id), reuse=reuse):
                        out = mlp_model_adv_p_numbered(other_adv_ins[i], num_test, 'mlp', true_id, n_adv=n_adv, n_good=n_good,
                                              n_land=n_land, share_weights=share_weights, num_units=num_units,
                                              with_action=True, reuse=reuse)
                        other_adv_outs.append(out)
        else:
            other_adv_outs = []

        theta_out = []
        phi_out = []
        g_out = []

        theta_out.append(
            FULLY_CONNECTED(self_out, num_outputs=num_test, scope='theta_f', reuse=tf.AUTO_REUSE, activation_fn=None))
        phi_out.append(
            FULLY_CONNECTED(self_out, num_outputs=num_test, scope='phi_f', reuse=tf.AUTO_REUSE, activation_fn=None))
        g_out.append(
            FULLY_CONNECTED(self_out, num_outputs=num_test, scope='g_f', reuse=tf.AUTO_REUSE, activation_fn=None))
        for i, out in enumerate(other_good_outs):
            theta_out.append(
                FULLY_CONNECTED(out, num_outputs=num_test, scope='theta_f', reuse=tf.AUTO_REUSE, activation_fn=None))
            phi_out.append(
                FULLY_CONNECTED(out, num_outputs=num_test, scope='phi_f', reuse=tf.AUTO_REUSE, activation_fn=None))
            g_out.append(
                FULLY_CONNECTED(out, num_outputs=num_test, scope='g_f', reuse=tf.AUTO_REUSE, activation_fn=None))
        for i, out in enumerate(other_adv_outs):
            theta_out.append(
                FULLY_CONNECTED(out, num_outputs=num_test, scope='theta_f', reuse=tf.AUTO_REUSE, activation_fn=None))
            phi_out.append(
                FULLY_CONNECTED(out, num_outputs=num_test, scope='phi_f', reuse=tf.AUTO_REUSE, activation_fn=None))
            g_out.append(
                FULLY_CONNECTED(out, num_outputs=num_test, scope='g_f', reuse=tf.AUTO_REUSE, activation_fn=None))

        theta_outs = tf.stack(theta_out, 2)
        # print(theta_outs.get_shape(),'theta_outs')
        # print(theta_out[0].get_shape(),'theta')
        phi_outs = tf.stack(phi_out, 2)
        g_outs = tf.stack(g_out, 2)
        self_attention = tf.nn.softmax(tf.matmul(theta_outs, tf.transpose(phi_outs, [0, 2, 1])) / math.sqrt(num_test))
        # print(self_attention.get_shape(),'self_attention')
        input_all = tf.matmul(self_attention, g_outs)
        input_all_new = []
        for i in range(n_adv + n_good):
            input_all_new.append(
                tf.contrib.layers.layer_norm(input_all[:, :, i], scope='qlayernorm1', reuse=tf.AUTO_REUSE))
        input_all = tf.stack(input_all_new, 2)
        '''
        input_all = tf.contrib.layers.layer_norm(input_all)
        '''
        # input_all_new2 = tf.stack(input_all_new1, 2)
        input_all = tf.nn.relu(input_all)

        self_out_new = input_all[:, :, 0]
        good_out_new = input_all[:, :, 1:1 + n_good]
        adv_out_new = input_all[:, :, 1 + n_good:]

        if (n_adv > 0):
            other_adv_out_attn = tf.nn.softmax(
                tf.matmul(tf.expand_dims(self_out_new, 1), adv_out_new) / math.sqrt(num_test))
            other_adv_out = tf.squeeze(tf.matmul(other_adv_out_attn, tf.transpose(adv_out_new, [0, 2, 1])), 1)
            other_adv_out = tf.contrib.layers.layer_norm(other_adv_out)
            other_adv_out = tf.nn.relu(other_adv_out)

        other_good_out_attn = tf.nn.softmax(
            tf.matmul(tf.expand_dims(self_out_new, 1), good_out_new) / math.sqrt(num_test))
        other_good_out = tf.squeeze(tf.matmul(other_good_out_attn, tf.transpose(good_out_new, [0, 2, 1])), 1)
        other_good_out = tf.contrib.layers.layer_norm(other_good_out)
        other_good_out = tf.nn.relu(other_good_out)

        # merge layer for all

        if n_adv == 1:
            input_merge = tf.concat([self_out, other_good_out], 1)
        elif n_adv <= 0:
            input_merge = tf.concat([self_out, other_good_out], 1)
        else:
            input_merge = tf.concat([self_out, other_good_out, other_adv_out], 1)

        out = FULLY_CONNECTED(input_merge, num_outputs=num_units, scope='last_1', activation_fn=tf.nn.leaky_relu)
        out = FULLY_CONNECTED(out, num_outputs=num_units, scope='last_11', activation_fn=tf.nn.leaky_relu)
        out = FULLY_CONNECTED(out, num_outputs=num_outputs, scope='last_2', activation_fn=None)

        # print("mlp_model_adv_q",
        #       len(tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope=tf.get_variable_scope().name)))

        return out
