import tensorflow as tf
import skimage.io as io
import numpy as np
import random
import argparse
import pandas as pd
from weighted_unet import UNet
from sklearn.metrics import recall_score
from sklearn.metrics import precision_score

DIM = 128

def record_parser(record):
    keys_to_features = {
            'ddat': tf.FixedLenFeature([],tf.string),
            'm'   : tf.FixedLenFeature([],tf.int64),
            'n'   : tf.FixedLenFeature([],tf.int64)}

    parsed = tf.parse_single_example(record, keys_to_features)

    m    = tf.cast(parsed['m'],tf.int64)
    n    = tf.cast(parsed['n'],tf.int64)

    ddat_shape = tf.stack([101,m,n])

    ddat = tf.decode_raw(parsed['ddat'],tf.float32)
    ddat = tf.reshape(ddat,ddat_shape)
    ddat = tf.random_crop(ddat,[101,128,128])

    k  = np.random.randint(100)

    data = tf.slice(ddat,[k,0,0],[1,128,128])
    data = tf.reshape(data,[1,128,128,1])

    labl = tf.slice(ddat,[99,0,0],[1,128,128])
    labl = tf.reshape(labl,[1,128,128,1])

    return (data,labl,m,n)

def test_record_parser(record):
    keys_to_features = {
            'name': tf.FixedLenFeature([],tf.string),
            'ddat': tf.FixedLenFeature([],tf.string),
            'm'   : tf.FixedLenFeature([],tf.int64),
            'n'   : tf.FixedLenFeature([],tf.int64)}

    parsed = tf.parse_single_example(record, keys_to_features)

    m    = tf.cast(parsed['m'],tf.int64)
    n    = tf.cast(parsed['n'],tf.int64)

    ddat_shape = tf.stack([100,m,n])

    ddat = tf.decode_raw(parsed['ddat'],tf.float32)
    ddat = tf.reshape(ddat,ddat_shape)

    return (parsed['name'],ddat,m,n)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description = "Data Maker",
        epilog = "Use this program to randomly split the training data for p4 into random sub-samples.",
        add_help = "How to use",
        prog = "python trainer.py -i <path_to_TFRecordFile> [OPTIONAL ARGUMENTS]" )

    parser.add_argument("-t", "--tid",
        help = "The path to find the .tfrecord file for the training set")

    parser.add_argument("-v", "--vid",
        help = "The path to find the .tfrecord file for the validation set")

    parser.add_argument("-z", "--tsid",
        help = "The path to find the .tfrecord file for the test set")

    parser.add_argument("-e", "--epochs", type = int, default = 3000,
        help = "The number of epochs to run the training for.")

    parser.add_argument("-l", "--lr", type = float, default = 0.0001,
        help = "Learning rate hyperparameter; default is 0.0001.")

    parser.add_argument("-o", "--opt", type = str, default = 'RMSProp',
        choices = ['RMSProp','SGD', 'Adam', 'Adagrad', 'Momentum', 'Ftrl'],
        help = "Optimizer hyperparameter; default is RMSProp.")

    parser.add_argument("-w", "--weight", type = float, default = 1.,
        help = "Weighting of positives relative to negatives in loss; default is 1.")

    parser.add_argument("-x", "--training", action = "store_false",
        help = "Flag to indicate that this is to produce test results.")

    parser.add_argument("-r", "--reload",
        help = "Path frm which to reload the UNET weights. NOTE: Should only be used in conjunction with the '-x' flag.")

    parser.add_argument("-s", "--save_path",
        help = "Path to save the results of a test session to. NOTE: Should only be used in conjunction with the '-x' flag.")

    name = "p4"

    args = vars(parser.parse_args())

    train_filename      = args['tid']
    validation_filename = args['vid']
    test_filename       = args['tsid']
    save_path           = args['save_path']
    reload_path         = args['reload']
    epochs              = args['epochs']
    lr                  = args['lr']
    opt                 = args['opt']
    weight              = args['weight']
    training            = args['training']
    
    if training:
        chk_path = "../data/Nick/checkpoints/"
        res_path = "../data/Nick/results/"
        csv_path = "../data/Nick/model_stats.csv"


        # for saving model statistics:
        try:
            stats_df = pd.read_csv(models_csv_path)
        except:
            stats_df = pd.DataFrame(columns=["model_name","epochs","dice","loss","precision","recall"])

        sess = tf.Session()

        train_dataset = tf.data.TFRecordDataset([train_filename])
        train_dataset = train_dataset.map(record_parser)

        validation_dataset = tf.data.TFRecordDataset([validation_filename])
        validation_dataset = validation_dataset.map(record_parser)

        iterator = tf.data.Iterator.from_structure(train_dataset.output_types,train_dataset.output_shapes)
        next_element = iterator.get_next()

        train_init_op = iterator.make_initializer(train_dataset)
        validation_init_op = iterator.make_initializer(validation_dataset)

        model = UNet(128, is_training=True,k=1)
        train_op = model.train(lr, opt, weight)

        tf_writer = tf.summary.FileWriter(logdir='./')
        config = tf.ConfigProto()

        sess.run(tf.global_variables_initializer())
        saver = tf.train.Saver()
        avg_dice_score = 0.0
        avg_loss =0.0
        best_dice_score = 0.0
        best_loss = 0.0
        best_precision = 0.0
        best_recall = 0.0
        sum_dice_score = 0.0
        sum_loss = 0.0
        sum_precision = 0.0
        iters = 0 if (len(stats_df.index)==1) else len(stats_df.index)
        count = 0
        for i in range(epochs):
            sess.run(train_init_op)
            while True:
                try:
                    val = sess.run(next_element)
                    data,labl,m,n = val
                    _, loss_np, gs_np, dice_acc_np, summary_np ,flat_output_mask = sess.run(
                            [train_op, model.loss, model.gs, model.dice_acc, model.merged_summary,model.flat_output_mask],
                            feed_dict={model.input: data, model.gt_mask: labl}
                        )
                    recall = 0#recall_score(labl.reshape(DIM*DIM), np.round(flat_output_mask), average='macro',labels=[0,1])
                    precision = 0#precision_score(labl.reshape(DIM*DIM), np.round(flat_output_mask), average='macro',labels=[0,1])
                    sum_dice_score = sum_dice_score + dice_acc_np
                    sum_loss       = sum_loss + loss_np
                    sum_recall     = 0#sum_recall + recall
                    sum_precision  = sum_precision + precision
                    ratio_predicted = np.count_nonzero(np.round(flat_output_mask)/flat_output_mask.shape[0]/(DIM*DIM))
                    ratio_actual = np.count_nonzero(np.round(labl)/labl[0]/(DIM*DIM))
                    mismatch = float(ratio_predicted/ratio_actual)
                    count = count + 1
                except tf.errors.OutOfRangeError:
                    break
            sess.run(validation_init_op)
            while True:
                try:
                    val = sess.run(next_element)
                    data,labl,m,n = val
                    _, loss_np, gs_np, dice_acc_np, summary_np ,flat_output_mask = sess.run(
                        [train_op, model.loss, model.gs, model.dice_acc, model.merged_summary,model.flat_output_mask],
                        feed_dict={model.input: data, model.gt_mask: labl}
                    )
                    recall = 0#recall_score(labl.reshape(DIM*DIM), np.round(flat_output_mask), average='macro',labels=[0,1])
                    precision = 0#precision_score(labl.reshape(DIM*DIM), np.round(flat_output_mask), average='macro',labels=[0,1])
                    sum_dice_score = sum_dice_score + dice_acc_np
                    sum_loss       = sum_loss + loss_np
                    sum_recall     = 0#sum_recall + recall
                    sum_precision  = sum_precision + precision
                    ratio_predicted = np.count_nonzero(np.round(flat_output_mask)/flat_output_mask.shape[0]/(DIM*DIM))
                    ratio_actual = np.count_nonzero(np.round(labl)/labl[0]/(DIM*DIM))
                    mismatch = float(ratio_predicted/ratio_actual)
                    count = count + 1
                except tf.errors.OutOfRangeError:
                    break
            if i%500==0:
                    stats_df = stats_df.append({
                            "model_name": name,
                            "epochs": i,
                            "dice": sum_dice_score/count,
                            "loss": sum_loss/count,
                            "precision": sum_recall/count,
                            "recall": sum_precision/count
                        },ignore_index=True)
                    iters += 1
                    epoch_chk_path = chk_path + "epoch" + str(i) + ".ckpt"
                    saver.save(sess,epoch_chk_path)
                    stats_df.to_csv(csv_path, index=False)
        chk_path = chk_path + "epoch" + str(i) + ".ckpt"
        saver.save(sess, chk_path)
        #epoch information
    else:
        sess = tf.Session()
        
        tf_writer = tf.summary.FileWriter(logdir='./')
    
        test_dataset = tf.data.TFRecordDataset([test_filename])
        test_dataset = test_dataset.map(test_record_parser)

        iterator = test_dataset.make_one_shot_iterator()
        next_element = iterator.get_next()

        model_test_predict = UNet(128, is_training=True,k=1)
        #saver = tf.train.Saver()
        saver = tf.train.import_meta_graph(reload_path+"epoch3500.ckpt.meta")
        saver.restore(sess, tf.train.latest_checkpoint(reload_path))
        init = tf.global_variables_initializer()
        sess.run(init)
        while True:
            try:
                predict = model_test_predict.predict();
                val = sess.run(next_element)
                name,data,m,n = val
                data = data.reshape(100,m,n,1)
                print("predicting for {}".format(name))
                predict = sess.run([predict],feed_dict={model_test_predict.input:data})
                predict = np.array(predict).reshape(100,m,n)
                predict = np.sum(predict,axis=0)/100
                predict = np.round(predict)
                #for dat in data:
                #    dat = dat.reshape(1,128,128,1)
                #    
                #    predict = np.array(predict)
                #    predict = predict.reshape(m,n)
                #    res.append(predict)
                #res = np.array(res)
                #res = np.sum(res,axis=0)/100
                #res = np.round(res)
                print("save path: ", save_path)
                print("name : ", name)
                np.save("{}{}.npy".format(save_path,name),predict)
            except tf.errors.OutOfRangeError:
                break
