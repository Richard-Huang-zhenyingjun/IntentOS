import cv2

cap = cv2.VideoCapture(0)
print(f"Camera opened: {cap.isOpened()}")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Can't read frame")
        break
    
    cv2.imshow('Test', frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()





