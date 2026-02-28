
import torch
import cv2

# Load the pre-trained gesture detection model
model = torch.load('gesture_detection_model.pth')

# Initialize the video capture
cap = cv2.VideoCapture(0)

while True:
    # Capture frame-by-frame
    ret, frame = cap.read()

    # Pre-process the frame
    frame = cv2.resize(frame, (224, 224))
    frame = frame / 255.0

    # Perform gesture detection
    output = model(torch.tensor([frame]))

    # Display the results
    print("Gesture detected:", torch.argmax(output).item())

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release handle
cap.release()
cv2.destroyAllWindows()
