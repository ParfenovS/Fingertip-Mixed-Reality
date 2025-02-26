import os
import cv2
import time
import numpy as np
import imgaug as ia
from utils.iou import iou
from imgaug import augmenters as iaa
from yolo.detector import YOLO
from fingertip import Fingertips

hand = YOLO('weights/yolo.h5', threshold=0.5)
fingertip = Fingertips(model='vgg', weights='weights/vgg16.h5')
resolution = 1


def flip_horizontal(img, keys):
    """ Flipping """
    aug = iaa.Sequential([iaa.Fliplr(1.0)])
    seq_det = aug.to_deterministic()
    keys = ia.KeypointsOnImage([ia.Keypoint(x=keys[0], y=keys[1]),
                                ia.Keypoint(x=keys[2], y=keys[3]),
                                ia.Keypoint(x=keys[4], y=keys[5]),
                                ia.Keypoint(x=keys[6], y=keys[7])], shape=img.shape)

    image_aug = seq_det.augment_images([img])[0]
    keys_aug = seq_det.augment_keypoints([keys])[0]
    k = keys_aug.keypoints
    keys_aug = [k[0].x, k[0].y, k[1].x, k[1].y, k[2].x, k[2].y, k[3].x, k[3].y]

    return image_aug, keys_aug


image_directory = '../Dataset/Test/'
label_directory = '../Dataset/label/'
image_files = os.listdir(image_directory)

""" Ground truth label file for TI1K dataset """
file = open(label_directory + 'TI1K.txt')
lines = file.readlines()
file.close()

""" Ground truth label file for SingleEight dataset """
file = open(label_directory + 'SingleEight.txt')
ego_lines = file.readlines()
file.close()

total_error = np.zeros([1, 4])
avg_hand_detect_time = 0
avg_fingertip_detect_time = 0
avg_time = 0
avg_iou = 0
count = 0
distance_error = []

height = int(480 * resolution)
width = int(640 * resolution)

for image_file in image_files:
    """ Generating ground truths labels """
    image = cv2.imread(image_directory + image_file)
    image = cv2.resize(image, (width, height))
    name = image_file[:-4]
    splits = name.split('_')
    gt = []

    if 'TI1K' in splits:
        """ TI1K Dataset """
        label = []
        for line in lines:
            line = line.strip().split()
            if image_file == line[0]:
                label = line[1:]
                break

        label = [float(i) for i in label]
        x1 = label[0] * width
        y1 = label[1] * height
        x2 = label[2] * width
        y2 = label[3] * height
        xt = label[4] * width
        yt = label[5] * height
        xi = label[6] * width
        yi = label[7] * height

        gt = [x1, y1, x2, y2, xt, yt, xi, yi]
        image_flip, gt_flip = flip_horizontal(image, np.asarray(gt))
        gt_box = [x1, y1, x2, y2]
        gt_box_flip = [gt_flip[2], gt_flip[1], gt_flip[0], gt_flip[3]]
        image_flip = image_flip.copy()

    else:
        """ SingleEight Dataset """
        label = []
        for line in ego_lines:
            line = line.strip().split()
            name = line[0].split('/')[3]
            if image_file == name:
                label = line[1:]
                break

        label = [float(i) for i in label]
        x1 = label[0] * width
        y1 = label[1] * height
        x2 = label[2] * width
        y2 = label[3] * height
        xt = label[4] * width
        yt = label[5] * height
        xi = label[8] * width
        yi = label[9] * height

        gt = [x1, y1, x2, y2, xt, yt, xi, yi]
        image_flip, gt_flip = flip_horizontal(image, np.asarray(gt))
        gt_box = [x1, y1, x2, y2]
        gt_box_flip = [gt_flip[2], gt_flip[1], gt_flip[0], gt_flip[3]]
        image_flip = image_flip.copy()

    tic1 = time.time()
    """ Predictions for the test images """
    image = cv2.imread(image_directory + image_file)
    image = cv2.resize(image, (width, height))
    tic2 = time.time()
    tl, br = hand.detect(image=image)
    toc2 = time.time()
    avg_hand_detect_time = avg_hand_detect_time + (toc2 - tic2)
    if tl and br is not None:
        pr_box = [tl[0], tl[1], br[0], br[1]]
        IOU = iou(boxA=pr_box, boxB=gt_box)
        if IOU < 0.5:
            continue
        avg_iou = avg_iou + IOU

        tl = (tl[0], tl[1])
        br = (br[0], br[1])

        xmin = int(tl[0])
        ymin = int(tl[1])
        xmax = int(br[0])
        ymax = int(br[1])

        ymin = ymin if ymin > 0 else 0
        xmin = xmin if xmin > 0 else 0

        cropped_image = image[ymin:ymax, xmin:xmax]
        cols, rows, _ = cropped_image.shape
        cropped_image = cv2.resize(cropped_image, (128, 128))
        tic3 = time.time()
        position = fingertip.classify(image=cropped_image)
        toc3 = time.time()
        avg_fingertip_detect_time = avg_fingertip_detect_time + (toc3 - tic3)

        for i in range(0, len(position), 2):
            position[i] = (position[i]) * rows
            position[i + 1] = (position[i + 1]) * cols

        for i in range(0, len(position), 2):
            position[i] = (position[i] + tl[0])
            position[i + 1] = (position[i + 1] + tl[1])

        pr = [tl[0], tl[1], br[0], br[1], position[0], position[1], position[2], position[3]]

        # Calculating error for fingertips only
        gt = np.asarray(gt[4:])
        pr = np.asarray(pr[4:])
        abs_err = abs(gt - pr)
        total_error = total_error + abs_err
        D = np.sqrt((gt[0] - gt[2]) ** 2 + (gt[1] - gt[3]) ** 2)
        D_hat = np.sqrt((pr[0] - pr[2]) ** 2 + (pr[1] - pr[3]) ** 2)
        distance_error.append(abs(D - D_hat))
        count = count + 1
        print('Detected Image: {0}  IOU: {1:.4f}'.format(count, IOU))

    """ Predictions for the flipped test images """
    tic2 = time.time()
    tl, br = hand.detect(image=image_flip)
    toc2 = time.time()
    avg_hand_detect_time = avg_hand_detect_time + (toc2 - tic2)
    if tl and br is not None:
        pr_box = [tl[0], tl[1], br[0], br[1]]
        IOU = iou(boxA=pr_box, boxB=gt_box_flip)
        if IOU < 0.5:
            continue
        avg_iou = avg_iou + IOU

        tl = (tl[0], tl[1])
        br = (br[0], br[1])

        """ Fingertip detection """
        xmin = int(tl[0])
        ymin = int(tl[1])
        xmax = int(br[0])
        ymax = int(br[1])

        ymin = ymin if ymin > 0 else 0
        xmin = xmin if xmin > 0 else 0

        cropped_image = image_flip[ymin:ymax, xmin:xmax]
        cols, rows, _ = cropped_image.shape
        cropped_image = cv2.resize(cropped_image, (128, 128))
        tic3 = time.time()
        position = fingertip.classify(image=cropped_image)
        toc3 = time.time()
        avg_fingertip_detect_time = avg_fingertip_detect_time + (toc3 - tic3)

        for i in range(0, len(position), 2):
            position[i] = (position[i]) * rows
            position[i + 1] = (position[i + 1]) * cols

        for i in range(0, len(position), 2):
            position[i] = (position[i] + tl[0])
            position[i + 1] = (position[i + 1] + tl[1])

        pr = [tl[0], tl[1], br[0], br[1], position[0], position[1], position[2], position[3]]

        # Calculating error for fingertips only
        gt_flip = np.asarray(gt_flip[4:])
        pr = np.asarray(pr[4:])
        abs_err = abs(gt_flip - pr)
        total_error = total_error + abs_err
        D = np.sqrt((gt_flip[0] - gt_flip[2]) ** 2 + (gt_flip[1] - gt_flip[3]) ** 2)
        D_hat = np.sqrt((pr[0] - pr[2]) ** 2 + (pr[1] - pr[3]) ** 2)
        distance_error.append(abs(D - D_hat))
        count = count + 1
        print('Detected Image: {0}  IOU: {1:.4f}'.format(count, IOU))

    toc1 = time.time()
    avg_time = avg_time + (toc1 - tic1)

er = total_error / count
avg_iou = avg_iou / count
er = er[0]
er = np.round(er, 4)
distance_error = np.array(distance_error)
distance_error = np.mean(distance_error)
distance_error = np.round(distance_error, 4)

print('Total Detected Image: {0}'.format(count))
print('Average IOU: {0}'.format(avg_iou))
print('Pixel errors: xt = {0}, yt = {1}, xi = {2}, yi = {3}, D-D_hat = {4}'.format(er[0], er[1],
                                                                                   er[2], er[3],
                                                                                   distance_error))

avg_time = avg_time / 1000
avg_hand_detect_time = avg_hand_detect_time / count
avg_fingertip_detect_time = avg_fingertip_detect_time / count

print('Average execution time: {0:1.5f} ms'.format(avg_time * 1000))
print('Average hand detection time: {0:1.5f} ms'.format(avg_hand_detect_time * 1000))
print('Average fingertip detection time: {0:1.5f} ms'.format(avg_fingertip_detect_time * 1000))

print('{0} & {1} & {2} & {3} & {4}'.format(er[0], er[1], er[2], er[3], distance_error))
