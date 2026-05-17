import cv2

cap = cv2.VideoCapture(0)
i = 0

while True:
    ret, frame = cap.read()
    cv2.imshow("foto", frame)

    key = cv2.waitKey(1)

    if key == ord('s'):
        cv2.imwrite(f"calib_{i}.jpg", frame)
        print("salvo", i)
        i += 1

    if key == 27:
        break

cap.release()
cv2.destroyAllWindows()