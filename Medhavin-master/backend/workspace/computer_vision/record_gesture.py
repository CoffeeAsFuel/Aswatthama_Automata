
import cv2
import torch

# Initialize the video capture
cap = cv2.VideoCapture(0)

while True:
    # Capture frame-by-frame
    ret, frame = cap.read()

    # Display the resulting frame
    cv2.imshow('Gesture Recording', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release handle
cap.release()
cv2.destroyAllWindows()
