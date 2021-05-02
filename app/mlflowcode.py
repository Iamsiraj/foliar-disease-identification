# -*- coding: utf-8 -*-
"""Untitled8.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1bu67yJKlc3i16Naz6EL2c9hgXBLfBqsj
"""

#!pip install efficientnet

import os
import gc
import re

import cv2
import math
import numpy as np
import scipy as sp
import pandas as pd
import mlflow
import tensorflow as tf
import mlflow.tensorflow
#import mlflow.tensorflow

import efficientnet.tfkeras as efn
from keras.utils import plot_model
import tensorflow.keras.layers as L
from keras.utils import model_to_dot
import tensorflow.keras.backend as K
from tensorflow.keras.models import Model
#from kaggle_datasets import KaggleDatasets
from tensorflow.keras.applications import DenseNet121
#from mlflow import pyfunc
#import seaborn as sns
#from tqdm import tqdm
import matplotlib.cm as cm
from sklearn import metrics
#import matplotlib.pyplot as plt
from sklearn.utils import shuffle
from sklearn.model_selection import train_test_split




#tqdm.pandas()
#import plotly.express as px
#import plotly.graph_objects as go
#import plotly.figure_factory as ff
#from plotly.subplots import make_subplots

np.random.seed(0)
tf.random.set_seed(0)
print(tf.__version__)

#import warnings
#warnings.filterwarnings("ignore")

#from google.colab import drive
#drive.mount('/content/drive')

EPOCHS = 2
SAMPLE_LEN = 100
IMAGE_PATH = "C:/Users/siraj/Downloads/plant-pathology-2020/images/"

TEST_PATH = "../data/test.csv"

TRAIN_PATH = "../data/train.csv"

#IMAGE_PATH = "/content/drive/MyDrive/DSPD Project/Data/images/"

#TEST_PATH = "/content/drive/MyDrive/DSPD Project/Data/test.csv"
#TRAIN_PATH = "/content/drive/MyDrive/DSPD Project/Data/train.csv"
#SUB_PATH = "/content/drive/MyDrive/DSPD Project/Data/sample_submission.csv"

#sub = pd.read_csv(SUB_PATH)
test_data = pd.read_csv(TEST_PATH)
train_data = pd.read_csv(TRAIN_PATH)

def format_path(st):
    return IMAGE_PATH  + st + '.jpg'

test_paths = test_data.image_id.apply(format_path).values
train_paths = train_data.image_id.apply(format_path).values
train_labels = np.float32(train_data.loc[:, 'healthy':'scab'].values)
train_paths, valid_paths, train_labels, valid_labels =train_test_split(train_paths, train_labels, test_size=0.15, random_state=2020)

def decode_image(filename, label=None, image_size=(512, 512)):
    bits = tf.io.read_file(filename)
    image = tf.image.decode_jpeg(bits, channels=3)
    image = tf.cast(image, tf.float32) / 255.0
    image = tf.image.resize(image, image_size)
    
    if label is None:
        return image
    else:
        return image, label

def data_augment(image, label=None):
    image = tf.image.random_flip_left_right(image)
    image = tf.image.random_flip_up_down(image)
    
    if label is None:
        return image
    else:
        return image, label

AUTO = tf.data.experimental.AUTOTUNE
strategy = tf.distribute.get_strategy()
BATCH_SIZE = 16 * strategy.num_replicas_in_sync
train_dataset = (
    tf.data.Dataset
    .from_tensor_slices((train_paths, train_labels))
    .map(decode_image, num_parallel_calls=AUTO)
    .map(data_augment, num_parallel_calls=AUTO)
    .repeat()
    .shuffle(512)
    .batch(BATCH_SIZE)
    .prefetch(AUTO)
)

valid_dataset = (
    tf.data.Dataset
    .from_tensor_slices((valid_paths, valid_labels))
    .map(decode_image, num_parallel_calls=AUTO)
    .batch(BATCH_SIZE)
    .cache()
    .prefetch(AUTO)
)

test_dataset = (
    tf.data.Dataset
    .from_tensor_slices(test_paths)
    .map(decode_image, num_parallel_calls=AUTO)
    .batch(BATCH_SIZE)
)

#helper function

def build_lrfn(lr_start=0.00001, lr_max=0.00002,
               lr_min=0.00001, lr_rampup_epochs=1,
               lr_sustain_epochs=0, lr_exp_decay=.8):
    lr_max = lr_max * strategy.num_replicas_in_sync

    def lrfn(epoch):
        if epoch < lr_rampup_epochs:
            lr = (lr_max - lr_start) / lr_rampup_epochs * epoch + lr_start
        elif epoch < lr_rampup_epochs + lr_sustain_epochs:
            lr = lr_max
        else:
            lr = (lr_max - lr_min) *\
                 lr_exp_decay**(epoch - lr_rampup_epochs\
                                - lr_sustain_epochs) + lr_min
        return lr
    return lrfn

lrfn = build_lrfn()
STEPS_PER_EPOCH = train_labels.shape[0] // BATCH_SIZE
lr_schedule = tf.keras.callbacks.LearningRateScheduler(lrfn, verbose=1)

mlflow.start_run()
with strategy.scope():
    model = tf.keras.Sequential([DenseNet121(input_shape=(512, 512, 3),
                                             weights='imagenet',
                                             include_top=False),
                                 L.GlobalAveragePooling2D(),
                                 L.Dense(train_labels.shape[1],
                                         activation='softmax')])
        
    model.compile(optimizer='adam',
                  loss = 'categorical_crossentropy',
                  metrics=['categorical_accuracy'])
    model.summary()
    print("test")

history = model.fit(train_dataset,
                    epochs=EPOCHS,
                    callbacks=[lr_schedule],
                    steps_per_epoch=STEPS_PER_EPOCH,
                    validation_data=valid_dataset)

print(history)
mlflow.end_run()
def process(img):
    return cv2.resize(img/255.0, (512, 512)).reshape(-1, 512, 512, 3)
def predict(img):
    return model.layers[2](model.layers[1](model.layers[0](process(img)))).numpy()[0]

#loading images
def load_image(image_id):
    file_path = image_id + ".jpg"
    image = cv2.imread(IMAGE_PATH + file_path)
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

train_images = train_data["image_id"][:SAMPLE_LEN].progress_apply(load_image)

preds = predict(train_images[2])

preds