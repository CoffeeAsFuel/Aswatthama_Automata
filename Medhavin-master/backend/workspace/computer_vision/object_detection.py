
import cv2
from tensorflow import keras

# Load the model
model = keras.models.load_model('mobile_net_model.h5')

# Load the image
image_path = 'path_to_your_image.jpg'
image = cv2.imread(image_path)

# Perform object detection
results = model.detect([image])

# Print the results
for result in results:
    for detection in result:
        print(f"Object detected: {detection['class_id']}, Confidence: {detection['score']}")

print("Object detection complete!")
